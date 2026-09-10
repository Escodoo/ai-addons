# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from unittest import mock

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


class _FakeStreamResponse:
    def __init__(self, lines, status_code=200, text=""):
        self.status_code = status_code
        self._lines = lines
        self.content = b""
        self.text = text

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)

    def close(self):
        return None


@tagged("post_install", "-at_install")
class TestAiAssistantStream(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]

    def test_assistant_stream_url_appends_stream(self):
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        self.assertTrue(
            self.Assistant._assistant_stream_url(bridge).endswith("/stream")
        )
        bridge.url = "http://agno:8000/bridge/assistant/chat/stream"
        self.assertEqual(
            self.Assistant._assistant_stream_url(bridge),
            "http://agno:8000/bridge/assistant/chat/stream",
        )

    def test_iter_assistant_chat_stream_requires_message(self):
        with self.assertRaises(UserError):
            list(self.Assistant._iter_assistant_chat_stream(message="   "))

    def test_iter_assistant_chat_stream_sanitizes_done(self):
        fake = _FakeStreamResponse(
            [
                'data: {"event": "status", "code": "reading", "model": "sale.order"}',
                (
                    'data: {"event": "done", "result": '
                    '{"body": "<p>Hi</p><script>x()</script>", '
                    '"body_is_html": true, "actions": []}}'
                ),
            ]
        )
        with mock.patch(
            "odoo.addons.ai_agno_assistant.models.ai_assistant_stream.requests.post",
            return_value=fake,
        ):
            events = list(self.Assistant._iter_assistant_chat_stream(message="hello"))
        payloads = [
            json.loads(line[5:].strip()) for line in events if line.startswith("data:")
        ]
        codes = [item.get("code") for item in payloads if item.get("event") == "status"]
        self.assertIn("thinking", codes)
        self.assertIn("reading", codes)
        done = next(item for item in payloads if item.get("event") == "done")
        self.assertIn("Hi", done["result"]["body"])
        self.assertNotIn("<script", done["result"]["body"].lower())
        self.assertTrue(done["result"]["session_key"])

    def test_iter_assistant_chat_stream_maps_agno_error(self):
        fake = _FakeStreamResponse(['data: {"event": "error", "text": "boom"}'])
        with mock.patch(
            "odoo.addons.ai_agno_assistant.models.ai_assistant_stream.requests.post",
            return_value=fake,
        ):
            events = list(self.Assistant._iter_assistant_chat_stream(message="hello"))
        payloads = [
            json.loads(line[5:].strip()) for line in events if line.startswith("data:")
        ]
        self.assertEqual(payloads[-1]["event"], "error")
        self.assertTrue(payloads[-1]["text"])
