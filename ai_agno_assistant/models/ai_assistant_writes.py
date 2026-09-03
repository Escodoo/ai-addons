# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.ai_agno_connector.tool_registry import agno_tool

_logger = logging.getLogger(__name__)


class AiAssistantWrites(models.AbstractModel):
    _inherit = "ai.assistant"  # pylint: disable=consider-merging-classes-inherited

    @agno_tool(
        "ai.assistant",
        args=("name", "email", "phone", "is_company"),
        description="Create a draft partner/contact for human review.",
    )
    @api.model
    def prepare_partner(self, name=None, email=None, phone=None, is_company=False):
        self._check_ai_user()
        title = (name or "").strip() if isinstance(name, str) else ""
        if not title:
            return {"error": "missing_name", "detail": "Provide a partner name."}
        values = {
            "name": title[:128],
            "is_company": bool(is_company),
        }
        if isinstance(email, str) and email.strip():
            values["email"] = email.strip()[:128]
        if isinstance(phone, str) and phone.strip():
            values["phone"] = phone.strip()[:64]
        partner, error = self._safe_create("res.partner", values, "partner")
        if error:
            return error
        return {
            "partner_id": partner.id,
            "name": partner.display_name,
            "open_record": {
                "type": "open_record",
                "model": "res.partner",
                "res_id": partner.id,
            },
        }

    @agno_tool(
        "ai.assistant",
        args=("model", "res_id", "summary", "note", "date_deadline"),
        description="Schedule a follow-up activity on a record the user can access.",
    )
    @api.model
    def prepare_activity(
        self,
        model=None,
        res_id=None,
        summary=None,
        note=None,
        date_deadline=None,
        res_model=None,
    ):
        self._check_ai_user()
        model = res_model or model
        if "mail.activity" not in self.env:
            return {
                "error": "activity_unavailable",
                "detail": "Activities are not available.",
            }
        if self._is_blocked_open_model(model):
            return {
                "error": "model_not_allowed",
                "detail": "Cannot schedule on this model.",
            }
        try:
            record_id = int(res_id)
        except (TypeError, ValueError):
            return {"error": "invalid_res_id", "detail": "Provide a record id."}
        if model not in self.env or record_id <= 0:
            return {
                "error": "invalid_res_id",
                "detail": "Provide a valid model and id.",
            }
        record = self.env[model].browse(record_id)
        if not record.exists():
            return {"error": "not_found", "detail": "Record not found."}
        try:
            record.check_access("read")
        except AccessError as exc:
            return {"error": "access_denied", "detail": str(exc)}
        ir_model = self.env["ir.model"]._get(model)
        if not ir_model:
            return {"error": "model_not_allowed", "detail": "Unknown model."}
        title = (
            summary.strip()
            if isinstance(summary, str) and summary.strip()
            else "Follow-up"
        )
        values = {
            "res_model_id": ir_model.id,
            "res_id": record.id,
            "summary": title[:100],
            "date_deadline": date_deadline or fields.Date.context_today(self),
            "user_id": self.env.user.id,
        }
        if note and isinstance(note, str):
            values["note"] = self._sanitize_draft_html(note, 2000)
        ActivityType = self.env["mail.activity.type"]
        default_type = ActivityType.search(
            [("res_model", "in", (model, False))], limit=1
        )
        if default_type:
            values["activity_type_id"] = default_type.id
        activity, error = self._safe_create("mail.activity", values, "activity")
        if error:
            return error
        return {
            "activity_id": activity.id,
            "summary": activity.summary,
            "res_model": model,
            "res_id": record.id,
            "open_record": {
                "type": "open_record",
                "model": model,
                "res_id": record.id,
            },
        }

    @agno_tool(
        "ai.assistant",
        args=("model", "res_id", "product_ref", "qty", "price_unit"),
        description="Add a draft line to the current sale or purchase order.",
    )
    @api.model
    def add_order_line(
        self,
        model=None,
        res_id=None,
        product_ref=None,
        qty=None,
        price_unit=None,
        res_model=None,
    ):
        self._check_ai_user()
        model = res_model or model
        if model not in {"sale.order", "purchase.order"} or model not in self.env:
            return {
                "error": "order_unavailable",
                "detail": "Provide sale.order or purchase.order.",
            }
        try:
            order_id = int(res_id)
        except (TypeError, ValueError):
            return {"error": "invalid_res_id", "detail": "Provide the order id."}
        order = self.env[model].browse(order_id)
        if not order.exists():
            return {"error": "not_found", "detail": "Order not found."}
        try:
            order.check_access("write")
        except AccessError as exc:
            return {"error": "access_denied", "detail": str(exc)}
        if order.state not in {"draft", "sent"}:
            return {
                "error": "invalid_state",
                "detail": "Lines can only be added on draft/sent orders.",
            }
        product = self._resolve_product(product_ref)
        if isinstance(product, dict):
            return product
        quantity, qty_error = self._parse_line_qty(
            {"qty": qty}, product, ("qty", "product_qty", "product_uom_qty")
        )
        if qty_error:
            return qty_error
        line_model = (
            "sale.order.line" if model == "sale.order" else "purchase.order.line"
        )
        values = {"order_id": order.id, "product_id": product.id}
        if model == "sale.order":
            values["product_uom_qty"] = quantity
        else:
            values["product_qty"] = quantity
            values["name"] = product.display_name
            values["product_uom"] = (
                product.uom_po_id.id
                if "uom_po_id" in product._fields
                else product.uom_id.id
            )
            values["date_planned"] = fields.Datetime.now()
        price, price_error = self._parse_line_price_unit(
            {"price_unit": price_unit}, product
        )
        if price_error:
            return price_error
        if price is not None:
            values["price_unit"] = price
        line, error = self._safe_create(line_model, values, "order_line")
        if error:
            return error
        return {
            "line_id": line.id,
            "order_id": order.id,
            "product": product.display_name,
            "qty": quantity,
            "open_record": {
                "type": "open_record",
                "model": model,
                "res_id": order.id,
            },
        }
