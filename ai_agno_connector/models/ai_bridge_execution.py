# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time
import traceback
from io import StringIO

import requests

from odoo import models, tools

# Scope for signing the requesting user identity sent to the agent.
HMAC_SCOPE = "agno_connector-rpc-user"

# HTTP timeout (seconds) for bridge calls to the agent. LLM responses
# routinely exceed the 30s hardcoded upstream.
BRIDGE_REQUEST_TIMEOUT = 120


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _add_extra_payload_fields(self, payload):
        """Sign the requesting user id with the database secret.

        Only for bridges marked ``is_agno_bridge``. The agent forwards the
        signature untouched and the /agno/rpc gateway verifies it before
        impersonating the user, so a compromised agent (or any bridge-token
        holder) cannot forge an arbitrary user_id.
        """
        payload = super()._add_extra_payload_fields(payload)
        if not self.ai_bridge_id.is_agno_bridge:
            return payload
        odoo_meta = payload.get("_odoo")
        if odoo_meta and odoo_meta.get("user_id"):
            timestamp = int(time.time())
            odoo_meta["user_hmac"] = tools.hmac(
                self.env(su=True), HMAC_SCOPE, (odoo_meta["user_id"], timestamp)
            )
            odoo_meta["user_hmac_ts"] = timestamp
        return payload

    def _execute(self, **kwargs):
        """Replicate upstream _execute with a longer request timeout.

        Only for bridges marked ``is_agno_bridge``; other bridges keep the
        upstream 30s timeout. Upstream hardcodes ``timeout=30`` in the
        ``requests.post`` call, which LLM-backed agent replies routinely
        exceed on cold sessions, and passing ``timeout`` through
        ``_execute_kwargs`` would raise ``TypeError`` there (duplicate
        keyword). The method body is replicated so the timeout can default
        to ``BRIDGE_REQUEST_TIMEOUT`` while still honoring an explicit
        ``timeout`` kwarg.
        """
        self.ensure_one()
        if not self.ai_bridge_id.is_agno_bridge:
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
        timeout = request_kwargs.pop("timeout", BRIDGE_REQUEST_TIMEOUT)
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
