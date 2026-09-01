# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import AccessError
from odoo.tools import html_escape

from odoo.addons.mail.tools.discuss import Store

CUSTOMER_CHANNEL_TYPES = ("gateway", "livechat")


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    ai_bridge_paused = fields.Boolean(
        string="AI Assistant Paused",
        copy=False,
        help="When enabled, the AI bridges of this conversation stop answering "
        "so a human can take over.",
    )

    # Conversation and author classification

    def _is_ai_customer_conversation(self):
        """Gateway and livechat channels are conversations with a customer.

        Unlike internal Discuss channels, they are not driven by mentions: the
        assistant is expected to answer the customer even when several
        operators are members of the channel.
        """
        self.ensure_one()
        return self.channel_type in CUSTOMER_CHANNEL_TYPES

    def _is_ai_conversation_open(self):
        self.ensure_one()
        if self.channel_type == "livechat":
            return self.livechat_active
        return True

    def _ai_bridge_members(self):
        self.ensure_one()
        return self.sudo().channel_member_ids.filtered(
            lambda member: member.partner_id.user_ids.ai_bridge_id
        )

    def _partner_is_ai_bridge(self, partner):
        return bool(partner) and bool(partner.sudo().user_ids.ai_bridge_id)

    def _partner_is_internal_operator(self, partner):
        # partner_share is False only for partners having an internal user, so
        # portal users and partners without user stay on the customer side.
        return bool(partner) and not partner.sudo().partner_share

    def _is_ai_customer_author(self, message):
        self.ensure_one()
        # sudo: the author is inspected on behalf of the bot, and the message
        # may have been posted by a guest with no access to it.
        message = message.sudo()
        if self.env.context.get("ai_bridge_gateway_inbound"):
            # The webhook is the customer side. Telegram often posts the
            # mail.guest without author_guest_id, so author_id stays empty
            # or is attributed to the webhook user (frequently the bot).
            return True
        if message.author_guest_id:
            return True
        partner = message.author_id
        if not partner:
            return False
        if self._partner_is_ai_bridge(partner):
            return False
        return not self._partner_is_internal_operator(partner)

    def _eligibile_for_ai(self, message, recipient):
        if not self._is_ai_customer_conversation():
            return super()._eligibile_for_ai(message, recipient)
        if self.ai_bridge_paused or not self._is_ai_conversation_open():
            return False
        return self._is_ai_customer_author(message)

    # Human handoff

    def _is_ai_bridge_inbound_post(self, **kwargs):
        """Whether the message is being created by a gateway webhook.

        Inbound posts pass no_gateway_notification on the call. The flag must
        not be read from the environment: the AI reply is posted in the same
        request and would otherwise be treated as another inbound message.
        """
        return bool(kwargs.get("no_gateway_notification"))

    def _is_ai_bridge_operator_post(self, **kwargs):
        """Whether an internal user is writing to the customer from Odoo."""
        self.ensure_one()
        if kwargs.get("message_type", "notification") != "comment":
            # System notifications (joins, leaves, logs) are not a handoff.
            return False
        author_id = kwargs.get("author_id")
        if author_id:
            partner = self.env["res.partner"].browse(author_id)
            if self._partner_is_ai_bridge(partner):
                return False
            return self._partner_is_internal_operator(partner)
        if not self.env.user._is_internal():
            return False
        return not self.env.user.sudo().ai_bridge_id

    def message_post(self, **kwargs):
        channel = self
        inbound = False
        post_kwargs = kwargs
        if self.channel_type in CUSTOMER_CHANNEL_TYPES:
            inbound = self._is_ai_bridge_inbound_post(**kwargs)
            if not inbound and self._is_ai_bridge_operator_post(**kwargs):
                self._ai_bridge_set_paused(True, handoff=True)
            ctx = {"ai_bridge_gateway_inbound": inbound}
            # mail.thread rejects unknown notify kwargs. Published
            # mail_gateway versions still forward no_gateway_notification
            # to _notify_thread, so move it to the context (which both
            # current and older mail_gateway already honour).
            if "no_gateway_notification" in kwargs:
                post_kwargs = dict(kwargs)
                ctx["no_gateway_notification"] = post_kwargs.pop(
                    "no_gateway_notification"
                )
            channel = self.with_context(**ctx)
        message = super(DiscussChannel, channel).message_post(**post_kwargs)
        if inbound:
            # Use the original env so the AI reply does not inherit the
            # inbound / no_gateway_notification flags.
            self._ai_bridge_trigger_inbound(message)
        return message

    def _ai_bridge_trigger_inbound(self, message):
        """Create the chatter execution when OCA skipped an inbound post.

        ai_oca_bridge_chatter refuses to answer a message authored by an AI
        bridge user. Gateway webhooks often run as that same user and leave
        author_id empty, so the inbound customer line never reaches Agno.
        """
        self.ensure_one()
        if self.ai_bridge_paused or not self._is_ai_conversation_open():
            return
        message = message.sudo()
        model_id = self.env.ref("mail.model_mail_message").id
        members = self._ai_bridge_members()
        if message.author_id and not self._partner_is_ai_bridge(message.author_id):
            members = members.filtered(
                lambda member: member.partner_id != message.author_id
            )
        for member in members:
            member._notify_typing(is_typing=True)
            for user in member.partner_id.user_ids:
                for bridge in user.ai_bridge_id:
                    already = (
                        self.env["ai.bridge.execution"]
                        .sudo()
                        .search(
                            [
                                ("ai_bridge_id", "=", bridge.id),
                                ("model_id", "=", model_id),
                                ("res_id", "=", message.id),
                            ],
                            limit=1,
                        )
                    )
                    if already:
                        continue
                    execution = (
                        self.env["ai.bridge.execution"]
                        .sudo()
                        .create(
                            {
                                "ai_bridge_id": bridge.id,
                                "model_id": model_id,
                                "res_id": message.id,
                                "chatter_user_id": user.id,
                            }
                        )
                    )
                    execution._execute()

    # Pause and resume

    def action_ai_bridge_pause(self):
        self._check_ai_bridge_pause_access()
        return self._ai_bridge_set_paused(True)

    def action_ai_bridge_resume(self):
        self._check_ai_bridge_pause_access()
        return self._ai_bridge_set_paused(False)

    def _check_ai_bridge_pause_access(self):
        if not self.env.user._is_internal():
            raise AccessError(
                _("Only internal users can pause or resume the AI assistant.")
            )

    def _ai_bridge_set_paused(self, paused, handoff=False):
        for channel in self:
            if channel.ai_bridge_paused == paused:
                continue
            # sudo: writing a conversation flag is allowed to any operator
            # having access to the conversation itself.
            channel.sudo().ai_bridge_paused = paused
            channel._bus_send_store(channel, {"ai_bridge_paused": paused})
            if channel._ai_bridge_note_stays_internal():
                channel._ai_bridge_post_paused_note(paused, handoff=handoff)
        return True

    def _ai_bridge_note_stays_internal(self):
        """Whether a note posted here is kept out of the customer conversation.

        Gateways drop notification messages instead of forwarding them, but a
        livechat visitor reads the channel itself, so a note posted there would
        disclose the handoff to the customer.
        """
        self.ensure_one()
        return self.channel_type != "livechat"

    def _ai_bridge_paused_note_body(self, paused, handoff=False):
        self.ensure_one()
        user_name = self.env.user.display_name
        if not paused:
            return _(
                "%(user)s gave the conversation back to the AI assistant.",
                user=user_name,
            )
        if handoff:
            return _(
                "%(user)s took over the conversation. AI assistant paused.",
                user=user_name,
            )
        return _("%(user)s paused the AI assistant.", user=user_name)

    def _ai_bridge_post_paused_note(self, paused, handoff=False):
        self.ensure_one()
        body = Markup(
            '<div class="o_mail_notification o_hide_author">%s</div>'
        ) % html_escape(self._ai_bridge_paused_note_body(paused, handoff=handoff))
        # The note is authored by the acting user so that Discuss renders it as
        # a plain system line instead of repeating the author name.
        # sudo: the note documents an operator action on the conversation.
        self.sudo().message_post(
            body=body,
            author_id=self.env.user.partner_id.id,
            message_type="notification",
            subtype_xmlid="mail.mt_comment",
        )

    # Client store

    def _to_store(self, store: Store):
        result = super()._to_store(store)
        for channel in self:
            if channel.channel_type not in CUSTOMER_CHANNEL_TYPES:
                continue
            store.add(
                channel,
                {
                    "ai_bridge_paused": channel.ai_bridge_paused,
                    "has_ai_bridge": bool(channel._ai_bridge_members()),
                },
            )
        return result
