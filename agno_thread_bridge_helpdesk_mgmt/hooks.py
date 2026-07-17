# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install hook for the helpdesk ticket thread bridge."""

from odoo.addons.agno_thread_bridge_base.hooks import (
    apply_auth_token,
    set_bridge_fields,
)

_BRIDGE_XMLID = "agno_thread_bridge_helpdesk_mgmt.ai_bridge_helpdesk_ticket_analysis"

_TICKET_FIELD_NAMES = (
    "number",
    "name",
    "description",
    "stage_id",
    "partner_id",
    "partner_name",
    "partner_email",
    "team_id",
    "user_id",
    "priority",
    "category_id",
    "tag_ids",
    "channel_id",
)


def post_init_hook(env):
    apply_auth_token(env, [_BRIDGE_XMLID])
    set_bridge_fields(
        env,
        _BRIDGE_XMLID,
        "helpdesk.ticket",
        _TICKET_FIELD_NAMES,
    )
