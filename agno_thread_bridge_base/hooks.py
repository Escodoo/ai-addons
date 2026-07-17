# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Helpers and post-install hook for Agno thread bridges.

``ai.bridge`` stores ``domain`` and ``field_ids`` as computed fields that reset
when ``model_id`` is set. Child modules reuse ``apply_auth_token`` /
``set_bridge_fields`` from their own post_init hooks.
"""

from odoo.addons.agno_connector.token_utils import (
    CONFIG_BRIDGE_AUTH_TOKEN,
    ensure_token,
)

ICP_KEY = "agno_thread_bridge_base.bridge_auth_token"

_PARTNER_BRIDGE_XMLID = "agno_thread_bridge_base.ai_bridge_partner_analysis"

# Names only: ranks come from account when installed; missing fields are skipped.
_PARTNER_FIELD_NAMES = (
    "name",
    "email",
    "phone",
    "city",
    "country_id",
    "category_id",
    "customer_rank",
    "supplier_rank",
)


def apply_auth_token(env, bridge_xmlids):
    """Copy token (ICP or odoo.conf) onto bridges with an empty auth_token."""
    token = ensure_token(env, ICP_KEY, CONFIG_BRIDGE_AUTH_TOKEN)
    if not token:
        return
    for xmlid in bridge_xmlids:
        bridge = env.ref(xmlid, raise_if_not_found=False)
        if bridge and not bridge.auth_token:
            bridge.auth_token = token


def set_bridge_fields(env, bridge_xmlid, model_name, field_names, domain="[]"):
    """Set domain and field_ids on a thread bridge after install."""
    bridge = env.ref(bridge_xmlid, raise_if_not_found=False)
    if bridge.exists():
        fields = env["ir.model.fields"].search(
            [
                ("model", "=", model_name),
                ("name", "in", list(field_names)),
            ]
        )
        bridge.write(
            {
                "domain": domain,
                "field_ids": [(6, 0, fields.ids)],
            }
        )


def post_init_hook(env):
    apply_auth_token(env, [_PARTNER_BRIDGE_XMLID])
    set_bridge_fields(
        env,
        _PARTNER_BRIDGE_XMLID,
        "res.partner",
        _PARTNER_FIELD_NAMES,
    )
