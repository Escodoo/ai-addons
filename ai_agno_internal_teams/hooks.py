# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install hook to apply the shared Agno bridge auth token."""

from odoo.addons.ai_agno_connector.token_utils import (
    apply_auth_token,
    apply_bridge_base_url,
)

_BRIDGE_XMLIDS = (
    "ai_agno_internal_teams.ai_bridge_team_commercial_review",
    "ai_agno_internal_teams.ai_bridge_team_finance_ops",
)

_ICP_KEY = "ai_agno_internal_teams.bridge_auth_token"


def post_init_hook(env):
    apply_auth_token(env, _BRIDGE_XMLIDS, _ICP_KEY)
    apply_bridge_base_url(env, _BRIDGE_XMLIDS)
