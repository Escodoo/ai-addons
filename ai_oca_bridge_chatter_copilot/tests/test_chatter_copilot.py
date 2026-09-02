# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.mail.tools.discuss import Store

from .common import CopilotCommon


@tagged("post_install", "-at_install")
class TestChatterCopilot(CopilotCommon):
    # Internal Discuss channels keep the original behaviour

    def test_internal_channel_is_not_a_customer_conversation(self):
        """Without a glue module no channel type is a customer conversation."""
        channel = self._create_internal_channel()
        self.assertFalse(channel._is_ai_customer_conversation())

    def test_internal_channel_without_mention_not_called(self):
        channel = self._create_internal_channel()
        with self._mock_bridge() as mock_post:
            self._post_as_operator(channel, body="Team message")
            mock_post.assert_not_called()
        self.assertFalse(channel.ai_bridge_paused)

    def test_internal_channel_with_mention_called(self):
        channel = self._create_internal_channel()
        with self._mock_bridge() as mock_post:
            channel.with_user(self.operator).message_post(
                body="Team message",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=[self.bot.partner_id.id],
            )
            mock_post.assert_called_once()

    def test_internal_channel_operator_message_does_not_pause(self):
        """The handoff only applies to customer conversations."""
        channel = self._create_internal_channel()
        with self._mock_bridge():
            self._post_as_operator(channel)
        self.assertFalse(channel.ai_bridge_paused)

    # Author classification

    def test_empty_author_is_not_customer(self):
        channel = self._create_internal_channel()
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

    def test_bot_author_is_not_customer(self):
        channel = self._create_internal_channel()
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

    def test_operator_author_is_not_customer(self):
        channel = self._create_internal_channel()
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": channel.id,
                "body": "operator",
                "message_type": "comment",
                "author_id": self.operator.partner_id.id,
            }
        )
        self.assertFalse(channel._is_ai_customer_author(message))

    def test_portal_author_is_customer(self):
        """A customer linked to a portal user is still a customer."""
        channel = self._create_internal_channel()
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": channel.id,
                "body": "portal",
                "message_type": "comment",
                "author_id": self.portal_user.partner_id.id,
            }
        )
        self.assertTrue(channel._is_ai_customer_author(message))

    def test_guest_author_is_customer(self):
        channel = self._create_internal_channel()
        message = self.env["mail.message"].create(
            {
                "model": "discuss.channel",
                "res_id": channel.id,
                "body": "visitor",
                "message_type": "comment",
                "author_guest_id": self.guest.id,
            }
        )
        self.assertTrue(channel._is_ai_customer_author(message))

    # Pause and resume

    def test_pause_and_resume_post_a_note(self):
        channel = self._create_internal_channel()
        channel.with_user(self.operator).action_ai_bridge_pause()
        self.assertTrue(channel.ai_bridge_paused)
        self.assertEqual(1, len(self._ai_bridge_notes(channel)))
        channel.with_user(self.operator).action_ai_bridge_resume()
        self.assertFalse(channel.ai_bridge_paused)
        self.assertEqual(2, len(self._ai_bridge_notes(channel)))

    def test_pause_rejected_for_portal_user(self):
        channel = self._create_internal_channel()
        with self.assertRaises(AccessError):
            channel.with_user(self.portal_user).action_ai_bridge_pause()
        with self.assertRaises(AccessError):
            channel.with_user(self.portal_user).action_ai_bridge_resume()
        self.assertFalse(channel.ai_bridge_paused)

    def test_pause_is_idempotent(self):
        channel = self._create_internal_channel()
        channel.with_user(self.operator).action_ai_bridge_pause()
        notes = self._ai_bridge_notes(channel)
        channel.with_user(self.operator).action_ai_bridge_pause()
        self.assertTrue(channel.ai_bridge_paused)
        self.assertEqual(notes, self._ai_bridge_notes(channel))

    # Client store

    def test_to_store_skips_internal_channels(self):
        channel = self._create_internal_channel()
        store = Store()
        channel._to_store(store)
        channel_vals = store.data["discuss.channel"][(channel.id,)]
        self.assertNotIn("ai_bridge_paused", channel_vals)
        self.assertNotIn("has_ai_bridge", channel_vals)
