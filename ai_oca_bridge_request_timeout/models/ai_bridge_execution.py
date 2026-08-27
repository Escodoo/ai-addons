# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import traceback
from io import StringIO

import requests

from odoo import models


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _execute_kwargs(self, timeout=False, **kwargs):
        result = super()._execute_kwargs(timeout=timeout, **kwargs)
        if not result.get("timeout") and self.ai_bridge_id.request_timeout:
            result["timeout"] = self.ai_bridge_id.request_timeout
        return result

    def _execute(self, **kwargs):
        """Honor the per-bridge ``request_timeout`` field.

        Bridges without ``request_timeout`` keep the upstream behaviour.
        Current ``ai_oca_bridge`` hardcodes ``timeout=30`` and then unpacks
        ``_execute_kwargs``, which raises ``TypeError`` when timeout is also
        injected there. This replica stays until OCA/ai#107 is merged; after
        that only ``_execute_kwargs`` is needed.
        """
        self.ensure_one()
        if not self.ai_bridge_id.request_timeout:
            return super()._execute(**kwargs)
        record = None
        if self.res_id and self.model_id:
            record = self.env[self.sudo().model_id.model].browse(self.res_id)
        payload = self.ai_bridge_id._prepare_payload(
            record=record,
            res_id=self.res_id,
            model=self.sudo().model_id.model,
            **kwargs,
        )
        payload = self._add_extra_payload_fields(payload)
        request_kwargs = self._execute_kwargs(**kwargs)
        timeout = request_kwargs.pop("timeout", self.ai_bridge_id.request_timeout)
        try:
            response = requests.post(
                self.ai_bridge_id.url,
                json=payload,
                auth=self._get_auth(),
                headers=self._get_headers(),
                timeout=timeout,
                **request_kwargs,
            )
            self.result = response.content
            response.raise_for_status()
            self.state = "done"
            self.payload = payload
            if self.ai_bridge_id.result_kind == "immediate":
                return self._process_response(response.json())
        except Exception:
            self.state = "error"
            self.payload = payload
            buff = StringIO()
            traceback.print_exc(file=buff)
            self.error = buff.getvalue()
            buff.close()
