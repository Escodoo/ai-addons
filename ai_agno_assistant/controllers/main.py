# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import _, api, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


def _sse(payload):
    return f"data: {json.dumps(payload, default=str)}\n\n"


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

    @http.route(
        "/ai_agno_assistant/chat/stream",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=True,
    )
    def chat_stream(self):
        """SSE proxy: Agno tool status, then the same sanitized chat result."""
        if not request.env.user.has_group("ai_agno_assistant.group_system_ai_user"):
            return request.make_json_response(
                {"error": _("You are not allowed to use the system AI assistant.")},
                status=403,
            )
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            return request.make_json_response(
                {"error": _("Invalid request.")},
                status=400,
            )
        if not isinstance(body, dict):
            body = {}
        context = dict(body.get("ui_context") or {})
        session_key = body.get("session_key")
        if session_key and "session_key" not in context:
            context["session_key"] = session_key
        uid = request.env.uid
        env_context = dict(request.env.context)
        registry = request.env.registry
        generic_error = _("The AI request failed. Check the AI Bridge Execution log.")
        message = body.get("message")
        history = body.get("history")

        def _generate():
            # The HTTP request cursor is closed when the controller returns.
            # Stream on a dedicated cursor so tool status can flush live.
            with registry.cursor() as cr:
                env = api.Environment(cr, uid, env_context)
                try:
                    yield from env["ai.assistant"]._iter_assistant_chat_stream(
                        message=message,
                        history=history,
                        ui_context=context,
                    )
                except UserError as err:
                    cr.rollback()
                    yield _sse({"event": "error", "text": str(err)})
                except Exception:
                    cr.rollback()
                    _logger.exception("System AI assistant stream failed")
                    yield _sse({"event": "error", "text": generic_error})

        return request.make_response(
            _generate(),
            headers=[
                ("Content-Type", "text/event-stream"),
                ("Cache-Control", "no-cache"),
                ("X-Accel-Buffering", "no"),
            ],
        )
