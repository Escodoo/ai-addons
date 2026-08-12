# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time
from unittest import mock

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools import hmac as odoo_hmac
from odoo.tools import mute_logger

from odoo.addons.ai_agno_connector.controllers.main import (
    TEXT_TRUNCATE_LIMIT,
    X2MANY_NAMES_LIMIT,
    AgnoRpcController,
    _truncate,
)
from odoo.addons.ai_agno_connector.models.ai_bridge_execution import HMAC_SCOPE


@tagged("post_install", "-at_install")
class TestAgnoRpcCoverage(HttpCase):
    """Extra /agno/rpc branches not covered by the security smoke tests."""

    service_token = "test-agno-service-token"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rpc_user = cls.env.ref("base.user_admin")
        cls._set_icp(
            {
                "ai_agno_connector.service_token": cls.service_token,
                "ai_agno_connector.allow_unsigned_rpc": "",
                "ai_agno_connector.unsigned_user_id": "",
            }
        )
        cls.category = cls.env["res.partner.category"].create({"name": "Agno Cat"})
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "A" * (TEXT_TRUNCATE_LIMIT + 50),
                "comment": "<p>Hello <b>world</b></p>",
                "category_id": [(6, 0, [cls.category.id])],
            }
        )
        cls.empty_partner = cls.env["res.partner"].create(
            {"name": "Empty fields partner"}
        )

    @classmethod
    def _set_icp(cls, params):
        icp = cls.env["ir.config_parameter"].sudo()
        for key, value in params.items():
            icp.set_param(key, value)

    def _headers(self, token=None):
        return {
            "Authorization": f"Bearer {token or self.service_token}",
            "Content-Type": "application/json",
        }

    def _rpc(self, payload, token=None):
        url = f"{self.base_url()}/agno/rpc?db={self.env.cr.dbname}"
        return self.opener.post(
            url,
            json=payload,
            headers=self._headers(token),
            timeout=30,
        )

    def _signed_payload(self, user, **extra):
        timestamp = int(time.time())
        signature = odoo_hmac(self.env(su=True), HMAC_SCOPE, (user.id, timestamp))
        payload = {
            "user_id": user.id,
            "user_hmac": signature,
            "user_hmac_ts": timestamp,
            "model": "res.partner",
            "method": "search_count",
            "domain": [],
        }
        payload.update(extra)
        return payload

    def test_not_configured_without_service_token(self):
        from unittest.mock import patch

        self._set_icp({"ai_agno_connector.service_token": ""})
        try:
            with patch(
                "odoo.addons.ai_agno_connector.token_utils.odoo_config.get",
                return_value="",
            ):
                resp = self._rpc(self._signed_payload(self.rpc_user))
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(resp.json().get("error"), "not_configured")
        finally:
            self._set_icp({"ai_agno_connector.service_token": self.service_token})

    def test_non_integer_user_id_rejected(self):
        payload = self._signed_payload(self.rpc_user)
        payload["user_id"] = str(self.rpc_user.id)
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "invalid_user")

    def test_unknown_user_id_rejected(self):
        missing_id = (
            self.env["res.users"].sudo().search([], order="id desc", limit=1).id
            + 999999
        )
        timestamp = int(time.time())
        payload = {
            "user_id": missing_id,
            "user_hmac": odoo_hmac(
                self.env(su=True), HMAC_SCOPE, (missing_id, timestamp)
            ),
            "user_hmac_ts": timestamp,
            "model": "res.partner",
            "method": "search_count",
            "domain": [],
        }
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "invalid_user")

    def test_inactive_user_rejected(self):
        inactive = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .sudo()
            .create(
                {
                    "name": "Inactive Agno User",
                    "login": "inactive_agno_user@example.com",
                    "active": False,
                    "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
                }
            )
        )
        resp = self._rpc(self._signed_payload(inactive))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "invalid_user")

    def test_unknown_model(self):
        payload = self._signed_payload(
            self.rpc_user, model="agno.missing.model", method="search_count"
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json().get("error"), "unknown_model")

    def test_access_denied(self):
        payload = self._signed_payload(self.rpc_user)
        with mock.patch.object(
            AgnoRpcController, "_dispatch", side_effect=AccessError("denied")
        ):
            resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("error"), "access_denied")

    @mute_logger("odoo.addons.ai_agno_connector.controllers.main")
    def test_server_error(self):
        # Intentionally raises to cover the server_error branch; mute the
        # WARNING so oca_checklog_odoo does not treat it as a CI failure.
        # Exception detail stays in the log; the JSON body is generic.
        payload = self._signed_payload(self.rpc_user)
        with mock.patch.object(
            AgnoRpcController, "_dispatch", side_effect=RuntimeError("boom")
        ):
            resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("error"), "server_error")
        self.assertEqual(data.get("detail"), "Internal error, see server logs.")
        self.assertNotIn("boom", data.get("detail", ""))

    def test_fields_get_filters_blocked_and_binary(self):
        payload = self._signed_payload(
            self.rpc_user, method="fields_get", model="res.partner"
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        fields_data = resp.json()["result"]
        self.assertIn("name", fields_data)
        self.assertNotIn("image_1920", fields_data)
        for name in fields_data:
            lowered = name.lower()
            self.assertFalse(
                any(pattern in lowered for pattern in ("password", "token", "secret"))
            )

    def test_max_records_config_param(self):
        self._set_icp({"ai_agno_connector.max_records": "2"})
        try:
            payload = self._signed_payload(
                self.rpc_user,
                method="search_read",
                fields=["name"],
                limit=50,
                domain=[],
            )
            resp = self._rpc(payload)
            self.assertEqual(resp.status_code, 200)
            self.assertLessEqual(len(resp.json()["result"]), 2)
        finally:
            self._set_icp({"ai_agno_connector.max_records": ""})

    def test_search_read_formats_special_fields(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="search_read",
            domain=[("id", "=", self.partner.id)],
            fields=["name", "comment", "write_date", "category_id"],
            limit=1,
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()["result"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row["name"].endswith("..."))
        self.assertLessEqual(len(row["name"]), TEXT_TRUNCATE_LIMIT)
        self.assertNotIn("<", row["comment"])
        self.assertIsInstance(row["write_date"], str)
        self.assertRegex(row["write_date"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(
            row["category_id"], [[self.category.id, self.category.display_name]]
        )

    def test_search_read_empty_values_and_empty_result(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="search_read",
            domain=[("id", "=", self.empty_partner.id)],
            fields=["name", "comment", "category_id"],
            limit=1,
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()["result"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Empty fields partner")

        empty_payload = self._signed_payload(
            self.rpc_user,
            method="search_read",
            domain=[("id", "=", 0)],
            fields=["name", "write_date"],
            limit=1,
        )
        empty_resp = self._rpc(empty_payload)
        self.assertEqual(empty_resp.status_code, 200)
        self.assertEqual(empty_resp.json()["result"], [])


@tagged("post_install", "-at_install")
class TestAgnoRpcFormatters(HttpCase):
    """Direct coverage for monetary / x2many edge helpers."""

    service_token = "test-agno-service-token"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._set_icp({"ai_agno_connector.service_token": cls.service_token})

    @classmethod
    def _set_icp(cls, params):
        icp = cls.env["ir.config_parameter"].sudo()
        for key, value in params.items():
            icp.set_param(key, value)

    def test_truncate_helper(self):
        self.assertEqual(_truncate(123), 123)
        self.assertEqual(_truncate("short"), "short")
        long_value = "x" * (TEXT_TRUNCATE_LIMIT + 10)
        truncated = _truncate(long_value)
        self.assertTrue(truncated.endswith("..."))
        self.assertEqual(len(truncated), TEXT_TRUNCATE_LIMIT)

    def test_format_monetary_with_and_without_currency(self):
        controller = AgnoRpcController()
        currency = self.env.ref("base.USD")
        field = mock.Mock()
        field.get_currency_field.return_value = "currency_id"

        record = mock.MagicMock()
        record._fields = {"currency_id": True}
        record.__getitem__.return_value = currency
        record.env = self.env
        formatted = controller._format_monetary(record, field, 12.5)
        self.assertIsInstance(formatted, str)
        self.assertNotEqual(formatted, 12.5)

        self.assertEqual(controller._format_monetary(None, field, 12.5), 12.5)

        record_no_currency = mock.MagicMock()
        record_no_currency._fields = {}
        self.assertEqual(
            controller._format_monetary(record_no_currency, field, 12.5), 12.5
        )

    def test_format_x2many_ok_limit_and_access_error(self):
        controller = AgnoRpcController()
        category = self.env["res.partner.category"].create({"name": "X2"})
        field = mock.Mock()
        field.comodel_name = "res.partner.category"

        pairs = controller._format_x2many(self.env, field, [category.id])
        self.assertEqual(pairs, [[category.id, category.display_name]])

        many_ids = list(range(1, X2MANY_NAMES_LIMIT + 2))
        capped = controller._format_x2many(self.env, field, many_ids)
        self.assertEqual(capped, {"count": len(many_ids)})

        browse_result = mock.Mock()
        browse_result.mapped.side_effect = AccessError("no names")
        with mock.patch.object(
            type(self.env["res.partner.category"]),
            "browse",
            return_value=browse_result,
        ):
            denied = controller._format_x2many(self.env, field, [category.id])
        self.assertEqual(denied, {"count": 1})

    def test_format_rows_monetary_branch(self):
        controller = AgnoRpcController()
        currency = self.env.ref("base.USD")
        monetary_field = mock.Mock()
        monetary_field.type = "monetary"
        monetary_field.get_currency_field.return_value = "currency_id"

        record = mock.Mock()
        record.id = 1
        record._fields = {"currency_id": True}
        record.__getitem__ = mock.Mock(return_value=currency)
        record.env = self.env

        records = mock.MagicMock()
        records._fields = {"amount": monetary_field}
        records.browse.return_value = [record]
        records.env = self.env

        rows = [{"id": 1, "amount": 10.0}]
        formatted = controller._format_rows_for_llm(records, rows, ["amount"])
        self.assertEqual(len(formatted), 1)
        self.assertIsInstance(formatted[0]["amount"], str)
        records.browse.assert_called_once_with([1])

    def test_dispatch_assistant_typed_helpers(self):
        """Cover typed prepare_* / find_navigation dispatch branches."""
        controller = AgnoRpcController()
        records = mock.MagicMock()
        records.prepare_purchase_order.return_value = {"po_id": 42, "state": "draft"}
        records.prepare_opportunity.return_value = {"opportunity_id": 1}
        records.prepare_helpdesk_ticket.return_value = {"ticket_id": 2}
        records.prepare_sale_order.return_value = {"so_id": 3}
        records.prepare_timesheet.return_value = {"timesheet_id": 4}
        records.find_navigation.return_value = {"results": [{"name": "Purchase"}]}

        po_result = controller._dispatch(
            records,
            "prepare_purchase_order",
            {
                "vendor_ref": 7,
                "notes": "rush",
                # omit lines to exercise the ``or []`` default
            },
        )
        records.prepare_purchase_order.assert_called_once_with(
            vendor_ref=7,
            lines=[],
            notes="rush",
        )
        self.assertEqual(po_result["po_id"], 42)

        controller._dispatch(
            records,
            "prepare_opportunity",
            {"name": "Deal", "partner_ref": 1},
        )
        records.prepare_opportunity.assert_called_once_with(
            name="Deal",
            partner_ref=1,
            description=None,
            expected_revenue=None,
        )
        controller._dispatch(
            records,
            "prepare_helpdesk_ticket",
            {"name": "Outage", "description": "<p>down</p>"},
        )
        records.prepare_helpdesk_ticket.assert_called_once_with(
            name="Outage",
            description="<p>down</p>",
            partner_ref=None,
            team_ref=None,
        )
        controller._dispatch(
            records,
            "prepare_sale_order",
            {"partner_ref": 9},
        )
        records.prepare_sale_order.assert_called_once_with(
            partner_ref=9,
            lines=[],
            notes=None,
        )
        controller._dispatch(
            records,
            "prepare_timesheet",
            {"project_ref": 5, "unit_amount": 2.5},
        )
        records.prepare_timesheet.assert_called_once_with(
            project_ref=5,
            task_ref=None,
            unit_amount=2.5,
            name=None,
            date=None,
        )

        nav_result = controller._dispatch(
            records,
            "find_navigation",
            {"query": "purchase"},
        )
        records.find_navigation.assert_called_once_with(query="purchase", limit=8)
        self.assertEqual(nav_result["results"][0]["name"], "Purchase")

        controller._dispatch(
            records,
            "find_navigation",
            {"query": "crm", "limit": 3},
        )
        records.find_navigation.assert_called_with(query="crm", limit=3)
