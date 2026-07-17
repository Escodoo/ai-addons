# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAgnoThreadBridgeHelpdesk(TransactionCase):
    def test_helpdesk_ticket_bridge(self):
        bridge = self.env.ref(
            "ai_agno_thread_bridge_helpdesk_mgmt.ai_bridge_helpdesk_ticket_analysis"
        )
        self.assertEqual(bridge.usage, "thread")
        self.assertEqual(bridge.payload_type, "record")
        self.assertEqual(bridge.result_type, "message")
        self.assertEqual(bridge.url, "http://agno:8000/bridge/odoo")
        self.assertEqual(bridge.model_id.model, "helpdesk.ticket")
        self.assertTrue(bridge.field_ids)
        self.assertIn("name", bridge.field_ids.mapped("name"))
        self.assertIn("number", bridge.field_ids.mapped("name"))
