# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _is_ai_customer_conversation(self):
        self.ensure_one()
        if self.channel_type == "gateway":
            return True
        return super()._is_ai_customer_conversation()

    def _is_ai_customer_author(self, message):
        self.ensure_one()
        if self.channel_type == "gateway" and self.env.context.get(
            "ai_bridge_gateway_inbound"
        ):
            # The webhook is the customer side. Telegram often posts the
            # mail.guest without author_guest_id, so author_id stays empty or
            # is attributed to the webhook user, frequently the bot itself.
            return True
        return super()._is_ai_customer_author(message)

    def _is_ai_bridge_inbound_post(self, **kwargs):
        if kwargs.get("no_gateway_notification"):
            return True
        # message_post moves the flag to the context before going up the MRO,
        # so the handoff detection can only find it there.
        if self.env.context.get("ai_bridge_gateway_inbound"):
            return True
        return super()._is_ai_bridge_inbound_post(**kwargs)

    def message_post(self, **kwargs):
        if self.channel_type != "gateway":
            return super().message_post(**kwargs)
        # The flag is read from the call and never from the environment: the AI
        # reply is posted in the same request and would otherwise be treated as
        # another inbound message.
        inbound = bool(kwargs.get("no_gateway_notification"))
        post_kwargs = kwargs
        ctx = {"ai_bridge_gateway_inbound": inbound}
        # mail.thread rejects unknown notify kwargs. Published mail_gateway
        # versions still forward no_gateway_notification to _notify_thread, so
        # move it to the context, which every mail_gateway version honours.
        if "no_gateway_notification" in kwargs:
            post_kwargs = dict(kwargs)
            ctx["no_gateway_notification"] = post_kwargs.pop("no_gateway_notification")
        message = super(DiscussChannel, self.with_context(**ctx)).message_post(
            **post_kwargs
        )
        if inbound:
            # Use the original env so the AI reply does not inherit the inbound
            # nor the no_gateway_notification flag.
            self._ai_bridge_trigger_inbound(message)
        return message

    def _ai_bridge_trigger_inbound(self, message):
        """Create the chatter execution when OCA skipped an inbound post.

        ai_oca_bridge_chatter refuses to answer a message authored by an AI
        bridge user. Gateway webhooks often run as that same user and leave
        author_id empty, so the inbound customer line never reaches the bridge.
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
