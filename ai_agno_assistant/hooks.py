# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install helpers for the system AI assistant bridge."""

from odoo.addons.ai_agno_connector.token_utils import (
    apply_auth_token as apply_shared_token,
)
from odoo.addons.ai_agno_connector.token_utils import (
    apply_bridge_base_url,
)

ICP_KEY = "ai_agno_assistant.bridge_auth_token"

_BRIDGE_XMLIDS = ("ai_agno_assistant.ai_bridge_assistant_chat",)


def apply_auth_token(env, bridge_xmlids=None):
    """Copy token (ICP or odoo.conf) onto bridges with an empty auth_token."""
    xmlids = bridge_xmlids or _BRIDGE_XMLIDS
    apply_shared_token(env, xmlids, ICP_KEY)
    apply_bridge_base_url(env, xmlids)


def post_init_hook(env):
    apply_auth_token(env)
