# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import traceback
from io import StringIO
from queue import Empty, Queue
from threading import Thread

import requests

from odoo import _, models
from odoo.exceptions import UserError

from .ai_assistant import _AI_CHAT_MESSAGE_MAX_LEN

_logger = logging.getLogger(__name__)

_BRIDGE_CHAT = "ai_agno_assistant.ai_bridge_assistant_chat"
_SSE_KEEPALIVE = ": keepalive\n\n"
_AGNO_SSE_READ_WAIT = 1.0


def iter_agno_sse_lines(response, wait=_AGNO_SSE_READ_WAIT):
    """Yield Agno SSE lines without blocking the Odoo worker forever.

    ``None`` means "still waiting" so the HTTP proxy can send a keepalive
    and notice that the browser aborted. Closing ``response`` unblocks the
    reader; Agno then cancels the inline Team run.
    """
    queue = Queue()
    done = object()

    def _reader():
        try:
            for raw in response.iter_lines(decode_unicode=True):
                queue.put(raw)
        except Exception as exc:  # noqa: BLE001
            queue.put(exc)
        finally:
            queue.put(done)

    thread = Thread(target=_reader, daemon=True, name="ai-assistant-sse")
    thread.start()
    finished = False
    try:
        while True:
            try:
                item = queue.get(timeout=wait)
            except Empty:
                yield None
                continue
            if item is done:
                finished = True
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        if not finished:
            _logger.info("Assistant stream closed by client; closing the Agno request")
        response.close()
        thread.join(timeout=2)


def _sse(payload):
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _parse_agno_sse_line(raw):
    if raw is None:
        return "keepalive", _SSE_KEEPALIVE
    if not raw or not raw.startswith("data:"):
        return None
    try:
        event = json.loads(raw[5:].strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    kind = event.get("event")
    if kind == "status":
        return "status", _sse(event)
    if kind == "done":
        return "done", event.get("result") or {}
    if kind == "error":
        return "error", event.get("text") or "Assistant chat failed."
    return None


class AiAssistant(models.AbstractModel):
    _inherit = "ai.assistant"

    def _assistant_stream_error_sse(self):
        return _sse(
            {
                "event": "error",
                "text": _(
                    "The AI request failed. Check the AI Bridge Execution log "
                    "for details."
                ),
            }
        )

    def _iter_proxied_agno_sse(self, response, execution, payload, outcome):
        """Yield SSE chunks from Agno; store the done payload on ``outcome``."""
        for raw in iter_agno_sse_lines(response):
            classified = _parse_agno_sse_line(raw)
            if not classified:
                continue
            kind, value = classified
            if kind in ("keepalive", "status"):
                yield value
            elif kind == "done":
                outcome.append(value)
            elif kind == "error":
                execution.write(
                    {
                        "state": "error",
                        "payload": payload,
                        "error": value,
                    }
                )
                outcome.append(None)
                yield self._assistant_stream_error_sse()
                return

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
        outcome = []
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
            yield from self._iter_proxied_agno_sse(
                response, execution, payload, outcome
            )
        finally:
            response.close()
        if outcome and outcome[-1] is None:
            return
        done = outcome[-1] if outcome else None
        if done is None:
            execution.write(
                {
                    "state": "error",
                    "payload": payload,
                    "error": "Assistant stream ended without a result.",
                }
            )
            yield self._assistant_stream_error_sse()
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
