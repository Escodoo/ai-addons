# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import time

from odoo import models, tools

# Scope for signing the requesting user identity sent to the agent.
HMAC_SCOPE = "agno_connector-rpc-user"


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _add_extra_payload_fields(self, payload):
        """Sign the requesting user id with the database secret.

        Only for bridges with the ``agno`` provider. The agent forwards the
        signature untouched and the /agno/rpc gateway verifies it before
        impersonating the user, so a compromised agent (or any bridge-token
        holder) cannot forge an arbitrary user_id.
        """
        payload = super()._add_extra_payload_fields(payload)
        if self.ai_bridge_id.provider != "agno":
            return payload
        odoo_meta = payload.get("_odoo")
        if odoo_meta and odoo_meta.get("user_id"):
            timestamp = int(time.time())
            odoo_meta["user_hmac"] = tools.hmac(
                self.env(su=True), HMAC_SCOPE, (odoo_meta["user_id"], timestamp)
            )
            odoo_meta["user_hmac_ts"] = timestamp
        return payload
