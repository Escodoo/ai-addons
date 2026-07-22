# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    provider = fields.Selection(
        selection_add=[("agno", "Agno")],
        ondelete={"agno": "set default"},
    )
