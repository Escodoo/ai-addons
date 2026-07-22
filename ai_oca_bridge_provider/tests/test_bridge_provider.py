# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestBridgeProvider(TransactionCase):
    def test_provider_defaults_to_generic(self):
        bridge = self.env["ai.bridge"].create(
            {
                "name": "Provider Test Bridge",
                "model_id": self.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
                "result_kind": "immediate",
                "result_type": "none",
            }
        )
        self.assertEqual(bridge.provider, "generic")
