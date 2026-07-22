# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

import requests

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.ai_agno_connector.models.ai_bridge_execution import (
    AiBridgeExecution as ConnectorAiBridgeExecution,
)
from odoo.addons.ai_agno_llm_settings.models.ai_bridge_execution import MASKED_API_KEY
from odoo.addons.ai_agno_llm_settings.models.res_config_settings import (
    AGNO_BASE_URL,
    ICP_API_KEY,
    ICP_BRIDGE_AUTH_TOKEN,
    ICP_EMBEDDER_API_KEY,
    ICP_EMBEDDER_DIMENSIONS,
    ICP_EMBEDDER_HOST,
    ICP_EMBEDDER_MODEL,
    ICP_EMBEDDER_PROVIDER,
    ICP_HOST,
    ICP_MODEL,
    ICP_PROVIDER,
)
from odoo.addons.ai_oca_bridge.models.ai_bridge_execution import (
    AiBridgeExecution as BaseAiBridgeExecution,
)


@tagged("post_install", "-at_install")
class TestAgnoLlmSettings(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Agno LLM Settings Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
                "result_kind": "immediate",
                "result_type": "none",
                "provider": "agno",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "LLM Settings Partner"})
        cls.icp = cls.env["ir.config_parameter"].sudo()
        # Ensure a clean BYOK state for payload tests.
        cls.icp.set_param(ICP_PROVIDER, "")
        cls.icp.set_param(ICP_HOST, "")
        cls.icp.set_param(ICP_MODEL, "")
        cls.icp.set_param(ICP_API_KEY, "")
        cls.icp.set_param(ICP_EMBEDDER_PROVIDER, "")
        cls.icp.set_param(ICP_EMBEDDER_HOST, "")
        cls.icp.set_param(ICP_EMBEDDER_MODEL, "")
        cls.icp.set_param(ICP_EMBEDDER_API_KEY, "")
        cls.icp.set_param(ICP_EMBEDDER_DIMENSIONS, "")

    def _create_execution(self, bridge=None):
        bridge = bridge or self.bridge
        return self.env["ai.bridge.execution"].create(
            {
                "ai_bridge_id": bridge.id,
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.partner.id,
            }
        )

    def _mock_ok_response(self):
        response = mock.Mock()
        response.status_code = 200
        response.content = b'{"ok": true}'
        response.json.return_value = {"ok": True}
        response.raise_for_status = mock.Mock()
        return response

    def test_settings_persist_to_icp(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_llm_provider": "openai",
                "agno_llm_api_key": "sk-test-key",
                "agno_llm_host": "https://api.openai.com/v1",
                "agno_llm_model": "gpt-4o",
            }
        )
        settings.execute()
        self.assertEqual(self.icp.get_param(ICP_PROVIDER), "openai")
        self.assertEqual(self.icp.get_param(ICP_API_KEY), "sk-test-key")
        self.assertEqual(self.icp.get_param(ICP_HOST), "https://api.openai.com/v1")
        self.assertEqual(self.icp.get_param(ICP_MODEL), "gpt-4o")

    def test_settings_require_model_when_provider_set(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_llm_provider": "ollama",
                "agno_llm_host": "http://ollama:11434",
                "agno_llm_model": "",
                "agno_llm_api_key": "",
            }
        )
        with self.assertRaises(UserError):
            settings.execute()

    def test_settings_ollama_allows_empty_api_key(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_llm_provider": "ollama",
                "agno_llm_host": "http://ollama:11434",
                "agno_llm_model": "llama3.2:3b",
                "agno_llm_api_key": "",
            }
        )
        settings.execute()
        self.assertEqual(self.icp.get_param(ICP_PROVIDER), "ollama")
        self.assertEqual(self.icp.get_param(ICP_HOST), "http://ollama:11434")
        self.assertEqual(self.icp.get_param(ICP_MODEL), "llama3.2:3b")

    def test_settings_openai_requires_api_key(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_llm_provider": "openai",
                "agno_llm_host": "https://api.openai.com/v1",
                "agno_llm_model": "gpt-4o",
                "agno_llm_api_key": "",
            }
        )
        with self.assertRaises(UserError):
            settings.execute()

    def test_settings_ollama_requires_host(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_llm_provider": "ollama",
                "agno_llm_host": "",
                "agno_llm_model": "llama3.2:3b",
                "agno_llm_api_key": "",
            }
        )
        with self.assertRaises(UserError):
            settings.execute()

    def test_payload_omits_llm_and_embedder_when_providers_empty(self):
        execution = self._create_execution()
        payload = execution._add_extra_payload_fields({})
        self.assertNotIn("llm", payload["_odoo"])
        self.assertNotIn("embedder", payload["_odoo"])

    def test_payload_skips_llm_for_non_agno_bridge(self):
        self.icp.set_param(ICP_PROVIDER, "openai")
        self.icp.set_param(ICP_HOST, "https://api.openai.com/v1")
        self.icp.set_param(ICP_MODEL, "gpt-4o")
        self.icp.set_param(ICP_API_KEY, "sk-should-not-leak")
        self.icp.set_param(ICP_EMBEDDER_PROVIDER, "openai")
        self.icp.set_param(ICP_EMBEDDER_HOST, "https://api.openai.com/v1")
        self.icp.set_param(ICP_EMBEDDER_MODEL, "text-embedding-3-small")
        self.icp.set_param(ICP_EMBEDDER_DIMENSIONS, "1536")
        self.icp.set_param(ICP_EMBEDDER_API_KEY, "embed-should-not-leak")
        other = self.bridge.copy({"name": "Third Party", "provider": "generic"})
        execution = self._create_execution(bridge=other)
        payload = execution._add_extra_payload_fields({})
        self.assertNotIn("llm", payload["_odoo"])
        self.assertNotIn("embedder", payload["_odoo"])

    def test_execute_sends_api_key_and_masks_stored_payload(self):
        self.icp.set_param(ICP_PROVIDER, "ollama")
        self.icp.set_param(ICP_HOST, "https://ollama.com")
        self.icp.set_param(ICP_MODEL, "qwen3.5:397b-cloud")
        self.icp.set_param(ICP_API_KEY, "secret-client-key")
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_ok_response()
            execution._execute()
            sent = mock_post.call_args.kwargs["json"]
            self.assertEqual(sent["_odoo"]["llm"]["api_key"], "secret-client-key")
            self.assertEqual(sent["_odoo"]["llm"]["model"], "qwen3.5:397b-cloud")
        self.assertEqual(execution.state, "done")
        self.assertEqual(execution.payload["_odoo"]["llm"]["api_key"], MASKED_API_KEY)

    def test_onchange_sets_host_and_model_per_provider(self):
        # Selecting a provider from empty seeds defaults.
        settings = self.env["res.config.settings"].new({"agno_llm_provider": "openai"})
        settings._onchange_agno_llm_provider()
        self.assertEqual(settings.agno_llm_host, "https://api.openai.com/v1")
        self.assertEqual(settings.agno_llm_model, "gpt-4o")
        # Switching provider replaces defaults.
        settings.agno_llm_provider = "ollama"
        settings._onchange_agno_llm_provider()
        self.assertEqual(settings.agno_llm_host, "https://ollama.com")
        self.assertEqual(settings.agno_llm_model, "qwen3.5:397b-cloud")
        settings.agno_llm_provider = "gemini"
        settings._onchange_agno_llm_provider()
        self.assertFalse(settings.agno_llm_host)
        self.assertEqual(settings.agno_llm_model, "gemini-2.0-flash")
        settings.agno_llm_provider = False
        settings._onchange_agno_llm_provider()
        self.assertFalse(settings.agno_llm_host)
        self.assertFalse(settings.agno_llm_model)

    def test_onchange_preserves_custom_values_for_same_provider(self):
        # Simulate Settings opened with ICP values already loaded.
        settings = self.env["res.config.settings"].new(
            {
                "agno_llm_provider": "ollama",
                "agno_llm_host": "http://ollama:11434",
                "agno_llm_model": "llama3.2:3b",
            }
        )
        settings._onchange_agno_llm_provider()
        self.assertEqual(settings.agno_llm_host, "http://ollama:11434")
        self.assertEqual(settings.agno_llm_model, "llama3.2:3b")
        # Spurious re-fire with the same provider must not reset customs.
        settings._onchange_agno_llm_provider()
        self.assertEqual(settings.agno_llm_host, "http://ollama:11434")
        self.assertEqual(settings.agno_llm_model, "llama3.2:3b")

    def test_custom_host_and_model_persist_on_execute(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_llm_provider": "ollama",
                "agno_llm_host": "http://ollama:11434",
                "agno_llm_model": "llama3.2:3b",
                "agno_llm_api_key": "",
            }
        )
        settings.execute()
        self.assertEqual(self.icp.get_param(ICP_HOST), "http://ollama:11434")
        self.assertEqual(self.icp.get_param(ICP_MODEL), "llama3.2:3b")
        reloaded = self.env["res.config.settings"].create({})
        self.assertEqual(reloaded.agno_llm_host, "http://ollama:11434")
        self.assertEqual(reloaded.agno_llm_model, "llama3.2:3b")

    def test_mask_llm_secrets_helper(self):
        execution = self._create_execution()
        payload = {
            "_odoo": {
                "user_id": 1,
                "llm": {"provider": "ollama", "api_key": "plain-secret"},
                "embedder": {"provider": "openai", "api_key": "embed-secret"},
            }
        }
        masked = execution._mask_llm_secrets(payload)
        self.assertEqual(masked["_odoo"]["llm"]["api_key"], MASKED_API_KEY)
        self.assertEqual(masked["_odoo"]["embedder"]["api_key"], MASKED_API_KEY)
        self.assertEqual(payload["_odoo"]["llm"]["api_key"], "plain-secret")
        self.assertEqual(payload["_odoo"]["embedder"]["api_key"], "embed-secret")

    def test_mask_llm_secrets_passthrough_cases(self):
        execution = self._create_execution()
        self.assertEqual(execution._mask_llm_secrets({}), {})
        self.assertFalse(execution._mask_llm_secrets(None))
        without_meta = execution._mask_llm_secrets({"foo": 1})
        self.assertEqual(without_meta, {"foo": 1})
        odd_meta = execution._mask_llm_secrets({"_odoo": "not-a-dict"})
        self.assertEqual(odd_meta, {"_odoo": "not-a-dict"})

    def test_llm_settings_omit_empty_host_and_api_key(self):
        self.icp.set_param(ICP_PROVIDER, "gemini")
        self.icp.set_param(ICP_MODEL, "gemini-2.0-flash")
        execution = self._create_execution()
        llm = execution._get_agno_llm_settings()
        self.assertEqual(llm["provider"], "gemini")
        self.assertNotIn("host", llm)
        self.assertNotIn("api_key", llm)

    def test_embedder_settings_ignore_invalid_dimensions(self):
        self.icp.set_param(ICP_EMBEDDER_PROVIDER, "ollama")
        self.icp.set_param(ICP_EMBEDDER_MODEL, "qwen3-embedding:0.6b")
        self.icp.set_param(ICP_EMBEDDER_DIMENSIONS, "not-a-number")
        execution = self._create_execution()
        embedder = execution._get_agno_embedder_settings()
        self.assertEqual(embedder["provider"], "ollama")
        self.assertNotIn("dimensions", embedder)
        self.assertNotIn("host", embedder)
        self.assertNotIn("api_key", embedder)

    def test_add_extra_payload_fields_without_odoo_meta(self):
        execution = self._create_execution()
        with mock.patch.object(
            ConnectorAiBridgeExecution,
            "_add_extra_payload_fields",
            new=lambda self, payload: payload,
        ):
            payload = execution._add_extra_payload_fields({"data": 1})
        self.assertEqual(payload, {"data": 1})

    def test_execute_skips_mask_when_no_payload(self):
        execution = self._create_execution()
        # Patch the upstream implementation: intermediate overrides
        # (request timeout, error notify) just propagate its result here.
        with mock.patch.object(
            BaseAiBridgeExecution,
            "_execute",
            new=lambda self, **kwargs: "sentinel",
        ):
            result = execution._execute()
        self.assertEqual(result, "sentinel")
        self.assertFalse(execution.payload)

    def test_embedder_settings_persist_to_icp(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_embedder_provider": "ollama",
                "agno_embedder_host": "http://ollama:11434",
                "agno_embedder_model": "qwen3-embedding:0.6b",
                "agno_embedder_dimensions": "1024",
                "agno_embedder_api_key": "",
            }
        )
        settings.execute()
        self.assertEqual(self.icp.get_param(ICP_EMBEDDER_PROVIDER), "ollama")
        self.assertEqual(self.icp.get_param(ICP_EMBEDDER_HOST), "http://ollama:11434")
        self.assertEqual(self.icp.get_param(ICP_EMBEDDER_MODEL), "qwen3-embedding:0.6b")
        self.assertEqual(self.icp.get_param(ICP_EMBEDDER_DIMENSIONS), "1024")

    def test_embedder_openai_requires_api_key(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_embedder_provider": "openai",
                "agno_embedder_host": "https://api.openai.com/v1",
                "agno_embedder_model": "text-embedding-3-small",
                "agno_embedder_dimensions": "1536",
                "agno_embedder_api_key": "",
            }
        )
        with self.assertRaises(UserError):
            settings.execute()

    def test_embedder_requires_dimensions(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_embedder_provider": "ollama",
                "agno_embedder_host": "http://ollama:11434",
                "agno_embedder_model": "qwen3-embedding:0.6b",
                "agno_embedder_dimensions": "",
                "agno_embedder_api_key": "",
            }
        )
        with self.assertRaises(UserError):
            settings.execute()

    def test_embedder_requires_model(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_embedder_provider": "ollama",
                "agno_embedder_host": "http://ollama:11434",
                "agno_embedder_model": "",
                "agno_embedder_dimensions": "1024",
                "agno_embedder_api_key": "",
            }
        )
        with self.assertRaises(UserError):
            settings.execute()

    def test_embedder_dimensions_must_be_positive_integer(self):
        base_values = {
            "agno_embedder_provider": "ollama",
            "agno_embedder_host": "http://ollama:11434",
            "agno_embedder_model": "qwen3-embedding:0.6b",
            "agno_embedder_api_key": "",
        }
        for bad_dims in ("not-a-number", "0", "-5"):
            settings = self.env["res.config.settings"].create(
                dict(base_values, agno_embedder_dimensions=bad_dims)
            )
            with self.assertRaises(UserError):
                settings.execute()

    def test_embedder_ollama_requires_host(self):
        settings = self.env["res.config.settings"].create(
            {
                "agno_embedder_provider": "ollama",
                "agno_embedder_host": "",
                "agno_embedder_model": "qwen3-embedding:0.6b",
                "agno_embedder_dimensions": "1024",
                "agno_embedder_api_key": "",
            }
        )
        with self.assertRaises(UserError):
            settings.execute()

    def test_embedder_onchange_sets_defaults_per_provider(self):
        settings = self.env["res.config.settings"].new(
            {"agno_embedder_provider": "openai"}
        )
        settings._onchange_agno_embedder_provider()
        self.assertEqual(settings.agno_embedder_host, "https://api.openai.com/v1")
        self.assertEqual(settings.agno_embedder_model, "text-embedding-3-small")
        self.assertEqual(settings.agno_embedder_dimensions, "1536")
        settings.agno_embedder_provider = "ollama"
        settings._onchange_agno_embedder_provider()
        self.assertEqual(settings.agno_embedder_host, "http://ollama:11434")
        self.assertEqual(settings.agno_embedder_model, "qwen3-embedding:0.6b")
        self.assertEqual(settings.agno_embedder_dimensions, "1024")

    def test_embedder_onchange_preserves_custom_values(self):
        settings = self.env["res.config.settings"].new(
            {
                "agno_embedder_provider": "ollama",
                "agno_embedder_host": "http://custom:11434",
                "agno_embedder_model": "custom-embed",
                "agno_embedder_dimensions": "512",
            }
        )
        settings._onchange_agno_embedder_provider()
        self.assertEqual(settings.agno_embedder_host, "http://custom:11434")
        self.assertEqual(settings.agno_embedder_model, "custom-embed")
        self.assertEqual(settings.agno_embedder_dimensions, "512")
        settings._onchange_agno_embedder_provider()
        self.assertEqual(settings.agno_embedder_host, "http://custom:11434")

    def test_embedder_onchange_clears_fields_when_provider_removed(self):
        settings = self.env["res.config.settings"].new(
            {"agno_embedder_provider": "ollama"}
        )
        settings._onchange_agno_embedder_provider()
        self.assertEqual(settings.agno_embedder_host, "http://ollama:11434")
        settings.agno_embedder_provider = False
        settings._onchange_agno_embedder_provider()
        self.assertFalse(settings.agno_embedder_host)
        self.assertFalse(settings.agno_embedder_model)
        self.assertFalse(settings.agno_embedder_dimensions)
        self.assertFalse(settings.agno_embedder_last_provider)

    def test_execute_sends_embedder_and_masks_stored_payload(self):
        self.icp.set_param(ICP_EMBEDDER_PROVIDER, "openai")
        self.icp.set_param(ICP_EMBEDDER_HOST, "https://api.openai.com/v1")
        self.icp.set_param(ICP_EMBEDDER_MODEL, "text-embedding-3-small")
        self.icp.set_param(ICP_EMBEDDER_DIMENSIONS, "1536")
        self.icp.set_param(ICP_EMBEDDER_API_KEY, "embed-secret")
        execution = self._create_execution()
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_ok_response()
            execution._execute()
            sent = mock_post.call_args.kwargs["json"]
            self.assertEqual(sent["_odoo"]["embedder"]["api_key"], "embed-secret")
            self.assertEqual(sent["_odoo"]["embedder"]["dimensions"], 1536)
        self.assertEqual(
            execution.payload["_odoo"]["embedder"]["api_key"], MASKED_API_KEY
        )

    def test_reindex_calls_agno_and_syncs_pages_when_kb_installed(self):
        self.icp.set_param(ICP_BRIDGE_AUTH_TOKEN, "reindex-token")
        self.icp.set_param(ICP_EMBEDDER_PROVIDER, "ollama")
        self.icp.set_param(ICP_EMBEDDER_HOST, "http://ollama:11434")
        self.icp.set_param(ICP_EMBEDDER_MODEL, "qwen3-embedding:0.6b")
        self.icp.set_param(ICP_EMBEDDER_DIMENSIONS, "1024")
        settings = self.env["res.config.settings"].create({})
        kb_installed = bool(
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
        with mock.patch(
            "odoo.addons.ai_agno_llm_settings.models.res_config_settings.requests.post"
        ) as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200,
                json=lambda: {
                    "ok": True,
                    "knowledge_bases": [
                        "support",
                        "legal",
                        "processes",
                        "commercial",
                        "public",
                    ],
                },
                text='{"ok": true}',
            )
            sync_target = (
                "odoo.addons.ai_agno_document_page_kb.hooks.sync_kb_pages"
                if kb_installed
                else None
            )
            if sync_target:
                with mock.patch(sync_target) as mock_sync:
                    result = settings.action_reindex_agno_knowledge()
                    mock_sync.assert_called_once()
            else:
                result = settings.action_reindex_agno_knowledge()
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], f"{AGNO_BASE_URL}/bridge/kb/reindex")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer reindex-token")
            self.assertEqual(
                kwargs["json"]["_odoo"]["embedder"]["model"], "qwen3-embedding:0.6b"
            )
            self.assertNotIn("architect", kwargs["json"])
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")

    def test_reindex_requires_bridge_token(self):
        self.icp.set_param(ICP_BRIDGE_AUTH_TOKEN, "")
        settings = self.env["res.config.settings"].create({})
        with mock.patch(
            "odoo.addons.ai_agno_llm_settings.models.res_config_settings.ensure_token",
            return_value="",
        ):
            with self.assertRaises(UserError):
                settings.action_reindex_agno_knowledge()

    def test_reindex_raises_on_agno_error(self):
        self.icp.set_param(ICP_BRIDGE_AUTH_TOKEN, "reindex-token")
        settings = self.env["res.config.settings"].create({})
        with mock.patch(
            "odoo.addons.ai_agno_llm_settings.models.res_config_settings.requests.post"
        ) as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=503,
                text='{"detail":"No embedder configured."}',
                json=lambda: {"detail": "No embedder configured."},
            )
            with self.assertRaises(UserError) as err:
                settings.action_reindex_agno_knowledge()
            self.assertIn("No embedder configured", str(err.exception))

    def test_reindex_raises_when_agno_unreachable(self):
        self.icp.set_param(ICP_BRIDGE_AUTH_TOKEN, "reindex-token")
        settings = self.env["res.config.settings"].create({})
        with mock.patch(
            "odoo.addons.ai_agno_llm_settings.models.res_config_settings.requests.post",
            side_effect=requests.ConnectionError("connection refused"),
        ):
            with self.assertRaises(UserError) as err:
                settings.action_reindex_agno_knowledge()
            self.assertIn("Could not reach Agno", str(err.exception))

    def test_reindex_error_with_non_json_body_uses_raw_text(self):
        self.icp.set_param(ICP_BRIDGE_AUTH_TOKEN, "reindex-token")
        settings = self.env["res.config.settings"].create({})
        response = mock.Mock(status_code=500, text="plain error text")
        response.json.side_effect = ValueError("not json")
        with mock.patch(
            "odoo.addons.ai_agno_llm_settings.models.res_config_settings.requests.post",
            return_value=response,
        ):
            with self.assertRaises(UserError) as err:
                settings.action_reindex_agno_knowledge()
            self.assertIn("plain error text", str(err.exception))

    def test_reindex_error_json_without_detail_keeps_raw_text(self):
        self.icp.set_param(ICP_BRIDGE_AUTH_TOKEN, "reindex-token")
        settings = self.env["res.config.settings"].create({})
        response = mock.Mock(status_code=502, text="bad gateway raw")
        response.json.return_value = ["unexpected", "shape"]
        with mock.patch(
            "odoo.addons.ai_agno_llm_settings.models.res_config_settings.requests.post",
            return_value=response,
        ):
            with self.assertRaises(UserError) as err:
                settings.action_reindex_agno_knowledge()
            self.assertIn("bad gateway raw", str(err.exception))

    def test_reindex_skips_page_sync_when_kb_not_installed(self):
        self.icp.set_param(ICP_BRIDGE_AUTH_TOKEN, "reindex-token")
        settings = self.env["res.config.settings"].create({})
        module_cls = type(self.env["ir.module.module"])
        original_search = module_cls.search

        def fake_search(model, domain, *args, **kwargs):
            # Pretend the KB module is not installed for this domain only.
            if ("name", "=", "ai_agno_document_page_kb") in (domain or []):
                return model.browse()
            return original_search(model, domain, *args, **kwargs)

        with (
            mock.patch(
                "odoo.addons.ai_agno_llm_settings.models."
                "res_config_settings.requests.post"
            ) as mock_post,
            mock.patch.object(module_cls, "search", fake_search),
        ):
            mock_post.return_value = mock.Mock(
                status_code=200,
                json=lambda: {"ok": True},
                text='{"ok": true}',
            )
            result = settings.action_reindex_agno_knowledge()
        self.assertEqual(result["tag"], "display_notification")
        self.assertNotIn("document.page", result["params"]["message"])
