# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    @api.depends("model_id", "res_id", "ai_bridge_id")
    def _compute_name(self):
        """Avoid browsing AbstractModel records (no display_name / no table)."""
        concrete = self.browse()
        for record in self:
            model_name = record.sudo().model_id.model
            if (
                model_name
                and model_name in self.env
                and (self.env[model_name]._abstract or not record.res_id)
            ):
                label = record.sudo().model_id.name or model_name
                record.name = f"{label} - {record.ai_bridge_id.name}"
            else:
                concrete |= record
        if concrete:
            return super(AiBridgeExecution, concrete)._compute_name()

    def _process_response_assistant(self, response):
        """Return the Agno payload to the systray OWL caller."""
        self.ensure_one()
        if not isinstance(response, dict):
            return {
                "body": "",
                "body_is_html": False,
                "actions": [],
                "artifacts": [],
            }
        return {
            "body": response.get("body") or "",
            "body_is_html": bool(response.get("body_is_html", False)),
            "actions": response.get("actions") or [],
            "artifacts": [],
        }
