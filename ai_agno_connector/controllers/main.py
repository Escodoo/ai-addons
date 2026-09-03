# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hmac
import logging
import time

from odoo import fields, http, tools
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.osv import expression
from odoo.tools.mail import html_to_inner_content

from ..models.ai_bridge_execution import HMAC_SCOPE
from ..tool_registry import AGNO_TOOLS, allowed_methods_for, get_tools_catalog

_logger = logging.getLogger(__name__)

# Maximum accepted age (seconds) for a signed user identity.
HMAC_MAX_AGE = 600

ALLOWED_METHODS = {"search_read", "search_count", "fields_get", "read_group"}

# High-level write helpers allowed only on dedicated assistant models.
# Never expose generic create/write/unlink through the gateway.
# Keep in sync with ai_agno_assistant helpers + Agno AssistantTools
# (see readme/USAGE.md — "Typed model allowlist").
ALLOWED_MODEL_METHODS = {
    "ai.assistant": frozenset(
        {
            "prepare_purchase_order",
            "prepare_opportunity",
            "prepare_helpdesk_ticket",
            "prepare_sale_order",
            "prepare_timesheet",
            "find_navigation",
            "get_attention_digest",
            "get_record_context",
            "prepare_partner",
            "prepare_activity",
            "add_order_line",
            "propose_confirm_sale_order",
            "propose_confirm_purchase_order",
        }
    ),
}

# Technical / credential models that must never be exposed to agents,
# regardless of the requesting user's own access rights.
BLOCKED_MODELS = {
    "res.users",
    "res.users.apikeys",
    "res.users.identitycheck",
    "res.users.log",
    "res.users.settings",
    "auth_totp.device",
    "payment.token",
    "ir.config_parameter",
    "ir.default",
    "ir.mail_server",
    "fetchmail.server",
    "ir.cron",
    "ir.rule",
    "ir.model.access",
}

# Prefixes blocked for generic ORM reads (typed helpers stay allowlisted).
BLOCKED_MODEL_PREFIXES = ("ir.",)

# Field name fragments that are stripped from requests and responses.
BLOCKED_FIELD_PATTERNS = ("password", "token", "secret", "api_key")

# Default cap on records per search_read, overridable with the
# ``ai_agno_connector.max_records`` config parameter.
DEFAULT_MAX_RECORDS = 80

# Cap on group buckets returned by read_group.
DEFAULT_MAX_GROUPS = 50

# Caps applied when formatting values for the LLM context.
TEXT_TRUNCATE_LIMIT = 500
X2MANY_NAMES_LIMIT = 50


def _is_blocked_field(field_name):
    lowered = field_name.lower()
    return any(pattern in lowered for pattern in BLOCKED_FIELD_PATTERNS)


def _truncate(value, size=TEXT_TRUNCATE_LIMIT):
    if not isinstance(value, str) or len(value) <= size:
        return value
    return value[: size - 3] + "..."


def spec_tool_kwargs(gateway_model, spec_args, params):
    """Build typed-tool kwargs without colliding with the gateway ``model``.

    ``/agno/rpc`` uses ``model`` for the allowlisted target. Helpers that
    also take a record model must send it as ``res_model``.
    """
    kwargs = {}
    for name in spec_args:
        value = params.get(name)
        if name == "model" and value in (None, "", False, gateway_model):
            value = params.get("res_model")
        kwargs[name] = value
    return kwargs


def _secure_compare(left, right):
    """Constant-time compare that never raises on length mismatch."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


class AgnoRpcController(http.Controller):
    # auth=none defaults to readonly=True in Odoo 18; assistant prepare_* helpers
    # need a read/write cursor (still gated by allowlists + HMAC identity).
    @http.route(
        "/agno/rpc",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        readonly=False,
    )
    def agno_rpc(self, db=None):
        # ``db`` is consumed by the post_load patch for database resolution;
        # declared here so the dispatcher does not warn about ignored args.
        error = self._check_service_token()
        if error:
            return error

        params = request.get_json_data() or {}
        user = self._get_request_user(params)
        if user is None:
            return self._json_error(
                "invalid_user",
                "Unknown user_id or invalid identity signature.",
                status=403,
            )

        model = params.get("model") or ""
        method = params.get("method") or ""
        allowed_for_model = ALLOWED_MODEL_METHODS.get(
            model, frozenset()
        ) | allowed_methods_for(model)
        if method not in ALLOWED_METHODS and method not in allowed_for_model:
            return self._json_error(
                "method_not_allowed", f"Method {method!r}.", status=400
            )
        if self._is_blocked_model(model, request.env):
            return self._json_error(
                "model_not_allowed",
                f"Model {model!r} is not available to agents.",
                status=403,
            )

        env = request.env(user=user.id, su=False)
        if model not in env:
            return self._json_error(
                "unknown_model", f"Model {model!r} not found.", status=404
            )

        if method in {"search_read", "search_count", "read_group"}:
            domain_error = self._domain_error(env[model], params.get("domain") or [])
            if domain_error:
                return domain_error

        try:
            result = self._dispatch(env[model], method, params)
        except AccessError as exc:
            return self._json_error("access_denied", str(exc), status=403)
        except ValueError as exc:
            return self._json_error("invalid_params", str(exc), status=400)
        except Exception as exc:  # noqa: BLE001 - log detail, return generic message
            _logger.warning("Agno RPC error on %s.%s: %s", model, method, exc)
            return self._json_error(
                "server_error", "Internal error, see server logs.", status=200
            )
        return request.make_json_response({"result": result})

    @http.route(
        "/agno/tools",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
        readonly=True,
    )
    def agno_tools(self, db=None):
        """Expose the typed helper catalog for the Agno service."""
        error = self._check_service_token()
        if error:
            return error
        return request.make_json_response({"tools": get_tools_catalog()})

    def _check_service_token(self):
        from ..token_utils import (
            CONFIG_SERVICE_TOKEN,
            ICP_SERVICE_TOKEN,
            ensure_token,
        )

        expected = ensure_token(request.env, ICP_SERVICE_TOKEN, CONFIG_SERVICE_TOKEN)
        if not expected:
            return request.make_json_response(
                {
                    "error": "not_configured",
                    "detail": (
                        "ai_agno_connector.service_token is not set "
                        "(ICP or odoo.conf agno_service_token)."
                    ),
                },
                status=503,
            )
        auth_header = request.httprequest.headers.get("Authorization", "")
        if not _secure_compare(auth_header, f"Bearer {expected}"):
            return self._json_error(
                "unauthorized", "Invalid service token.", status=401
            )
        return None

    def _get_request_user(self, params):
        user_id = params.get("user_id")
        if not isinstance(user_id, int):
            return None
        if not self._check_user_signature(user_id, params):
            return None
        user = request.env["res.users"].sudo().browse(user_id).exists()
        if not user:
            return None
        if not user.active and not user._is_public():
            return None
        return user

    def _check_user_signature(self, user_id, params):
        """Verify the user identity was signed by Odoo itself.

        The signature is produced by ai.bridge.execution when building
        the bridge payload, so agents can only act for users that Odoo
        vouched for. Unsigned requests require a double gate (dev only):
        ``ai_agno_connector.allow_unsigned_rpc`` must be ``True`` and
        ``ai_agno_connector.unsigned_user_id`` must match ``user_id``.
        Leave both empty in production.
        """
        signature = params.get("user_hmac")
        timestamp = params.get("user_hmac_ts")
        if signature and isinstance(timestamp, int):
            if abs(time.time() - timestamp) > self._get_hmac_max_age():
                return False
            expected = tools.hmac(
                request.env(su=True), HMAC_SCOPE, (user_id, timestamp)
            )
            return _secure_compare(signature, expected)
        return self._allow_unsigned_user(user_id)

    def _allow_unsigned_user(self, user_id):
        """Accept unsigned RPC only when both dev params are set."""
        icp = request.env["ir.config_parameter"].sudo()
        if icp.get_param("ai_agno_connector.allow_unsigned_rpc") != "True":
            return False
        unsigned_user_id = icp.get_param("ai_agno_connector.unsigned_user_id", "")
        if not (unsigned_user_id.isdigit() and int(unsigned_user_id) == user_id):
            return False
        _logger.warning(
            "Accepting unsigned /agno/rpc for user_id=%s "
            "(ai_agno_connector.allow_unsigned_rpc is enabled; "
            "disable in production).",
            user_id,
        )
        return True

    def _json_error(self, error, detail, status=400):
        try:
            params = request.get_json_data() or {}
        except Exception:  # noqa: BLE001 - logging must not break the response
            params = {}
        _logger.info(
            "Agno RPC %s (%s) on %s.%s: %s",
            error,
            status,
            params.get("model") or "?",
            params.get("method") or "?",
            detail,
        )
        return request.make_json_response(
            {"error": error, "detail": detail},
            status=status,
        )

    def _get_blocked_models(self, env):
        models = set(BLOCKED_MODELS)
        extra = (
            env["ir.config_parameter"]
            .sudo()
            .get_param("ai_agno_connector.extra_blocked_models", "")
        )
        for name in extra.replace(",", " ").split():
            if name:
                models.add(name.strip())
        return models

    def _is_blocked_model(self, model, env):
        if not model:
            return False
        if model in self._get_blocked_models(env):
            return True
        return any(model.startswith(prefix) for prefix in BLOCKED_MODEL_PREFIXES)

    def _get_hmac_max_age(self):
        param = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_agno_connector.hmac_max_age", "")
        )
        if param.isdigit() and int(param) > 0:
            return int(param)
        return HMAC_MAX_AGE

    def _domain_error(self, records, domain):
        """Reject domains that probe blocked fields or traverse blocked models."""
        try:
            leaves = list(self._iter_domain_leaves(domain))
            expression.normalize_domain(domain)
        except (ValueError, AssertionError) as exc:
            return self._json_error("invalid_domain", str(exc), status=400)
        for field_path in leaves:
            reason = self._domain_leaf_blocked(records, field_path)
            if reason == "blocked_domain_field":
                return self._json_error(
                    "blocked_domain_field",
                    f"Field {field_path!r} is not available to agents.",
                    status=403,
                )
            if reason == "blocked_domain_model":
                return self._json_error(
                    "blocked_domain_model",
                    f"Domain path {field_path!r} traverses a blocked model.",
                    status=403,
                )
            if reason == "invalid_domain":
                return self._json_error(
                    "invalid_domain",
                    f"Invalid domain field {field_path!r}.",
                    status=400,
                )
        return None

    def _iter_domain_leaves(self, domain):
        if not isinstance(domain, list):
            raise ValueError("Domain must be a list.")
        for item in domain:
            if item in ("&", "|", "!"):
                continue
            # Odoo only treats 3-tuples as leaves. Nested lists are not
            # subdomains except as the value of an any/not any operator.
            if not (isinstance(item, list | tuple) and len(item) == 3):
                raise ValueError("Invalid domain leaf.")
            yield item[0]
            if item[1] in ("any", "not any") and isinstance(item[2], list):
                yield from self._iter_domain_leaves(item[2])

    def _domain_leaf_blocked(self, records, field_path):
        if not isinstance(field_path, str) or not field_path:
            return "invalid_domain"
        parts = field_path.split(".")
        current = records
        for index, part in enumerate(parts):
            if _is_blocked_field(part):
                return "blocked_domain_field"
            field = current._fields.get(part)
            if field is None:
                if index < len(parts) - 1:
                    return "invalid_domain"
                return None
            if index == len(parts) - 1:
                return None
            if field.type not in ("many2one", "one2many", "many2many"):
                return "invalid_domain"
            comodel_name = field.comodel_name
            if self._is_blocked_model(comodel_name, current.env):
                return "blocked_domain_model"
            if comodel_name not in current.env:
                return "invalid_domain"
            current = current.env[comodel_name]
        return None

    def _dispatch(self, records, method, params):
        spec = AGNO_TOOLS.get(records._name, {}).get(method)
        if spec:
            kwargs = spec_tool_kwargs(records._name, spec["args"], params)
            return getattr(records, method)(**kwargs)
        domain = params.get("domain") or []
        if method == "search_count":
            return records.search_count(domain)
        if method == "fields_get":
            fields_data = records.fields_get(attributes=["string", "type"])
            return {
                name: info
                for name, info in fields_data.items()
                if not _is_blocked_field(name) and info.get("type") != "binary"
            }
        if method == "prepare_purchase_order":
            return records.prepare_purchase_order(
                vendor_ref=params.get("vendor_ref"),
                lines=params.get("lines") or [],
                notes=params.get("notes"),
            )
        if method == "prepare_opportunity":
            return records.prepare_opportunity(
                name=params.get("name"),
                partner_ref=params.get("partner_ref"),
                description=params.get("description"),
                expected_revenue=params.get("expected_revenue"),
            )
        if method == "prepare_helpdesk_ticket":
            return records.prepare_helpdesk_ticket(
                name=params.get("name"),
                description=params.get("description"),
                partner_ref=params.get("partner_ref"),
                team_ref=params.get("team_ref"),
            )
        if method == "prepare_sale_order":
            return records.prepare_sale_order(
                partner_ref=params.get("partner_ref"),
                lines=params.get("lines") or [],
                notes=params.get("notes"),
            )
        if method == "prepare_timesheet":
            return records.prepare_timesheet(
                project_ref=params.get("project_ref"),
                task_ref=params.get("task_ref"),
                unit_amount=params.get("unit_amount"),
                name=params.get("name"),
                date=params.get("date"),
            )
        if method == "find_navigation":
            return records.find_navigation(
                query=params.get("query"),
                limit=params.get("limit") or 8,
            )
        if method == "read_group":
            return self._dispatch_read_group(records, params)
        # search_read
        field_defs = records._fields
        field_names = [
            name
            for name in (params.get("fields") or ["display_name"])
            if not _is_blocked_field(name)
            # Never return base64 payloads to the LLM context.
            and (name not in field_defs or field_defs[name].type != "binary")
        ] or ["display_name"]
        limit = min(int(params.get("limit") or 10), self._get_max_records())
        rows = records.search_read(domain, field_names, limit=limit)
        return self._format_rows_for_llm(records, rows, field_names)

    def _dispatch_read_group(self, records, params):
        """Aggregate records for the LLM (group_by + measures, ACL-aware)."""
        field_defs = records._fields
        raw_groupby = params.get("groupby") or params.get("group_by") or []
        if isinstance(raw_groupby, str):
            raw_groupby = [raw_groupby]
        if not isinstance(raw_groupby, list) or not raw_groupby:
            raise ValueError("read_group requires a groupby list.")
        groupby = []
        for name in raw_groupby[:8]:
            if not isinstance(name, str) or not name:
                continue
            field_name = name.split(":")[0]
            if _is_blocked_field(field_name) or field_name not in field_defs:
                continue
            groupby.append(name)
        if not groupby:
            raise ValueError("No valid groupby fields.")
        raw_fields = params.get("fields") or []
        if isinstance(raw_fields, str):
            raw_fields = [raw_fields]
        measures = []
        for name in raw_fields[:12]:
            if not isinstance(name, str) or not name:
                continue
            field_name = name.split(":")[0]
            if _is_blocked_field(field_name):
                continue
            if field_name not in field_defs and field_name != "id":
                continue
            measures.append(name)
        try:
            limit = min(int(params.get("limit") or 20), DEFAULT_MAX_GROUPS)
        except (TypeError, ValueError):
            limit = 20
        rows = records.read_group(
            params.get("domain") or [],
            measures,
            groupby,
            limit=limit,
            lazy=False,
        )
        return self._format_read_group_for_llm(records, rows)

    def _format_read_group_for_llm(self, records, rows):
        """Keep read_group rows JSON-safe and short for the LLM."""
        cleaned = []
        for row in rows[:DEFAULT_MAX_GROUPS]:
            if not isinstance(row, dict):
                continue
            item = {}
            for key, value in row.items():
                if key.startswith("__") and key not in {"__count", "__domain"}:
                    continue
                if key == "__domain":
                    continue
                if _is_blocked_field(str(key).split(":")[0]):
                    continue
                if isinstance(value, bytes):
                    continue
                item[key] = value
            cleaned.append(item)
        return cleaned

    def _get_max_records(self):
        param = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_agno_connector.max_records", "")
        )
        if param.isdigit() and int(param) > 0:
            return int(param)
        return DEFAULT_MAX_RECORDS

    def _format_rows_for_llm(self, records, rows, field_names):
        """Reformat raw search_read values for LLM consumption.

        Inspired by Odoo Enterprise ``_ai_read``: datetimes in the user
        timezone, monetary values with their currency, x2many as display
        names, HTML as plain text and long strings truncated (which also
        limits prompt injection through record data).
        """
        field_defs = records._fields
        special = {
            name: field_defs[name]
            for name in field_names
            if name in field_defs
            and field_defs[name].type
            in ("datetime", "html", "monetary", "one2many", "many2many", "char", "text")
        }
        if not rows or not special:
            return rows

        records_by_id = {}
        if any(field.type == "monetary" for field in special.values()):
            browsed = records.browse([row["id"] for row in rows])
            records_by_id = {record.id: record for record in browsed}

        x2many_name_maps = {}
        for name, field in special.items():
            if field.type not in ("one2many", "many2many"):
                continue
            collected = []
            for row in rows:
                value = row.get(name)
                if value and len(value) <= X2MANY_NAMES_LIMIT:
                    collected.extend(value)
            x2many_name_maps[name] = self._x2many_name_map(
                records.env, field, collected
            )

        for row in rows:
            for name, field in special.items():
                value = row.get(name)
                if not value:
                    continue
                if field.type == "datetime":
                    row[name] = fields.Datetime.context_timestamp(
                        records, value
                    ).strftime("%Y-%m-%d %H:%M:%S")
                elif field.type == "html":
                    row[name] = _truncate(html_to_inner_content(value))
                elif field.type == "monetary":
                    row[name] = self._format_monetary(
                        records_by_id.get(row["id"]), field, value
                    )
                elif field.type in ("one2many", "many2many"):
                    row[name] = self._format_x2many_from_map(
                        value, x2many_name_maps.get(name)
                    )
                else:  # char / text
                    row[name] = _truncate(value)
        return rows

    def _format_monetary(self, record, field, value):
        currency_field = field.get_currency_field(record) if record else None
        currency = (
            record[currency_field]
            if record is not None and currency_field in record._fields
            else None
        )
        if not currency:
            return value
        return tools.formatLang(record.env, value, currency_obj=currency)

    def _x2many_name_map(self, env, field, ids):
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return {}
        try:
            names = env[field.comodel_name].browse(unique_ids).mapped("display_name")
        except AccessError:
            return None
        return {
            record_id: _truncate(name, 120)
            for record_id, name in zip(unique_ids, names, strict=True)
        }

    def _format_x2many_from_map(self, ids, name_map):
        if len(ids) > X2MANY_NAMES_LIMIT or name_map is None:
            return {"count": len(ids)}
        return [[record_id, name_map.get(record_id, "")] for record_id in ids]

    def _format_x2many(self, env, field, ids):
        """Replace id lists with ``[id, display_name]`` pairs (capped)."""
        if len(ids) > X2MANY_NAMES_LIMIT:
            return {"count": len(ids)}
        return self._format_x2many_from_map(ids, self._x2many_name_map(env, field, ids))
