# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install hook to apply the bridge auth token from ICP or odoo.conf."""

from odoo.addons.agno_connector.token_utils import (
    CONFIG_BRIDGE_AUTH_TOKEN,
    ensure_token,
)

_BRIDGE_XMLIDS = (
    "agno_chatter_bots.ai_bridge_chatter_erp",
    "agno_chatter_bots.ai_bridge_chatter_ops",
    "agno_chatter_bots.ai_bridge_chatter_support",
    "agno_chatter_bots.ai_bridge_chatter_sales",
    "agno_chatter_bots.ai_bridge_chatter_web",
)

_ICP_KEY = "agno_chatter_bots.bridge_auth_token"


def post_init_hook(env):
    """Copy token onto chatter bridges that still have an empty auth_token."""
    token = ensure_token(env, _ICP_KEY, CONFIG_BRIDGE_AUTH_TOKEN)
    if not token:
        return
    for xmlid in _BRIDGE_XMLIDS:
        bridge = env.ref(xmlid, raise_if_not_found=False)
        if bridge and not bridge.auth_token:
            bridge.auth_token = token
