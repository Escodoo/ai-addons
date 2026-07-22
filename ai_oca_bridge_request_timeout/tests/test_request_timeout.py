# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRequestTimeout(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Timeout Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
                "result_kind": "immediate",
                "result_type": "none",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Timeout Partner"})

    def _create_execution(self):
        return self.env["ai.bridge.execution"].create(
            {
                "ai_bridge_id": self.bridge.id,
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.partner.id,
            }
        )

    def _mock_ok_response(self):
        response = mock.Mock()
        response.status_code = 200
        response.content = b'{"ok": true}'
        response.json.return_value = {"ok": True}
        response.raise_for_status = mock.Mock()
        return response

    def test_without_field_uses_upstream_timeout(self):
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_ok_response()
            execution._execute()
            mock_post.assert_called_once()
            self.assertEqual(mock_post.call_args.kwargs["timeout"], 30)
        self.assertEqual(execution.state, "done")

    def test_field_overrides_timeout(self):
        self.bridge.request_timeout = 77
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_ok_response()
            execution._execute()
            mock_post.assert_called_once()
            self.assertEqual(mock_post.call_args.kwargs["timeout"], 77)
        self.assertEqual(execution.state, "done")

    def test_explicit_kwarg_wins_over_field(self):
        self.bridge.request_timeout = 77
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_ok_response()
            execution._execute(timeout=45)
            mock_post.assert_called_once()
            self.assertEqual(mock_post.call_args.kwargs["timeout"], 45)
        self.assertEqual(execution.state, "done")

    def test_error_path_with_field(self):
        self.bridge.request_timeout = 77
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("connection refused")
            execution._execute()
        self.assertEqual(execution.state, "error")
        self.assertTrue(execution.error)
