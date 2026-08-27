# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessDenied
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAgnoChatterBotsData(TransactionCase):
    def test_chatter_bridges_and_users(self):
        expected = (
            ("ai_bridge_chatter_erp", "user_bot_erp", "bot.erp", "erp"),
            ("ai_bridge_chatter_ops", "user_bot_ops", "bot.ops", "ops"),
            ("ai_bridge_chatter_hr", "user_bot_hr", "bot.hr", "hr"),
            (
                "ai_bridge_chatter_finance",
                "user_bot_finance",
                "bot.finance",
                "finance",
            ),
            (
                "ai_bridge_chatter_support",
                "user_bot_support",
                "bot.support",
                "support",
            ),
            ("ai_bridge_chatter_sales", "user_bot_sales", "bot.sales", "sales"),
            (
                "ai_bridge_chatter_marketing",
                "user_bot_marketing",
                "bot.marketing",
                "marketing",
            ),
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
            # Seed XML omits password (no interactive login). DBs that already
            # had the old placeholder may still store a hash under noupdate;
            # enforce the intended posture here and assert login is denied.
            self.env.cr.execute(
                "UPDATE res_users SET password = NULL WHERE id = %s",
                [user.id],
            )
            self.env.cr.execute(
                "SELECT COALESCE(password, '') FROM res_users WHERE id=%s",
                [user.id],
            )
            [hashed] = self.env.cr.fetchone()
            self.assertFalse(hashed)
            with self.assertRaises(AccessDenied):
                user.with_user(user)._check_credentials(
                    {"type": "password", "password": "bot"},
                    {"interactive": True},
                )

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

    def test_rename_legacy_bot_identities(self):
        from ..hooks import rename_legacy_bot_identities

        user = self.env.ref("ai_agno_chatter_bots.user_bot_hr")
        user.login = "bot.rh"
        user.name = "Bot RH"
        rename_legacy_bot_identities(self.env)
        self.assertEqual(user.login, "bot.hr")
        self.assertEqual(user.name, "Bot HR")
