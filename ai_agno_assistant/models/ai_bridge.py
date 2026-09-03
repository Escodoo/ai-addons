# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import fields, models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    payload_type = fields.Selection(
        selection_add=[("assistant", "System Assistant")],
        ondelete={"assistant": "set default"},
    )
    result_type = fields.Selection(
        selection_add=[("assistant", "Return Assistant Result")],
        ondelete={"assistant": "set default"},
    )

    def _prepare_payload_assistant(
        self,
        record=None,
        message=None,
        history=None,
        ui_context=None,
        session_id=None,
        res_model=False,
        res_id=False,
        model=False,
        **kwargs,
    ):
        """Prepare a system-assistant payload for the Agno service."""
        self.ensure_one()
        model_name = res_model or model or (record._name if record else False) or False
        record_id = (
            res_id if res_id not in (None, False) else (record.id if record else False)
        )
        return json.loads(
            json.dumps(
                {
                    "_model": model_name,
                    "_id": record_id,
                    "message": message or False,
                    "history": history or [],
                    "ui_context": ui_context or {},
                    "session_id": session_id or False,
                },
                default=self.custom_serializer,
            )
        )
