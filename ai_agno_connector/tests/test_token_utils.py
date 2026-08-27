# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.ai_agno_connector.token_utils import (
    DEFAULT_AGNO_BASE_URL,
    apply_auth_token,
    apply_bridge_base_url,
    ensure_bridge_token,
    ensure_token,
    get_agno_base_url,
)


@tagged("post_install", "-at_install")
class TestAgnoTokenUtils(TransactionCase):
    def test_icp_wins_over_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_connector.service_token", "from-icp"
        )
        with patch(
            "odoo.addons.ai_agno_connector.token_utils.odoo_config.get",
            return_value="from-conf",
        ):
            token = ensure_token(
                self.env, "ai_agno_connector.service_token", "agno_service_token"
            )
        self.assertEqual(token, "from-icp")

    def test_falls_back_to_odoo_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_connector.service_token", ""
        )
        with patch(
            "odoo.addons.ai_agno_connector.token_utils.odoo_config.get",
            return_value="from-conf",
        ):
            token = ensure_token(
                self.env, "ai_agno_connector.service_token", "agno_service_token"
            )
        self.assertEqual(token, "from-conf")

    def test_empty_when_neither_set(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_connector.service_token", False
        )
        with patch(
            "odoo.addons.ai_agno_connector.token_utils.odoo_config.get",
            return_value=False,
        ):
            token = ensure_token(
                self.env, "ai_agno_connector.service_token", "agno_service_token"
            )
        self.assertEqual(token, "")

    def test_ensure_bridge_token_prefers_module_then_canonical(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("ai_agno_chatter_bots.bridge_auth_token", "module-token")
        icp.set_param("ai_agno_connector.bridge_auth_token", "canonical-token")
        self.assertEqual(
            ensure_bridge_token(self.env, "ai_agno_chatter_bots.bridge_auth_token"),
            "module-token",
        )
        icp.set_param("ai_agno_chatter_bots.bridge_auth_token", "")
        self.assertEqual(ensure_bridge_token(self.env), "canonical-token")

    def test_apply_auth_token_and_base_url(self):
        bridge = self.env["ai.bridge"].create(
            {
                "name": "Token URL Bridge",
                "model_id": self.env.ref("base.model_res_partner").id,
                "url": "http://agno:8000/bridge/demo",
                "auth_type": "none",
                "usage": "none",
                "result_kind": "immediate",
                "result_type": "none",
            }
        )
        xmlid = "ai_agno_connector.test_token_url_bridge"
        self.env["ir.model.data"].create(
            {
                "name": "test_token_url_bridge",
                "module": "ai_agno_connector",
                "model": "ai.bridge",
                "res_id": bridge.id,
            }
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_connector.bridge_auth_token", "shared-token"
        )
        apply_auth_token(self.env, [xmlid])
        self.assertEqual(bridge.auth_token, "shared-token")
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_connector.base_url", "https://agno.example"
        )
        apply_bridge_base_url(self.env, [xmlid])
        self.assertEqual(bridge.url, "https://agno.example/bridge/demo")
        self.assertEqual(get_agno_base_url(self.env), "https://agno.example")
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_connector.base_url", ""
        )
        self.assertEqual(get_agno_base_url(self.env), DEFAULT_AGNO_BASE_URL)
