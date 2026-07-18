# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    is_agno_bridge = fields.Boolean(
        string="Agno Bridge",
        default=False,
        help="Enable Agno-specific behaviour for this bridge: signed user "
        "identity (user_hmac), longer HTTP timeout, and BYOK LLM/embedder "
        "payload injection when ai_agno_llm_settings is installed. Leave "
        "unchecked for third-party bridges (e.g. Hermes).",
    )
