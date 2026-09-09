# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    agno_llm_profile_id = fields.Many2one(
        "agno.llm.profile",
        string="Agno LLM Profile",
        help="When set, this Agno bridge sends that profile as _odoo.llm "
        "instead of the default Chat LLM. Use Fast for the public web "
        "channel. Leave empty for the standard Settings Chat LLM.",
    )
