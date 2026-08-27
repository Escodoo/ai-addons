# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class AiBridge(models.Model):
    _inherit = "ai.bridge"

    def execute_ai_bridge(self, *args, **kwargs):
        """Queue KB syncs when queue_job is available so writes stay fast."""
        self.ensure_one()
        if self._should_delay_agno_kb_sync():
            return (
                self.with_delay(
                    channel="root.agno_kb",
                    description=f"Agno KB sync: {self.name}",
                )
                .with_context(agno_kb_sync_now=True)
                .execute_ai_bridge(*args, **kwargs)
            )
        return super().execute_ai_bridge(*args, **kwargs)

    def _should_delay_agno_kb_sync(self):
        if self.env.context.get("agno_kb_sync_now"):
            return False
        if "queue.job" not in self.env or not hasattr(self, "with_delay"):
            return False
        xmlid = self.get_external_id().get(self.id) or ""
        return xmlid.startswith("ai_agno_document_page_kb.")
