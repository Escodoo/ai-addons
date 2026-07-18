# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from unittest import mock

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestChatterErrorNotify(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env.ref("ai_agno_chatter_bots.ai_bridge_chatter_ops")
        cls.bot = cls.env.ref("ai_agno_chatter_bots.user_bot_ops")
        cls.user = cls.env.ref("base.user_admin")
        cls.channel = (
            cls.env["discuss.channel"]
            .with_user(cls.user)
            .create(
                {
                    "name": "Ops Error Notify Test",
                    "channel_type": "chat",
                    "channel_member_ids": [
                        (0, 0, {"partner_id": cls.user.partner_id.id}),
                        (0, 0, {"partner_id": cls.bot.partner_id.id}),
                    ],
                }
            )
        )

    def _create_execution(self, message=None, chatter_user=None):
        values = {
            "ai_bridge_id": self.bridge.id,
            "model_id": self.env["ir.model"]._get_id("mail.message"),
        }
        if message:
            values["res_id"] = message.id
        if chatter_user:
            values["chatter_user_id"] = chatter_user.id
        return self.env["ai.bridge.execution"].create(values)

    def _bot_message_count(self):
        return self.env["mail.message"].search_count(
            [("author_id", "=", self.bot.partner_id.id)]
        )

    def test_http_error_posted_in_chatter(self):
        error_detail = (
            "No chat LLM configured. Set LLM_PROVIDER / LLM_HOST / "
            "LLM_MODEL, or configure BYOK in Odoo Settings → Agno AI."
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=503,
                content=f'{{"detail":"{error_detail}"}}'.encode(),
                raise_for_status=mock.Mock(
                    side_effect=Exception(f"503 Server Error: {error_detail}")
                ),
            )
            self.channel.with_user(self.user).message_post(body="olá")

        bot_messages = self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", self.channel.id),
                ("author_id", "=", self.bot.partner_id.id),
            ]
        )
        self.assertEqual(len(bot_messages), 1)
        self.assertIn("AI error", bot_messages.body)
        self.assertIn("No chat LLM configured", bot_messages.body)

        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(execution.state, "error")

    def test_execute_swallows_notify_errors(self):
        execution_model = type(self.env["ai.bridge.execution"])
        with (
            mock.patch("requests.post") as mock_post,
            mock.patch.object(
                execution_model,
                "_notify_chatter_error",
                side_effect=RuntimeError("notify boom"),
            ),
            self.assertLogs(
                "odoo.addons.ai_agno_chatter_bots.models.ai_bridge_execution",
                level="ERROR",
            ) as logs,
        ):
            mock_post.return_value = mock.Mock(
                status_code=500,
                content=b"kaboom",
                raise_for_status=mock.Mock(side_effect=Exception("500 Server Error")),
            )
            self.channel.with_user(self.user).message_post(body="oi")
        self.assertTrue(
            any("Failed to post chatter error" in line for line in logs.output)
        )
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(execution.state, "error")

    def test_chatter_error_detail_variants(self):
        execution = self._create_execution(chatter_user=self.bot)
        cases = [
            # (stored result, substring expected in the detail)
            (False, "Check the AI Execution log"),
            ("   ", "Check the AI Execution log"),
            ("plain error text", "plain error text"),
            ('{"other": 1}', '{"other": 1}'),
            (json.dumps({"detail": "   "}), '{"detail"'),
            (
                json.dumps({"detail": [{"msg": "first"}, {"msg": "second"}]}),
                "first; second",
            ),
            (json.dumps({"detail": [{"other": 1}]}), '{"detail"'),
        ]
        for result, expected in cases:
            execution.result = result
            self.assertIn(expected, execution._chatter_error_detail())

    def test_chatter_error_detail_truncates_long_text(self):
        execution = self._create_execution(chatter_user=self.bot)
        execution.result = "x" * 600
        self.assertEqual(len(execution._chatter_error_detail()), 500)

    def test_notify_skips_without_chatter_user(self):
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": self.channel.id,
                "body": "ping",
                "message_type": "comment",
                "author_id": self.user.partner_id.id,
            }
        )
        execution = self._create_execution(message=message)
        before = self._bot_message_count()
        execution._notify_chatter_error()
        self.assertEqual(self._bot_message_count(), before)

    def test_notify_skips_without_channel(self):
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": self.channel.id,
                "body": "ping",
                "message_type": "comment",
                "author_id": self.user.partner_id.id,
            }
        )
        execution = self._create_execution(message=message, chatter_user=self.bot)
        execution_model = type(self.env["ai.bridge.execution"])
        before = self._bot_message_count()
        with mock.patch.object(execution_model, "_get_channel", return_value=None):
            execution._notify_chatter_error()
        self.assertEqual(self._bot_message_count(), before)

    def test_notify_posts_even_without_channel_membership(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.user)
            .create({"name": "No Bot Channel", "channel_type": "channel"})
        )
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": channel.id,
                "body": "ping",
                "message_type": "comment",
                "author_id": self.user.partner_id.id,
            }
        )
        execution = self._create_execution(message=message, chatter_user=self.bot)
        before = self._bot_message_count()
        execution._notify_chatter_error()
        self.assertEqual(self._bot_message_count(), before + 1)
