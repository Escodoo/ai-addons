# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import traceback
from io import StringIO

import requests

from odoo import _, models
from odoo.exceptions import UserError

from .ai_assistant import _AI_CHAT_MESSAGE_MAX_LEN

_logger = logging.getLogger(__name__)

_BRIDGE_CHAT = "ai_agno_assistant.ai_bridge_assistant_chat"


def _sse(payload):
    return f"data: {json.dumps(payload, default=str)}\n\n"


class AiAssistant(models.AbstractModel):
    _inherit = "ai.assistant"

    def _assistant_stream_url(self, bridge):
        """Derive /chat/stream from the configured /chat bridge URL."""
        url = (bridge.url or "").rstrip("/")
        if url.endswith("/stream"):
            return url
        return f"{url}/stream"

    def _iter_assistant_chat_stream(self, message=None, history=None, ui_context=None):
        """Yield SSE lines: Agno status events, then a sanitized done result."""
        self._check_ai_user()
        text = (message or "").strip()
        if not text:
            raise UserError(_("Please enter a question for the assistant."))
        if len(text) > _AI_CHAT_MESSAGE_MAX_LEN:
            text = text[:_AI_CHAT_MESSAGE_MAX_LEN]
        normalized_ui = self._normalize_ui_context(ui_context)
        history = self._normalize_ai_chat_history(history)
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
        payload = bridge._prepare_payload(
            message=text,
            history=history,
            ui_context=normalized_ui,
            session_id=normalized_ui.get("session_key") or False,
            model="ai.assistant",
            res_id=0,
        )
        payload = execution._add_extra_payload_fields(payload)
        stream_url = self._assistant_stream_url(bridge)
        timeout = bridge.request_timeout or 180
        headers = execution._get_headers()
        headers["Accept"] = "text/event-stream"
        yield _sse({"event": "status", "code": "thinking", "text": "Thinking…"})
        try:
            response = requests.post(
                stream_url,
                json=payload,
                auth=execution._get_auth(),
                headers=headers,
                timeout=timeout,
                stream=True,
            )
        except Exception:
            buff = StringIO()
            traceback.print_exc(file=buff)
            execution.write(
                {
                    "state": "error",
                    "payload": payload,
                    "error": buff.getvalue(),
                }
            )
            buff.close()
            raise UserError(
                _(
                    "The AI request failed. Check the AI Bridge Execution log "
                    "for details."
                )
            ) from None
        done = None
        try:
            if response.status_code >= 400:
                execution.write(
                    {
                        "state": "error",
                        "payload": payload,
                        "result": response.content,
                        "error": response.text[:2000],
                    }
                )
                raise UserError(
                    _(
                        "The AI request failed. Check the AI Bridge Execution log "
                        "for details."
                    )
                )
            for raw in response.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                try:
                    event = json.loads(raw[5:].strip())
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("event")
                if kind == "status":
                    yield _sse(event)
                elif kind == "done":
                    done = event.get("result") or {}
                elif kind == "error":
                    execution.write(
                        {
                            "state": "error",
                            "payload": payload,
                            "error": event.get("text") or "Assistant chat failed.",
                        }
                    )
                    yield _sse(
                        {
                            "event": "error",
                            "text": _(
                                "The AI request failed. Check the AI Bridge "
                                "Execution log for details."
                            ),
                        }
                    )
                    return
        finally:
            response.close()
        if done is None:
            execution.write(
                {
                    "state": "error",
                    "payload": payload,
                    "error": "Assistant stream ended without a result.",
                }
            )
            yield _sse(
                {
                    "event": "error",
                    "text": _(
                        "The AI request failed. Check the AI Bridge Execution log "
                        "for details."
                    ),
                }
            )
            return
        finalized = self._apply_assistant_chat_result(text, done, normalized_ui)
        execution.write(
            {
                "state": "done",
                "payload": payload,
                "result": json.dumps(finalized, default=str),
            }
        )
        yield _sse({"event": "done", "result": finalized})
