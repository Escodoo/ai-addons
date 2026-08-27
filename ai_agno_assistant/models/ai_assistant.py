# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import html
import logging

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)

AI_USER_GROUP = "ai_agno_assistant.group_system_ai_user"
_BRIDGE_CHAT = "ai_agno_assistant.ai_bridge_assistant_chat"

_AI_CHAT_HISTORY_LIMIT = 20
_AI_CHAT_MESSAGE_MAX_LEN = 2000
_AI_CHAT_ACTIONS_LIMIT = 5


class AiAssistant(models.AbstractModel):
    _name = "ai.assistant"
    _description = "System AI Assistant"

    @api.model
    def _check_ai_user(self):
        if not self.env.user.has_group(AI_USER_GROUP):
            raise AccessError(_("You are not allowed to use the system AI assistant."))

    @api.model
    def _sanitize_assistant_body(self, body, body_is_html):
        """Sanitize assistant body before the OWL client renders it."""
        if isinstance(body, str):
            text = body
        elif body in (None, False):
            text = ""
        else:
            text = str(body)
        if not text:
            return ""
        if body_is_html:
            return html_sanitize(
                text,
                sanitize_attributes=True,
                strip_style=True,
                strip_classes=True,
            )
        return html.escape(text)

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
        body_is_html = bool(result.get("body_is_html", False))
        actions = self._sanitize_ai_chat_actions(result.get("actions"))
        return {
            "body": self._sanitize_assistant_body(
                result.get("body") or "", body_is_html
            ),
            "body_is_html": body_is_html,
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
