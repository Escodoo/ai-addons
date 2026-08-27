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

    def _require_models(self, *models, reason):
        """Skip when optional apps are missing (local runs without soft deps)."""
        if any(model not in self.env for model in models):  # pragma: no cover
            self.skipTest(reason)

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
        self._require_models(
            "purchase.order",
            "product.product",
            reason="Purchase/Product apps are not installed",
        )
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
        self._require_models("crm.lead", reason="CRM app is not installed")
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
        # Use a base Settings query — Purchase menus are absent on minimal CI DBs.
        resp = self._rpc(
            self._signed_payload(
                method="find_navigation",
                query="settings",
                limit=5,
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertNotIn("error", data["result"])
        self.assertTrue(data["result"].get("results"))

    def test_prepare_sale_order_allowed(self):
        self._require_models(
            "sale.order",
            "product.product",
            reason="Sales/Product apps are not installed",
        )
        product = self.product or self.env[
            "product.product"
        ].create(  # pragma: no cover
            {
                "name": "RPC AI Sale Product",
                "default_code": "RPC-AI-SO",
                "type": "consu",
                "sale_ok": True,
            }
        )
        resp = self._rpc(
            self._signed_payload(
                method="prepare_sale_order",
                partner_ref=self.vendor.id,
                lines=[{"product_id": product.id, "qty": 1}],
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertNotIn("error", data["result"])
        self.assertEqual(data["result"]["open_record"]["model"], "sale.order")

    def test_prepare_helpdesk_ticket_allowed(self):
        self._require_models("helpdesk.ticket", reason="Helpdesk app is not installed")
        resp = self._rpc(
            self._signed_payload(
                method="prepare_helpdesk_ticket",
                name="RPC AI Ticket",
                description="Need help",
                partner_ref=self.vendor.id,
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertNotIn("error", data["result"])
        self.assertEqual(data["result"]["open_record"]["model"], "helpdesk.ticket")

    def test_prepare_timesheet_allowed(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet / Project apps are not installed",
        )
        project = self.env["project.project"].create({"name": "RPC AI Project"})
        AnalyticLine = self.env["account.analytic.line"]
        if (  # pragma: no cover
            "employee_id" in AnalyticLine._fields and "hr.employee" in self.env
        ):
            if not getattr(self.rpc_user, "employee_id", False):  # pragma: no cover
                self.env["hr.employee"].create(
                    {
                        "name": "RPC AI Employee",
                        "user_id": self.rpc_user.id,
                    }
                )
        resp = self._rpc(
            self._signed_payload(
                method="prepare_timesheet",
                project_ref=project.id,
                unit_amount=1.5,
                name="RPC AI timesheet",
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertNotIn("error", data["result"])
        self.assertEqual(
            data["result"]["open_record"]["model"], "account.analytic.line"
        )

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
