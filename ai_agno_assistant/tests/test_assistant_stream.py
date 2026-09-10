# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import threading
from unittest import mock

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.ai_agno_assistant.models import ai_assistant as ai_assistant_mod
from odoo.addons.ai_agno_assistant.models import ai_assistant_stream as stream_mod


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

    def test_iter_assistant_chat_stream_truncates_long_message(self):
        captured = {}
        fake = _FakeStreamResponse(
            [
                'data: {"event": "done", "result": '
                '{"body": "ok", "body_is_html": false, "actions": []}}'
            ]
        )

        def _post(*_args, **kwargs):
            captured["payload"] = kwargs.get("json")
            return fake

        long_message = "q" * (ai_assistant_mod._AI_CHAT_MESSAGE_MAX_LEN + 10)
        with mock.patch(
            "odoo.addons.ai_agno_assistant.models.ai_assistant_stream.requests.post",
            side_effect=_post,
        ):
            list(self.Assistant._iter_assistant_chat_stream(message=long_message))
        self.assertEqual(
            len(captured["payload"]["message"]),
            ai_assistant_mod._AI_CHAT_MESSAGE_MAX_LEN,
        )

    def test_iter_assistant_chat_stream_not_configured(self):
        with mock.patch.object(
            type(self.env),
            "ref",
            return_value=self.env["ai.bridge"],
        ):
            with self.assertRaises(UserError):
                list(self.Assistant._iter_assistant_chat_stream(message="hi"))

    def test_iter_assistant_chat_stream_inactive(self):
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        bridge.active = False
        with self.assertRaises(UserError):
            list(self.Assistant._iter_assistant_chat_stream(message="hi"))

    def test_iter_assistant_chat_stream_group_denied(self):
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        restricted_group = self.env.ref("base.group_system")
        bridge.group_ids = [(6, 0, [restricted_group.id])]
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "AI Stream Limited User",
                    "login": "ai_stream_limited_user",
                    "groups_id": [(6, 0, [self.ai_group.id])],
                }
            )
        )
        with self.assertRaises(UserError):
            list(
                self.Assistant.with_user(user)._iter_assistant_chat_stream(message="hi")
            )

    def test_iter_assistant_chat_stream_connection_error(self):
        with (
            mock.patch(
                "odoo.addons.ai_agno_assistant.models.ai_assistant_stream.requests.post",
                side_effect=ConnectionError("down"),
            ),
            self.assertRaises(UserError),
        ):
            list(self.Assistant._iter_assistant_chat_stream(message="hello"))

    def test_iter_assistant_chat_stream_http_error(self):
        fake = _FakeStreamResponse([], status_code=502, text="bad gateway")
        with (
            mock.patch(
                "odoo.addons.ai_agno_assistant.models.ai_assistant_stream.requests.post",
                return_value=fake,
            ),
            self.assertRaises(UserError),
        ):
            list(self.Assistant._iter_assistant_chat_stream(message="hello"))

    def test_iter_assistant_chat_stream_skips_junk_and_needs_done(self):
        fake = _FakeStreamResponse(
            [
                "",
                "comment: ignore",
                "data: not-json",
                "data: [1, 2]",
                'data: {"event": "status", "code": "consulting"}',
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
        self.assertIn("consulting", [item.get("code") for item in payloads])
        self.assertEqual(payloads[-1]["event"], "error")

    def test_iter_assistant_chat_stream_closes_agno_when_client_aborts(self):
        closed = threading.Event()

        class _HangingStreamResponse:
            status_code = 200
            content = b""
            text = ""

            def iter_lines(self, decode_unicode=True):
                yield 'data: {"event": "status", "code": "routing"}'
                closed.wait(5)

            def close(self):
                closed.set()

        hanging = _HangingStreamResponse()
        with mock.patch(
            "odoo.addons.ai_agno_assistant.models.ai_assistant_stream.requests.post",
            return_value=hanging,
        ):
            gen = self.Assistant._iter_assistant_chat_stream(message="hello")
            saw_routing = False
            for line in gen:
                if "routing" in line:
                    saw_routing = True
                    gen.close()
                    break
        self.assertTrue(saw_routing)
        self.assertTrue(closed.is_set())

    def test_iter_agno_sse_lines_emits_wait_sentinel(self):
        started = threading.Event()
        closed = threading.Event()

        class _SlowResponse:
            def iter_lines(self, decode_unicode=True):
                started.set()
                closed.wait(5)
                return iter(())

            def close(self):
                closed.set()

        lines = []
        response = _SlowResponse()
        gen = stream_mod.iter_agno_sse_lines(response, wait=0.05)
        lines.append(next(gen))
        self.assertTrue(started.is_set())
        gen.close()
        self.assertIsNone(lines[0])
        self.assertTrue(closed.is_set())

    def test_iter_agno_sse_lines_reraises_reader_errors(self):
        class _BoomResponse:
            def iter_lines(self, decode_unicode=True):
                raise OSError("broken pipe")

            def close(self):
                return None

        gen = stream_mod.iter_agno_sse_lines(_BoomResponse(), wait=0.05)
        with self.assertRaises(OSError):
            next(gen)

    def test_parse_agno_sse_line_covers_event_kinds(self):
        self.assertEqual(stream_mod._parse_agno_sse_line(None)[0], "keepalive")
        self.assertIsNone(stream_mod._parse_agno_sse_line(""))
        self.assertIsNone(stream_mod._parse_agno_sse_line("comment: ignore"))
        self.assertIsNone(stream_mod._parse_agno_sse_line("data: not-json"))
        self.assertIsNone(stream_mod._parse_agno_sse_line("data: [1, 2]"))
        self.assertIsNone(stream_mod._parse_agno_sse_line('data: {"event": "other"}'))
        kind, result = stream_mod._parse_agno_sse_line('data: {"event": "done"}')
        self.assertEqual(kind, "done")
        self.assertEqual(result, {})
        kind, text = stream_mod._parse_agno_sse_line('data: {"event": "error"}')
        self.assertEqual(kind, "error")
        self.assertEqual(text, "Assistant chat failed.")

    def test_iter_proxied_agno_sse_keepalive_and_client_close(self):
        execution = mock.Mock()
        stopped = threading.Event()

        class _HangAfterStatus:
            def iter_lines(self, decode_unicode=True):
                yield 'data: {"event": "status", "code": "routing"}'
                stopped.wait(5)

            def close(self):
                stopped.set()

        outcome = []
        gen = self.Assistant._iter_proxied_agno_sse(
            _HangAfterStatus(), execution, {}, outcome
        )
        first = next(gen)
        self.assertIn("routing", first)
        gen.close()
        self.assertEqual(outcome, [])

    def test_iter_proxied_agno_sse_yields_keepalive_then_done(self):
        def _lines(_response, wait=1.0):
            yield None
            yield 'data: {"event": "other"}'
            yield 'data: {"event": "done", "result": {"body": "ok"}}'

        with mock.patch.object(stream_mod, "iter_agno_sse_lines", side_effect=_lines):
            outcome = []
            events = list(
                self.Assistant._iter_proxied_agno_sse(
                    mock.Mock(), mock.Mock(), {}, outcome
                )
            )
        self.assertIn(stream_mod._SSE_KEEPALIVE, events)
        self.assertEqual(outcome, [{"body": "ok"}])

    def test_iter_proxied_agno_sse_maps_error_and_generator_exit(self):
        def _error_lines(_response, wait=1.0):
            yield 'data: {"event": "error"}'

        with mock.patch.object(
            stream_mod, "iter_agno_sse_lines", side_effect=_error_lines
        ):
            outcome = []
            execution = mock.Mock()
            events = list(
                self.Assistant._iter_proxied_agno_sse(
                    mock.Mock(), execution, {"message": "hi"}, outcome
                )
            )
        self.assertEqual(outcome, [None])
        self.assertTrue(events)
        self.assertEqual(events[-1][0:5], "data:")
        execution.write.assert_called_once()

        def _raise_exit(_response, wait=1.0):
            raise GeneratorExit()

        with (
            mock.patch.object(
                stream_mod, "iter_agno_sse_lines", side_effect=_raise_exit
            ),
            self.assertRaises(GeneratorExit),
        ):
            list(
                self.Assistant._iter_proxied_agno_sse(mock.Mock(), mock.Mock(), {}, [])
            )
