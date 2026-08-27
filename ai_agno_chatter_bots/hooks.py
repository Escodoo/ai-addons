# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install hook to apply the bridge auth token from ICP or odoo.conf."""

from odoo.addons.ai_agno_connector.token_utils import (
    apply_auth_token,
    apply_bridge_base_url,
)

_BRIDGE_XMLIDS = (
    "ai_agno_chatter_bots.ai_bridge_chatter_erp",
    "ai_agno_chatter_bots.ai_bridge_chatter_ops",
    "ai_agno_chatter_bots.ai_bridge_chatter_hr",
    "ai_agno_chatter_bots.ai_bridge_chatter_finance",
    "ai_agno_chatter_bots.ai_bridge_chatter_support",
    "ai_agno_chatter_bots.ai_bridge_chatter_sales",
    "ai_agno_chatter_bots.ai_bridge_chatter_marketing",
    "ai_agno_chatter_bots.ai_bridge_chatter_web",
)

_ICP_KEY = "ai_agno_chatter_bots.bridge_auth_token"

# English logins for databases that still have the original Portuguese values.
_LEGACY_BOT_LOGINS = {
    "bot.rh": "bot.hr",
    "bot.financeiro": "bot.finance",
    "bot.suporte": "bot.support",
    "bot.comercial": "bot.sales",
}
_BOT_ENGLISH_NAMES = {
    "ai_agno_chatter_bots.user_bot_hr": "Bot HR",
    "ai_agno_chatter_bots.user_bot_finance": "Bot Finance",
    "ai_agno_chatter_bots.user_bot_support": "Bot Support",
    "ai_agno_chatter_bots.user_bot_sales": "Bot Sales",
}


def rename_legacy_bot_identities(env):
    """Rename leftover Portuguese bot logins/names (noupdate XML)."""
    Users = env["res.users"].sudo()
    for old_login, new_login in _LEGACY_BOT_LOGINS.items():
        user = Users.search([("login", "=", old_login)], limit=1)
        if user and not Users.search([("login", "=", new_login)], limit=1):
            user.login = new_login
    for xmlid, name in _BOT_ENGLISH_NAMES.items():
        user = env.ref(xmlid, raise_if_not_found=False)
        if user and user.name != name:
            user.name = name


def post_init_hook(env):
    """Copy token onto chatter bridges that still have an empty auth_token."""
    rename_legacy_bot_identities(env)
    apply_auth_token(env, _BRIDGE_XMLIDS, _ICP_KEY)
    apply_bridge_base_url(env, _BRIDGE_XMLIDS)
