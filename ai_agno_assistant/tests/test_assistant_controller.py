# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from unittest import mock

from odoo import http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import JsonRpcException
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestAiAssistantController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.chat_user = cls.env["res.users"].create(
            {
                "name": "Assistant HTTP User",
                "login": "ai_http_user",
                "password": "ai_http_user",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.ai_group.id,
                        ],
                    )
                ],
            }
        )
        cls.blocked_user = cls.env["res.users"].create(
            {
                "name": "Assistant HTTP Blocked",
                "login": "ai_http_blocked",
                "password": "ai_http_blocked",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def _chat(self, **params):
        return self.make_jsonrpc_request("/ai_agno_assistant/chat", params)

    def _chat_stream(self, payload):
        token = http.Request.csrf_token(self)
        return self.url_open(
            f"/ai_agno_assistant/chat/stream?csrf_token={token}",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )

    @mute_logger("odoo.http")
    def test_chat_requires_assistant_group(self):
        self.authenticate("ai_http_blocked", "ai_http_blocked")
        with self.assertRaises(JsonRpcException) as err:
            self._chat(message="hello")
        self.assertIn("AccessError", str(err.exception))

    def test_chat_forwards_session_key_and_returns_bridge_payload(self):
        self.authenticate("ai_http_user", "ai_http_user")
        captured = {}

        def _fake_chat(*_args, **kwargs):
            captured["message"] = kwargs.get("message")
            captured["history"] = kwargs.get("history")
            captured["ui_context"] = kwargs.get("ui_context")
            return {
                "body": "<p>On screen</p>",
                "body_is_html": True,
                "actions": [],
                "artifacts": [],
            }

        with mock.patch.object(
            type(self.env["ai.assistant"]),
            "action_ai_chat",
            side_effect=_fake_chat,
        ):
            result = self._chat(
                message="How many RFQs?",
                history=[{"role": "user", "content": "Hi"}],
                ui_context={"action": "purchase.purchase_rfq"},
                session_key="conv-http-1",
            )
        self.assertEqual(result["body"], "<p>On screen</p>")
        self.assertEqual(result["artifacts"], [])
        self.assertEqual(captured["message"], "How many RFQs?")
        self.assertEqual(captured["ui_context"]["session_key"], "conv-http-1")
        self.assertEqual(captured["ui_context"]["action"], "purchase.purchase_rfq")

    @mute_logger("odoo.http")
    def test_chat_reraises_user_error(self):
        self.authenticate("ai_http_user", "ai_http_user")
        with (
            mock.patch.object(
                type(self.env["ai.assistant"]),
                "action_ai_chat",
                side_effect=UserError("Missing message."),
            ),
            self.assertRaises(JsonRpcException) as err,
        ):
            self._chat(message="   ")
        self.assertIn("UserError", str(err.exception))

    @mute_logger("odoo.http", "odoo.addons.ai_agno_assistant.controllers.main")
    def test_chat_wraps_unexpected_errors(self):
        self.authenticate("ai_http_user", "ai_http_user")
        with (
            mock.patch.object(
                type(self.env["ai.assistant"]),
                "action_ai_chat",
                side_effect=RuntimeError("bridge down"),
            ),
            self.assertRaises(JsonRpcException) as err,
        ):
            self._chat(message="hello")
        self.assertIn("UserError", str(err.exception))

    def test_chat_stream_requires_assistant_group(self):
        self.authenticate("ai_http_blocked", "ai_http_blocked")
        response = self._chat_stream({"message": "hello"})
        self.assertEqual(response.status_code, 403)

    def test_chat_stream_proxies_status_and_done(self):
        self.authenticate("ai_http_user", "ai_http_user")

        def _fake_stream(*_args, **_kwargs):
            yield 'data: {"event": "status", "code": "thinking"}\n\n'
            yield (
                'data: {"event": "done", "result": '
                '{"body": "<p>On screen</p>", "body_is_html": true, "actions": []}}\n\n'
            )

        with mock.patch.object(
            type(self.env["ai.assistant"]),
            "_iter_assistant_chat_stream",
            side_effect=_fake_stream,
        ):
            response = self._chat_stream(
                {"message": "How many RFQs?", "session_key": "conv-http-1"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("event-stream", response.headers.get("Content-Type", ""))
        body = response.text
        self.assertIn("thinking", body)
        self.assertIn("On screen", body)

    def test_chat_stream_empty_message_is_error_event(self):
        self.authenticate("ai_http_user", "ai_http_user")
        response = self._chat_stream({"message": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertIn('"event": "error"', response.text)
        self.assertNotIn("Bridge Execution log", response.text)
