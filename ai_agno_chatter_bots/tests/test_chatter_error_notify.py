# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

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
