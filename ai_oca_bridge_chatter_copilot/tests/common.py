# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase


class CopilotCommon(TransactionCase):
    """Shared fixtures, reused by the gateway and livechat glue modules."""

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

    def _create_internal_channel(self, name="Internal Channel"):
        return self.env["discuss.channel"].create(
            {
                "name": name,
                "channel_type": "channel",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.bot.partner_id.id}),
                    (0, 0, {"partner_id": self.operator.partner_id.id}),
                    (0, 0, {"partner_id": self.env.user.partner_id.id}),
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
