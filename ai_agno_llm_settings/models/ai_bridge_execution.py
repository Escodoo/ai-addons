# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import copy

from odoo import models

from .res_config_settings import (
    ICP_API_KEY,
    ICP_EMBEDDER_API_KEY,
    ICP_EMBEDDER_DIMENSIONS,
    ICP_EMBEDDER_HOST,
    ICP_EMBEDDER_MODEL,
    ICP_EMBEDDER_PROVIDER,
    ICP_HOST,
    ICP_MODEL,
    ICP_PROVIDER,
)

MASKED_API_KEY = "***"


class AiBridgeExecution(models.Model):
    _inherit = "ai.bridge.execution"

    def _get_agno_llm_settings(self):
        """Return BYOK LLM dict for the bridge payload, or None if unset.

        When no provider is configured, Agno must fall back to its own env
        (including optional empty token for local Ollama).
        """
        get_param = self.env["ir.config_parameter"].sudo().get_param
        provider = (get_param(ICP_PROVIDER) or "").strip()
        if not provider:
            return None

        host = (get_param(ICP_HOST) or "").strip()
        model = (get_param(ICP_MODEL) or "").strip()
        api_key = (get_param(ICP_API_KEY) or "").strip()

        llm = {
            "provider": provider,
            "model": model,
        }
        if host:
            llm["host"] = host
        if api_key:
            llm["api_key"] = api_key
        return llm

    def _get_agno_embedder_settings(self):
        """Return BYOK embedder dict for the bridge payload, or None if unset."""
        get_param = self.env["ir.config_parameter"].sudo().get_param
        provider = (get_param(ICP_EMBEDDER_PROVIDER) or "").strip()
        if not provider:
            return None

        host = (get_param(ICP_EMBEDDER_HOST) or "").strip()
        model = (get_param(ICP_EMBEDDER_MODEL) or "").strip()
        api_key = (get_param(ICP_EMBEDDER_API_KEY) or "").strip()
        dimensions_raw = (get_param(ICP_EMBEDDER_DIMENSIONS) or "").strip()
        try:
            dimensions = int(dimensions_raw) if dimensions_raw else None
        except ValueError:
            dimensions = None

        embedder = {
            "provider": provider,
            "model": model,
        }
        if host:
            embedder["host"] = host
        if api_key:
            embedder["api_key"] = api_key
        if dimensions is not None:
            embedder["dimensions"] = dimensions
        return embedder

    def _mask_llm_secrets(self, payload):
        """Return a copy of payload safe to persist (API keys masked)."""
        if not payload:
            return payload
        masked = copy.deepcopy(payload)
        odoo_meta = masked.get("_odoo")
        if not isinstance(odoo_meta, dict):
            return masked
        for key in ("llm", "embedder"):
            block = odoo_meta.get(key)
            if isinstance(block, dict) and block.get("api_key"):
                block["api_key"] = MASKED_API_KEY
        return masked

    def _add_extra_payload_fields(self, payload):
        payload = super()._add_extra_payload_fields(payload)
        if self.ai_bridge_id.provider != "agno":
            return payload
        odoo_meta = payload.get("_odoo")
        if isinstance(odoo_meta, dict):
            llm = self._get_agno_llm_settings()
            if llm:
                odoo_meta["llm"] = llm
            else:
                odoo_meta.pop("llm", None)
            embedder = self._get_agno_embedder_settings()
            if embedder:
                odoo_meta["embedder"] = embedder
            else:
                odoo_meta.pop("embedder", None)
        return payload

    def _execute(self, **kwargs):
        """Run the bridge request, then mask LLM/embedder secrets in payload."""
        result = super()._execute(**kwargs)
        if self.payload:
            self.payload = self._mask_llm_secrets(self.payload)
        return result
