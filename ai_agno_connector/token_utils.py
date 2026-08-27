# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Resolve Agno tokens from ICP (override) or odoo.conf (conf.d expansion)."""

from odoo.tools import config as odoo_config

CONFIG_BRIDGE_AUTH_TOKEN = "agno_bridge_auth_token"
CONFIG_SERVICE_TOKEN = "agno_service_token"
CONFIG_AGNO_BASE_URL = "agno_base_url"

ICP_SERVICE_TOKEN = "ai_agno_connector.service_token"
ICP_BRIDGE_AUTH_TOKEN = "ai_agno_connector.bridge_auth_token"
ICP_AGNO_BASE_URL = "ai_agno_connector.base_url"

DEFAULT_AGNO_BASE_URL = "http://agno:8000"


def ensure_token(env, icp_key, config_key):
    """Return a token: ICP override wins, else odoo.conf from conf.d.

    Does not write secrets into ir.config_parameter.
    """
    value = (env["ir.config_parameter"].sudo().get_param(icp_key) or "").strip()
    if value:
        return value
    return (odoo_config.get(config_key) or "").strip()


def ensure_bridge_token(env, *extra_icp_keys):
    """Resolve the shared Agno bridge auth token.

    Extra module ICPs win, then the canonical
    ``ai_agno_connector.bridge_auth_token``, then odoo.conf.
    """
    for key in extra_icp_keys + (ICP_BRIDGE_AUTH_TOKEN,):
        value = (env["ir.config_parameter"].sudo().get_param(key) or "").strip()
        if value:
            return value
    return (odoo_config.get(CONFIG_BRIDGE_AUTH_TOKEN) or "").strip()


def apply_auth_token(env, bridge_xmlids, *extra_icp_keys):
    """Copy the shared token onto bridges that still have an empty auth_token."""
    token = ensure_bridge_token(env, *extra_icp_keys)
    if not token:
        return
    for xmlid in bridge_xmlids:
        bridge = env.ref(xmlid, raise_if_not_found=False)
        if bridge and not bridge.auth_token:
            bridge.auth_token = token


def get_agno_base_url(env):
    """Return the Agno origin: ICP, odoo.conf, then the Docker default."""
    configured = (
        env["ir.config_parameter"].sudo().get_param(ICP_AGNO_BASE_URL) or ""
    ).strip()
    if configured:
        return configured.rstrip("/")
    from_conf = (odoo_config.get(CONFIG_AGNO_BASE_URL) or "").strip()
    if from_conf:
        return from_conf.rstrip("/")
    return DEFAULT_AGNO_BASE_URL


def apply_bridge_base_url(env, bridge_xmlids):
    """Rewrite leftover Docker URLs when a custom Agno base URL is set."""
    base = get_agno_base_url(env)
    if base == DEFAULT_AGNO_BASE_URL:
        return
    for xmlid in bridge_xmlids:
        bridge = env.ref(xmlid, raise_if_not_found=False)
        if not bridge or not bridge.url:
            continue
        if "://agno:8000" in bridge.url:
            bridge.url = bridge.url.replace("http://agno:8000", base, 1)
