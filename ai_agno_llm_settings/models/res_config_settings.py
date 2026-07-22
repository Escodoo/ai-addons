# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.ai_agno_connector.token_utils import (
    CONFIG_BRIDGE_AUTH_TOKEN,
    ensure_token,
)

_logger = logging.getLogger(__name__)

ICP_PROVIDER = "ai_agno_llm_settings.provider"
ICP_API_KEY = "ai_agno_llm_settings.api_key"
ICP_HOST = "ai_agno_llm_settings.host"
ICP_MODEL = "ai_agno_llm_settings.model"

ICP_EMBEDDER_PROVIDER = "ai_agno_llm_settings.embedder_provider"
ICP_EMBEDDER_API_KEY = "ai_agno_llm_settings.embedder_api_key"
ICP_EMBEDDER_HOST = "ai_agno_llm_settings.embedder_host"
ICP_EMBEDDER_MODEL = "ai_agno_llm_settings.embedder_model"
ICP_EMBEDDER_DIMENSIONS = "ai_agno_llm_settings.embedder_dimensions"
ICP_BRIDGE_AUTH_TOKEN = "ai_agno_llm_settings.bridge_auth_token"
ICP_AGNO_BASE_URL = "ai_agno_llm_settings.agno_base_url"

# Default host the document.page / chatter bridges use inside Docker.
# Override with ICP ``ai_agno_llm_settings.agno_base_url`` outside Compose.
DEFAULT_AGNO_BASE_URL = "http://agno:8000"
# Kept for backward-compatible imports in tests.
AGNO_BASE_URL = DEFAULT_AGNO_BASE_URL
REINDEX_TIMEOUT_SECONDS = 300

HOST_BY_PROVIDER = {
    "ollama": "https://ollama.com",
    "openai": "https://api.openai.com/v1",
    "gemini": "",
}

MODEL_BY_PROVIDER = {
    "ollama": "qwen3.5:397b-cloud",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
}

EMBEDDER_HOST_BY_PROVIDER = {
    "ollama": "http://ollama:11434",
    "openai": "https://api.openai.com/v1",
}

EMBEDDER_MODEL_BY_PROVIDER = {
    "ollama": "qwen3-embedding:0.6b",
    "openai": "text-embedding-3-small",
}

EMBEDDER_DIMENSIONS_BY_PROVIDER = {
    "ollama": "1024",
    "openai": "1536",
}

# Providers that require an API key (Ollama may be local / unauthenticated).
PROVIDERS_REQUIRING_API_KEY = frozenset({"openai", "gemini"})
EMBEDDER_PROVIDERS_REQUIRING_API_KEY = frozenset({"openai"})


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    agno_llm_provider = fields.Selection(
        [
            ("ollama", "Ollama"),
            ("openai", "OpenAI"),
            ("gemini", "Google Gemini"),
        ],
        string="LLM Provider",
        config_parameter=ICP_PROVIDER,
        help="When empty, Agno uses its environment (LLM_*). "
        "When set, Agno uses only these credentials (never the service env "
        "token). For Ollama, Host must be reachable from the Agno service "
        "(e.g. http://ollama:11434 or https://ollama.com).",
    )
    agno_llm_api_key = fields.Char(
        string="LLM API Key",
        config_parameter=ICP_API_KEY,
        groups="base.group_system",
        help="Customer API key sent to Agno per bridge request (BYOK). "
        "Required for OpenAI and Gemini. Optional for Ollama (local / no auth). "
        "Not the same as BRIDGE_AUTH_TOKEN (infrastructure).",
    )
    agno_llm_host = fields.Char(
        string="LLM Host / Base URL",
        config_parameter=ICP_HOST,
        help="URL reachable from the Agno container. Examples: "
        "http://ollama:11434 (Docker local), https://ollama.com (cloud), "
        "or https://api.openai.com/v1. Not used for Gemini.",
    )
    agno_llm_model = fields.Char(
        string="LLM Model",
        config_parameter=ICP_MODEL,
        help="Model id for the selected provider (e.g. llama3.2:3b, "
        "qwen3.5:397b-cloud, gpt-4o, gemini-2.0-flash).",
    )
    # Keeps the last provider seen in this settings form so onchange can
    # distinguish "form just loaded" / "same provider re-fired" from a real
    # provider switch (must be present in the view as invisible).
    agno_llm_last_provider = fields.Char(store=False)

    agno_embedder_provider = fields.Selection(
        [
            ("ollama", "Ollama"),
            ("openai", "OpenAI"),
        ],
        string="Embedder Provider",
        config_parameter=ICP_EMBEDDER_PROVIDER,
        help="When empty, Agno uses its environment (EMBEDDER_*). "
        "When set, Agno uses only these credentials. "
        "Changing model or dimensions requires re-indexing knowledge bases.",
    )
    agno_embedder_api_key = fields.Char(
        string="Embedder API Key",
        config_parameter=ICP_EMBEDDER_API_KEY,
        groups="base.group_system",
        help="Customer embedder API key sent to Agno per bridge/KB request "
        "(BYOK). Required for OpenAI. Optional for Ollama.",
    )
    agno_embedder_host = fields.Char(
        string="Embedder Host / Base URL",
        config_parameter=ICP_EMBEDDER_HOST,
        help="URL reachable from the Agno container "
        "(e.g. http://ollama:11434 or https://api.openai.com/v1).",
    )
    agno_embedder_model = fields.Char(
        string="Embedder Model",
        config_parameter=ICP_EMBEDDER_MODEL,
        help="Embedding model id (e.g. qwen3-embedding:0.6b, "
        "text-embedding-3-small). Changing it requires re-indexing.",
    )
    agno_embedder_dimensions = fields.Char(
        string="Embedder Dimensions",
        config_parameter=ICP_EMBEDDER_DIMENSIONS,
        help="Vector size for the chosen model (e.g. 1024 for "
        "qwen3-embedding:0.6b, 1536 for text-embedding-3-small). Must match "
        "LanceDB tables; changing it requires re-indexing.",
    )
    agno_embedder_last_provider = fields.Char(store=False)

    @api.onchange("agno_llm_provider")
    def _onchange_agno_llm_provider(self):
        """Suggest host/model only when the provider actually changes.

        Avoid overwriting ICP-loaded or user-edited values when the form
        reloads or the selection widget re-fires onchange for the same
        provider (the previous bug that reset custom host/model on save).
        """
        provider = self.agno_llm_provider or False
        last = self.agno_llm_last_provider or False

        if not provider:
            self.agno_llm_host = False
            self.agno_llm_model = False
            self.agno_llm_last_provider = False
            return

        host_set = bool((self.agno_llm_host or "").strip())
        model_set = bool((self.agno_llm_model or "").strip())
        # First onchange after opening Settings with values from ICP: sync
        # tracker only, do not replace persisted host/model.
        if not last and (host_set or model_set):
            self.agno_llm_last_provider = provider
            return

        if last != provider:
            self.agno_llm_host = HOST_BY_PROVIDER.get(provider) or False
            self.agno_llm_model = MODEL_BY_PROVIDER.get(provider) or False

        self.agno_llm_last_provider = provider

    @api.onchange("agno_embedder_provider")
    def _onchange_agno_embedder_provider(self):
        """Suggest embedder host/model/dimensions on real provider changes."""
        provider = self.agno_embedder_provider or False
        last = self.agno_embedder_last_provider or False

        if not provider:
            self.agno_embedder_host = False
            self.agno_embedder_model = False
            self.agno_embedder_dimensions = False
            self.agno_embedder_last_provider = False
            return

        host_set = bool((self.agno_embedder_host or "").strip())
        model_set = bool((self.agno_embedder_model or "").strip())
        dims_set = bool((self.agno_embedder_dimensions or "").strip())
        if not last and (host_set or model_set or dims_set):
            self.agno_embedder_last_provider = provider
            return

        if last != provider:
            self.agno_embedder_host = EMBEDDER_HOST_BY_PROVIDER.get(provider) or False
            self.agno_embedder_model = EMBEDDER_MODEL_BY_PROVIDER.get(provider) or False
            self.agno_embedder_dimensions = (
                EMBEDDER_DIMENSIONS_BY_PROVIDER.get(provider) or False
            )

        self.agno_embedder_last_provider = provider

    def set_values(self):
        provider = (self.agno_llm_provider or "").strip()
        if provider:
            model = (self.agno_llm_model or "").strip()
            api_key = (self.agno_llm_api_key or "").strip()
            host = (self.agno_llm_host or "").strip()
            if not model:
                raise UserError(
                    _("When an LLM provider is selected, Model is required.")
                )
            if provider == "ollama" and not host:
                raise UserError(
                    _(
                        "Ollama requires a Host / Base URL reachable from "
                        "the Agno service (e.g. http://ollama:11434 or "
                        "https://ollama.com)."
                    )
                )
            if provider in PROVIDERS_REQUIRING_API_KEY and not api_key:
                raise UserError(
                    _(
                        "OpenAI and Google Gemini require an API Key when "
                        "selected as LLM provider."
                    )
                )

        embedder_provider = (self.agno_embedder_provider or "").strip()
        if embedder_provider:
            embedder_model = (self.agno_embedder_model or "").strip()
            embedder_host = (self.agno_embedder_host or "").strip()
            embedder_api_key = (self.agno_embedder_api_key or "").strip()
            dims_raw = (self.agno_embedder_dimensions or "").strip()
            if not embedder_model:
                raise UserError(
                    _(
                        "When an embedder provider is selected, "
                        "Embedder Model is required."
                    )
                )
            if not dims_raw:
                raise UserError(
                    _(
                        "When an embedder provider is selected, "
                        "Embedder Dimensions is required."
                    )
                )
            try:
                dimensions = int(dims_raw)
            except ValueError as exc:
                raise UserError(
                    _("Embedder Dimensions must be a positive integer.")
                ) from exc
            if dimensions <= 0:
                raise UserError(_("Embedder Dimensions must be a positive integer."))
            if embedder_provider == "ollama" and not embedder_host:
                raise UserError(
                    _(
                        "Ollama embedder requires a Host / Base URL reachable "
                        "from the Agno service (e.g. http://ollama:11434)."
                    )
                )
            if (
                embedder_provider in EMBEDDER_PROVIDERS_REQUIRING_API_KEY
                and not embedder_api_key
            ):
                raise UserError(
                    _(
                        "OpenAI requires an Embedder API Key when selected "
                        "as embedder provider."
                    )
                )
        return super().set_values()

    def _get_agno_base_url(self):
        """Return Agno base URL from ICP, or the Docker Compose default."""
        configured = (
            self.env["ir.config_parameter"].sudo().get_param(ICP_AGNO_BASE_URL) or ""
        ).strip()
        return configured or DEFAULT_AGNO_BASE_URL

    def action_reindex_agno_knowledge(self):
        """Call Agno to wipe/rebuild business KBs, then sync document.pages.

        Does not reindex the architect knowledge base.
        """
        self.ensure_one()
        # Persist current form values (including embedder BYOK) before Agno runs.
        self.set_values()

        token = ensure_token(self.env, ICP_BRIDGE_AUTH_TOKEN, CONFIG_BRIDGE_AUTH_TOKEN)
        if not token:
            raise UserError(
                _(
                    "Bridge auth token is not configured. Set "
                    "agno_bridge_auth_token (odoo.conf) or the ICP "
                    "ai_agno_llm_settings.bridge_auth_token."
                )
            )

        execution = self.env["ai.bridge.execution"].new({})
        embedder = execution._get_agno_embedder_settings()
        payload = {"_odoo": {}}
        if embedder:
            payload["_odoo"]["embedder"] = embedder

        url = f"{self._get_agno_base_url().rstrip('/')}/bridge/kb/reindex"
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=REINDEX_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise UserError(
                _("Could not reach Agno at %(url)s: %(error)s")
                % {"url": url, "error": exc}
            ) from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("detail"):
                    detail = body["detail"]
            except (ValueError, TypeError):
                _logger.debug(
                    "Agno reindex error body was not JSON; using raw text.",
                    exc_info=True,
                )
            raise UserError(
                _("Agno reindex failed (%(code)s): %(detail)s")
                % {"code": response.status_code, "detail": detail}
            )

        synced_pages = False
        kb_module = (
            self.env["ir.module.module"]
            .sudo()
            .search(
                [
                    ("name", "=", "ai_agno_document_page_kb"),
                    ("state", "=", "installed"),
                ],
                limit=1,
            )
        )
        if kb_module:
            from odoo.addons.ai_agno_document_page_kb.hooks import sync_kb_pages

            sync_kb_pages(self.env)
            synced_pages = True
        else:
            _logger.info(
                "ai_agno_document_page_kb not installed; skipped document.page sync."
            )

        message = _(
            "Business knowledge bases were reindexed "
            "(support, legal, processes, commercial, public). "
            "The architect KB was not modified."
        )
        if synced_pages:
            message = _(
                "%(base)s Tagged document.page records were re-sent to Agno."
            ) % {"base": message}

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Knowledge reindex"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
