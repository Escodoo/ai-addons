# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.osv import expression

from odoo.addons.ai_agno_connector.tool_registry import agno_tool

_logger = logging.getLogger(__name__)

# Models the assistant may open via open_record (navigation / draft review).
_OPEN_RECORD_MODELS = frozenset(
    {
        "purchase.order",
        "purchase.order.line",
        "res.partner",
        "product.product",
        "product.template",
        "sale.order",
        "crm.lead",
        "account.move",
        "account.analytic.line",
        "stock.picking",
        "project.project",
        "project.task",
        "helpdesk.ticket",
    }
)

_AI_CHAT_DOMAIN_LEAF_LIMIT = 20
_AI_CHAT_CONTEXT_MAX_DEPTH = 3
_AI_CHAT_CONTEXT_STR_MAX_LEN = 500
_AI_CHAT_CONTEXT_LIST_MAX_LEN = 50
_AI_CHAT_CONTEXT_DICT_MAX_LEN = 40
_CONTEXT_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BLOCKED_CONTEXT_KEYS = frozenset(
    {
        "uid",
        "login",
        "password",
        "pwd",
        "token",
        "api_key",
        "auth_token",
        "session_id",
    }
)
_BLOCKED_CONTEXT_FRAGMENTS = ("password", "token", "secret", "api_key")


class AiAssistantNavigation(models.AbstractModel):
    # Split from ai_assistant for maintainability (navigation vs drafts).
    _inherit = "ai.assistant"  # pylint: disable=consider-merging-classes-inherited

    @api.model
    def _action_record_to_dict(self, action):
        """Build a client-executable action dict from an ir.actions.* record."""
        if not action:
            return False
        ext_ids = action.get_external_id()
        xmlid = ext_ids.get(action.id)
        if xmlid:
            try:
                return self.env["ir.actions.actions"]._for_xml_id(xmlid)
            except ValueError:
                _logger.debug(
                    "Could not resolve action xmlid %s; falling back to read()",
                    xmlid,
                    exc_info=True,
                )
        action_dict = action.read()[0]
        action_dict["type"] = action._name
        return action_dict

    @api.model
    def _resolve_menu_to_action(self, menu, visible_ids=None, _seen=None):
        """Resolve a menu to an executable action, walking children if needed.

        Root apps (Invoicing, CRM, …) often have no action of their own; the
        first visible child with an action is used instead.
        """
        if not menu or menu._name != "ir.ui.menu":
            return False
        _seen = _seen if _seen is not None else set()
        if menu.id in _seen:
            return False
        _seen.add(menu.id)
        if visible_ids is not None and menu.id not in visible_ids:
            return False
        if menu.action:
            return self._action_record_to_dict(menu.action)
        for child in menu.child_id.sorted("sequence"):
            resolved = self._resolve_menu_to_action(child, visible_ids, _seen)
            if resolved:
                return resolved
        return False

    @api.model
    def _sanitize_action_domain(self, domain):
        """Return a validated domain list, or False when unsafe/invalid."""
        if not isinstance(domain, list):
            return False
        leaf_count = 0
        cleaned = []
        for token in domain:
            if expression.is_operator(token):
                cleaned.append(token)
                continue
            if not expression.is_leaf(token):
                return False
            leaf_count += 1
            if leaf_count > _AI_CHAT_DOMAIN_LEAF_LIMIT:
                return False
            left, operator, right = token[0], token[1], token[2]
            if not self._is_json_safe_value(right, depth=0):
                return False
            cleaned.append([left, operator, right])
        try:
            expression.normalize_domain(cleaned)
        except Exception:  # noqa: BLE001 - reject malformed domain shapes
            return False
        return cleaned

    @api.model
    def _is_json_safe_value(self, value, depth=0):
        if depth > _AI_CHAT_CONTEXT_MAX_DEPTH:
            return False
        if value is None or isinstance(value, bool | int | float):
            return True
        if isinstance(value, str):
            return len(value) <= _AI_CHAT_CONTEXT_STR_MAX_LEN
        if isinstance(value, list):
            if len(value) > _AI_CHAT_CONTEXT_LIST_MAX_LEN:
                return False
            return all(self._is_json_safe_value(item, depth + 1) for item in value)
        if isinstance(value, dict):
            if len(value) > _AI_CHAT_CONTEXT_DICT_MAX_LEN:
                return False
            for key, item in value.items():
                if not isinstance(key, str) or not _CONTEXT_KEY_RE.match(key):
                    return False
                if not self._is_json_safe_value(item, depth + 1):
                    return False
            return True
        return False

    @api.model
    def _sanitize_action_context(self, context):
        """Return a validated context dict, or False when empty/unsafe."""
        if not isinstance(context, dict):
            return False
        cleaned = {}
        for key, value in context.items():
            if not isinstance(key, str) or not _CONTEXT_KEY_RE.match(key):
                continue
            lowered = key.lower()
            if lowered in _BLOCKED_CONTEXT_KEYS or any(
                fragment in lowered for fragment in _BLOCKED_CONTEXT_FRAGMENTS
            ):
                continue
            if not self._is_json_safe_value(value, depth=0):
                continue
            cleaned[key] = value
            if len(cleaned) >= _AI_CHAT_CONTEXT_DICT_MAX_LEN:
                break
        return cleaned or False

    @api.model
    def _sanitize_open_action(self, entry):
        xml_id = entry.get("xml_id")
        if not isinstance(xml_id, str) or not xml_id or "." not in xml_id:
            return False
        # Allow menu xml ids passed as open_action by mistake.
        menu = self.env.ref(xml_id, raise_if_not_found=False)
        if menu and menu._name == "ir.ui.menu":
            return self._sanitize_open_menu(
                {"type": "open_menu", "menu_xml_id": xml_id}
            )
        try:
            action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        except ValueError:
            return False
        if not isinstance(action, dict) or not action.get("id"):
            return False
        # Server / client / window actions are all valid for doAction.
        if action.get("type") not in (
            "ir.actions.act_window",
            "ir.actions.client",
            "ir.actions.server",
            "ir.actions.act_url",
        ):
            return False
        sanitized = {"type": "open_action", "xml_id": xml_id, "action": action}
        domain = self._sanitize_action_domain(entry.get("domain"))
        if domain is not False and action.get("type") == "ir.actions.act_window":
            sanitized["domain"] = domain
            action = dict(action)
            action["domain"] = domain
            sanitized["action"] = action
        context = self._sanitize_action_context(entry.get("context"))
        if context:
            sanitized["context"] = context
            action = dict(sanitized["action"])
            base_ctx = action.get("context") or {}
            if isinstance(base_ctx, str):
                base_ctx = {}
            action["context"] = {**base_ctx, **context}
            sanitized["action"] = action
        return sanitized

    @api.model
    def _sanitize_open_action_ref(self, entry):
        """Open by database action id when no xml id is available (client actions)."""
        action_type = entry.get("action_type")
        if action_type not in (
            "ir.actions.act_window",
            "ir.actions.client",
            "ir.actions.server",
            "ir.actions.act_url",
        ):
            return False
        if action_type not in self.env:
            return False
        try:
            action_id = int(entry.get("action_id"))
        except (TypeError, ValueError):
            return False
        action = self.env[action_type].browse(action_id).exists()
        if not action:
            return False
        action_dict = self._action_record_to_dict(action)
        if not action_dict:
            return False
        return {
            "type": "open_action_ref",
            "action_type": action_type,
            "action_id": action_id,
            "action": action_dict,
        }

    @api.model
    def _sanitize_open_record(self, entry):
        model = entry.get("model")
        if not isinstance(model, str) or model not in _OPEN_RECORD_MODELS:
            return False
        if model not in self.env:
            return False
        try:
            res_id = int(entry.get("res_id"))
        except (TypeError, ValueError):
            return False
        if res_id <= 0:
            return False
        record = self.env[model].browse(res_id)
        if not record.exists():
            return False
        try:
            record.check_access("read")
        except AccessError:
            return False
        return {
            "type": "open_record",
            "model": model,
            "res_id": res_id,
            "action": {
                "type": "ir.actions.act_window",
                "res_model": model,
                "res_id": res_id,
                "view_mode": "form",
                "views": [[False, "form"]],
                "target": "current",
            },
        }

    @api.model
    def _sanitize_open_menu(self, entry):
        menu_xml_id = entry.get("menu_xml_id")
        if (
            not isinstance(menu_xml_id, str)
            or not menu_xml_id
            or "." not in menu_xml_id
        ):
            return False
        menu = self.env.ref(menu_xml_id, raise_if_not_found=False)
        if not menu or menu._name != "ir.ui.menu":
            return False
        visible_ids = set(self.env["ir.ui.menu"]._visible_menu_ids())
        action_dict = self._resolve_menu_to_action(menu, visible_ids)
        if not action_dict:
            return False
        return {
            "type": "open_menu",
            "menu_xml_id": menu_xml_id,
            "action": action_dict,
        }

    @api.model
    def _navigation_search_terms(self, text):
        """Expand user wording with common EN/PT aliases for app names."""
        lowered = (text or "").strip().lower()
        terms = {lowered} if lowered else set()
        # Only expand when the alias key itself appears in the query.
        # (Avoid cross-pollution via shared synonym lists.)
        aliases = {
            "faturamento": ("invoicing", "accounting", "invoice", "faturas"),
            "contabilidade": ("accounting", "invoicing"),
            "invoicing": ("faturamento", "accounting", "invoice"),
            "invoice": ("faturamento", "invoicing", "faturas"),
            "accounting": ("faturamento", "contabilidade", "invoicing"),
            "funil": ("pipeline", "opportunities", "opportunity"),
            "pipeline": ("funil", "opportunities", "opportunity"),
            "opportunities": ("pipeline", "funil", "opportunity"),
            "vendas": ("sales", "quotations", "orders"),
            "sales": ("vendas", "quotations", "orders"),
            "compras": ("purchase", "rfq"),
            "purchase": ("compras", "rfq"),
            "crm": ("pipeline", "opportunities", "funil", "leads"),
        }
        for key, values in aliases.items():
            if key in lowered:
                terms.add(key)
                terms.update(values)
        return [term for term in terms if len(term) >= 2]

    @api.model
    def _menu_domain_for_terms(self, terms):
        # ir.ui.menu.complete_name is non-stored and cannot be searched.
        domain = None
        for term in terms:
            term_domain = [("name", "ilike", term)]
            domain = (
                term_domain if domain is None else expression.OR([domain, term_domain])
            )
        return domain or [("id", "=", False)]

    @api.model
    def _prefetch_external_ids(self, recordsets):
        """Batch xml ids for one or more recordsets into ``{(model, id): xmlid}``."""
        cache = {}
        for records in recordsets:
            if not records:
                continue
            for rec_id, xmlid in records.get_external_id().items():
                cache[(records._name, rec_id)] = xmlid or False
        return cache

    @api.model
    def _xmlid_from_cache(self, cache, model_name, rec_id, record=None):
        """Return a cached xmlid, or look it up once on cache miss."""
        if not model_name or not rec_id:
            return False
        key = (model_name, rec_id)
        if key in cache:
            return cache[key] or False
        if record is None:
            return False
        xmlid = record.get_external_id().get(rec_id) or False
        cache[key] = xmlid
        return xmlid

    @api.model
    def _navigation_menu_result(self, menu, visible_ids, xmlid_cache=None):
        """Build one navigation hit from a visible menu, or False if unusable."""
        if menu.id not in visible_ids:
            return False
        action_dict = self._resolve_menu_to_action(menu, visible_ids)
        if not action_dict:
            return False
        xmlid_cache = xmlid_cache or {}
        menu_xml = self._xmlid_from_cache(xmlid_cache, menu._name, menu.id, record=menu)
        action_xml = False
        action_type = action_dict.get("type")
        action_id = action_dict.get("id")
        if action_type and action_id and action_type in self.env:
            action_record = self.env[action_type].browse(action_id)
            action_xml = self._xmlid_from_cache(
                xmlid_cache, action_type, action_id, record=action_record
            )
        suggested = False
        if menu_xml:
            suggested = {"type": "open_menu", "menu_xml_id": menu_xml}
        elif action_xml:
            suggested = {"type": "open_action", "xml_id": action_xml}
        elif action_type and action_id:
            suggested = {
                "type": "open_action_ref",
                "action_type": action_type,
                "action_id": action_id,
            }
        return {
            "name": menu.complete_name,
            "menu_xml_id": menu_xml,
            "action_xml_id": action_xml,
            "action_type": action_type,
            "action_id": action_id or False,
            "suggested_action": suggested,
            "_dedupe_key": menu_xml or action_xml or f"{action_type}:{action_id}",
        }

    @api.model
    def _append_menu_navigation_results(
        self, menus, visible_ids, results, seen, limit, xmlid_cache=None
    ):
        for menu in menus:
            if len(results) >= limit:
                break
            entry = self._navigation_menu_result(
                menu, visible_ids, xmlid_cache=xmlid_cache
            )
            if not entry:
                continue
            key = entry.pop("_dedupe_key")
            if key in seen:
                continue
            seen.add(key)
            results.append(entry)

    @api.model
    def _append_window_navigation_results(self, terms, results, seen, limit):
        if len(results) >= limit:
            return
        action_domain = self._menu_domain_for_terms(terms)
        windows = self.env["ir.actions.act_window"].search(action_domain, limit=limit)
        window_xmlids = windows.get_external_id()
        for act in windows:
            if len(results) >= limit:
                break
            xml = window_xmlids.get(act.id)
            if not xml or xml in seen:
                continue
            try:
                self.env["ir.actions.actions"]._for_xml_id(xml)
            except ValueError:
                continue
            seen.add(xml)
            results.append(
                {
                    "name": act.name,
                    "menu_xml_id": False,
                    "action_xml_id": xml,
                    "action_type": "ir.actions.act_window",
                    "suggested_action": {
                        "type": "open_action",
                        "xml_id": xml,
                    },
                }
            )

    @agno_tool(
        "ai.assistant",
        args=("query", "limit"),
        description="Find menus/actions the user can open.",
    )
    @api.model
    def find_navigation(self, query=None, limit=8):
        """Search menus/actions the current user can open.

        Used by the Agno agent so it does not invent xml ids for apps/screens.
        """
        self._check_ai_user()
        text = (query or "").strip()
        if len(text) < 2:
            return {
                "error": "missing_query",
                "detail": "Provide an app or screen name to search.",
            }
        try:
            limit = min(max(int(limit or 8), 1), 15)
        except (TypeError, ValueError):
            limit = 8

        terms = self._navigation_search_terms(text)
        Menu = self.env["ir.ui.menu"]
        visible_ids = set(Menu._visible_menu_ids())
        domain = self._menu_domain_for_terms(terms)
        # Search in the user language and in English (source terms).
        menus = Menu.browse()
        for lang in {self.env.user.lang or "en_US", "en_US"}:
            menus |= Menu.with_context(lang=lang).search(domain, limit=limit * 4)

        action_ids_by_model = {}
        for menu in menus:
            action = menu.action
            if action:
                action_ids_by_model.setdefault(action._name, set()).add(action.id)
        action_sets = [
            self.env[model_name].browse(list(ids))
            for model_name, ids in action_ids_by_model.items()
            if model_name in self.env
        ]
        xmlid_cache = self._prefetch_external_ids([menus, *action_sets])

        results = []
        seen = set()
        self._append_menu_navigation_results(
            menus, visible_ids, results, seen, limit, xmlid_cache=xmlid_cache
        )
        self._append_window_navigation_results(terms, results, seen, limit)

        if not results:
            return {
                "error": "not_found",
                "detail": f"No openable screen matching {text!r}.",
            }
        return {"results": results}
