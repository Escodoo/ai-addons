# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _is_ai_customer_conversation(self):
        self.ensure_one()
        if self.channel_type == "livechat":
            return True
        return super()._is_ai_customer_conversation()

    def _is_ai_conversation_open(self):
        self.ensure_one()
        if self.channel_type == "livechat":
            return self.livechat_active
        return super()._is_ai_conversation_open()

    def _ai_bridge_note_stays_internal(self):
        self.ensure_one()
        if self.channel_type == "livechat":
            # The visitor reads the channel itself, so a note posted there would
            # disclose the handoff to them.
            return False
        return super()._ai_bridge_note_stays_internal()
