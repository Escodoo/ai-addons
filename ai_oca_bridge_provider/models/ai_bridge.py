# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    provider = fields.Selection(
        [("generic", "Generic")],
        default="generic",
        required=True,
        help="AI runtime this bridge targets. Integration modules add their "
        "own values and scope provider-specific behaviour (extra payload, "
        "signing, timeouts) to bridges with their provider.",
    )
