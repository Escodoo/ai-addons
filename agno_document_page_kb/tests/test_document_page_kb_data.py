# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAgnoDocumentPageKbData(TransactionCase):
    def test_post_init_applies_token_when_empty(self):
        from ..hooks import post_init_hook

        bridge = self.env.ref("agno_document_page_kb.ai_bridge_support_create")
        bridge.auth_token = False
        self.env["ir.config_parameter"].sudo().set_param(
            "agno_document_page_kb.bridge_auth_token", "test-bridge-token"
        )
        post_init_hook(self.env)
        self.assertEqual(bridge.auth_token, "test-bridge-token")

        bridge.auth_token = "keep-me"
        self.env["ir.config_parameter"].sudo().set_param(
            "agno_document_page_kb.bridge_auth_token", "other-token"
        )
        post_init_hook(self.env)
        self.assertEqual(bridge.auth_token, "keep-me")
