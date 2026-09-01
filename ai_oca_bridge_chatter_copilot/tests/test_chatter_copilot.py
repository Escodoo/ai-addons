# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.mail.tools.discuss import Store


@tagged("post_install", "-at_install")
class TestChatterCopilot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, mail_create_nosubscribe=True))
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Copilot Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "chatter",
                "payload_type": "chatter",
                "result_kind": "immediate",
                "result_type": "message",
            }
        )
        cls.bot = new_test_user(cls.env, login="copilot-bot", groups="base.group_user")
        cls.bot.write({"ai_bridge_id": cls.bridge.id})
        cls.operator = new_test_user(
            cls.env, login="copilot-operator", groups="base.group_user"
        )
        cls.customer = cls.env["res.partner"].create({"name": "Copilot Customer"})
        cls.portal_user = new_test_user(
            cls.env, login="copilot-portal", groups="base.group_portal"
        )
        cls.guest = cls.env["mail.guest"].create({"name": "Copilot Visitor"})
        cls.public_user = cls.env.ref("base.public_user")

    # Helpers

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

    def _mock_bridge(self):
        return mock.patch(
            "requests.post",
            return_value=mock.Mock(
                status_code=200,
                content=b'{"body": "AI answer"}',
                json=lambda: {"body": "AI answer"},
            ),
        )

    def _post_inbound(self, channel, author, body="Customer message"):
        """Simulate an inbound gateway message created by the webhook user."""
        return channel.message_post(
            body=body,
            author_id=author.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            no_gateway_notification=True,
        )

    def _post_as_guest(self, channel, body="Visitor message"):
        return (
            channel.with_user(self.public_user)
            .with_context(guest=self.guest)
            .message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        )

    def _post_as_operator(self, channel, body="Operator message"):
        return channel.with_user(self.operator).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def _ai_bridge_notes(self, channel):
        return self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", channel.id),
                ("message_type", "=", "notification"),
                ("body", "like", "AI assistant"),
            ]
        )

    # Gateway conversations

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
            channel.message_post(
                body="hello from telegram",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                no_gateway_notification=True,
            )
            mock_post.assert_called_once()

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
        # mail_gateway does not forward notification messages to Telegram.
        self.assertEqual("notification", notes.message_type)

    # Livechat conversations

    def test_livechat_answers_guest(self):
        channel = self._create_livechat_channel()
        with self._mock_bridge() as mock_post:
            self._post_as_guest(channel)
            mock_post.assert_called_once()

    def test_livechat_operator_message_pauses_bridge(self):
        channel = self._create_livechat_channel()
        with self._mock_bridge():
            self._post_as_operator(channel)
        self.assertTrue(channel.ai_bridge_paused)
        with self._mock_bridge() as mock_post:
            self._post_as_guest(channel, body="Are you there?")
            mock_post.assert_not_called()

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

    # Internal Discuss channels keep the original behaviour

    def test_internal_channel_without_mention_not_called(self):
        channel = self.env["discuss.channel"].create(
            {
                "name": "Internal Channel",
                "channel_type": "channel",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.bot.partner_id.id}),
                    (0, 0, {"partner_id": self.operator.partner_id.id}),
                    (0, 0, {"partner_id": self.env.user.partner_id.id}),
                ],
            }
        )
        with self._mock_bridge() as mock_post:
            channel.with_user(self.operator).message_post(
                body="Team message",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            mock_post.assert_not_called()
        self.assertFalse(channel.ai_bridge_paused)

    def test_internal_channel_with_mention_called(self):
        channel = self.env["discuss.channel"].create(
            {
                "name": "Internal Channel",
                "channel_type": "channel",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.bot.partner_id.id}),
                    (0, 0, {"partner_id": self.operator.partner_id.id}),
                    (0, 0, {"partner_id": self.env.user.partner_id.id}),
                ],
            }
        )
        with self._mock_bridge() as mock_post:
            channel.with_user(self.operator).message_post(
                body="Team message",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=[self.bot.partner_id.id],
            )
            mock_post.assert_called_once()

    def test_pause_rejected_for_portal_user(self):
        channel = self._create_gateway_channel()
        with self.assertRaises(AccessError):
            channel.with_user(self.portal_user).action_ai_bridge_pause()
        with self.assertRaises(AccessError):
            channel.with_user(self.portal_user).action_ai_bridge_resume()
        self.assertFalse(channel.ai_bridge_paused)

    def test_pause_is_idempotent(self):
        channel = self._create_gateway_channel()
        channel.with_user(self.operator).action_ai_bridge_pause()
        notes = self._ai_bridge_notes(channel)
        channel.with_user(self.operator).action_ai_bridge_pause()
        self.assertTrue(channel.ai_bridge_paused)
        self.assertEqual(notes, self._ai_bridge_notes(channel))

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

    def test_to_store_exposes_pause_on_customer_channels(self):
        gateway = self._create_gateway_channel()
        store = Store()
        gateway._to_store(store)
        gateway_vals = store.data["discuss.channel"][(gateway.id,)]
        self.assertFalse(gateway_vals["ai_bridge_paused"])
        self.assertTrue(gateway_vals["has_ai_bridge"])

        internal = self.env["discuss.channel"].create(
            {
                "name": "Internal Channel",
                "channel_type": "channel",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.bot.partner_id.id}),
                    (0, 0, {"partner_id": self.operator.partner_id.id}),
                ],
            }
        )
        store = Store()
        internal._to_store(store)
        internal_vals = store.data["discuss.channel"][(internal.id,)]
        self.assertNotIn("ai_bridge_paused", internal_vals)
        self.assertNotIn("has_ai_bridge", internal_vals)
