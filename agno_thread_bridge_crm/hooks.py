# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install hook for the CRM lead/opportunity thread bridge."""

from odoo.addons.agno_thread_bridge_base.hooks import (
    apply_auth_token,
    set_bridge_fields,
)

_BRIDGE_XMLID = "agno_thread_bridge_crm.ai_bridge_crm_lead_analysis"

_LEAD_FIELD_NAMES = (
    "name",
    "type",
    "stage_id",
    "priority",
    "partner_id",
    "partner_name",
    "contact_name",
    "email_from",
    "phone",
    "user_id",
    "team_id",
    "expected_revenue",
    "probability",
    "date_deadline",
    "tag_ids",
    "description",
    "source_id",
    "medium_id",
    "campaign_id",
)


def post_init_hook(env):
    apply_auth_token(env, [_BRIDGE_XMLID])
    set_bridge_fields(
        env,
        _BRIDGE_XMLID,
        "crm.lead",
        _LEAD_FIELD_NAMES,
    )
