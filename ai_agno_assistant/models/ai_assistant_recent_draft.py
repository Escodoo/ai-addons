# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiAssistantRecentDraft(models.TransientModel):
    _name = "ai.assistant.recent.draft"
    _description = "Recent AI assistant draft"
    _order = "id desc"

    user_id = fields.Many2one(
        "res.users", required=True, index=True, ondelete="cascade"
    )
    model_name = fields.Char(required=True)
    res_id = fields.Integer(required=True)
