# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

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
