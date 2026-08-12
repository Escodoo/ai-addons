# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAiAssistantSanitize(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]

    def test_sanitize_rejects_unknown_action_type(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "delete_everything"}]
        )
        self.assertEqual(actions, [])

    def test_sanitize_rejects_unknown_xml_id(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": "ai_agno_assistant.does_not_exist"}]
        )
        self.assertEqual(actions, [])

    def test_sanitize_open_action_purchase_rfq(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": "purchase.purchase_rfq"}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_action")
        self.assertIn("action", actions[0])
        self.assertEqual(actions[0]["action"].get("type"), "ir.actions.act_window")

    def test_sanitize_open_record_requires_access(self):
        partner = self.env["res.partner"].create({"name": "AI Assistant Partner"})
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_record", "model": "res.partner", "res_id": partner.id}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["res_id"], partner.id)

        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_record", "model": "res.partner", "res_id": 999999999}]
        )
        self.assertEqual(actions, [])

        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_record", "model": "ir.config_parameter", "res_id": 1}]
        )
        self.assertEqual(actions, [])

    def test_sanitize_open_menu(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [
                {
                    "type": "open_menu",
                    "menu_xml_id": "purchase.menu_purchase_form_action",
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_menu")
        self.assertIn("action", actions[0])

    def test_sanitize_open_root_app_menu_resolves_child(self):
        """Root apps (Invoicing) have no action; resolve the first child screen."""
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_menu", "menu_xml_id": "account.menu_finance"}]
        )
        self.assertEqual(len(actions), 1)
        self.assertIn("action", actions[0])
        self.assertTrue(actions[0]["action"].get("type"))

    def test_sanitize_open_action_crm_pipeline(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": "crm.crm_lead_action_pipeline"}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_action")

    def test_sanitize_open_action_menu_xml_id_fallback(self):
        """LLM sometimes passes a menu xml id as open_action."""
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": "account.menu_finance"}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_menu")

    def test_find_navigation_pipeline(self):
        result = self.Assistant.find_navigation(query="funil", limit=8)
        self.assertNotIn("error", result)
        self.assertTrue(result.get("results"))
        suggested = [
            row.get("suggested_action")
            for row in result["results"]
            if row.get("suggested_action")
        ]
        self.assertTrue(suggested)

    def test_find_navigation_invoicing(self):
        result = self.Assistant.find_navigation(query="faturamento", limit=8)
        self.assertNotIn("error", result)
        names = " ".join(
            (row.get("name") or "").lower() for row in result.get("results") or []
        )
        menu_ids = {row.get("menu_xml_id") for row in result.get("results") or []}
        action_ids = {row.get("action_xml_id") for row in result.get("results") or []}
        self.assertTrue(
            "account.menu_finance" in menu_ids
            or "invoicing" in names
            or "faturamento" in names
            or any(xml and xml.startswith("account.") for xml in menu_ids | action_ids),
            result,
        )
        self.assertTrue(
            all(row.get("suggested_action") for row in result["results"]),
            result,
        )

    def test_action_ai_chat_requires_message(self):
        with self.assertRaises(UserError):
            self.Assistant.action_ai_chat(message="   ")

    def test_action_ai_chat_requires_group(self):
        self.env.user.groups_id = [(3, self.ai_group.id)]
        with self.assertRaises(AccessError):
            self.Assistant.action_ai_chat(message="hello")
