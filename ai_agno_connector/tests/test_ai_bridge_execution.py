# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import hmac as odoo_hmac

from odoo.addons.ai_agno_connector.models.ai_bridge_execution import HMAC_SCOPE


@tagged("post_install", "-at_install")
class TestAgnoBridgeExecution(TransactionCase):
    """Coverage for HMAC signing scoped to the agno provider."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Agno Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
                "result_kind": "immediate",
                "result_type": "none",
                "provider": "agno",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner"})

    def _create_execution(self, bridge=None):
        bridge = bridge or self.bridge
        return self.env["ai.bridge.execution"].create(
            {
                "ai_bridge_id": bridge.id,
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.partner.id,
            }
        )

    def _mock_ok_response(self, payload=None):
        response = mock.Mock()
        response.status_code = 200
        response.content = b'{"ok": true}'
        response.json.return_value = payload if payload is not None else {"ok": True}
        response.raise_for_status = mock.Mock()
        return response

    def test_add_extra_payload_fields_signs_user(self):
        execution = self._create_execution()
        payload = execution._add_extra_payload_fields({})
        odoo_meta = payload["_odoo"]
        self.assertEqual(odoo_meta["user_id"], self.env.user.id)
        self.assertIn("user_hmac", odoo_meta)
        self.assertIn("user_hmac_ts", odoo_meta)
        expected = odoo_hmac(
            self.env(su=True),
            HMAC_SCOPE,
            (odoo_meta["user_id"], odoo_meta["user_hmac_ts"]),
        )
        self.assertEqual(odoo_meta["user_hmac"], expected)
        self.assertIn("db_hash", odoo_meta)

    def test_add_extra_payload_fields_skips_generic_provider(self):
        other = self.bridge.copy({"name": "Third Party", "provider": "generic"})
        execution = self._create_execution(bridge=other)
        payload = execution._add_extra_payload_fields({})
        odoo_meta = payload["_odoo"]
        self.assertEqual(odoo_meta["user_id"], self.env.user.id)
        self.assertNotIn("user_hmac", odoo_meta)
        self.assertNotIn("user_hmac_ts", odoo_meta)

    def test_execute_sends_hmac(self):
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_ok_response()
            execution._execute()
            mock_post.assert_called_once()
            sent = mock_post.call_args.kwargs["json"]
            self.assertIn("user_hmac", sent["_odoo"])
            self.assertIn("user_hmac_ts", sent["_odoo"])
        self.assertEqual(execution.state, "done")
        self.assertIn("user_hmac", execution.payload["_odoo"])

    def test_execute_generic_provider_has_no_hmac(self):
        other = self.bridge.copy({"name": "Third Party", "provider": "generic"})
        execution = self._create_execution(bridge=other)
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_ok_response()
            execution._execute()
            mock_post.assert_called_once()
            sent = mock_post.call_args.kwargs["json"]
            self.assertNotIn("user_hmac", sent["_odoo"])
        self.assertEqual(execution.state, "done")

    def test_execute_error_path(self):
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("connection refused")
            execution._execute()
        self.assertEqual(execution.state, "error")
        self.assertTrue(execution.error)
        self.assertIn("user_hmac", execution.payload["_odoo"])
