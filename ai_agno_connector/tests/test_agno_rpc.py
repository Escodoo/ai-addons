# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time

from odoo.tests import HttpCase, tagged
from odoo.tools import hmac as odoo_hmac
from odoo.tools import mute_logger

from odoo.addons.ai_agno_connector.controllers.main import HMAC_MAX_AGE
from odoo.addons.ai_agno_connector.models.ai_bridge_execution import HMAC_SCOPE


@tagged("post_install", "-at_install")
class TestAgnoRpc(HttpCase):
    """Security and allowlist checks for /agno/rpc."""

    service_token = "test-agno-service-token"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rpc_user = cls.env.ref("base.user_admin")
        cls._set_icp(
            {
                "ai_agno_connector.service_token": cls.service_token,
                # Double gate off by default (production posture).
                "ai_agno_connector.allow_unsigned_rpc": "",
                "ai_agno_connector.unsigned_user_id": "",
            }
        )

    @classmethod
    def _set_icp(cls, params):
        """Set system parameters visible to HttpCase requests via TestCursor."""
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

    def test_unauthorized_without_token(self):
        url = f"{self.base_url()}/agno/rpc?db={self.env.cr.dbname}"
        resp = self.opener.post(
            url,
            json={"user_id": self.rpc_user.id, "model": "res.partner"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        self.assertEqual(resp.status_code, 401)

    def test_signed_search_count_ok(self):
        resp = self._rpc(self._signed_payload(self.rpc_user))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertIsInstance(data["result"], int)

    def test_expired_hmac_rejected(self):
        payload = self._signed_payload(self.rpc_user)
        payload["user_hmac_ts"] = int(time.time()) - HMAC_MAX_AGE - 10
        payload["user_hmac"] = odoo_hmac(
            self.env(su=True), HMAC_SCOPE, (self.rpc_user.id, payload["user_hmac_ts"])
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "invalid_user")

    def test_unsigned_without_allow_flag_rejected(self):
        self._set_icp(
            {
                "ai_agno_connector.unsigned_user_id": str(self.rpc_user.id),
                "ai_agno_connector.allow_unsigned_rpc": "",
            }
        )
        resp = self._rpc(
            {
                "user_id": self.rpc_user.id,
                "model": "res.partner",
                "method": "search_count",
                "domain": [],
            }
        )
        self.assertEqual(resp.status_code, 403)

    @mute_logger("odoo.addons.ai_agno_connector.controllers.main")
    def test_unsigned_double_gate_accepted(self):
        # Mute the production-warning logged when the unsigned bypass is used.
        self._set_icp(
            {
                "ai_agno_connector.allow_unsigned_rpc": "True",
                "ai_agno_connector.unsigned_user_id": str(self.rpc_user.id),
            }
        )
        try:
            resp = self._rpc(
                {
                    "user_id": self.rpc_user.id,
                    "model": "res.partner",
                    "method": "search_count",
                    "domain": [],
                }
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("result", resp.json())
        finally:
            # Restore production posture for later tests / residual DB state.
            self._set_icp(
                {
                    "ai_agno_connector.allow_unsigned_rpc": "",
                    "ai_agno_connector.unsigned_user_id": "",
                }
            )

    def test_method_not_allowed(self):
        payload = self._signed_payload(
            self.rpc_user, method="create", values={"name": "X"}
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("error"), "method_not_allowed")

    def test_blocked_model(self):
        payload = self._signed_payload(
            self.rpc_user, model="res.users", method="search_count", domain=[]
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "model_not_allowed")

    def test_blocked_fields_filtered(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="search_read",
            model="res.partner",
            domain=[],
            fields=["name", "password", "signup_token"],
            limit=1,
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        for row in data["result"]:
            self.assertNotIn("password", row)
            self.assertNotIn("signup_token", row)

    def test_blocked_domain_field(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="search_count",
            domain=[("signup_token", "!=", False)],
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "blocked_domain_field")

    def test_blocked_domain_traversal(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="search_count",
            domain=[("create_uid.login", "=", "admin")],
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "blocked_domain_model")

    def test_relational_id_filter_on_blocked_comodel_allowed(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="search_count",
            domain=[("create_uid", "=", self.rpc_user.id)],
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("result", resp.json())

    def test_invalid_domain_rejected(self):
        payload = self._signed_payload(
            self.rpc_user, method="search_count", domain="name"
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("error"), "invalid_domain")

    def test_ir_prefix_blocked(self):
        payload = self._signed_payload(
            self.rpc_user, model="ir.ui.menu", method="search_count", domain=[]
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "model_not_allowed")

    def test_extra_blocked_models_icp(self):
        self._set_icp({"ai_agno_connector.extra_blocked_models": "res.partner"})
        try:
            payload = self._signed_payload(self.rpc_user)
            resp = self._rpc(payload)
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json().get("error"), "model_not_allowed")
        finally:
            self._set_icp({"ai_agno_connector.extra_blocked_models": ""})

    def test_tools_catalog_requires_token(self):
        url = f"{self.base_url()}/agno/tools?db={self.env.cr.dbname}"
        resp = self.opener.get(url, timeout=30)
        self.assertEqual(resp.status_code, 401)

    def test_read_group_partners(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="read_group",
            model="res.partner",
            domain=[],
            groupby=["is_company"],
            fields=[],
            limit=10,
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("result", data)
        self.assertIsInstance(data["result"], list)

    def test_read_group_requires_groupby(self):
        payload = self._signed_payload(
            self.rpc_user,
            method="read_group",
            model="res.partner",
            domain=[],
            groupby=[],
            fields=[],
        )
        resp = self._rpc(payload)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("error"), "invalid_params")

    def test_tools_catalog_ok(self):
        url = f"{self.base_url()}/agno/tools?db={self.env.cr.dbname}"
        resp = self.opener.get(url, headers=self._headers(), timeout=30)
        self.assertEqual(resp.status_code, 200)
        tools = resp.json().get("tools")
        self.assertIsInstance(tools, list)

    def test_hmac_max_age_icp(self):
        self._set_icp({"ai_agno_connector.hmac_max_age": "5"})
        try:
            payload = self._signed_payload(self.rpc_user)
            payload["user_hmac_ts"] = int(time.time()) - 10
            payload["user_hmac"] = odoo_hmac(
                self.env(su=True),
                HMAC_SCOPE,
                (self.rpc_user.id, payload["user_hmac_ts"]),
            )
            resp = self._rpc(payload)
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json().get("error"), "invalid_user")
        finally:
            self._set_icp({"ai_agno_connector.hmac_max_age": ""})

    def test_spec_tool_kwargs_uses_res_model(self):
        from ..controllers.main import spec_tool_kwargs

        kwargs = spec_tool_kwargs(
            "ai.assistant",
            ("model", "res_id"),
            {
                "model": "ai.assistant",
                "method": "get_record_context",
                "res_model": "res.partner",
                "res_id": 7,
            },
        )
        self.assertEqual(kwargs["model"], "res.partner")
        self.assertEqual(kwargs["res_id"], 7)
