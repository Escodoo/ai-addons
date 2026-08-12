# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPreparePurchaseOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "AI Test Vendor Unique XYZ",
                "supplier_rank": 1,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "AI Test Product Unique XYZ",
                "default_code": "AI-TEST-XYZ",
                "type": "consu",
                "purchase_ok": True,
                "list_price": 10.0,
                "standard_price": 5.0,
            }
        )

    def test_prepare_purchase_order_creates_draft(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_id": self.product.id, "qty": 10}],
        )
        self.assertNotIn("error", result)
        self.assertEqual(result["state"], "draft")
        order = self.env["purchase.order"].browse(result["po_id"])
        self.assertTrue(order.exists())
        self.assertEqual(order.partner_id, self.vendor)
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_id, self.product)
        self.assertEqual(order.order_line.product_qty, 10)
        self.assertEqual(result["open_record"]["res_id"], order.id)

    def test_prepare_purchase_order_by_name(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref="AI Test Vendor Unique XYZ",
            lines=[{"product_ref": "AI-TEST-XYZ", "qty": 3}],
        )
        self.assertNotIn("error", result)
        order = self.env["purchase.order"].browse(result["po_id"])
        self.assertEqual(order.partner_id, self.vendor)
        self.assertEqual(order.order_line.product_qty, 3)

    def test_prepare_purchase_order_respects_price_unit(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[
                {
                    "product_id": self.product.id,
                    "qty": 15,
                    "price_unit": 134.0,
                }
            ],
        )
        self.assertNotIn("error", result)
        order = self.env["purchase.order"].browse(result["po_id"])
        self.assertEqual(order.order_line.price_unit, 134.0)
        self.assertEqual(result["lines_summary"][0]["price_unit"], 134.0)

    def test_prepare_purchase_order_missing_vendor(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=None,
            lines=[{"product_id": self.product.id, "qty": 1}],
        )
        self.assertEqual(result.get("error"), "missing_vendor")

    def test_prepare_purchase_order_ambiguous_product(self):
        self.env["product.product"].create(
            {
                "name": "AI Ambiguous Widget Alpha",
                "purchase_ok": True,
                "type": "consu",
            }
        )
        self.env["product.product"].create(
            {
                "name": "AI Ambiguous Widget Beta",
                "purchase_ok": True,
                "type": "consu",
            }
        )
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_ref": "AI Ambiguous Widget", "qty": 1}],
        )
        self.assertEqual(result.get("error"), "product_ambiguous")
        self.assertGreaterEqual(len(result.get("candidates") or []), 2)
