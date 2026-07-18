# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestChatterErrorNotify(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, mail_create_nosubscribe=True))
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Error Notify Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "chatter",
                "payload_type": "chatter",
                "result_kind": "immediate",
                "result_type": "message",
            }
        )
        cls.bot = new_test_user(
            cls.env,
            login="test-error-notify-bot",
            groups="base.group_user",
        )
        cls.bot.write({"ai_bridge_id": cls.bridge.id})
        cls.user = new_test_user(
            cls.env,
            login="test-error-notify-user",
            groups="base.group_user",
        )
        cls.channel = (
            cls.env["discuss.channel"]
            .with_user(cls.user)
            .create(
                {
                    "name": "Error Notify Test",
                    "channel_type": "chat",
                    "channel_member_ids": [
                        (0, 0, {"partner_id": cls.user.partner_id.id}),
                        (0, 0, {"partner_id": cls.bot.partner_id.id}),
                    ],
                }
            )
        )

    def test_http_error_posted_in_chatter(self):
        error_detail = "No chat LLM configured on the AI service."
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=503,
                content=f'{{"detail":"{error_detail}"}}'.encode(),
                raise_for_status=mock.Mock(
                    side_effect=Exception(f"503 Server Error: {error_detail}")
                ),
            )
            self.channel.with_user(self.user).message_post(body="hello")

        bot_messages = self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", self.channel.id),
                ("author_id", "=", self.bot.partner_id.id),
            ]
        )
        self.assertEqual(len(bot_messages), 1)
        self.assertIn("AI error", bot_messages.body)
        self.assertIn(error_detail, bot_messages.body)

        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(execution.state, "error")

    def test_error_detail_fallback_without_result(self):
        execution = (
            self.env["ai.bridge.execution"]
            .sudo()
            .create(
                {
                    "ai_bridge_id": self.bridge.id,
                    "model_id": self.env["ir.model"]._get_id("mail.message"),
                    "res_id": 0,
                }
            )
        )
        detail = execution._chatter_error_detail()
        self.assertIn("could not process your message", detail)
