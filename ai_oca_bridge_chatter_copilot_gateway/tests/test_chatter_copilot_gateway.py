# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from odoo.addons.ai_oca_bridge_chatter_copilot.tests.common import CopilotCommon
from odoo.addons.mail.tools.discuss import Store


@tagged("post_install", "-at_install")
class TestChatterCopilotGateway(CopilotCommon):
    def _create_gateway_channel(self):
        return self.env["discuss.channel"].create(
            {
                "name": "Gateway Conversation",
                "channel_type": "gateway",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.bot.partner_id.id}),
                    (0, 0, {"partner_id": self.operator.partner_id.id}),
                    (0, 0, {"partner_id": self.customer.id}),
                ],
            }
        )

    def _post_inbound(self, channel, author=None, body="Customer message"):
        """Simulate an inbound gateway message created by the webhook user."""
        kwargs = {}
        if author:
            kwargs["author_id"] = author.id
        return channel.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            no_gateway_notification=True,
            **kwargs,
        )

    def test_gateway_is_a_customer_conversation(self):
        channel = self._create_gateway_channel()
        self.assertTrue(channel._is_ai_customer_conversation())

    def test_gateway_answers_with_extra_members(self):
        """The bot answers the customer even with a human in the channel."""
        channel = self._create_gateway_channel()
        # More than two members would disable the answer on a Discuss channel.
        self.assertGreater(len(channel.channel_member_ids), 2)
        with self._mock_bridge() as mock_post:
            self._post_inbound(channel, self.customer)
            mock_post.assert_called_once()

    def test_gateway_ignores_operator_message(self):
        """An operator message is not answered by the bot."""
        channel = self._create_gateway_channel()
        with self._mock_bridge() as mock_post:
            self._post_as_operator(channel)
            mock_post.assert_not_called()

    def test_gateway_operator_message_pauses_bridge(self):
        """The first operator message hands the conversation over."""
        channel = self._create_gateway_channel()
        self.assertFalse(channel.ai_bridge_paused)
        with self._mock_bridge():
            self._post_as_operator(channel)
        self.assertTrue(channel.ai_bridge_paused)
        with self._mock_bridge() as mock_post:
            self._post_inbound(channel, self.customer, body="Still there?")
            mock_post.assert_not_called()

    def test_gateway_resume_gives_conversation_back(self):
        """Resuming lets the bot answer the next customer message."""
        channel = self._create_gateway_channel()
        with self._mock_bridge():
            self._post_as_operator(channel)
        channel.with_user(self.operator).action_ai_bridge_resume()
        self.assertFalse(channel.ai_bridge_paused)
        with self._mock_bridge() as mock_post:
            self._post_inbound(channel, self.customer, body="Thanks")
            mock_post.assert_called_once()

    def test_gateway_answers_portal_customer(self):
        """A customer linked to a portal user is still a customer."""
        channel = self._create_gateway_channel()
        channel.channel_member_ids.filtered(
            lambda member: member.partner_id == self.customer
        ).unlink()
        channel.write(
            {
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.portal_user.partner_id.id})
                ]
            }
        )
        with self._mock_bridge() as mock_post:
            self._post_inbound(channel, self.portal_user.partner_id)
            mock_post.assert_called_once()

    def test_gateway_manual_pause_action(self):
        """Pausing before taking over stops the bot without a message."""
        channel = self._create_gateway_channel()
        channel.with_user(self.operator).action_ai_bridge_pause()
        self.assertTrue(channel.ai_bridge_paused)
        with self._mock_bridge() as mock_post:
            self._post_inbound(channel, self.customer)
            mock_post.assert_not_called()

    def test_gateway_inbound_without_author_answers(self):
        """Telegram guest posts often have no author_id nor author_guest_id."""
        channel = self._create_gateway_channel()
        with self._mock_bridge() as mock_post:
            self._post_inbound(channel, body="hello from telegram")
            mock_post.assert_called_once()

    def test_gateway_inbound_without_author_does_not_pause(self):
        """The webhook user is internal but is not taking the conversation."""
        channel = self._create_gateway_channel()
        with self._mock_bridge():
            self._post_inbound(channel, body="hello from telegram")
        self.assertFalse(channel.ai_bridge_paused)

    def test_gateway_inbound_as_webhook_bot_answers(self):
        """The webhook user is often the bot; inbound is still the customer."""
        channel = self._create_gateway_channel()
        with self._mock_bridge() as mock_post:
            channel.with_user(self.bot).message_post(
                body="hello from telegram",
                author_id=self.bot.partner_id.id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                no_gateway_notification=True,
            )
            mock_post.assert_called_once()

    def test_gateway_bot_answer_does_not_pause(self):
        """The answer posted by the bot is not a human handoff."""
        channel = self._create_gateway_channel()
        with self._mock_bridge():
            self._post_inbound(channel, self.customer)
        self.assertFalse(channel.ai_bridge_paused)
        bot_messages = self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", channel.id),
                ("author_id", "=", self.bot.partner_id.id),
            ]
        )
        self.assertEqual(1, len(bot_messages))

    def test_gateway_handoff_posts_note(self):
        """A gateway keeps the handoff note for the operators only."""
        channel = self._create_gateway_channel()
        with self._mock_bridge():
            self._post_as_operator(channel)
        notes = self._ai_bridge_notes(channel)
        self.assertEqual(1, len(notes))
        # mail_gateway does not forward notification messages to the service.
        self.assertEqual("notification", notes.message_type)

    def test_operator_post_with_author_id_pauses(self):
        """Passing author_id still counts as a human writing from Odoo."""
        channel = self._create_gateway_channel()
        with self._mock_bridge():
            channel.message_post(
                body="Taking over",
                author_id=self.operator.partner_id.id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        self.assertTrue(channel.ai_bridge_paused)

    def test_bot_post_with_author_id_does_not_pause(self):
        channel = self._create_gateway_channel()
        with self._mock_bridge() as mock_post:
            channel.message_post(
                body="Bot line",
                author_id=self.bot.partner_id.id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            mock_post.assert_not_called()
        self.assertFalse(channel.ai_bridge_paused)

    def test_to_store_exposes_pause_on_gateway(self):
        channel = self._create_gateway_channel()
        store = Store()
        channel._to_store(store)
        channel_vals = store.data["discuss.channel"][(channel.id,)]
        self.assertFalse(channel_vals["ai_bridge_paused"])
        self.assertTrue(channel_vals["has_ai_bridge"])
