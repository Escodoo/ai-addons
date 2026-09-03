# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import re
import uuid

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_SESSION_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SESSION_MESSAGE_LIMIT = 40


class AiAssistantSession(models.Model):
    _name = "ai.assistant.session"
    _description = "AI assistant conversation"
    _order = "last_activity desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.user,
    )
    name = fields.Char(required=True, default="New conversation")
    session_key = fields.Char(required=True, index=True)
    messages_json = fields.Text(default="[]")
    last_activity = fields.Datetime(default=fields.Datetime.now, index=True)

    _sql_constraints = [
        (
            "user_session_key_unique",
            "unique(user_id, session_key)",
            "Session key must be unique per user.",
        )
    ]


class AiAssistantSessionHelpers(models.AbstractModel):
    _inherit = "ai.assistant"  # pylint: disable=consider-merging-classes-inherited

    @api.model
    def _normalize_session_key(self, value):
        text = (value or "").strip() if isinstance(value, str) else ""
        if _SESSION_KEY_RE.match(text):
            return text
        return False

    @api.model
    def _new_session_key(self):
        return uuid.uuid4().hex

    @api.model
    def _get_or_create_session(self, session_key=None):
        if "ai.assistant.session" not in self.env:
            return False
        Session = self.env["ai.assistant.session"]
        key = self._normalize_session_key(session_key) or self._new_session_key()
        session = Session.search(
            [("user_id", "=", self.env.user.id), ("session_key", "=", key)],
            limit=1,
        )
        if session:
            return session
        return Session.create(
            {
                "user_id": self.env.user.id,
                "session_key": key,
                "name": "New conversation",
            }
        )

    @api.model
    def _remember_chat_turn(self, message, body, body_is_html, session_key=None):
        """Persist the latest user/assistant turn on the user's session."""
        try:
            session = self._get_or_create_session(session_key)
            if not session:
                return False
            raw = session.messages_json or "[]"
            try:
                stored = json.loads(raw)
            except (TypeError, ValueError):
                stored = []
            if not isinstance(stored, list):
                stored = []
            stored.append({"role": "user", "text": message, "isHtml": False})
            stored.append(
                {
                    "role": "assistant",
                    "text": body or "",
                    "isHtml": bool(body_is_html),
                }
            )
            stored = stored[-_SESSION_MESSAGE_LIMIT:]
            title = (message or "").strip().replace("\n", " ")[:60] or session.name
            session.write(
                {
                    "messages_json": json.dumps(stored, ensure_ascii=False),
                    "last_activity": fields.Datetime.now(),
                    "name": (
                        title
                        if session.name in (False, "New conversation")
                        else session.name
                    ),
                }
            )
            return session
        except Exception:  # noqa: BLE001 - chat must not fail on history persist
            _logger.debug("Could not persist AI assistant session", exc_info=True)
            return False

    @api.model
    def _session_has_messages(self, session):
        raw = session.messages_json or "[]"
        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            return False
        return isinstance(stored, list) and bool(stored)

    @api.model
    def _prune_empty_sessions(self):
        """Drop unused drafts so they never appear as 'New conversation'."""
        if "ai.assistant.session" not in self.env:
            return
        sessions = self.env["ai.assistant.session"].search(
            [("user_id", "=", self.env.user.id)]
        )
        empties = sessions.filtered(lambda rec: not self._session_has_messages(rec))
        if empties:
            empties.unlink()

    @api.model
    def action_ai_list_sessions(self, limit=8):
        self._check_ai_user()
        if "ai.assistant.session" not in self.env:
            return []
        self._prune_empty_sessions()
        try:
            limit = min(max(int(limit or 8), 1), 20)
        except (TypeError, ValueError):
            limit = 8
        sessions = self.env["ai.assistant.session"].search(
            [("user_id", "=", self.env.user.id)],
            limit=limit,
        )
        return [
            {
                "id": session.id,
                "session_key": session.session_key,
                "name": session.name,
                "last_activity": fields.Datetime.to_string(session.last_activity),
            }
            for session in sessions
            if self._session_has_messages(session)
        ]

    @api.model
    def action_ai_load_session(self, session_key=None):
        self._check_ai_user()
        session = self._get_or_create_session(session_key)
        if not session:
            return {"session_key": False, "messages": []}
        try:
            messages = json.loads(session.messages_json or "[]")
        except (TypeError, ValueError):
            messages = []
        if not isinstance(messages, list):
            messages = []
        return {
            "session_id": session.id,
            "session_key": session.session_key,
            "name": session.name,
            "messages": messages[-_SESSION_MESSAGE_LIMIT:],
        }

    @api.model
    def action_ai_new_session(self):
        """Return a draft key only. The row is created on the first message."""
        self._check_ai_user()
        self._prune_empty_sessions()
        return {
            "session_id": False,
            "session_key": self._new_session_key(),
            "name": "New conversation",
            "messages": [],
        }

    @api.model
    def action_ai_delete_session(self, session_key=None):
        """Permanently remove the current user's conversation."""
        self._check_ai_user()
        key = self._normalize_session_key(session_key)
        if not key or "ai.assistant.session" not in self.env:
            return {"deleted": False, "session_key": key or False}
        session = self.env["ai.assistant.session"].search(
            [("user_id", "=", self.env.user.id), ("session_key", "=", key)],
            limit=1,
        )
        if not session:
            return {"deleted": False, "session_key": key}
        session.unlink()
        return {"deleted": True, "session_key": key}
