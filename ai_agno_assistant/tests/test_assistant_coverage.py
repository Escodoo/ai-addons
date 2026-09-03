# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from ..models.ai_assistant_artifacts import (
    _plain_text_to_pdf,
    _safe_filename,
    markdownish_to_html,
    wrap_report_html,
)


@tagged("post_install", "-at_install")
class TestAiAssistantCoverage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]

    def test_prepare_partner_guards_and_create_error(self):
        self.assertEqual(
            self.Assistant.prepare_partner(name="  ")["error"], "missing_name"
        )
        with mock.patch.object(
            type(self.Assistant),
            "_safe_create",
            return_value=(self.env["res.partner"], {"error": "create_failed"}),
        ):
            self.assertEqual(
                self.Assistant.prepare_partner(name="Acme")["error"],
                "create_failed",
            )

    def test_prepare_activity_error_paths(self):
        self.assertEqual(
            self.Assistant.prepare_activity(model="ir.config_parameter", res_id=1)[
                "error"
            ],
            "model_not_allowed",
        )
        self.assertEqual(
            self.Assistant.prepare_activity(model="res.partner", res_id="x")["error"],
            "invalid_res_id",
        )
        self.assertEqual(
            self.Assistant.prepare_activity(model="res.partner", res_id=0)["error"],
            "invalid_res_id",
        )
        self.assertEqual(
            self.Assistant.prepare_activity(model="unknown.model", res_id=1)["error"],
            "model_not_allowed",
        )
        missing = self.Assistant.prepare_activity(model="res.partner", res_id=999999)
        self.assertEqual(missing["error"], "not_found")
        partner = self.env["res.partner"].create({"name": "Locked"})
        with mock.patch.object(
            type(self.env["res.partner"]),
            "check_access",
            side_effect=AccessError("no"),
        ):
            denied = self.Assistant.prepare_activity(
                model="res.partner", res_id=partner.id
            )
        self.assertEqual(denied["error"], "access_denied")
        with mock.patch.object(
            type(self.Assistant),
            "_safe_create",
            return_value=(self.env["mail.activity"], {"error": "create_failed"}),
        ):
            failed = self.Assistant.prepare_activity(
                res_model="res.partner",
                res_id=partner.id,
                note="<b>Hi</b>",
            )
        if failed.get("error") == "activity_unavailable":
            self.skipTest("mail.activity is not available")
        self.assertEqual(failed["error"], "create_failed")

    def test_add_order_line_guards(self):
        self.assertEqual(
            self.Assistant.add_order_line(model="res.partner", res_id=1)["error"],
            "order_unavailable",
        )
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        self.assertEqual(
            self.Assistant.add_order_line(model="sale.order", res_id="x")["error"],
            "invalid_res_id",
        )
        self.assertEqual(
            self.Assistant.add_order_line(model="sale.order", res_id=999999)["error"],
            "not_found",
        )
        partner = self.env["res.partner"].create({"name": "SO Customer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        with mock.patch.object(
            type(order),
            "check_access",
            side_effect=AccessError("no"),
        ):
            denied = self.Assistant.add_order_line(
                model="sale.order", res_id=order.id, product_ref="X"
            )
        self.assertEqual(denied["error"], "access_denied")
        with mock.patch.object(
            type(order),
            "state",
            new_callable=mock.PropertyMock,
            return_value="sale",
        ):
            self.assertEqual(
                self.Assistant.add_order_line(
                    model="sale.order", res_id=order.id, product_ref="X"
                )["error"],
                "invalid_state",
            )

    def test_add_order_line_on_draft_sale(self):
        if "sale.order" not in self.env or "product.product" not in self.env:
            self.skipTest("sale/product is not installed")
        partner = self.env["res.partner"].create({"name": "Line Customer"})
        product = self.env["product.product"].create(
            {"name": "Coverage Desk", "type": "consu"}
        )
        order = self.env["sale.order"].create({"partner_id": partner.id})
        result = self.Assistant.add_order_line(
            res_model="sale.order",
            res_id=order.id,
            product_ref=product.id,
            qty=2,
            price_unit=10,
        )
        self.assertFalse(result.get("error"), result)
        self.assertEqual(result["qty"], 2)
        self.assertEqual(result["open_record"]["res_id"], order.id)
        bad_qty = self.Assistant.add_order_line(
            model="sale.order",
            res_id=order.id,
            product_ref=product.id,
            qty=-3,
        )
        self.assertTrue(bad_qty.get("error"), bad_qty)

    def test_pending_error_and_confirm_paths(self):
        self.assertFalse(
            self.Assistant._remember_pending_action("x", "sale.order", False, "", "")
        )
        self.assertFalse(self.Assistant._sanitize_confirm_pending())
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        missing = self.Assistant.propose_confirm_sale_order("SO-MISSING")
        self.assertTrue(missing.get("error"), missing)
        partner = self.env["res.partner"].create({"name": "Confirm Customer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        with mock.patch.object(
            type(order),
            "check_access",
            side_effect=AccessError("no"),
        ):
            denied = self.Assistant.propose_confirm_sale_order(order.id)
        self.assertEqual(denied["error"], "access_denied")
        with mock.patch.object(
            type(order),
            "state",
            new_callable=mock.PropertyMock,
            return_value="sale",
        ):
            self.assertEqual(
                self.Assistant.propose_confirm_sale_order(order.id)["error"],
                "invalid_state",
            )
        proposed = self.Assistant.propose_confirm_sale_order(order.id)
        self.assertTrue(proposed.get("pending"), proposed)
        pending = self.Assistant._latest_pending_action()
        pending.res_id = 999999
        self.assertEqual(
            self.Assistant.action_ai_execute_pending(True)["error"], "not_found"
        )
        self.Assistant.propose_confirm_sale_order(order.id)
        pending = self.Assistant._latest_pending_action()
        pending.action_key = "unknown_thing"
        self.assertEqual(
            self.Assistant.action_ai_execute_pending(True)["error"],
            "unsupported",
        )
        confirm_method = (
            "action_confirm" if hasattr(order, "action_confirm") else "button_confirm"
        )
        self.Assistant.propose_confirm_sale_order(order.id)
        with mock.patch.object(
            type(order),
            confirm_method,
            side_effect=UserError("cannot confirm"),
        ):
            failed = self.Assistant.action_ai_execute_pending(True)
        self.assertEqual(failed["error"], "validation_error")
        self.Assistant.propose_confirm_sale_order(order.id)
        with (
            mock.patch.object(
                type(order),
                confirm_method,
                side_effect=RuntimeError("boom"),
            ),
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant_pending"),
        ):
            crashed = self.Assistant.action_ai_execute_pending(True)
        self.assertEqual(crashed["error"], "confirm_failed")

    def test_propose_confirm_purchase_when_available(self):
        if "purchase.order" not in self.env:
            result = self.Assistant.propose_confirm_purchase_order(1)
            self.assertEqual(result["error"], "purchase_unavailable")
            return
        vendor = self.env["res.partner"].create({"name": "RFQ Vendor"})
        order = self.env["purchase.order"].create({"partner_id": vendor.id})
        proposed = self.Assistant.propose_confirm_purchase_order(order.id)
        self.assertTrue(proposed.get("pending"), proposed)
        cancelled = self.Assistant.action_ai_execute_pending(False)
        self.assertTrue(cancelled.get("cancelled"))

    def test_insight_guards(self):
        self.assertEqual(self.Assistant._hydrate_record_preview("x"), "x")
        blocked = self.Assistant._hydrate_record_preview(
            {"current_model": "ir.config_parameter", "current_res_id": 1}
        )
        self.assertNotIn("record_preview", blocked)
        self.assertNotIn(
            "record_preview",
            self.Assistant._hydrate_record_preview(
                {"current_model": "res.partner", "current_res_id": "bad"}
            ),
        )
        self.assertNotIn(
            "record_preview",
            self.Assistant._hydrate_record_preview(
                {"current_model": "res.partner", "current_res_id": 999999}
            ),
        )
        partner = self.env["res.partner"].create({"name": "Preview"})
        with mock.patch.object(
            type(self.env["res.partner"]),
            "check_access",
            side_effect=AccessError("no"),
        ):
            denied = self.Assistant._hydrate_record_preview(
                {"current_model": "res.partner", "current_res_id": partner.id}
            )
        self.assertNotIn("record_preview", denied)
        with (
            mock.patch.object(
                type(self.env["res.partner"]),
                "read",
                side_effect=RuntimeError("read failed"),
            ),
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant_insight"),
        ):
            failed = self.Assistant._hydrate_record_preview(
                {"current_model": "res.partner", "current_res_id": partner.id}
            )
        self.assertNotIn("record_preview", failed)
        self.assertIsNone(self.Assistant._safe_count("no.such.model", []))
        with mock.patch.object(
            type(self.env["res.partner"]),
            "search_count",
            side_effect=AccessError("no"),
        ):
            self.assertIsNone(self.Assistant._safe_count("res.partner", []))
        with (
            mock.patch.object(
                type(self.env["res.partner"]),
                "search_count",
                side_effect=RuntimeError("x"),
            ),
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant_insight"),
        ):
            self.assertIsNone(self.Assistant._safe_count("res.partner", []))
        self.assertEqual(
            self.Assistant.get_record_context("res.partner", None)["error"],
            "invalid_res_id",
        )
        self.assertEqual(
            self.Assistant.get_record_context("res.partner", 0)["error"],
            "invalid_res_id",
        )
        self.assertEqual(
            self.Assistant.get_record_context("res.partner", 999999)["error"],
            "not_found",
        )
        with mock.patch.object(
            type(self.env["res.partner"]),
            "check_access",
            side_effect=AccessError("no"),
        ):
            denied_ctx = self.Assistant.get_record_context("res.partner", partner.id)
        self.assertEqual(denied_ctx["error"], "access_denied")

    def _without_session_model(self):
        original_contains = type(self.env).__contains__

        def fake_contains(env, key):
            if key == "ai.assistant.session":
                return False
            return original_contains(env, key)

        return mock.patch.object(type(self.env), "__contains__", fake_contains)

    def test_session_error_and_invalid_payloads(self):
        self.assertFalse(self.Assistant._normalize_session_key("short"))
        self.assertFalse(
            self.Assistant.action_ai_delete_session("bad key").get("deleted")
        )
        created = self.Assistant.action_ai_new_session()
        session = self.Assistant._get_or_create_session(created["session_key"])
        session.messages_json = "{"
        loaded = self.Assistant.action_ai_load_session(created["session_key"])
        self.assertEqual(loaded["messages"], [])
        self.assertFalse(self.Assistant._session_has_messages(session))
        recovered = self.Assistant._remember_chat_turn(
            "Recover",
            "ok",
            False,
            session_key=created["session_key"],
        )
        self.assertTrue(recovered)
        session.messages_json = "{}"
        self.assertFalse(self.Assistant._session_has_messages(session))
        loaded_obj = self.Assistant.action_ai_load_session(created["session_key"])
        self.assertEqual(loaded_obj["messages"], [])
        rewritten = self.Assistant._remember_chat_turn(
            "Rewrite",
            "again",
            False,
            session_key=created["session_key"],
        )
        self.assertTrue(rewritten)
        self.assertIsInstance(self.Assistant.action_ai_list_sessions(limit="bad"), list)
        with (
            mock.patch.object(
                type(session),
                "write",
                side_effect=RuntimeError("persist failed"),
            ),
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant_session"),
        ):
            self.assertFalse(
                self.Assistant._remember_chat_turn(
                    "Hi",
                    "<p>x</p>",
                    True,
                    session_key=created["session_key"],
                )
            )
        with self._without_session_model():
            self.assertFalse(self.Assistant._get_or_create_session())
            self.assertFalse(self.Assistant._remember_chat_turn("Hi", "x", False))
            self.Assistant._prune_empty_sessions()
            self.assertEqual(self.Assistant.action_ai_list_sessions(), [])
            self.assertEqual(
                self.Assistant.action_ai_load_session()["messages"],
                [],
            )
            deleted = self.Assistant.action_ai_delete_session("validkey")
            self.assertFalse(deleted["deleted"])

    def test_markdownish_headings_lists_and_filename(self):
        html = markdownish_to_html(
            "# Title\n\n- one\n- two\n\n1. first\n2. second\n\nPlain **bold**"
        )
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<ol>", html)
        self.assertIn("<b>bold</b>", html)
        self.assertEqual(markdownish_to_html(""), "")
        self.assertIn("Report", wrap_report_html("", "<p>x</p>"))
        self.assertTrue(_safe_filename("Weekly briefing!!", ".md").endswith(".md"))
        self.assertTrue(_safe_filename(None, ".pdf").endswith(".pdf"))
        pdf = _plain_text_to_pdf("", "")
        self.assertTrue(pdf.startswith(b"%PDF"))
        long_pdf = _plain_text_to_pdf("T", "\n".join(["line"] * 60))
        self.assertTrue(long_pdf.startswith(b"%PDF"))
        default = self.Assistant.action_ai_export_message(content="Hello", title="  ")
        self.assertTrue(default["filename"].lower().startswith("assistant-briefing"))
