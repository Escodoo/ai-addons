# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install helpers for the system AI assistant bridge."""

from odoo.addons.ai_agno_connector.token_utils import (
    CONFIG_BRIDGE_AUTH_TOKEN,
    ensure_token,
)

ICP_KEY = "ai_agno_assistant.bridge_auth_token"

_BRIDGE_XMLIDS = ("ai_agno_assistant.ai_bridge_assistant_chat",)


def apply_auth_token(env, bridge_xmlids=None):
    """Copy token (ICP or odoo.conf) onto bridges with an empty auth_token."""
    token = ensure_token(env, ICP_KEY, CONFIG_BRIDGE_AUTH_TOKEN)
    if not token:
        return
    for xmlid in bridge_xmlids or _BRIDGE_XMLIDS:
        bridge = env.ref(xmlid, raise_if_not_found=False)
        if bridge and not bridge.auth_token:
            bridge.auth_token = token


def post_init_hook(env):
    apply_auth_token(env)
