# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import SkipTest, mock

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestPreparePurchaseOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "purchase.order" not in cls.env or "product.product" not in cls.env:
            # Soft dependency: skip when Purchase/Product are not installed.
            raise SkipTest("Purchase/Product apps are not installed")
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]
        vendor_vals = {
            "name": "AI Test Vendor Unique XYZ",
            "is_company": True,
        }
        if "supplier_rank" in cls.env["res.partner"]._fields:
            vendor_vals["supplier_rank"] = 1
        cls.vendor = cls.env["res.partner"].create(vendor_vals)
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

    def test_prepare_purchase_order_with_notes(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_id": self.product.id, "qty": 1}],
            notes="  Please deliver ASAP  ",
        )
        self.assertNotIn("error", result)
        order = self.env["purchase.order"].browse(result["po_id"])
        self.assertIn("Please deliver ASAP", str(order.notes or ""))

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

    def test_prepare_purchase_order_seller_price(self):
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "price": 77.0,
                "min_qty": 1.0,
            }
        )
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_id": self.product.id, "qty": 2}],
        )
        self.assertNotIn("error", result)
        order = self.env["purchase.order"].browse(result["po_id"])
        self.assertEqual(order.order_line.price_unit, 77.0)

    def test_prepare_purchase_order_missing_vendor(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=None,
            lines=[{"product_id": self.product.id, "qty": 1}],
        )
        self.assertEqual(result.get("error"), "missing_vendor")

    def test_prepare_purchase_order_vendor_not_found_by_id(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=999999999,
            lines=[{"product_id": self.product.id, "qty": 1}],
        )
        self.assertEqual(result.get("error"), "vendor_not_found")

    def test_prepare_purchase_order_vendor_not_found_by_name(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref="Definitely Missing Vendor ZZZ999",
            lines=[{"product_id": self.product.id, "qty": 1}],
        )
        self.assertEqual(result.get("error"), "vendor_not_found")

    def test_prepare_purchase_order_vendor_fallback_display_name(self):
        contact_vals = {
            "name": "AI Contact Only Display Unique",
            "is_company": False,
        }
        if "supplier_rank" in self.env["res.partner"]._fields:
            contact_vals["supplier_rank"] = 0
        contact = self.env["res.partner"].create(contact_vals)
        result = self.Assistant.prepare_purchase_order(
            vendor_ref="AI Contact Only Display Unique",
            lines=[{"product_id": self.product.id, "qty": 1}],
        )
        self.assertNotIn("error", result)
        order = self.env["purchase.order"].browse(result["po_id"])
        self.assertEqual(order.partner_id, contact)

    def test_prepare_purchase_order_vendor_ambiguous(self):
        for suffix in ("Alpha", "Beta"):
            vals = {
                "name": f"AI Ambiguous Vendor {suffix}",
                "is_company": True,
            }
            if "supplier_rank" in self.env["res.partner"]._fields:
                vals["supplier_rank"] = 1
            self.env["res.partner"].create(vals)
        result = self.Assistant.prepare_purchase_order(
            vendor_ref="AI Ambiguous Vendor",
            lines=[{"product_id": self.product.id, "qty": 1}],
        )
        self.assertEqual(result.get("error"), "vendor_ambiguous")
        self.assertGreaterEqual(len(result.get("candidates") or []), 2)

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

    def test_prepare_purchase_order_product_exact_default_code(self):
        # Both match name ilike the query; only one has matching default_code.
        self.env["product.product"].create(
            {
                "name": "Widget AI-SHARED-TOKEN Alpha",
                "default_code": "OTHER-CODE-1",
                "purchase_ok": True,
                "type": "consu",
            }
        )
        exact = self.env["product.product"].create(
            {
                "name": "Widget AI-SHARED-TOKEN Beta",
                "default_code": "AI-SHARED-TOKEN",
                "purchase_ok": True,
                "type": "consu",
            }
        )
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_ref": "AI-SHARED-TOKEN", "qty": 1}],
        )
        self.assertNotIn("error", result)
        order = self.env["purchase.order"].browse(result["po_id"])
        self.assertEqual(order.order_line.product_id, exact)

    def test_prepare_purchase_order_product_not_found(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_ref": 999999999, "qty": 1}],
        )
        self.assertEqual(result.get("error"), "product_not_found")
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_ref": "Missing Product ZZZ999", "qty": 1}],
        )
        self.assertEqual(result.get("error"), "product_not_found")

    def test_prepare_purchase_order_missing_product_and_lines(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=None,
        )
        self.assertEqual(result.get("error"), "missing_lines")
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_ref": "", "qty": 1}],
        )
        self.assertEqual(result.get("error"), "missing_product")
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=["skip-me"],
        )
        self.assertEqual(result.get("error"), "missing_lines")

    def test_prepare_purchase_order_invalid_qty_and_price(self):
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_id": self.product.id, "qty": 0}],
        )
        self.assertEqual(result.get("error"), "invalid_qty")
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[{"product_id": self.product.id, "qty": "abc"}],
        )
        self.assertEqual(result.get("error"), "invalid_qty")
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[
                {
                    "product_id": self.product.id,
                    "qty": 1,
                    "price_unit": "not-a-number",
                }
            ],
        )
        self.assertEqual(result.get("error"), "invalid_price")
        result = self.Assistant.prepare_purchase_order(
            vendor_ref=self.vendor.id,
            lines=[
                {
                    "product_id": self.product.id,
                    "qty": 1,
                    "price_unit": -5,
                }
            ],
        )
        self.assertEqual(result.get("error"), "invalid_price")

    def test_prepare_purchase_order_unavailable(self):
        # Use ``new=`` (not MagicMock): patching ``__contains__`` with a mock
        # breaks the ``in`` operator arity.
        with mock.patch.object(
            type(self.env),
            "__contains__",
            new=lambda _env, model: model != "purchase.order",
        ):
            result = self.Assistant.prepare_purchase_order(
                vendor_ref=self.vendor.id,
                lines=[{"product_id": self.product.id, "qty": 1}],
            )
        self.assertEqual(result.get("error"), "purchase_unavailable")

    def test_prepare_purchase_order_create_errors(self):
        PurchaseOrder = type(self.env["purchase.order"])
        with mock.patch.object(
            PurchaseOrder,
            "create",
            side_effect=AccessError("no access"),
        ):
            result = self.Assistant.prepare_purchase_order(
                vendor_ref=self.vendor.id,
                lines=[{"product_id": self.product.id, "qty": 1}],
            )
        self.assertEqual(result.get("error"), "access_denied")

        with mock.patch.object(
            PurchaseOrder,
            "create",
            side_effect=UserError("invalid"),
        ):
            result = self.Assistant.prepare_purchase_order(
                vendor_ref=self.vendor.id,
                lines=[{"product_id": self.product.id, "qty": 1}],
            )
        self.assertEqual(result.get("error"), "validation_error")

        with mock.patch.object(
            PurchaseOrder,
            "create",
            side_effect=ValidationError("bad data"),
        ):
            result = self.Assistant.prepare_purchase_order(
                vendor_ref=self.vendor.id,
                lines=[{"product_id": self.product.id, "qty": 1}],
            )
        self.assertEqual(result.get("error"), "validation_error")

        with (
            mock.patch.object(
                PurchaseOrder,
                "create",
                side_effect=RuntimeError("unexpected"),
            ),
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant_drafts"),
        ):
            result = self.Assistant.prepare_purchase_order(
                vendor_ref=self.vendor.id,
                lines=[{"product_id": self.product.id, "qty": 1}],
            )
        self.assertEqual(result.get("error"), "create_failed")
