# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class AiAssistantController(http.Controller):
    @http.route(
        "/ai_agno_assistant/chat",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def chat(self, message=None, history=None, ui_context=None, session_key=None):
        """JSON entry used by the systray so the client can abort the request."""
        if not request.env.user.has_group("ai_agno_assistant.group_system_ai_user"):
            raise AccessError(_("You are not allowed to use the system AI assistant."))
        context = dict(ui_context or {})
        if session_key and "session_key" not in context:
            context["session_key"] = session_key
        try:
            return request.env["ai.assistant"].action_ai_chat(
                message=message,
                history=history,
                ui_context=context,
            )
        except UserError:
            raise
        except Exception:
            _logger.exception("System AI assistant chat failed")
            raise UserError(
                _("The AI request failed. Check the AI Bridge Execution log.")
            ) from None
