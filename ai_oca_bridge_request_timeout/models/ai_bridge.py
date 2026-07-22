# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    request_timeout = fields.Integer(
        default=0,
        help="HTTP timeout in seconds for requests sent by this bridge. "
        "0 keeps the default timeout (30s). Raise it for endpoints backed "
        "by LLMs, which routinely take longer to answer.",
    )
