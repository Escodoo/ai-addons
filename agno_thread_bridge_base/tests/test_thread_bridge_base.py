# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..hooks import ICP_KEY, apply_auth_token, post_init_hook, set_bridge_fields


@tagged("post_install", "-at_install")
class TestAgnoThreadBridgeBase(TransactionCase):
    def test_partner_bridge(self):
        bridge = self.env.ref("agno_thread_bridge_base.ai_bridge_partner_analysis")
        self.assertEqual(bridge.usage, "thread")
        self.assertEqual(bridge.payload_type, "record")
        self.assertEqual(bridge.result_type, "message")
        self.assertEqual(bridge.result_kind, "immediate")
        self.assertEqual(bridge.auth_type, "token")
        self.assertEqual(bridge.url, "http://agno:8000/bridge/odoo")
        self.assertEqual(bridge.model_id.model, "res.partner")
        self.assertTrue(bridge.field_ids)
        self.assertIn("name", bridge.field_ids.mapped("name"))

    def test_helpers_apply_token_and_fields(self):
        bridge = self.env.ref("agno_thread_bridge_base.ai_bridge_partner_analysis")
        bridge.auth_token = False
        self.env["ir.config_parameter"].sudo().set_param(ICP_KEY, "test-token")
        apply_auth_token(
            self.env, ["agno_thread_bridge_base.ai_bridge_partner_analysis"]
        )
        self.assertEqual(bridge.auth_token, "test-token")

        bridge.auth_token = "keep-me"
        self.env["ir.config_parameter"].sudo().set_param(ICP_KEY, "other")
        apply_auth_token(
            self.env, ["agno_thread_bridge_base.ai_bridge_partner_analysis"]
        )
        self.assertEqual(bridge.auth_token, "keep-me")

        set_bridge_fields(
            self.env,
            "agno_thread_bridge_base.ai_bridge_partner_analysis",
            "res.partner",
            ("name", "email"),
        )
        self.assertEqual(set(bridge.field_ids.mapped("name")), {"name", "email"})

        post_init_hook(self.env)
        self.assertTrue(bridge.field_ids)
