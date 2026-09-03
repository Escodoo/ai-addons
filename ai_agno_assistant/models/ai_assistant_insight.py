# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.ai_agno_connector.tool_registry import agno_tool

_logger = logging.getLogger(__name__)

_PREVIEW_FIELD_CANDIDATES = (
    "name",
    "display_name",
    "state",
    "partner_id",
    "amount_total",
    "date",
    "date_order",
    "invoice_date",
    "user_id",
    "company_id",
    "email",
    "phone",
    "expected_revenue",
    "priority",
)
_PREVIEW_FIELD_LIMIT = 12
_BLOCKED_PREVIEW_TYPES = frozenset({"binary", "html", "properties"})


class AiAssistantInsight(models.AbstractModel):
    _inherit = "ai.assistant"  # pylint: disable=consider-merging-classes-inherited

    @api.model
    def _hydrate_record_preview(self, ui_context):
        """Attach a short, ACL-aware snapshot of the current form record."""
        if not isinstance(ui_context, dict):
            return ui_context
        model = ui_context.get("current_model")
        res_id = ui_context.get("current_res_id")
        if self._is_blocked_open_model(model) or not res_id:
            return ui_context
        try:
            record = self.env[model].browse(int(res_id))
        except (TypeError, ValueError):
            return ui_context
        if not record.exists():
            return ui_context
        try:
            record.check_access("read")
        except AccessError:
            return ui_context
        field_names = self._preview_fields_for(record)
        if not field_names:
            return ui_context
        try:
            preview = record.read(field_names)[0]
        except Exception:  # noqa: BLE001 - preview is optional
            _logger.debug("Could not hydrate assistant record preview", exc_info=True)
            return ui_context
        ui_context["record_preview"] = preview
        return ui_context

    @api.model
    def _preview_fields_for(self, record):
        names = []
        for name in _PREVIEW_FIELD_CANDIDATES:
            field = record._fields.get(name)
            if not field or field.type in _BLOCKED_PREVIEW_TYPES:
                continue
            if "password" in name or "token" in name or "secret" in name:
                continue
            names.append(name)
            if len(names) >= _PREVIEW_FIELD_LIMIT:
                break
        return names

    @api.model
    def _safe_count(self, model_name, domain):
        if model_name not in self.env:
            return None
        try:
            return self.env[model_name].search_count(domain)
        except AccessError:
            return None
        except Exception:  # noqa: BLE001 - digest sections are optional
            _logger.debug(
                "Attention digest count failed on %s", model_name, exc_info=True
            )
            return None

    @agno_tool(
        "ai.assistant",
        args=(),
        description="Summarize items that need the user's attention today.",
    )
    @api.model
    def get_attention_digest(self):
        """Return counts of pending work across installed business apps."""
        self._check_ai_user()
        today = fields.Date.context_today(self)
        items = []

        def _add(key, label, model_name, domain):
            count = self._safe_count(model_name, domain)
            if count is None:
                return
            items.append(
                {"key": key, "label": label, "count": count, "model": model_name}
            )

        _add(
            "open_rfqs",
            "Open RFQs",
            "purchase.order",
            [("state", "in", ["draft", "sent"])],
        )
        _add(
            "draft_quotations",
            "Draft quotations",
            "sale.order",
            [("state", "in", ["draft", "sent"])],
        )
        if "account.move" in self.env:
            Move = self.env["account.move"]
            invoice_domain = [("move_type", "=", "out_invoice")]
            if "payment_state" in Move._fields:
                invoice_domain += [
                    ("payment_state", "in", ["not_paid", "partial"]),
                    ("invoice_date_due", "<", today),
                    ("state", "=", "posted"),
                ]
            else:
                invoice_domain += [("state", "=", "posted")]
            _add(
                "overdue_invoices",
                "Overdue customer invoices",
                "account.move",
                invoice_domain,
            )
        _add(
            "open_opportunities",
            "Open opportunities",
            "crm.lead",
            [("type", "=", "opportunity"), ("probability", "<", 100)],
        )
        if "helpdesk.ticket" in self.env:
            Ticket = self.env["helpdesk.ticket"]
            closed_field = "closed" if "closed" in Ticket._fields else False
            domain = (
                [(closed_field, "=", False)]
                if closed_field
                else [("stage_id.closed", "=", False)]
            )
            if closed_field or "stage_id" in Ticket._fields:
                _add(
                    "open_tickets",
                    "Open helpdesk tickets",
                    "helpdesk.ticket",
                    domain,
                )
        _add(
            "open_tasks",
            "Open project tasks",
            "project.task",
            (
                [("stage_id.fold", "=", False)]
                if "project.task" in self.env
                else [("id", "=", False)]
            ),
        )
        return {"date": str(today), "items": items}

    @agno_tool(
        "ai.assistant",
        args=("model", "res_id"),
        description="Read a short snapshot of a record the user can access.",
    )
    @api.model
    def get_record_context(self, model=None, res_id=None, res_model=None):
        """Return key fields of a record for 'explain this' questions.

        ``res_model`` is the transport alias: the RPC gateway already uses
        ``model`` for the allowlisted target (``ai.assistant``).
        """
        self._check_ai_user()
        model = res_model or model
        if self._is_blocked_open_model(model):
            return {
                "error": "model_not_allowed",
                "detail": "This model cannot be previewed.",
            }
        try:
            record_id = int(res_id)
        except (TypeError, ValueError):
            return {
                "error": "invalid_res_id",
                "detail": "Provide a positive record id.",
            }
        if record_id <= 0:
            return {
                "error": "invalid_res_id",
                "detail": "Provide a positive record id.",
            }
        record = self.env[model].browse(record_id)
        if not record.exists():
            return {"error": "not_found", "detail": "Record not found."}
        try:
            record.check_access("read")
        except AccessError as exc:
            return {"error": "access_denied", "detail": str(exc)}
        fields_list = self._preview_fields_for(record)
        data = record.read(fields_list)[0] if fields_list else {"id": record.id}
        return {
            "model": model,
            "res_id": record.id,
            "name": record.display_name,
            "fields": data,
        }
