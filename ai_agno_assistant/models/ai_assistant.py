# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression

_logger = logging.getLogger(__name__)

AI_USER_GROUP = "ai_agno_assistant.group_system_ai_user"
_BRIDGE_CHAT = "ai_agno_assistant.ai_bridge_assistant_chat"

_AI_CHAT_HISTORY_LIMIT = 10
_AI_CHAT_MESSAGE_MAX_LEN = 2000
_AI_CHAT_ACTIONS_LIMIT = 5

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
        "stock.picking",
        "project.project",
        "project.task",
        "helpdesk.ticket",
    }
)


class AiAssistant(models.AbstractModel):
    _name = "ai.assistant"
    _description = "System AI Assistant"

    @api.model
    def _check_ai_user(self):
        if not self.env.user.has_group(AI_USER_GROUP):
            raise AccessError(_("You are not allowed to use the system AI assistant."))

    @api.model
    def action_ai_chat(self, message=None, history=None, ui_context=None):
        """Answer a system-wide assistant question and return sanitized actions."""
        self._check_ai_user()
        text = (message or "").strip()
        if not text:
            raise UserError(_("Please enter a question for the assistant."))
        if len(text) > _AI_CHAT_MESSAGE_MAX_LEN:
            text = text[:_AI_CHAT_MESSAGE_MAX_LEN]
        result = self._run_assistant_bridge(
            message=text,
            history=self._normalize_ai_chat_history(history),
            ui_context=self._normalize_ui_context(ui_context),
        )
        actions = self._sanitize_ai_chat_actions(result.get("actions"))
        return {
            "body": result.get("body") or "",
            "body_is_html": bool(result.get("body_is_html", True)),
            "actions": actions,
        }

    @api.model
    def _normalize_ai_chat_history(self, history):
        if not history or not isinstance(history, list):
            return []
        cleaned = []
        for entry in history[-_AI_CHAT_HISTORY_LIMIT:]:
            if not isinstance(entry, dict):
                continue
            role = entry.get("role")
            content = (entry.get("content") or "").strip()
            if role not in ("user", "assistant") or not content:
                continue
            if len(content) > _AI_CHAT_MESSAGE_MAX_LEN:
                content = content[:_AI_CHAT_MESSAGE_MAX_LEN]
            cleaned.append({"role": role, "content": content})
        return cleaned

    @api.model
    def _normalize_ui_context(self, ui_context):
        if not isinstance(ui_context, dict):
            return {}
        cleaned = {}
        for key in (
            "current_action",
            "current_model",
            "current_res_id",
            "company_id",
        ):
            if key not in ui_context:
                continue
            value = ui_context.get(key)
            if key == "current_res_id":
                try:
                    cleaned[key] = (
                        int(value) if value not in (None, False, "") else False
                    )
                except (TypeError, ValueError):
                    cleaned[key] = False
            elif key == "company_id":
                try:
                    cleaned[key] = (
                        int(value) if value not in (None, False, "") else False
                    )
                except (TypeError, ValueError):
                    cleaned[key] = False
            elif isinstance(value, str):
                cleaned[key] = value[:200]
            else:
                cleaned[key] = value
        return cleaned

    @api.model
    def _sanitize_ai_chat_actions(self, actions):
        """Validate navigation actions before the OWL client runs them."""
        if not isinstance(actions, list):
            return []
        cleaned = []
        for entry in actions[:_AI_CHAT_ACTIONS_LIMIT]:
            if not isinstance(entry, dict):
                continue
            action_type = entry.get("type")
            if action_type == "open_action":
                sanitized = self._sanitize_open_action(entry)
            elif action_type == "open_action_ref":
                sanitized = self._sanitize_open_action_ref(entry)
            elif action_type == "open_record":
                sanitized = self._sanitize_open_record(entry)
            elif action_type == "open_menu":
                sanitized = self._sanitize_open_menu(entry)
            else:
                continue
            if sanitized:
                cleaned.append(sanitized)
        return cleaned

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
        domain = entry.get("domain")
        if isinstance(domain, list) and action.get("type") == "ir.actions.act_window":
            sanitized["domain"] = domain
            action = dict(action)
            action["domain"] = domain
            sanitized["action"] = action
        context = entry.get("context")
        if isinstance(context, dict):
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
    def _navigation_menu_result(self, menu, visible_ids):
        """Build one navigation hit from a visible menu, or False if unusable."""
        if menu.id not in visible_ids:
            return False
        action_dict = self._resolve_menu_to_action(menu, visible_ids)
        if not action_dict:
            return False
        menu_xml = menu.get_external_id().get(menu.id) or False
        action_xml = False
        action_type = action_dict.get("type")
        action_id = action_dict.get("id")
        if action_type and action_id and action_type in self.env:
            action_xml = (
                self.env[action_type].browse(action_id).get_external_id().get(action_id)
                or False
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
    def _append_menu_navigation_results(self, menus, visible_ids, results, seen, limit):
        for menu in menus:
            if len(results) >= limit:
                break
            entry = self._navigation_menu_result(menu, visible_ids)
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
        for act in windows:
            if len(results) >= limit:
                break
            xml = act.get_external_id().get(act.id)
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

        results = []
        seen = set()
        self._append_menu_navigation_results(menus, visible_ids, results, seen, limit)
        self._append_window_navigation_results(terms, results, seen, limit)

        if not results:
            return {
                "error": "not_found",
                "detail": f"No openable screen matching {text!r}.",
            }
        return {"results": results}

    @api.model
    def prepare_purchase_order(self, vendor_ref=None, lines=None, notes=None):
        """Create a draft RFQ for the requesting user and return a summary.

        Never confirms the order. The user reviews and confirms in the form.
        """
        self._check_ai_user()
        if "purchase.order" not in self.env:
            return {
                "error": "purchase_unavailable",
                "detail": "Purchase app is not available.",
            }
        partner = self._resolve_vendor(vendor_ref)
        if isinstance(partner, dict):
            return partner
        line_vals, line_error = self._prepare_po_lines(lines, partner=partner)
        if line_error:
            return line_error
        values = {
            "partner_id": partner.id,
            "order_line": [(0, 0, line) for line in line_vals],
        }
        if notes and isinstance(notes, str):
            # Price belongs on order lines (price_unit), not in notes.
            values["notes"] = notes.strip()[:2000]
        try:
            with self.env.cr.savepoint():
                order = self.env["purchase.order"].create(values)
        except AccessError as exc:
            return {"error": "access_denied", "detail": str(exc)}
        except (UserError, ValidationError) as exc:
            return {"error": "validation_error", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - return structured error to the agent
            _logger.warning("AI assistant PO create failed: %s", exc)
            return {"error": "create_failed", "detail": str(exc)}
        _logger.info(
            "AI assistant draft PO %s created by user %s (partner=%s, lines=%s)",
            order.name,
            self.env.user.login,
            partner.id,
            [line.get("product_id") for line in line_vals],
        )
        return {
            "po_id": order.id,
            "name": order.name,
            "partner": {"id": partner.id, "name": partner.display_name},
            "state": order.state,
            "currency": order.currency_id.name,
            "lines_summary": [
                {
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "qty": line.product_qty,
                    "price_unit": line.price_unit,
                }
                for line in order.order_line
            ],
            "open_record": {
                "type": "open_record",
                "model": "purchase.order",
                "res_id": order.id,
            },
        }

    @api.model
    def _resolve_vendor(self, vendor_ref):
        Partner = self.env["res.partner"]
        if vendor_ref in (None, False, ""):
            return {
                "error": "missing_vendor",
                "detail": "Provide a vendor name, reference or id.",
            }
        if isinstance(vendor_ref, int) or (
            isinstance(vendor_ref, str) and vendor_ref.isdigit()
        ):
            partner = Partner.browse(int(vendor_ref)).exists()
            if not partner:
                return {
                    "error": "vendor_not_found",
                    "detail": f"No partner with id {vendor_ref}.",
                }
            return partner
        name = str(vendor_ref).strip()
        domain = expression.AND(
            [
                ["|", ("supplier_rank", ">", 0), ("is_company", "=", True)],
                ["|", ("name", "ilike", name), ("ref", "=ilike", name)],
            ]
        )
        partners = Partner.search(domain, limit=5)
        if not partners:
            partners = Partner.search(
                ["|", ("name", "ilike", name), ("display_name", "ilike", name)],
                limit=5,
            )
        if not partners:
            return {
                "error": "vendor_not_found",
                "detail": f"No vendor matching {name!r}.",
            }
        if len(partners) > 1:
            return {
                "error": "vendor_ambiguous",
                "detail": "Multiple vendors matched; ask the user to clarify.",
                "candidates": [{"id": p.id, "name": p.display_name} for p in partners],
            }
        return partners

    @api.model
    def _resolve_line_price_unit(self, entry, product, partner, qty, uom):
        """Prefer explicit line price, then vendor pricelist, then cost."""
        raw_price = entry.get("price_unit", entry.get("price"))
        if raw_price not in (None, False, ""):
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                return None, {
                    "error": "invalid_price",
                    "detail": (
                        f"Unit price must be a number for {product.display_name}."
                    ),
                }
            if price < 0:
                return None, {
                    "error": "invalid_price",
                    "detail": (
                        f"Unit price cannot be negative for {product.display_name}."
                    ),
                }
            return price, None
        if partner and hasattr(product, "_select_seller"):
            seller = product._select_seller(
                partner_id=partner,
                quantity=qty,
                uom_id=uom,
            )
            if seller:
                return float(seller.price), None
        return float(product.standard_price or 0.0), None

    @api.model
    def _prepare_po_lines(self, lines, partner=None):
        if not isinstance(lines, list) or not lines:
            return None, {
                "error": "missing_lines",
                "detail": "Provide at least one line with product and quantity.",
            }
        prepared = []
        for entry in lines[:20]:
            if not isinstance(entry, dict):
                continue
            product = self._resolve_product(
                entry.get("product_id") or entry.get("product_ref")
            )
            if isinstance(product, dict):
                return None, product
            try:
                qty = float(entry.get("qty") or entry.get("product_qty") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                return None, {
                    "error": "invalid_qty",
                    "detail": f"Quantity must be positive for {product.display_name}.",
                }
            uom = (
                product.uom_po_id if "uom_po_id" in product._fields else product.uom_id
            )
            price_unit, price_error = self._resolve_line_price_unit(
                entry, product, partner, qty, uom
            )
            if price_error:
                return None, price_error
            line = {
                "product_id": product.id,
                "name": product.display_name,
                "product_qty": qty,
                "product_uom": uom.id,
                "price_unit": price_unit,
                "date_planned": fields.Datetime.now(),
            }
            prepared.append(line)
        if not prepared:
            return None, {
                "error": "missing_lines",
                "detail": "Provide at least one valid purchase line.",
            }
        return prepared, None

    @api.model
    def _resolve_product(self, product_ref):
        Product = self.env["product.product"]
        if product_ref in (None, False, ""):
            return {
                "error": "missing_product",
                "detail": "Provide a product name, default_code or id.",
            }
        if isinstance(product_ref, int) or (
            isinstance(product_ref, str) and product_ref.isdigit()
        ):
            product = Product.browse(int(product_ref)).exists()
            if not product:
                return {
                    "error": "product_not_found",
                    "detail": f"No product with id {product_ref}.",
                }
            return product
        name = str(product_ref).strip()
        domain = [
            "|",
            ("default_code", "=ilike", name),
            "|",
            ("barcode", "=", name),
            ("name", "ilike", name),
        ]
        products = Product.search(domain, limit=5)
        if not products:
            return {
                "error": "product_not_found",
                "detail": f"No product matching {name!r}.",
            }
        if len(products) > 1:
            # Prefer exact default_code match when present.
            exact = products.filtered(
                lambda p: (p.default_code or "").lower() == name.lower()
            )
            if len(exact) == 1:
                return exact
            return {
                "error": "product_ambiguous",
                "detail": "Multiple products matched; ask the user to clarify.",
                "candidates": [
                    {
                        "id": p.id,
                        "name": p.display_name,
                        "default_code": p.default_code or False,
                    }
                    for p in products
                ],
            }
        return products

    @api.model
    def _run_assistant_bridge(self, **kwargs):
        bridge = self.env.ref(_BRIDGE_CHAT, raise_if_not_found=False)
        if not bridge:
            raise UserError(_("The system AI assistant bridge is not configured."))
        if not bridge.active or (
            bridge.group_ids and not self.env.user.groups_id & bridge.group_ids
        ):
            raise UserError(_("%s is not active.", bridge.name))
        model = self.env["ir.model"]._get("ai.assistant")
        execution = (
            self.env["ai.bridge.execution"]
            .sudo()
            .create(
                {
                    "ai_bridge_id": bridge.id,
                    "model_id": model.id if model else False,
                    "res_id": 0,
                }
            )
        )
        # Do not pass record/res_id/model here: ai.bridge.execution._execute
        # already injects them into _prepare_payload and **kwargs would collide.
        result = execution._execute(**kwargs)
        if execution.state == "error":
            _logger.warning(
                "System AI assistant bridge failed: %s",
                execution.error,
            )
            raise UserError(
                _(
                    "The AI request failed. Check the AI Bridge Execution log "
                    "for details."
                )
            )
        return result or {}
