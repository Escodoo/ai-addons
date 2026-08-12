# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..hooks import ICP_KEY, apply_auth_token, post_init_hook


@tagged("post_install", "-at_install")
class TestAiAssistantBridges(TransactionCase):
    def test_bridge_configured(self):
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        self.assertEqual(bridge.usage, "none")
        self.assertEqual(bridge.payload_type, "assistant")
        self.assertEqual(bridge.result_type, "assistant")
        self.assertEqual(bridge.provider, "agno")
        self.assertTrue(bridge.url.endswith("/bridge/assistant/chat"))

    def test_apply_auth_token(self):
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        bridge.auth_token = False
        self.env["ir.config_parameter"].sudo().set_param(ICP_KEY, "assistant-token")
        apply_auth_token(self.env)
        self.assertEqual(bridge.auth_token, "assistant-token")
        post_init_hook(self.env)
        self.assertEqual(bridge.auth_token, "assistant-token")

    def test_prepare_payload_accepts_execution_kwargs(self):
        """Mirror ai.bridge.execution._execute kwargs without res_id collision."""
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        payload = bridge._prepare_payload(
            record=None,
            res_id=0,
            model="ai.assistant",
            message="hello",
            history=[{"role": "user", "content": "hi"}],
            ui_context={"current_model": "purchase.order"},
        )
        self.assertEqual(payload.get("_model"), "ai.assistant")
        self.assertEqual(payload.get("_id"), 0)
        self.assertEqual(payload.get("message"), "hello")
        self.assertEqual(
            payload.get("ui_context", {}).get("current_model"), "purchase.order"
        )

    def test_execution_name_with_abstract_model(self):
        """Creating an execution on ai.assistant must not crash on display_name."""
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        model = self.env["ir.model"]._get("ai.assistant")
        execution = (
            self.env["ai.bridge.execution"]
            .sudo()
            .create(
                {
                    "ai_bridge_id": bridge.id,
                    "model_id": model.id,
                    "res_id": 0,
                }
            )
        )
        self.assertTrue(execution.name)
        self.assertIn(bridge.name, execution.name)
