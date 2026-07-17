# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from markupsafe import Markup

from odoo import _, models
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _execute(self, **kwargs):
        """On chatter failures, stop typing and post the error in Discuss."""
        result = super()._execute(**kwargs)
        if self.state == "error" and self.ai_bridge_id.usage == "chatter":
            try:
                self._notify_chatter_error()
            except Exception:
                # Never hide the original bridge failure behind a notify bug.
                _logger.exception(
                    "Failed to post chatter error for execution %s", self.id
                )
        return result

    def _chatter_error_detail(self):
        """Extract a short user-facing message from the bridge HTTP body."""
        self.ensure_one()
        if self.result:
            try:
                data = json.loads(self.result)
            except (TypeError, ValueError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict):
                detail = data.get("detail")
                if isinstance(detail, str) and detail.strip():
                    return detail.strip()
                if isinstance(detail, list):
                    # FastAPI validation errors: [{msg, ...}, ...]
                    parts = [
                        item.get("msg")
                        for item in detail
                        if isinstance(item, dict) and item.get("msg")
                    ]
                    if parts:
                        return "; ".join(parts)
            text = (
                self.result.decode("utf-8", errors="replace")
                if isinstance(self.result, bytes | bytearray)
                else str(self.result)
            )
            text = text.strip()
            if text:
                return text[:500]
        return _(
            "The AI service could not process your message. "
            "Check the AI Execution log for details."
        )

    def _notify_chatter_error(self):
        """Clear typing indicator and post the error as the bot in the channel."""
        self.ensure_one()
        if not self.chatter_user_id:
            return
        channel = self._get_channel()
        if not channel:
            return
        member = (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("partner_id", "=", self.chatter_user_id.partner_id.id),
                    ("channel_id", "=", channel.id),
                ],
                limit=1,
            )
        )
        if member:
            member._notify_typing(is_typing=False)

        detail = self._chatter_error_detail()
        body = Markup("<p><b>%s</b></p><p>%s</p>") % (
            html_escape(_("AI error")),
            html_escape(detail),
        )
        channel.with_user(self.chatter_user_id.id).message_post(
            body=body,
            body_is_html=True,
            author_id=self.chatter_user_id.partner_id.id,
            message_type="comment",
        )
