# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock
from unittest.mock import MagicMock

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.ai_agno_assistant.models import ai_assistant as ai_assistant_mod


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

    def test_sanitize_rejects_non_list_and_non_dict_entries(self):
        self.assertEqual(self.Assistant._sanitize_ai_chat_actions(None), [])
        self.assertEqual(self.Assistant._sanitize_ai_chat_actions("oops"), [])
        actions = self.Assistant._sanitize_ai_chat_actions(
            ["not-a-dict", {"type": "delete_everything"}]
        )
        self.assertEqual(actions, [])

    def test_sanitize_rejects_unknown_xml_id(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": "ai_agno_assistant.does_not_exist"}]
        )
        self.assertEqual(actions, [])

    def test_sanitize_open_action_invalid_xml_id(self):
        self.assertFalse(
            self.Assistant._sanitize_open_action({"type": "open_action", "xml_id": ""})
        )
        self.assertFalse(
            self.Assistant._sanitize_open_action(
                {"type": "open_action", "xml_id": "nodot"}
            )
        )
        self.assertFalse(
            self.Assistant._sanitize_open_action(
                {"type": "open_action", "xml_id": 12345}
            )
        )

    def test_sanitize_open_action_purchase_rfq(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": "purchase.purchase_rfq"}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_action")
        self.assertIn("action", actions[0])
        self.assertEqual(actions[0]["action"].get("type"), "ir.actions.act_window")

    def test_sanitize_open_action_with_domain_and_context(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [
                {
                    "type": "open_action",
                    "xml_id": "purchase.purchase_rfq",
                    "domain": [("state", "=", "draft")],
                    "context": {"search_default_draft": 1},
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["domain"], [("state", "=", "draft")])
        self.assertEqual(actions[0]["context"]["search_default_draft"], 1)
        self.assertIn("search_default_draft", actions[0]["action"]["context"])

    def test_sanitize_open_action_merges_string_base_context(self):
        xml_id = "purchase.purchase_rfq"
        action = dict(self.env["ir.actions.actions"]._for_xml_id(xml_id))
        action["context"] = "{'lang': 'en_US'}"
        with mock.patch.object(
            type(self.env["ir.actions.actions"]),
            "_for_xml_id",
            return_value=action,
        ):
            sanitized = self.Assistant._sanitize_open_action(
                {
                    "type": "open_action",
                    "xml_id": xml_id,
                    "context": {"ai_flag": True},
                }
            )
        self.assertTrue(sanitized)
        self.assertEqual(sanitized["action"]["context"].get("ai_flag"), True)

    def test_sanitize_open_action_rejects_unsupported_type(self):
        with mock.patch.object(
            type(self.env["ir.actions.actions"]),
            "_for_xml_id",
            return_value={"id": 1, "type": "ir.actions.report"},
        ):
            self.assertFalse(
                self.Assistant._sanitize_open_action(
                    {"type": "open_action", "xml_id": "base.action_partner_form"}
                )
            )

    def test_sanitize_open_action_rejects_empty_action_dict(self):
        with mock.patch.object(
            type(self.env["ir.actions.actions"]),
            "_for_xml_id",
            return_value={},
        ):
            self.assertFalse(
                self.Assistant._sanitize_open_action(
                    {"type": "open_action", "xml_id": "base.action_partner_form"}
                )
            )

    def test_sanitize_open_action_ref(self):
        action = self.env.ref("purchase.purchase_rfq")
        actions = self.Assistant._sanitize_ai_chat_actions(
            [
                {
                    "type": "open_action_ref",
                    "action_type": "ir.actions.act_window",
                    "action_id": action.id,
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_action_ref")
        self.assertEqual(actions[0]["action_id"], action.id)

    def test_sanitize_open_action_ref_rejects_invalid(self):
        self.assertFalse(
            self.Assistant._sanitize_open_action_ref(
                {"action_type": "ir.actions.report", "action_id": 1}
            )
        )
        self.assertFalse(
            self.Assistant._sanitize_open_action_ref(
                {"action_type": "ir.actions.act_window", "action_id": "abc"}
            )
        )
        self.assertFalse(
            self.Assistant._sanitize_open_action_ref(
                {"action_type": "ir.actions.act_window", "action_id": 999999999}
            )
        )

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

    def test_sanitize_open_record_invalid_inputs(self):
        self.assertFalse(
            self.Assistant._sanitize_open_record(
                {"model": "res.partner", "res_id": "abc"}
            )
        )
        self.assertFalse(
            self.Assistant._sanitize_open_record({"model": "res.partner", "res_id": 0})
        )
        self.assertFalse(
            self.Assistant._sanitize_open_record({"model": "res.partner", "res_id": -3})
        )
        # Allowed model name that may be missing from the registry.
        missing_model = next(
            (
                name
                for name in (
                    "helpdesk.ticket",
                    "project.task",
                    "project.project",
                )
                if name not in self.env
            ),
            None,
        )
        if missing_model:
            self.assertFalse(
                self.Assistant._sanitize_open_record(
                    {"model": missing_model, "res_id": 1}
                )
            )

    def test_sanitize_open_record_access_denied(self):
        partner = self.env["res.partner"].create({"name": "AI Access Denied Partner"})
        with mock.patch.object(
            type(partner),
            "check_access",
            side_effect=AccessError("denied"),
        ):
            self.assertFalse(
                self.Assistant._sanitize_open_record(
                    {"model": "res.partner", "res_id": partner.id}
                )
            )

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

    def test_sanitize_open_menu_rejects_invalid(self):
        self.assertFalse(self.Assistant._sanitize_open_menu({"menu_xml_id": "nodot"}))
        self.assertFalse(
            self.Assistant._sanitize_open_menu(
                {"menu_xml_id": "ai_agno_assistant.missing_menu"}
            )
        )
        # Point at a non-menu xml id.
        self.assertFalse(
            self.Assistant._sanitize_open_menu({"menu_xml_id": "purchase.purchase_rfq"})
        )

    def test_sanitize_open_menu_no_resolvable_action(self):
        menu = self.env["ir.ui.menu"].create(
            {
                "name": "AI Empty Menu",
                "parent_id": self.env.ref("base.menu_administration").id,
            }
        )
        self.env["ir.model.data"].create(
            {
                "name": "menu_ai_empty_test",
                "module": "ai_agno_assistant",
                "model": "ir.ui.menu",
                "res_id": menu.id,
            }
        )
        with mock.patch.object(
            type(self.env["ir.ui.menu"]),
            "_visible_menu_ids",
            return_value=frozenset({menu.id}),
        ):
            self.assertFalse(
                self.Assistant._sanitize_open_menu(
                    {"menu_xml_id": "ai_agno_assistant.menu_ai_empty_test"}
                )
            )

    def test_sanitize_open_root_app_menu_resolves_child(self):
        """Root apps (Invoicing) have no action; resolve the first child screen."""
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_menu", "menu_xml_id": "account.menu_finance"}]
        )
        self.assertEqual(len(actions), 1)
        self.assertIn("action", actions[0])
        self.assertTrue(actions[0]["action"].get("type"))

    def test_sanitize_open_action_crm_pipeline(self):
        if not self.env.ref("crm.crm_lead_action_pipeline", raise_if_not_found=False):
            self.skipTest("crm pipeline action is not available")
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

    def test_action_record_to_dict_empty_and_fallback(self):
        self.assertFalse(self.Assistant._action_record_to_dict(False))
        action = self.env.ref("purchase.purchase_rfq")
        with (
            mock.patch.object(
                type(action),
                "get_external_id",
                return_value={action.id: "purchase.purchase_rfq"},
            ),
            mock.patch.object(
                type(self.env["ir.actions.actions"]),
                "_for_xml_id",
                side_effect=ValueError("broken"),
            ),
        ):
            action_dict = self.Assistant._action_record_to_dict(action)
        self.assertEqual(action_dict["type"], "ir.actions.act_window")
        self.assertEqual(action_dict["id"], action.id)

        with mock.patch.object(
            type(action),
            "get_external_id",
            return_value={},
        ):
            action_dict = self.Assistant._action_record_to_dict(action)
        self.assertEqual(action_dict["type"], "ir.actions.act_window")

    def test_resolve_menu_to_action_guards(self):
        menu = self.env.ref("purchase.menu_purchase_form_action")
        self.assertFalse(self.Assistant._resolve_menu_to_action(False))
        self.assertFalse(self.Assistant._resolve_menu_to_action(self.env.user))
        self.assertFalse(self.Assistant._resolve_menu_to_action(menu, _seen={menu.id}))
        self.assertFalse(
            self.Assistant._resolve_menu_to_action(menu, visible_ids=set())
        )
        empty = self.env["ir.ui.menu"].create(
            {
                "name": "AI Orphan Menu",
                "parent_id": self.env.ref("base.menu_administration").id,
            }
        )
        self.assertFalse(
            self.Assistant._resolve_menu_to_action(empty, visible_ids={empty.id})
        )

    def test_normalize_ai_chat_history(self):
        self.assertEqual(self.Assistant._normalize_ai_chat_history(None), [])
        self.assertEqual(self.Assistant._normalize_ai_chat_history("x"), [])
        long_content = "x" * (ai_assistant_mod._AI_CHAT_MESSAGE_MAX_LEN + 50)
        cleaned = self.Assistant._normalize_ai_chat_history(
            [
                "skip",
                {"role": "system", "content": "nope"},
                {"role": "user", "content": "  "},
                {"role": "user", "content": " hello "},
                {"role": "assistant", "content": long_content},
            ]
        )
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(cleaned[0], {"role": "user", "content": "hello"})
        self.assertEqual(
            len(cleaned[1]["content"]), ai_assistant_mod._AI_CHAT_MESSAGE_MAX_LEN
        )

    def test_normalize_ui_context(self):
        self.assertEqual(self.Assistant._normalize_ui_context(None), {})
        self.assertEqual(self.Assistant._normalize_ui_context("x"), {})
        cleaned = self.Assistant._normalize_ui_context(
            {
                "current_action": "a" * 250,
                "current_model": "purchase.order",
                "current_res_id": "42",
                "company_id": "",
                "ignored": True,
            }
        )
        self.assertEqual(cleaned["current_action"], "a" * 200)
        self.assertEqual(cleaned["current_model"], "purchase.order")
        self.assertEqual(cleaned["current_res_id"], 42)
        self.assertIs(cleaned["company_id"], False)

        cleaned = self.Assistant._normalize_ui_context(
            {
                "current_res_id": "not-int",
                "company_id": "7",
                "current_model": 123,
            }
        )
        self.assertIs(cleaned["current_res_id"], False)
        self.assertEqual(cleaned["company_id"], 7)
        self.assertEqual(cleaned["current_model"], 123)

        cleaned = self.Assistant._normalize_ui_context({"company_id": object()})
        self.assertIs(cleaned["company_id"], False)

    def test_find_navigation_pipeline(self):
        if (
            self.env["ir.module.module"].search_count(
                [("name", "=", "crm"), ("state", "=", "installed")]
            )
            == 0
        ):
            self.skipTest("crm is not installed")
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

    def test_find_navigation_missing_query_and_bad_limit(self):
        self.assertEqual(
            self.Assistant.find_navigation(query="a").get("error"), "missing_query"
        )
        result = self.Assistant.find_navigation(query="purchase", limit="bad")
        self.assertNotIn("error", result)
        self.assertLessEqual(len(result["results"]), 8)

    def test_find_navigation_not_found(self):
        result = self.Assistant.find_navigation(
            query="zzzxxyyunlikelymenuname999", limit=5
        )
        self.assertEqual(result.get("error"), "not_found")

    def test_find_navigation_respects_limit(self):
        result = self.Assistant.find_navigation(query="purchase", limit=1)
        self.assertNotIn("error", result)
        self.assertEqual(len(result["results"]), 1)

    def test_navigation_menu_result_branches(self):
        menu = self.env.ref("purchase.menu_purchase_form_action")
        self.assertFalse(self.Assistant._navigation_menu_result(menu, set()))
        empty = self.env["ir.ui.menu"].create(
            {
                "name": "AI Nav Empty",
                "parent_id": self.env.ref("base.menu_administration").id,
            }
        )
        self.assertFalse(self.Assistant._navigation_menu_result(empty, {empty.id}))

        action = self.env.ref("purchase.purchase_rfq")
        orphan_menu = self.env["ir.ui.menu"].create(
            {
                "name": "AI Nav Orphan Action Menu",
                "parent_id": self.env.ref("base.menu_administration").id,
                "action": f"ir.actions.act_window,{action.id}",
            }
        )
        with mock.patch.object(
            type(orphan_menu),
            "get_external_id",
            return_value={},
        ):
            entry = self.Assistant._navigation_menu_result(
                orphan_menu, {orphan_menu.id}
            )
        self.assertTrue(entry)
        self.assertEqual(entry["suggested_action"]["type"], "open_action")
        self.assertEqual(entry["suggested_action"]["xml_id"], "purchase.purchase_rfq")

        with (
            mock.patch.object(
                type(orphan_menu),
                "get_external_id",
                return_value={},
            ),
            mock.patch.object(
                type(action),
                "get_external_id",
                return_value={},
            ),
        ):
            entry = self.Assistant._navigation_menu_result(
                orphan_menu, {orphan_menu.id}
            )
        self.assertEqual(entry["suggested_action"]["type"], "open_action_ref")
        self.assertEqual(entry["suggested_action"]["action_id"], action.id)

    def test_append_menu_navigation_dedupe_and_skip(self):
        menu = self.env.ref("purchase.menu_purchase_form_action")
        results = []
        seen = set()
        self.Assistant._append_menu_navigation_results(
            menu + menu, {menu.id}, results, seen, limit=5
        )
        self.assertEqual(len(results), 1)
        # Second pass hits the dedupe key already in seen.
        self.Assistant._append_menu_navigation_results(
            menu, {menu.id}, results, seen, limit=5
        )
        self.assertEqual(len(results), 1)
        # Invisible / empty menus are skipped.
        empty = self.env["ir.ui.menu"].create(
            {
                "name": "AI Skip Menu",
                "parent_id": self.env.ref("base.menu_administration").id,
            }
        )
        before = len(results)
        self.Assistant._append_menu_navigation_results(
            empty, set(), results, seen, limit=5
        )
        self.assertEqual(len(results), before)
        # Limit break.
        results = [{"name": "existing"}]
        seen = set()
        self.Assistant._append_menu_navigation_results(
            menu, {menu.id}, results, seen, limit=1
        )
        self.assertEqual(len(results), 1)

    def test_append_window_navigation_results_guards(self):
        results = [{"name": "full"}]
        seen = set()
        self.Assistant._append_window_navigation_results(
            ["purchase"], results, seen, limit=1
        )
        self.assertEqual(len(results), 1)

        results = []
        seen = {"purchase.purchase_rfq"}
        action = self.env.ref("purchase.purchase_rfq")
        with (
            mock.patch.object(
                type(self.env["ir.actions.act_window"]),
                "search",
                return_value=action,
            ),
            mock.patch.object(
                type(self.env["ir.actions.actions"]),
                "_for_xml_id",
                side_effect=ValueError("nope"),
            ),
        ):
            self.Assistant._append_window_navigation_results(
                ["purchase"], results, seen, limit=5
            )
        self.assertEqual(results, [])

        results = []
        seen = set()
        with (
            mock.patch.object(
                type(action),
                "get_external_id",
                return_value={},
            ),
            mock.patch.object(
                type(self.env["ir.actions.act_window"]),
                "search",
                return_value=action,
            ),
        ):
            self.Assistant._append_window_navigation_results(
                ["purchase"], results, seen, limit=5
            )
        self.assertEqual(results, [])

    def test_action_ai_chat_requires_message(self):
        with self.assertRaises(UserError):
            self.Assistant.action_ai_chat(message="   ")

    def test_action_ai_chat_requires_group(self):
        self.env.user.groups_id = [(3, self.ai_group.id)]
        with self.assertRaises(AccessError):
            self.Assistant.action_ai_chat(message="hello")

    def test_action_ai_chat_truncates_and_returns_sanitized(self):
        long_message = "q" * (ai_assistant_mod._AI_CHAT_MESSAGE_MAX_LEN + 10)
        captured = {}

        def _fake_bridge(**kwargs):
            captured.update(kwargs)
            return {
                "body": "<p>ok</p>",
                "body_is_html": True,
                "actions": [
                    {"type": "open_action", "xml_id": "purchase.purchase_rfq"},
                    {"type": "delete_everything"},
                ],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(
                message=long_message,
                history=[{"role": "user", "content": "prev"}],
                ui_context={"current_model": "purchase.order", "current_res_id": 1},
            )
        self.assertEqual(
            len(captured["message"]), ai_assistant_mod._AI_CHAT_MESSAGE_MAX_LEN
        )
        self.assertEqual(captured["history"][0]["content"], "prev")
        self.assertEqual(captured["ui_context"]["current_model"], "purchase.order")
        self.assertEqual(result["body"], "<p>ok</p>")
        self.assertTrue(result["body_is_html"])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["type"], "open_action")

    def test_run_assistant_bridge_not_configured(self):
        bridge_xml = "ai_agno_assistant.ai_bridge_assistant_chat"
        real_ref = self.env.ref

        def fake_ref(xmlid, raise_if_not_found=True):
            if xmlid == bridge_xml:
                if raise_if_not_found:
                    raise ValueError(xmlid)
                return self.env["ai.bridge"]
            return real_ref(xmlid, raise_if_not_found=raise_if_not_found)

        with mock.patch.object(type(self.env), "ref", side_effect=fake_ref):
            with self.assertRaises(UserError):
                self.Assistant._run_assistant_bridge(message="hi")

    def test_run_assistant_bridge_inactive(self):
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        bridge.active = False
        with self.assertRaises(UserError):
            self.Assistant._run_assistant_bridge(message="hi")

    def test_run_assistant_bridge_group_denied(self):
        bridge = self.env.ref("ai_agno_assistant.ai_bridge_assistant_chat")
        restricted_group = self.env.ref("base.group_system")
        bridge.group_ids = [(6, 0, [restricted_group.id])]
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "AI Bridge Limited User",
                    "login": "ai_bridge_limited_user",
                    "groups_id": [(6, 0, [self.ai_group.id])],
                }
            )
        )
        with self.assertRaises(UserError):
            self.Assistant.with_user(user)._run_assistant_bridge(message="hi")

    def test_run_assistant_bridge_success_and_error(self):
        fake_execution = MagicMock()
        fake_execution.state = "done"
        fake_execution._execute.return_value = {"body": "hello", "actions": []}
        sudo_rs = MagicMock()
        sudo_rs.create.return_value = fake_execution
        with mock.patch.object(
            type(self.env["ai.bridge.execution"]),
            "sudo",
            return_value=sudo_rs,
        ):
            result = self.Assistant._run_assistant_bridge(message="hi")
        self.assertEqual(result["body"], "hello")
        fake_execution._execute.assert_called()

        fake_execution.state = "error"
        fake_execution.error = "boom"
        with mock.patch.object(
            type(self.env["ai.bridge.execution"]),
            "sudo",
            return_value=sudo_rs,
        ):
            with self.assertRaises(UserError):
                self.Assistant._run_assistant_bridge(message="hi")
