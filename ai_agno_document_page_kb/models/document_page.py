# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class DocumentPage(models.Model):
    _inherit = "document.page"

    def _agno_sync_all_kb_pages(self):
        """Job entrypoint: upsert tagged pages into Agno knowledge bases."""
        from ..hooks import sync_kb_pages

        sync_kb_pages(self.env)
        return True
