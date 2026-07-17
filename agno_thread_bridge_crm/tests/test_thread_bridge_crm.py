# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAgnoThreadBridgeCrm(TransactionCase):
    def test_crm_lead_bridge(self):
        bridge = self.env.ref("agno_thread_bridge_crm.ai_bridge_crm_lead_analysis")
        self.assertEqual(bridge.usage, "thread")
        self.assertEqual(bridge.payload_type, "record")
        self.assertEqual(bridge.result_type, "message")
        self.assertEqual(bridge.url, "http://agno:8000/bridge/odoo")
        self.assertEqual(bridge.model_id.model, "crm.lead")
        self.assertTrue(bridge.field_ids)
        self.assertIn("name", bridge.field_ids.mapped("name"))
        self.assertIn("stage_id", bridge.field_ids.mapped("name"))
