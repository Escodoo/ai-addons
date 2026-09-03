# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest import mock
from unittest.mock import MagicMock

from odoo import _, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from odoo.addons.ai_agno_assistant.models import ai_assistant as ai_assistant_mod


@tagged("post_install", "-at_install")
class TestAiAssistantSanitize(TransactionCase):
    # Always available act_window / menu (no business app dependency).
    _STABLE_ACTION_XMLID = "base.ir_sequence_actions"
    _STABLE_MENU_XMLID = "base.menu_ir_sequence_form"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]
        cls.has_purchase = "purchase.order" in cls.env
        cls.stable_action = cls.env.ref(cls._STABLE_ACTION_XMLID)
        cls.stable_menu = cls.env.ref(cls._STABLE_MENU_XMLID)

    def _require_purchase(self):
        if not self.has_purchase:  # pragma: no cover
            self.skipTest("Purchase app is not installed")

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
            [{"type": "open_action", "xml_id": self._STABLE_ACTION_XMLID}]
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
                    "xml_id": self._STABLE_ACTION_XMLID,
                    "domain": [("code", "=", "draft")],
                    "context": {"search_default_draft": 1},
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["domain"], [["code", "=", "draft"]])
        self.assertEqual(actions[0]["context"]["search_default_draft"], 1)
        self.assertIn("search_default_draft", actions[0]["action"]["context"])

    def test_sanitize_open_action_drops_invalid_domain(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [
                {
                    "type": "open_action",
                    "xml_id": self._STABLE_ACTION_XMLID,
                    "domain": "state = draft",
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertNotIn("domain", actions[0])

        actions = self.Assistant._sanitize_ai_chat_actions(
            [
                {
                    "type": "open_action",
                    "xml_id": self._STABLE_ACTION_XMLID,
                    "domain": [("code", "bogus_op", "draft")],
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertNotIn("domain", actions[0])

    def test_sanitize_open_action_filters_unsafe_context(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [
                {
                    "type": "open_action",
                    "xml_id": self._STABLE_ACTION_XMLID,
                    "context": {
                        "search_default_draft": 1,
                        "uid": 1,
                        "api_token": "secret",
                        "bad-key": 1,
                        "obj": object(),
                    },
                }
            ]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["context"], {"search_default_draft": 1})
        self.assertEqual(actions[0]["action"]["context"].get("search_default_draft"), 1)
        self.assertNotIn("uid", actions[0]["action"]["context"])
        self.assertNotIn("api_token", actions[0]["action"]["context"])

    def test_sanitize_action_domain_guards(self):
        sanitize = self.Assistant._sanitize_action_domain
        self.assertFalse(sanitize("not-a-list"))
        self.assertEqual(sanitize([]), [])
        self.assertEqual(
            sanitize(["|", ("code", "=", "a"), ("code", "=", "b")]),
            ["|", ["code", "=", "a"], ["code", "=", "b"]],
        )
        self.assertFalse(sanitize([("code", "=", object())]))
        self.assertFalse(sanitize([("code",)]))
        too_many = [("code", "=", str(i)) for i in range(21)]
        self.assertFalse(sanitize(too_many))
        # Malformed operator shape rejected by normalize_domain.
        self.assertFalse(sanitize(["|", ("code", "=", "a")]))

    def test_is_json_safe_value_limits(self):
        safe = self.Assistant._is_json_safe_value
        self.assertTrue(safe(None))
        self.assertTrue(safe(True))
        self.assertTrue(safe(1.5))
        self.assertTrue(safe("ok"))
        self.assertFalse(safe("x" * 501))
        self.assertFalse(safe(["a"] * 51))
        self.assertTrue(safe(["a", 1, None]))
        self.assertFalse(safe({f"k{i}": i for i in range(41)}))
        self.assertFalse(safe({"bad-key": 1}))
        self.assertFalse(safe({"nested": {"too": {"deep": {"x": 1}}}}))
        self.assertFalse(safe(object()))
        self.assertFalse(safe({"ok": object()}))
        self.assertTrue(safe({"ok": 1, "nested": {"flag": True}}))
        self.assertFalse(safe({1: "x"}))

    def test_sanitize_action_context_limits_and_types(self):
        self.assertFalse(self.Assistant._sanitize_action_context("nope"))
        self.assertFalse(self.Assistant._sanitize_action_context({}))
        large = {f"key_{i}": i for i in range(50)}
        cleaned = self.Assistant._sanitize_action_context(large)
        self.assertEqual(len(cleaned), 40)
        cleaned = self.Assistant._sanitize_action_context(
            {
                1: "skip-non-str-key",
                "ok_flag": True,
                "password": "secret",
                "user_secret": 1,
                "unsafe": object(),
            }
        )
        self.assertEqual(cleaned, {"ok_flag": True})

    def test_navigation_search_terms_aliases(self):
        terms = self.Assistant._navigation_search_terms("purchase")
        self.assertIn("purchase", terms)
        self.assertIn("compras", terms)
        self.assertIn("rfq", terms)
        terms = self.Assistant._navigation_search_terms("crm pipeline")
        self.assertIn("crm", terms)
        self.assertIn("pipeline", terms)
        self.assertIn("funil", terms)
        terms = self.Assistant._navigation_search_terms("vendas")
        self.assertIn("sales", terms)
        self.assertEqual(self.Assistant._navigation_search_terms("x"), [])
        self.assertEqual(
            self.Assistant._menu_domain_for_terms([]),
            [("id", "=", False)],
        )

    def test_sanitize_open_action_merges_string_base_context(self):
        xml_id = self._STABLE_ACTION_XMLID
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
        action = self.stable_action
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
        # Whitelisted type missing from the registry.
        original_contains = type(self.env).__contains__

        def fake_contains(env, key):
            if key == "ir.actions.act_url":
                return False
            return original_contains(env, key)

        with mock.patch.object(type(self.env), "__contains__", fake_contains):
            self.assertFalse(
                self.Assistant._sanitize_open_action_ref(
                    {"action_type": "ir.actions.act_url", "action_id": 1}
                )
            )
        # Record exists but cannot be turned into a client action dict.
        action = self.stable_action
        with mock.patch.object(
            type(self.Assistant),
            "_action_record_to_dict",
            return_value=False,
        ):
            self.assertFalse(
                self.Assistant._sanitize_open_action_ref(
                    {
                        "action_type": "ir.actions.act_window",
                        "action_id": action.id,
                    }
                )
            )

    def test_sanitize_open_record_requires_access(self):
        partner = self.env["res.partner"].create({"name": "AI Assistant Partner"})
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_record", "model": "res.partner", "res_id": partner.id}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["res_id"], partner.id)
        self.assertEqual(actions[0]["name"], partner.display_name)

        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_record", "model": "res.partner", "res_id": 999999999}]
        )
        self.assertEqual(actions, [])

        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_record", "model": "ir.config_parameter", "res_id": 1}]
        )
        self.assertEqual(actions, [])

        country = self.env.ref("base.br")
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_record", "model": "res.country", "res_id": country.id}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["model"], "res.country")
        self.assertTrue(actions[0].get("label"))

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
        original_contains = type(self.env).__contains__

        def fake_contains(env, key):
            if key == "purchase.order":
                return False
            return original_contains(env, key)

        with mock.patch.object(type(self.env), "__contains__", fake_contains):
            self.assertFalse(
                self.Assistant._sanitize_open_record(
                    {"model": "purchase.order", "res_id": 1}
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

    def test_sanitize_open_record_coerces_non_string_display_name(self):
        partner = self.env["res.partner"].create({"name": "AI NonStr Name"})
        with mock.patch.object(
            type(partner),
            "display_name",
            new_callable=mock.PropertyMock,
            return_value=12345,
        ):
            sanitized = self.Assistant._sanitize_open_record(
                {"model": "res.partner", "res_id": partner.id}
            )
        self.assertEqual(sanitized["name"], "12345")

    def test_sanitize_open_menu(self):
        actions = self.Assistant._sanitize_ai_chat_actions(
            [
                {
                    "type": "open_menu",
                    "menu_xml_id": self._STABLE_MENU_XMLID,
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
            self.Assistant._sanitize_open_menu(
                {"menu_xml_id": self._STABLE_ACTION_XMLID}
            )
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
        """Root apps often have no action; resolve the first child screen."""
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_menu", "menu_xml_id": "base.menu_administration"}]
        )
        self.assertEqual(len(actions), 1)
        self.assertIn("action", actions[0])
        self.assertTrue(actions[0]["action"].get("type"))

    def test_sanitize_open_action_stable_form(self):
        """Sanitize a core act_window that does not need business apps."""
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": self._STABLE_ACTION_XMLID}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_action")

    def test_sanitize_open_action_menu_xml_id_fallback(self):
        """LLM sometimes passes a menu xml id as open_action."""
        actions = self.Assistant._sanitize_ai_chat_actions(
            [{"type": "open_action", "xml_id": self._STABLE_MENU_XMLID}]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "open_menu")

    def test_action_record_to_dict_empty_and_fallback(self):
        self.assertFalse(self.Assistant._action_record_to_dict(False))
        action = self.stable_action
        with (
            mock.patch.object(
                type(action),
                "get_external_id",
                return_value={action.id: self._STABLE_ACTION_XMLID},
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
        menu = self.stable_menu
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
                "current_model": "res.partner",
                "current_res_id": "42",
                "company_id": "",
                "ignored": True,
            }
        )
        self.assertEqual(cleaned["current_action"], "a" * 200)
        self.assertEqual(cleaned["current_model"], "res.partner")
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

    def test_find_navigation_purchases(self):
        """Alias expansion for purchases when the Purchase app is installed."""
        self._require_purchase()
        result = self.Assistant.find_navigation(query="compras", limit=8)
        self.assertNotIn("error", result)
        self.assertTrue(result.get("results"))
        suggested = [
            row.get("suggested_action")
            for row in result["results"]
            if row.get("suggested_action")
        ]
        self.assertTrue(suggested)

    def test_find_navigation_settings(self):
        """Core menus are always searchable without business apps."""
        result = self.Assistant.find_navigation(query="sequence", limit=8)
        self.assertNotIn("error", result)
        self.assertTrue(result.get("results"))
        self.assertTrue(
            all(row.get("suggested_action") for row in result["results"]),
            result,
        )

    def test_find_navigation_invoicing(self):
        if "account.move" not in self.env:  # pragma: no cover
            self.skipTest("Accounting app is not installed")
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
        result = self.Assistant.find_navigation(query="sequence", limit="bad")
        self.assertNotIn("error", result)
        self.assertLessEqual(len(result["results"]), 8)

    def test_find_navigation_not_found(self):
        result = self.Assistant.find_navigation(
            query="zzzxxyyunlikelymenuname999", limit=5
        )
        self.assertEqual(result.get("error"), "not_found")

    def test_find_navigation_respects_limit(self):
        result = self.Assistant.find_navigation(query="sequence", limit=1)
        self.assertNotIn("error", result)
        self.assertEqual(len(result["results"]), 1)

    def test_navigation_menu_result_branches(self):
        menu = self.stable_menu
        self.assertFalse(self.Assistant._navigation_menu_result(menu, set()))
        empty = self.env["ir.ui.menu"].create(
            {
                "name": "AI Nav Empty",
                "parent_id": self.env.ref("base.menu_administration").id,
            }
        )
        self.assertFalse(self.Assistant._navigation_menu_result(empty, {empty.id}))

        action = self.stable_action
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
        self.assertEqual(entry["suggested_action"]["xml_id"], self._STABLE_ACTION_XMLID)

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

    def test_xmlid_cache_helpers(self):
        empty = self.Assistant._prefetch_external_ids([self.env["ir.ui.menu"].browse()])
        self.assertEqual(empty, {})
        self.assertFalse(self.Assistant._xmlid_from_cache({}, "", 1))
        self.assertFalse(self.Assistant._xmlid_from_cache({}, "ir.ui.menu", 0))
        self.assertFalse(self.Assistant._xmlid_from_cache({}, "ir.ui.menu", 1))
        cache = {("ir.ui.menu", self.stable_menu.id): False}
        self.assertFalse(
            self.Assistant._xmlid_from_cache(cache, "ir.ui.menu", self.stable_menu.id)
        )
        cache = {}
        xmlid = self.Assistant._xmlid_from_cache(
            cache, self.stable_menu._name, self.stable_menu.id, record=self.stable_menu
        )
        self.assertEqual(xmlid, self._STABLE_MENU_XMLID)
        self.assertEqual(
            cache[(self.stable_menu._name, self.stable_menu.id)],
            self._STABLE_MENU_XMLID,
        )

    def test_navigation_menu_result_unknown_action_type(self):
        menu = self.stable_menu
        with (
            mock.patch.object(
                type(self.Assistant),
                "_resolve_menu_to_action",
                return_value={"type": "ir.actions.missing", "id": 99},
            ),
            mock.patch.object(type(menu), "get_external_id", return_value={}),
        ):
            entry = self.Assistant._navigation_menu_result(menu, {menu.id})
        self.assertFalse(entry["action_xml_id"])
        self.assertEqual(entry["suggested_action"]["type"], "open_action_ref")
        self.assertEqual(entry["suggested_action"]["action_type"], "ir.actions.missing")

    def test_append_menu_navigation_dedupe_and_skip(self):
        menu = self.stable_menu
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
            ["sequence"], results, seen, limit=1
        )
        self.assertEqual(len(results), 1)

        results = []
        seen = set()
        action = self.stable_action
        # Keep a real xml id so the ValueError branch is reached (not the
        # ``xml in seen`` continue that previously short-circuited this test).
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

        # Happy path: a resolvable window action is appended.
        results = []
        seen = set()
        self.Assistant._append_window_navigation_results(
            ["sequence"], results, seen, limit=5
        )
        self.assertTrue(results)
        self.assertEqual(results[0]["suggested_action"]["type"], "open_action")
        self.assertTrue(results[0]["action_xml_id"])
        # Dedupe via seen + inner limit break.
        before = len(results)
        self.Assistant._append_window_navigation_results(
            ["sequence"], results, seen, limit=before
        )
        self.assertEqual(len(results), before)

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
                    {
                        "type": "open_action",
                        "xml_id": self._STABLE_ACTION_XMLID,
                    },
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
                ui_context={"current_model": "res.partner", "current_res_id": 1},
            )
        self.assertEqual(
            len(captured["message"]), ai_assistant_mod._AI_CHAT_MESSAGE_MAX_LEN
        )
        self.assertEqual(captured["history"][0]["content"], "prev")
        self.assertEqual(captured["ui_context"]["current_model"], "res.partner")
        self.assertEqual(result["body"], "<p>ok</p>")
        self.assertTrue(result["body_is_html"])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["type"], "open_action")

    def test_action_ai_chat_sanitizes_html_body(self):
        def _fake_bridge(**kwargs):
            return {
                "body": (
                    "<p>Hello</p><script>alert(1)</script>"
                    '<img src=x onerror="alert(1)">'
                ),
                "body_is_html": True,
                "actions": [],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="hi")
        body = result["body"]
        self.assertIn("Hello", body)
        self.assertNotIn("<script", body.lower())
        self.assertNotIn("onerror", body.lower())

    def test_action_ai_chat_escapes_plain_body(self):
        def _fake_bridge(**kwargs):
            return {
                "body": "<b>plain</b>",
                "body_is_html": False,
                "actions": [],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="hi")
        self.assertFalse(result["body_is_html"])
        self.assertEqual(result["body"], "&lt;b&gt;plain&lt;/b&gt;")

    def test_sanitize_assistant_body_coerces_empty_and_non_str(self):
        sanitize = self.Assistant._sanitize_assistant_body
        self.assertEqual(sanitize(None, True), "")
        self.assertEqual(sanitize(False, False), "")
        self.assertEqual(sanitize("", True), "")
        self.assertEqual(sanitize(42, False), "42")
        self.assertIn("ok", sanitize("<b>ok</b>", True))
        self.assertEqual(sanitize("<b>ok</b>", False), "&lt;b&gt;ok&lt;/b&gt;")

    def test_is_backend_record_href_rejects_unsafe_and_plain_urls(self):
        is_backend = ai_assistant_mod._is_backend_record_href
        self.assertFalse(is_backend(""))
        self.assertFalse(is_backend("javascript:alert(1)"))
        self.assertFalse(is_backend("data:text/html,x"))
        self.assertFalse(is_backend("vbscript:msg"))
        self.assertFalse(is_backend("https://example.com"))
        self.assertFalse(is_backend("/web#action=42"))
        self.assertFalse(is_backend("#home"))
        self.assertTrue(is_backend("/web#id=8&model=helpdesk.ticket"))
        self.assertTrue(is_backend("#id=8"))
        self.assertTrue(is_backend("#model=helpdesk.ticket"))

    def test_strip_assistant_record_links_keeps_safe_anchors(self):
        strip = self.Assistant._strip_assistant_record_links
        self.assertEqual(strip(""), "")
        self.assertEqual(strip("<p>No link</p>"), "<p>No link</p>")
        body = (
            '<p><a href="/web#id=8&amp;model=helpdesk.ticket">Ticket</a></p>'
            '<p><a href="https://example.com">docs</a></p>'
            '<p><a href="#id=9">hash</a></p>'
        )
        cleaned = strip(body)
        self.assertNotIn("Ticket", cleaned)
        self.assertNotIn("hash", cleaned)
        self.assertIn("https://example.com", cleaned)
        self.assertIn("docs", cleaned)

    def test_action_ai_chat_defaults_body_is_html(self):
        def _fake_bridge(**kwargs):
            return {"body": "<p>Hi</p>", "actions": []}

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="hi")
        self.assertFalse(result["body_is_html"])
        self.assertIn("&lt;p&gt;Hi&lt;/p&gt;", result["body"])

    def test_action_ai_chat_notes_when_open_record_is_dropped(self):
        def _fake_bridge(**kwargs):
            return {
                "body": "<p>Opening ticket 53</p>",
                "body_is_html": True,
                "actions": [
                    {
                        "type": "open_record",
                        "model": "helpdesk.ticket",
                        "res_id": 999999999,
                    }
                ],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="open ticket 53")
        self.assertEqual(result["actions"], [])
        dropped_note = _(
            "I could not open that record. It may not exist, or you may lack access."
        )
        self.assertIn(dropped_note.lower(), result["body"].lower())
        self.assertIn("<p>", result["body"])

    def test_action_ai_chat_notes_dropped_open_record_plain_body(self):
        def _fake_bridge(**kwargs):
            return {
                "body": "Opening ticket 53",
                "body_is_html": False,
                "actions": [
                    {
                        "type": "open_record",
                        "model": "helpdesk.ticket",
                        "res_id": 999999999,
                    }
                ],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="open ticket 53")
        self.assertEqual(result["actions"], [])
        self.assertIn("Opening ticket 53", result["body"])
        dropped_note = _(
            "I could not open that record. It may not exist, or you may lack access."
        )
        self.assertIn(dropped_note.lower(), result["body"].lower())
        self.assertNotIn("<p>", result["body"])

    def test_action_ai_chat_keeps_open_record_without_html_link(self):
        partner = self.env["res.partner"].create({"name": "AI Button Partner"})

        def _fake_bridge(**kwargs):
            return {
                "body": (
                    "<p>Created</p>"
                    f'<p><a href="/web#id={partner.id}&amp;model=res.partner">'
                    "Open partner</a></p>"
                ),
                "body_is_html": True,
                "actions": [
                    {
                        "type": "open_record",
                        "model": "res.partner",
                        "res_id": partner.id,
                    }
                ],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="create")
        self.assertNotIn("<a href=", result["body"])
        self.assertNotIn("/web#", result["body"])
        self.assertIn("Created", result["body"])
        self.assertEqual(result["actions"][0]["res_id"], partner.id)

    def test_action_ai_chat_create_turn_leaves_actions_empty(self):
        partner = self.env["res.partner"].create({"name": "AI Create Turn Draft"})

        def _fake_bridge(**kwargs):
            self.Assistant._remember_recent_draft("res.partner", partner)
            return {
                "body": "<p>The partner is ready. Should I open it?</p>",
                "body_is_html": True,
                "actions": [],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="create a partner")
        self.assertEqual(result["actions"], [])
        self.assertTrue(
            self.env["ai.assistant.recent.draft"].search(
                [("user_id", "=", self.env.user.id), ("res_id", "=", partner.id)]
            )
        )

    def test_action_ai_chat_resolves_open_last_draft(self):
        partner = self.env["res.partner"].create({"name": "AI Confirm Draft"})
        self.Assistant._remember_recent_draft("res.partner", partner)

        def _fake_bridge(**kwargs):
            return {
                "body": "<p>Opening the partner</p>",
                "body_is_html": True,
                "actions": [{"type": "open_last_draft"}],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            result = self.Assistant.action_ai_chat(message="yes")
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["res_id"], partner.id)
        self.assertFalse(
            self.env["ai.assistant.recent.draft"].search(
                [("user_id", "=", self.env.user.id)]
            )
        )

    def _without_recent_draft_model(self):
        original_contains = type(self.env).__contains__

        def fake_contains(env, key):
            if key == "ai.assistant.recent.draft":
                return False
            return original_contains(env, key)

        return mock.patch.object(type(self.env), "__contains__", fake_contains)

    def test_remember_recent_draft_guards_and_create_error(self):
        partner = self.env["res.partner"].create({"name": "AI Remember Guards"})
        self.Assistant._remember_recent_draft("", partner)
        self.Assistant._remember_recent_draft("res.partner", self.env["res.partner"])
        with self._without_recent_draft_model():
            self.Assistant._remember_recent_draft("res.partner", partner)
        Draft = self.env["ai.assistant.recent.draft"]
        with mock.patch.object(type(Draft), "create", side_effect=Exception("fail")):
            with mute_logger(
                "odoo.addons.ai_agno_assistant.models.ai_assistant_drafts"
            ):
                self.Assistant._remember_recent_draft("res.partner", partner)
        self.assertFalse(
            Draft.search(
                [("user_id", "=", self.env.user.id), ("res_id", "=", partner.id)]
            )
        )

    def test_sanitize_open_last_draft_happy_path(self):
        partner = self.env["res.partner"].create({"name": "AI Last Draft"})
        self.Assistant._remember_recent_draft("res.partner", partner)
        sanitized = self.Assistant._sanitize_open_last_draft()
        self.assertEqual(sanitized["res_id"], partner.id)
        self.assertEqual(sanitized["model"], "res.partner")
        self.assertFalse(
            self.env["ai.assistant.recent.draft"].search(
                [("user_id", "=", self.env.user.id)]
            )
        )

    def test_sanitize_open_last_draft_nothing_pending(self):
        self.env["ai.assistant.recent.draft"].search(
            [("user_id", "=", self.env.user.id)]
        ).unlink()
        self.assertFalse(self.Assistant._sanitize_open_last_draft())

    def test_sanitize_open_last_draft_expired_ttl(self):
        partner = self.env["res.partner"].create({"name": "AI Expired Draft"})
        self.Assistant._remember_recent_draft("res.partner", partner)
        Draft = self.env["ai.assistant.recent.draft"].sudo()
        draft = Draft.search([("user_id", "=", self.env.user.id)], limit=1)
        expired = fields.Datetime.now() - timedelta(minutes=31)
        self.env.cr.execute(
            "UPDATE ai_assistant_recent_draft SET create_date = %s WHERE id = %s",
            [expired, draft.id],
        )
        draft.invalidate_recordset(["create_date"])
        self.assertFalse(self.Assistant._sanitize_open_last_draft())
        self.assertFalse(Draft.search([("user_id", "=", self.env.user.id)]))

    def test_sanitize_open_last_draft_model_outside_allowlist(self):
        param = self.env["ir.config_parameter"].search([], limit=1)
        self.Assistant._remember_recent_draft("ir.config_parameter", param)
        self.assertFalse(self.Assistant._sanitize_open_last_draft())
        self.assertFalse(
            self.env["ai.assistant.recent.draft"].search(
                [("user_id", "=", self.env.user.id)]
            )
        )

    def test_sanitize_open_last_draft_single_use(self):
        partner = self.env["res.partner"].create({"name": "AI Single Use Draft"})
        self.Assistant._remember_recent_draft("res.partner", partner)
        first = self.Assistant._sanitize_open_last_draft()
        self.assertEqual(first["res_id"], partner.id)
        self.assertFalse(self.Assistant._sanitize_open_last_draft())

    def test_sanitize_open_last_draft_missing_model_and_search_error(self):
        with self._without_recent_draft_model():
            self.assertFalse(self.Assistant._sanitize_open_last_draft())
        Draft = self.env["ai.assistant.recent.draft"]
        with mock.patch.object(type(Draft), "search", side_effect=Exception("missing")):
            with mute_logger(
                "odoo.addons.ai_agno_assistant.models.ai_assistant_drafts"
            ):
                self.assertFalse(self.Assistant._sanitize_open_last_draft())

    def test_run_assistant_bridge_not_configured(self):
        with mock.patch.object(
            type(self.env),
            "ref",
            return_value=self.env["ai.bridge"],
        ):
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
        with (
            mock.patch.object(
                type(self.env["ai.bridge.execution"]),
                "sudo",
                return_value=sudo_rs,
            ),
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant"),
        ):
            with self.assertRaises(UserError):
                self.Assistant._run_assistant_bridge(message="hi")
