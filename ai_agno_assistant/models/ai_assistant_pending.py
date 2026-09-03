# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.ai_agno_connector.tool_registry import agno_tool

_logger = logging.getLogger(__name__)

_PENDING_TTL_MINUTES = 30
_CONFIRMABLE_STATES = frozenset({"draft", "sent"})


class AiAssistantPendingAction(models.TransientModel):
    _name = "ai.assistant.pending.action"
    _description = "Pending AI assistant confirmation"
    _order = "id desc"

    user_id = fields.Many2one(
        "res.users", required=True, index=True, ondelete="cascade"
    )
    action_key = fields.Char(required=True)
    model_name = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    label = fields.Char()
    summary = fields.Char()


class AiAssistantPendingHelpers(models.AbstractModel):
    _inherit = "ai.assistant"  # pylint: disable=consider-merging-classes-inherited

    @api.model
    def _remember_pending_action(self, action_key, model_name, record, label, summary):
        if "ai.assistant.pending.action" not in self.env or not record:
            return False
        Pending = self.env["ai.assistant.pending.action"].sudo()
        Pending.search([("user_id", "=", self.env.user.id)]).unlink()
        Pending.create(
            {
                "user_id": self.env.user.id,
                "action_key": action_key,
                "model_name": model_name,
                "res_id": record.id,
                "label": (label or "")[:80],
                "summary": (summary or "")[:200],
            }
        )
        return True

    @api.model
    def _latest_pending_action(self):
        if "ai.assistant.pending.action" not in self.env:
            return False
        cutoff = fields.Datetime.now() - timedelta(minutes=_PENDING_TTL_MINUTES)
        return (
            self.env["ai.assistant.pending.action"]
            .sudo()
            .search(
                [
                    ("user_id", "=", self.env.user.id),
                    ("create_date", ">=", cutoff),
                ],
                order="id desc",
                limit=1,
            )
        )

    @api.model
    def _sanitize_confirm_pending(self, entry=None):
        pending = self._latest_pending_action()
        if not pending:
            return False
        return {
            "type": "confirm_pending",
            "label": pending.label or _("Confirm"),
            "summary": pending.summary or "",
            "action_key": pending.action_key,
        }

    @api.model
    def _propose_confirm_order(self, model_name, order_ref, *, role, unavailable):
        if model_name not in self.env:
            return {"error": unavailable, "detail": f"{role} app is not available."}
        Model = self.env[model_name]
        record = self._resolve_by_id_or_name(Model, order_ref, role=role)
        if isinstance(record, dict):
            return record
        try:
            record.check_access("write")
        except AccessError as exc:
            return {"error": "access_denied", "detail": str(exc)}
        if record.state not in _CONFIRMABLE_STATES:
            return {
                "error": "invalid_state",
                "detail": (
                    f"{record.display_name} is {record.state}; "
                    "only draft/sent can be confirmed."
                ),
            }
        label = _("Confirm %s", record.display_name)
        summary = _(
            "This will confirm %s. The action cannot be undone from the chat.",
            record.display_name,
        )
        self._remember_pending_action(
            f"confirm_{model_name}",
            model_name,
            record,
            label,
            summary,
        )
        return {
            "pending": True,
            "model": model_name,
            "res_id": record.id,
            "name": record.display_name,
            "state": record.state,
            "label": label,
            "summary": summary,
        }

    @agno_tool(
        "ai.assistant",
        args=("order_ref",),
        description=(
            "Propose confirming a draft sales order (needs user confirmation)."
        ),
    )
    @api.model
    def propose_confirm_sale_order(self, order_ref=None):
        self._check_ai_user()
        return self._propose_confirm_order(
            "sale.order",
            order_ref,
            role="sale_order",
            unavailable="sale_unavailable",
        )

    @agno_tool(
        "ai.assistant",
        args=("order_ref",),
        description="Propose confirming a draft RFQ (needs user confirmation).",
    )
    @api.model
    def propose_confirm_purchase_order(self, order_ref=None):
        self._check_ai_user()
        return self._propose_confirm_order(
            "purchase.order",
            order_ref,
            role="purchase_order",
            unavailable="purchase_unavailable",
        )

    @api.model
    def action_ai_execute_pending(self, accepted=True):
        """Confirm or discard the pending HITL action for this user."""
        self._check_ai_user()
        pending = self._latest_pending_action()
        if not pending:
            return {
                "error": "expired",
                "detail": "There is no pending action to confirm.",
            }
        model_name = pending.model_name
        res_id = pending.res_id
        action_key = pending.action_key
        pending.sudo().unlink()
        if not accepted:
            return {"cancelled": True}
        if model_name not in self.env:
            return {
                "error": "unavailable",
                "detail": "The target app is not installed.",
            }
        record = self.env[model_name].browse(res_id)
        if not record.exists():
            return {"error": "not_found", "detail": "The record no longer exists."}
        try:
            record.check_access("write")
            with self.env.cr.savepoint():
                if action_key.startswith("confirm_") and hasattr(
                    record, "button_confirm"
                ):
                    record.button_confirm()
                elif action_key.startswith("confirm_") and hasattr(
                    record, "action_confirm"
                ):
                    record.action_confirm()
                else:
                    return {"error": "unsupported", "detail": "Unknown pending action."}
        except AccessError as exc:
            return {"error": "access_denied", "detail": str(exc)}
        except (UserError, ValidationError) as exc:
            return {"error": "validation_error", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - structured error for the UI
            _logger.warning("AI assistant pending confirm failed: %s", exc)
            return {"error": "confirm_failed", "detail": str(exc)}
        return {
            "ok": True,
            "model": model_name,
            "res_id": record.id,
            "name": record.display_name,
            "state": record.state,
            "open_record": {
                "type": "open_record",
                "model": model_name,
                "res_id": record.id,
            },
        }
