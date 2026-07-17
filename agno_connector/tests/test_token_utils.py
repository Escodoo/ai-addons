# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.agno_connector.token_utils import ensure_token


@tagged("post_install", "-at_install")
class TestAgnoTokenUtils(TransactionCase):
    def test_icp_wins_over_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "agno_connector.service_token", "from-icp"
        )
        with patch(
            "odoo.addons.agno_connector.token_utils.odoo_config.get",
            return_value="from-conf",
        ):
            token = ensure_token(
                self.env, "agno_connector.service_token", "agno_service_token"
            )
        self.assertEqual(token, "from-icp")

    def test_falls_back_to_odoo_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "agno_connector.service_token", ""
        )
        with patch(
            "odoo.addons.agno_connector.token_utils.odoo_config.get",
            return_value="from-conf",
        ):
            token = ensure_token(
                self.env, "agno_connector.service_token", "agno_service_token"
            )
        self.assertEqual(token, "from-conf")

    def test_empty_when_neither_set(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "agno_connector.service_token", False
        )
        with patch(
            "odoo.addons.agno_connector.token_utils.odoo_config.get",
            return_value=False,
        ):
            token = ensure_token(
                self.env, "agno_connector.service_token", "agno_service_token"
            )
        self.assertEqual(token, "")
