# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from ..models import ai_assistant_insight as insight_mod
from ..models.ai_assistant_artifacts import (
    _plain_text_to_pdf,
    _safe_filename,
    _table_html,
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
        created = self.Assistant.prepare_partner(
            name="Phone Co",
            email="  ",
            phone=" +55119999 ",
        )
        self.assertFalse(created.get("error"), created)
        partner = self.env["res.partner"].browse(created["partner_id"])
        self.assertEqual(partner.phone, "+55119999")
        self.assertFalse(partner.email)
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
        self.assertEqual(failed["error"], "create_failed")
        with mock.patch.object(
            type(self.env["ir.model"]),
            "_get",
            return_value=self.env["ir.model"],
        ):
            unknown_ir = self.Assistant.prepare_activity(
                model="res.partner", res_id=partner.id
            )
        self.assertEqual(unknown_ir["error"], "model_not_allowed")
        with self._without_models("mail.activity"):
            self.assertIn("res.partner", self.env)
            unavailable = self.Assistant.prepare_activity(
                model="res.partner", res_id=partner.id
            )
        self.assertEqual(unavailable["error"], "activity_unavailable")

    def test_add_order_line_guards(self):
        self.assertEqual(
            self.Assistant.add_order_line(model="res.partner", res_id=1)["error"],
            "order_unavailable",
        )
        if "sale.order" not in self.env:  # pragma: no cover
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
        if (
            "sale.order" not in self.env or "product.product" not in self.env
        ):  # pragma: no cover
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
        missing_product = self.Assistant.add_order_line(
            model="sale.order",
            res_id=order.id,
            product_ref="NO-SUCH-PRODUCT-XYZ",
        )
        self.assertTrue(missing_product.get("error"), missing_product)
        bad_price = self.Assistant.add_order_line(
            model="sale.order",
            res_id=order.id,
            product_ref=product.id,
            qty=1,
            price_unit="free",
        )
        self.assertEqual(bad_price["error"], "invalid_price")
        with mock.patch.object(
            type(self.Assistant),
            "_safe_create",
            return_value=(self.env["sale.order.line"], {"error": "create_failed"}),
        ):
            failed = self.Assistant.add_order_line(
                model="sale.order",
                res_id=order.id,
                product_ref=product.id,
                qty=1,
            )
        self.assertEqual(failed["error"], "create_failed")
        if "purchase.order" not in self.env:  # pragma: no cover
            return
        vendor = self.env["res.partner"].create({"name": "PO Vendor"})
        purchase = self.env["purchase.order"].create({"partner_id": vendor.id})
        po_line = self.Assistant.add_order_line(
            model="purchase.order",
            res_id=purchase.id,
            product_ref=product.id,
            qty=3,
            price_unit=7.5,
        )
        self.assertFalse(po_line.get("error"), po_line)
        self.assertEqual(po_line["qty"], 3)
        fields_without_po_uom = {
            name: field
            for name, field in product._fields.items()
            if name != "uom_po_id"
        }
        with (
            mock.patch.object(
                type(product),
                "_fields",
                fields_without_po_uom,
            ),
            mock.patch.object(
                type(self.Assistant),
                "_safe_create",
                return_value=(
                    self.env["purchase.order.line"],
                    {"error": "create_failed"},
                ),
            ),
        ):
            fallback = self.Assistant.add_order_line(
                model="purchase.order",
                res_id=purchase.id,
                product_ref=product.id,
                qty=1,
            )
        self.assertEqual(fallback["error"], "create_failed")

    def test_pending_error_and_confirm_paths(self):
        self.assertFalse(
            self.Assistant._remember_pending_action("x", "sale.order", False, "", "")
        )
        self.assertFalse(self.Assistant._sanitize_confirm_pending())
        with self._without_models("ai.assistant.pending.action"):
            self.assertIn("res.partner", self.env)
            self.assertFalse(self.Assistant._latest_pending_action())
            self.assertFalse(
                self.Assistant._remember_pending_action(
                    "x", "res.partner", self.env.user.partner_id, "", ""
                )
            )
        with self._without_models("sale.order"):
            missing_app = self.Assistant.propose_confirm_sale_order(1)
        self.assertEqual(missing_app["error"], "sale_unavailable")
        if "sale.order" not in self.env:  # pragma: no cover
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
        if hasattr(order, "action_confirm"):
            confirm_method = "action_confirm"
        else:  # pragma: no cover
            confirm_method = "button_confirm"
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
        self.Assistant.propose_confirm_sale_order(order.id)
        pending = self.Assistant._latest_pending_action()
        pending.label = False
        pending.summary = False
        chip = self.Assistant._sanitize_confirm_pending({})
        self.assertEqual(chip["type"], "confirm_pending")
        self.assertTrue(chip["label"])
        pending.model_name = "no.such.model"
        self.assertEqual(
            self.Assistant.action_ai_execute_pending(True)["error"],
            "unavailable",
        )
        self.Assistant.propose_confirm_sale_order(order.id)
        with mock.patch.object(
            type(order),
            "check_access",
            side_effect=AccessError("no"),
        ):
            self.assertEqual(
                self.Assistant.action_ai_execute_pending(True)["error"],
                "access_denied",
            )
        self.Assistant.propose_confirm_sale_order(order.id)
        with mock.patch.object(
            type(order),
            confirm_method,
            side_effect=ValidationError("invalid"),
        ):
            self.assertEqual(
                self.Assistant.action_ai_execute_pending(True)["error"],
                "validation_error",
            )
        self.Assistant.propose_confirm_sale_order(order.id)
        with mock.patch.object(
            type(order),
            "button_confirm",
            create=True,
            return_value=True,
        ):
            clicked = self.Assistant.action_ai_execute_pending(True)
        self.assertTrue(clicked.get("ok"), clicked)
        self.Assistant.propose_confirm_sale_order(order.id)
        with mock.patch.object(type(order), confirm_method, return_value=True):
            confirmed = self.Assistant.action_ai_execute_pending(True)
        self.assertTrue(confirmed.get("ok"), confirmed)
        self.assertEqual(confirmed["res_id"], order.id)

    def test_propose_confirm_purchase_when_available(self):
        with self._without_models("purchase.order"):
            result = self.Assistant.propose_confirm_purchase_order(1)
        self.assertEqual(result["error"], "purchase_unavailable")
        if "purchase.order" not in self.env:  # pragma: no cover
            return
        vendor = self.env["res.partner"].create({"name": "RFQ Vendor"})
        order = self.env["purchase.order"].create({"partner_id": vendor.id})
        proposed = self.Assistant.propose_confirm_purchase_order(order.id)
        self.assertTrue(proposed.get("pending"), proposed)
        cancelled = self.Assistant.action_ai_execute_pending(False)
        self.assertTrue(cancelled.get("cancelled"))

    def test_blocked_open_model_prefixes_and_kinds(self):
        self.assertTrue(self.Assistant._is_blocked_open_model(""))
        self.assertTrue(self.Assistant._is_blocked_open_model(None))
        self.assertTrue(self.Assistant._is_blocked_open_model("ir.ui.view"))
        self.assertTrue(self.Assistant._is_blocked_open_model("ir.attachment"))
        self.assertTrue(self.Assistant._is_blocked_open_model("mail.alias"))
        self.assertTrue(self.Assistant._is_blocked_open_model("ai.assistant"))
        self.assertTrue(
            self.Assistant._is_blocked_open_model("ai.assistant.pending.action")
        )
        self.assertFalse(self.Assistant._is_blocked_open_model("res.partner"))
        self.assertFalse(
            self.Assistant._sanitize_open_record({"model": "ir.ui.view", "res_id": 1})
        )

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
        with mock.patch.object(
            type(self.Assistant),
            "_preview_fields_for",
            return_value=[],
        ):
            empty_preview = self.Assistant._hydrate_record_preview(
                {"current_model": "res.partner", "current_res_id": partner.id}
            )
            empty_ctx = self.Assistant.get_record_context("res.partner", partner.id)
        self.assertNotIn("record_preview", empty_preview)
        self.assertEqual(empty_ctx["fields"], {"id": partner.id})
        html_field = mock.Mock(type="html")
        char_field = mock.Mock(type="char")
        fake_record = mock.Mock()
        fake_record._fields = {
            "name": html_field,
            "display_name": char_field,
            "signup_token": char_field,
        }
        with mock.patch.object(
            insight_mod,
            "_PREVIEW_FIELD_CANDIDATES",
            ("name", "signup_token", "display_name"),
        ):
            names = self.Assistant._preview_fields_for(fake_record)
        self.assertEqual(names, ["display_name"])
        with mock.patch.object(insight_mod, "_PREVIEW_FIELD_LIMIT", 1):
            limited = self.Assistant._preview_fields_for(partner)
        self.assertEqual(len(limited), 1)
        with mock.patch.object(type(self.Assistant), "_safe_count", return_value=None):
            digest = self.Assistant.get_attention_digest()
        self.assertEqual(digest["items"], [])
        with self._without_models("account.move", "project.task", "helpdesk.ticket"):
            hidden = self.Assistant.get_attention_digest()
        self.assertIsInstance(hidden["items"], list)
        if "account.move" in self.env:
            move_fields = {
                name: field
                for name, field in self.env["account.move"]._fields.items()
                if name != "payment_state"
            }
            with mock.patch.object(
                type(self.env["account.move"]),
                "_fields",
                move_fields,
            ):
                posted = self.Assistant.get_attention_digest()
            self.assertTrue(
                any(item["key"] == "overdue_invoices" for item in posted["items"])
            )
        if "helpdesk.ticket" in self.env:  # pragma: no cover
            ticket_fields = dict(self.env["helpdesk.ticket"]._fields)
            with mock.patch.object(
                type(self.env["helpdesk.ticket"]),
                "_fields",
                {**ticket_fields, "closed": mock.Mock()},
            ):
                closed = self.Assistant.get_attention_digest()
            self.assertIsInstance(closed["items"], list)
            no_closed = {
                name: field for name, field in ticket_fields.items() if name != "closed"
            }
            with mock.patch.object(
                type(self.env["helpdesk.ticket"]),
                "_fields",
                no_closed,
            ):
                staged = self.Assistant.get_attention_digest()
            self.assertIsInstance(staged["items"], list)
            neither = {
                name: field for name, field in no_closed.items() if name != "stage_id"
            }
            with mock.patch.object(
                type(self.env["helpdesk.ticket"]),
                "_fields",
                neither,
            ):
                skipped = self.Assistant.get_attention_digest()
            self.assertFalse(
                any(item["key"] == "open_tickets" for item in skipped["items"])
            )

    def _without_models(self, *missing):
        original_contains = type(self.env).__contains__
        hidden = set(missing)

        def fake_contains(env, key):
            if key in hidden:
                return False
            return original_contains(env, key)

        return mock.patch.object(type(self.env), "__contains__", fake_contains)

    def _without_session_model(self):
        return self._without_models("ai.assistant.session")

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
            self.assertIn("res.partner", self.env)
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

    def test_chat_session_key_confirm_pending_and_labels(self):
        invalid = self.Assistant._normalize_ui_context({"session_key": "short"})
        self.assertIs(invalid["session_key"], False)
        key = self.Assistant._new_session_key()
        valid = self.Assistant._normalize_ui_context({"session_key": key})
        self.assertEqual(valid["session_key"], key)
        with mock.patch.object(
            type(self.Assistant),
            "_sanitize_confirm_pending",
            side_effect=lambda *args, **kwargs: {"type": "confirm_pending"},
        ):
            labeled = self.Assistant._sanitize_ai_chat_actions(
                [{"type": "confirm_pending", "label": "  Confirm now  "}]
            )
            fallback = self.Assistant._sanitize_ai_chat_actions(
                [{"type": "confirm_pending", "label": "   "}]
            )
        self.assertEqual(labeled[0]["label"], "Confirm now")
        self.assertEqual(fallback[0]["label"], "confirm_pending")
        with (
            mock.patch.object(
                type(self.Assistant),
                "_run_assistant_bridge",
                return_value={"body": "ok", "body_is_html": False, "actions": []},
            ),
            mock.patch.object(
                type(self.Assistant),
                "_remember_chat_turn",
                return_value=False,
            ),
        ):
            chat = self.Assistant.action_ai_chat(
                message="hello",
                ui_context={"session_key": key},
            )
        self.assertFalse(chat["session_id"])
        self.assertFalse(chat["session_key"])

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
        self.assertEqual(_safe_filename("notes.md", ".md"), "notes.md")
        self.assertEqual(_table_html([]), "")
        header_only = markdownish_to_html("| A | B |\n| --- | --- |")
        self.assertIn("<thead>", header_only)
        self.assertNotIn("<tbody>", header_only)
        padded = _table_html([["A"], ["1", "2"]])
        self.assertIn("<th>", padded)
        self.assertIn("<td>", padded)
        empty_header = _table_html([[], ["x"]])
        self.assertIn("<tbody>", empty_header)
        self.assertNotIn("<thead>", empty_header)
        self.assertIn("<ul>", markdownish_to_html("- only\n- items"))
        self.assertIn("<ol>", markdownish_to_html("1. only"))
        self.assertIn("<h3>", markdownish_to_html("### Sub"))
        self.assertEqual(markdownish_to_html("<p>already</p>"), "<p>already</p>")
        escaped = _plain_text_to_pdf("Title (draft)", "\\line\n" + ("x" * 100))
        self.assertTrue(escaped.startswith(b"%PDF"))
