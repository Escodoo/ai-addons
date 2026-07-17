# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Resolve Agno tokens from ICP (override) or odoo.conf (conf.d expansion)."""

from odoo.tools import config as odoo_config

CONFIG_BRIDGE_AUTH_TOKEN = "agno_bridge_auth_token"
CONFIG_SERVICE_TOKEN = "agno_service_token"

ICP_SERVICE_TOKEN = "ai_agno_connector.service_token"


def ensure_token(env, icp_key, config_key):
    """Return a token: ICP override wins, else odoo.conf from conf.d.

    Does not write secrets into ir.config_parameter.
    """
    value = (env["ir.config_parameter"].sudo().get_param(icp_key) or "").strip()
    if value:
        return value
    return (odoo_config.get(config_key) or "").strip()
