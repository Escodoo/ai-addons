# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from odoo.addons.ai_oca_bridge_chatter_copilot.tests.common import CopilotCommon
from odoo.addons.mail.tools.discuss import Store


@tagged("post_install", "-at_install")
class TestChatterCopilotLivechat(CopilotCommon):
    def _create_livechat_channel(self, livechat_active=True):
        return self.env["discuss.channel"].create(
            {
                "name": "Livechat Conversation",
                "channel_type": "livechat",
                "livechat_active": livechat_active,
                "livechat_operator_id": self.bot.partner_id.id,
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.bot.partner_id.id}),
                    (0, 0, {"partner_id": self.operator.partner_id.id}),
                    (0, 0, {"guest_id": self.guest.id}),
                ],
            }
        )

    def test_livechat_is_a_customer_conversation(self):
        channel = self._create_livechat_channel()
        self.assertTrue(channel._is_ai_customer_conversation())

    def test_livechat_answers_guest(self):
        channel = self._create_livechat_channel()
        with self._mock_bridge() as mock_post:
            self._post_as_guest(channel)
            mock_post.assert_called_once()

    def test_livechat_ignores_operator_message(self):
        channel = self._create_livechat_channel()
        with self._mock_bridge() as mock_post:
            self._post_as_operator(channel)
            mock_post.assert_not_called()

    def test_livechat_operator_message_pauses_bridge(self):
        channel = self._create_livechat_channel()
        with self._mock_bridge():
            self._post_as_operator(channel)
        self.assertTrue(channel.ai_bridge_paused)
        with self._mock_bridge() as mock_post:
            self._post_as_guest(channel, body="Are you there?")
            mock_post.assert_not_called()

    def test_livechat_resume_gives_conversation_back(self):
        channel = self._create_livechat_channel()
        with self._mock_bridge():
            self._post_as_operator(channel)
        channel.with_user(self.operator).action_ai_bridge_resume()
        with self._mock_bridge() as mock_post:
            self._post_as_guest(channel, body="Thanks")
            mock_post.assert_called_once()

    def test_livechat_handoff_posts_no_note(self):
        """The visitor reads the channel, so no note may be posted there."""
        channel = self._create_livechat_channel()
        with self._mock_bridge():
            self._post_as_operator(channel)
        self.assertTrue(channel.ai_bridge_paused)
        self.assertFalse(self._ai_bridge_notes(channel))
        channel.with_user(self.operator).action_ai_bridge_resume()
        self.assertFalse(self._ai_bridge_notes(channel))

    def test_livechat_closed_does_not_answer(self):
        channel = self._create_livechat_channel(livechat_active=False)
        with self._mock_bridge() as mock_post:
            self._post_as_guest(channel)
            mock_post.assert_not_called()

    def test_livechat_empty_author_is_not_customer(self):
        channel = self._create_livechat_channel()
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": channel.id,
                "body": "orphan",
                "message_type": "comment",
                "author_id": False,
            }
        )
        self.assertFalse(channel._is_ai_customer_author(message))

    def test_livechat_bot_author_is_not_customer(self):
        channel = self._create_livechat_channel()
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": channel.id,
                "body": "bot",
                "message_type": "comment",
                "author_id": self.bot.partner_id.id,
            }
        )
        self.assertFalse(channel._is_ai_customer_author(message))

    def test_to_store_exposes_pause_on_livechat(self):
        channel = self._create_livechat_channel()
        store = Store()
        channel._to_store(store)
        channel_vals = store.data["discuss.channel"][(channel.id,)]
        self.assertFalse(channel_vals["ai_bridge_paused"])
        self.assertTrue(channel_vals["has_ai_bridge"])
