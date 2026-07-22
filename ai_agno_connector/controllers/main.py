# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hmac
import logging
import time

from odoo import fields, http, tools
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.mail import html_to_inner_content

from ..models.ai_bridge_execution import HMAC_SCOPE

_logger = logging.getLogger(__name__)

# Maximum accepted age (seconds) for a signed user identity.
HMAC_MAX_AGE = 600

ALLOWED_METHODS = {"search_read", "search_count", "fields_get"}

# Technical / credential models that must never be exposed to agents,
# regardless of the requesting user's own access rights.
BLOCKED_MODELS = {
    "res.users",
    "res.users.apikeys",
    "res.users.identitycheck",
    "res.users.log",
    "ir.config_parameter",
    "ir.default",
    "ir.mail_server",
    "fetchmail.server",
    "ir.cron",
    "ir.rule",
    "ir.model.access",
}

# Field name fragments that are stripped from requests and responses.
BLOCKED_FIELD_PATTERNS = ("password", "token", "secret", "api_key")

# Default cap on records per search_read, overridable with the
# ``ai_agno_connector.max_records`` config parameter.
DEFAULT_MAX_RECORDS = 80

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


class AgnoRpcController(http.Controller):
    @http.route("/agno/rpc", type="http", auth="none", methods=["POST"], csrf=False)
    def agno_rpc(self, db=None):
        # ``db`` is consumed by the post_load patch for database resolution;
        # declared here so the dispatcher does not warn about ignored args.
        error = self._check_service_token()
        if error:
            return error

        params = request.get_json_data() or {}
        user = self._get_request_user(params)
        if user is None:
            return request.make_json_response(
                {
                    "error": "invalid_user",
                    "detail": "Unknown user_id or invalid identity signature.",
                },
                status=403,
            )

        model = params.get("model") or ""
        method = params.get("method") or ""
        if method not in ALLOWED_METHODS:
            return request.make_json_response(
                {"error": "method_not_allowed", "detail": f"Method {method!r}."},
                status=400,
            )
        if model in BLOCKED_MODELS:
            return request.make_json_response(
                {
                    "error": "model_not_allowed",
                    "detail": f"Model {model!r} is not available to agents.",
                },
                status=403,
            )

        env = request.env(user=user.id, su=False)
        if model not in env:
            return request.make_json_response(
                {"error": "unknown_model", "detail": f"Model {model!r} not found."},
                status=404,
            )

        try:
            result = self._dispatch(env[model], method, params)
        except AccessError as exc:
            return request.make_json_response(
                {"error": "access_denied", "detail": str(exc)}
            )
        except Exception as exc:  # noqa: BLE001 - log detail, return generic message
            _logger.warning("Agno RPC error on %s.%s: %s", model, method, exc)
            return request.make_json_response(
                {
                    "error": "server_error",
                    "detail": "Internal error, see server logs.",
                }
            )
        return request.make_json_response({"result": result})

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
        if not hmac.compare_digest(auth_header, f"Bearer {expected}"):
            return request.make_json_response(
                {"error": "unauthorized", "detail": "Invalid service token."},
                status=401,
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
            if abs(time.time() - timestamp) > HMAC_MAX_AGE:
                return False
            expected = tools.hmac(
                request.env(su=True), HMAC_SCOPE, (user_id, timestamp)
            )
            return hmac.compare_digest(signature, expected)
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

    def _dispatch(self, records, method, params):
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
                    row[name] = self._format_x2many(records.env, field, value)
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

    def _format_x2many(self, env, field, ids):
        """Replace id lists with ``[id, display_name]`` pairs (capped)."""
        if len(ids) > X2MANY_NAMES_LIMIT:
            return {"count": len(ids)}
        try:
            names = env[field.comodel_name].browse(ids).mapped("display_name")
        except AccessError:
            return {"count": len(ids)}
        return [
            [record_id, _truncate(name, 120)]
            for record_id, name in zip(ids, names, strict=True)
        ]
