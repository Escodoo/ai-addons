# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time

from odoo.tests import HttpCase, tagged
from odoo.tools import hmac as odoo_hmac

from odoo.addons.ai_agno_connector.models.ai_bridge_execution import HMAC_SCOPE


@tagged("post_install", "-at_install")
class TestAgnoRpcAssistant(HttpCase):
    """Gateway allowlist checks for ai.assistant helpers."""

    service_token = "test-agno-service-token-assistant"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rpc_user = cls.env.ref("base.user_admin")
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.rpc_user.groups_id = [(4, cls.ai_group.id)]
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_connector.service_token", cls.service_token
        )
        cls.has_purchase = "purchase.order" in cls.env and "product.product" in cls.env
        vendor_vals = {"name": "RPC AI Vendor"}
        if "supplier_rank" in cls.env["res.partner"]._fields:
            vendor_vals["supplier_rank"] = 1
        cls.vendor = cls.env["res.partner"].create(vendor_vals)
        cls.product = None
        if cls.has_purchase:
            cls.product = cls.env["product.product"].create(
                {
                    "name": "RPC AI Product",
                    "default_code": "RPC-AI-PROD",
                    "type": "consu",
                    "purchase_ok": True,
                    "standard_price": 2.0,
                }
            )

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.service_token}",
            "Content-Type": "application/json",
        }

    def _signed_payload(self, **extra):
        timestamp = int(time.time())
        signature = odoo_hmac(
            self.env(su=True), HMAC_SCOPE, (self.rpc_user.id, timestamp)
        )
        payload = {
            "user_id": self.rpc_user.id,
            "user_hmac": signature,
            "user_hmac_ts": timestamp,
            "model": "ai.assistant",
            "method": "prepare_purchase_order",
        }
        payload.update(extra)
        return payload

    def _rpc(self, payload):
        url = f"{self.base_url()}/agno/rpc?db={self.env.cr.dbname}"
        return self.opener.post(url, json=payload, headers=self._headers(), timeout=30)

    def test_prepare_purchase_order_allowed(self):
        if not self.has_purchase:
            self.skipTest("Purchase/Product apps are not installed")
        resp = self._rpc(
            self._signed_payload(
                vendor_ref=self.vendor.id,
                lines=[{"product_id": self.product.id, "qty": 2}],
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertNotIn("error", data["result"])
        self.assertEqual(data["result"]["state"], "draft")

    def test_prepare_opportunity_allowed(self):
        if "crm.lead" not in self.env:
            self.skipTest("CRM app is not installed")
        resp = self._rpc(
            self._signed_payload(
                method="prepare_opportunity",
                name="RPC AI Opportunity",
                partner_ref=self.vendor.id,
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertNotIn("error", data["result"])
        self.assertEqual(data["result"]["open_record"]["model"], "crm.lead")

    def test_find_navigation_allowed(self):
        resp = self._rpc(
            self._signed_payload(
                method="find_navigation",
                query="purchase",
                limit=5,
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertNotIn("error", data["result"])
        self.assertTrue(data["result"].get("results"))

    def test_generic_create_still_blocked(self):
        resp = self._rpc(
            self._signed_payload(
                model="purchase.order",
                method="create",
                values={"partner_id": self.vendor.id},
            )
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("error"), "method_not_allowed")
