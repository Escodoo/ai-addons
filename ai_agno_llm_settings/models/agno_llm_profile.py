# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models

PROFILE_KEYS = [
    ("fast", "Fast"),
    ("reasoning", "Reasoning"),
    ("extract", "Extract"),
]


class AgnoLlmProfile(models.Model):
    _name = "agno.llm.profile"
    _description = "Agno LLM Profile"
    _order = "key"

    key = fields.Selection(
        PROFILE_KEYS,
        required=True,
        help="Task profile sent to Agno as _odoo.llm_profiles.<key>. "
        "The default Chat LLM in Settings is the standard profile.",
    )
    provider = fields.Selection(
        [
            ("ollama", "Ollama"),
            ("openai", "OpenAI"),
            ("gemini", "Google Gemini"),
        ],
        required=True,
    )
    host = fields.Char(string="Host / Base URL")
    model = fields.Char(required=True)
    api_key = fields.Char(groups="base.group_system")
    active = fields.Boolean(default=True)
    name = fields.Char(compute="_compute_name", store=True)

    _sql_constraints = [
        ("key_uniq", "unique(key)", _("Each LLM profile key must be unique.")),
    ]

    @api.depends("key")
    def _compute_name(self):
        labels = dict(PROFILE_KEYS)
        for rec in self:
            rec.name = labels.get(rec.key) or rec.key or ""

    def _as_llm_dict(self):
        """Return the BYOK dict Agno expects, or None when incomplete."""
        self.ensure_one()
        provider = (self.provider or "").strip()
        model = (self.model or "").strip()
        if not provider:
            return None
        if not model:
            return None
        payload = {"provider": provider, "model": model}
        host = (self.host or "").strip()
        api_key = (self.api_key or "").strip()
        if host:
            payload["host"] = host
        if api_key:
            payload["api_key"] = api_key
        return payload
