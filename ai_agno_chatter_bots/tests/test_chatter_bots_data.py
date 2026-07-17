# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAgnoChatterBotsData(TransactionCase):
    def test_chatter_bridges_and_users(self):
        expected = (
            ("ai_bridge_chatter_erp", "user_bot_erp", "bot.erp", "erp"),
            ("ai_bridge_chatter_ops", "user_bot_ops", "bot.ops", "ops"),
            (
                "ai_bridge_chatter_support",
                "user_bot_support",
                "bot.suporte",
                "support",
            ),
            ("ai_bridge_chatter_sales", "user_bot_sales", "bot.comercial", "sales"),
            ("ai_bridge_chatter_web", "user_bot_web", "bot.website", "web"),
        )
        for bridge_xmlid, user_xmlid, login, agent_key in expected:
            bridge = self.env.ref(f"ai_agno_chatter_bots.{bridge_xmlid}")
            user = self.env.ref(f"ai_agno_chatter_bots.{user_xmlid}")
            self.assertEqual(bridge.usage, "chatter")
            self.assertEqual(bridge.payload_type, "chatter")
            self.assertEqual(bridge.result_type, "message")
            self.assertEqual(bridge.result_kind, "immediate")
            self.assertEqual(bridge.auth_type, "token")
            self.assertEqual(bridge.url, f"http://agno:8000/bridge/chatter/{agent_key}")
            self.assertEqual(user.login, login)
            self.assertEqual(user.ai_bridge_id, bridge)
            self.assertTrue(user.has_group("base.group_user"))

        self.assertFalse(
            self.env.ref(
                "ai_agno_chatter_bots.ai_bridge_chatter_architect",
                raise_if_not_found=False,
            )
        )
        self.assertFalse(
            self.env.ref(
                "ai_agno_chatter_bots.user_bot_architect",
                raise_if_not_found=False,
            )
        )

    def test_post_init_applies_token_when_empty(self):
        from ..hooks import post_init_hook

        bridge = self.env.ref("ai_agno_chatter_bots.ai_bridge_chatter_erp")
        bridge.auth_token = False
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_chatter_bots.bridge_auth_token", "test-bridge-token"
        )
        post_init_hook(self.env)
        self.assertEqual(bridge.auth_token, "test-bridge-token")

        bridge.auth_token = "keep-me"
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_chatter_bots.bridge_auth_token", "other-token"
        )
        post_init_hook(self.env)
        self.assertEqual(bridge.auth_token, "keep-me")
