# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
from unittest import mock

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestAiAssistantFeatures(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]

    def test_attention_digest_shape(self):
        digest = self.Assistant.get_attention_digest()
        self.assertIn("date", digest)
        self.assertIsInstance(digest["items"], list)
        for item in digest["items"]:
            self.assertIn("key", item)
            self.assertIn("count", item)

    def test_record_context_and_hydration(self):
        partner = self.env["res.partner"].create({"name": "Preview Partner"})
        result = self.Assistant.get_record_context("res.partner", partner.id)
        self.assertEqual(result["res_id"], partner.id)
        self.assertEqual(result["fields"]["name"], "Preview Partner")
        aliased = self.Assistant.get_record_context(
            res_model="res.partner", res_id=partner.id
        )
        self.assertEqual(aliased["res_id"], partner.id)

        blocked = self.Assistant.get_record_context("ir.config_parameter", 1)
        self.assertEqual(blocked.get("error"), "model_not_allowed")

        hydrated = self.Assistant._hydrate_record_preview(
            {"current_model": "res.partner", "current_res_id": partner.id}
        )
        self.assertEqual(hydrated["record_preview"]["id"], partner.id)

    def test_prepare_partner_and_ephemeral_export(self):
        partner = self.Assistant.prepare_partner(
            name="Acme AI", email="acme@example.com"
        )
        self.assertFalse(partner.get("error"))
        self.assertEqual(partner["open_record"]["model"], "res.partner")

        before = self.env["ir.attachment"].sudo().search_count([])
        exported = self.Assistant.action_ai_export_message(
            content="Sales were stable.",
            title="Weekly briefing",
            export_format="markdown",
        )
        self.assertEqual(exported["mimetype"], "text/markdown")
        self.assertTrue(exported["filename"].endswith(".md"))
        self.assertIn(
            "Sales were stable.", base64.b64decode(exported["datas"]).decode()
        )
        self.assertEqual(self.env["ir.attachment"].sudo().search_count([]), before)

        from ..models.ai_assistant_artifacts import (
            markdownish_to_html,
            wrap_report_html,
        )

        table_html = markdownish_to_html(
            "Relatório\n\n"
            "| Estágio | Quantidade |\n"
            "| --- | --- |\n"
            "| Novo | 9 |\n"
            "| Proposta | 4 |\n"
        )
        self.assertIn("<table>", table_html)
        self.assertIn("<th>Estágio</th>", table_html)
        self.assertIn("<td>Novo</td>", table_html)
        self.assertNotIn("| Novo |", table_html)
        wrapped = wrap_report_html("Relatório de Oportunidades", table_html)
        self.assertIn('charset="utf-8"', wrapped)
        self.assertIn("Relatório de Oportunidades", wrapped)
        self.assertIn('class="page"', wrapped)

        pdf = self.Assistant.action_ai_export_message(
            title="Relatório de Oportunidades",
            content=(
                "## Distribuição por Estágio\n\n"
                "| Estágio | Quantidade | Receita |\n"
                "| --- | --- | --- |\n"
                "| Novo | 9 | $ 80.000 |\n"
                "| Ganho | 1 | $ 19.800 |\n"
            ),
            export_format="pdf",
        )
        self.assertEqual(pdf["mimetype"], "application/pdf")
        self.assertTrue(base64.b64decode(pdf["datas"]).startswith(b"%PDF"))
        self.assertEqual(self.env["ir.attachment"].sudo().search_count([]), before)

        html_pdf = self.Assistant.action_ai_export_message(
            title="HTML briefing",
            content="<h2>Pipeline</h2><p>Nine new opportunities.</p>",
            export_format="pdf",
        )
        self.assertEqual(html_pdf["mimetype"], "application/pdf")

        captured = {}

        def _fake_wkhtmltopdf(bodies, **kwargs):
            captured["args"] = kwargs.get("specific_paperformat_args")
            return b"%PDF-1.4 compact"

        with mock.patch.object(
            type(self.env["ir.actions.report"]),
            "_run_wkhtmltopdf",
            side_effect=_fake_wkhtmltopdf,
        ):
            compact = self.Assistant.action_ai_export_message(
                title="Compact",
                content="<p>Close to the top.</p>",
                export_format="pdf",
            )
        self.assertEqual(
            captured["args"],
            {
                "data-report-margin-top": 16,
                "data-report-margin-bottom": 16,
                "data-report-header-spacing": 0,
            },
        )
        self.assertTrue(base64.b64decode(compact["datas"]).startswith(b"%PDF"))

        def _fake_bridge(**kwargs):
            return {
                "body": "<p>Files ready</p>",
                "body_is_html": True,
                "actions": [],
                "artifacts": [
                    {
                        "name": "weekly-brief.md",
                        "mimetype": "text/markdown",
                        "attachment_id": 42,
                    }
                ],
            }

        with mock.patch.object(
            type(self.Assistant),
            "_run_assistant_bridge",
            side_effect=_fake_bridge,
        ):
            chat = self.Assistant.action_ai_chat(message="download please")
        self.assertEqual(chat["artifacts"], [])

    def test_session_roundtrip(self):
        created = self.Assistant.action_ai_new_session()
        self.assertTrue(created["session_key"])
        self.Assistant._remember_chat_turn(
            message="Hello",
            body="<p>Hi</p>",
            body_is_html=True,
            session_key=created["session_key"],
        )
        loaded = self.Assistant.action_ai_load_session(created["session_key"])
        self.assertEqual(loaded["session_key"], created["session_key"])
        self.assertGreaterEqual(len(loaded["messages"]), 2)
        self.assertEqual(loaded["messages"][-1]["text"], "<p>Hi</p>")
        self.assertNotIn("artifacts", loaded["messages"][-1])
        listed = self.Assistant.action_ai_list_sessions()
        self.assertTrue(
            any(item["session_key"] == created["session_key"] for item in listed)
        )

    def test_delete_own_session_and_not_another_users(self):
        created = self.Assistant.action_ai_new_session()
        self.Assistant._remember_chat_turn(
            message="Delete me",
            body="<p>Soon gone</p>",
            body_is_html=True,
            session_key=created["session_key"],
        )
        demo = self.env.ref("base.user_demo")
        demo.groups_id = [(4, self.ai_group.id)]
        demo_assistant = self.env["ai.assistant"].with_user(demo)
        blocked = demo_assistant.action_ai_delete_session(created["session_key"])
        self.assertFalse(blocked.get("deleted"), blocked)
        listed = self.Assistant.action_ai_list_sessions()
        self.assertTrue(
            any(item["session_key"] == created["session_key"] for item in listed)
        )

        deleted = self.Assistant.action_ai_delete_session(created["session_key"])
        self.assertTrue(deleted.get("deleted"), deleted)
        self.assertEqual(deleted["session_key"], created["session_key"])
        listed = self.Assistant.action_ai_list_sessions()
        self.assertFalse(
            any(item["session_key"] == created["session_key"] for item in listed)
        )
        missing = self.Assistant.action_ai_delete_session(created["session_key"])
        self.assertFalse(missing.get("deleted"))

    def test_new_session_is_not_stored_until_first_message(self):
        created = self.Assistant.action_ai_new_session()
        self.assertTrue(created["session_key"])
        Session = self.env["ai.assistant.session"]
        self.assertFalse(Session.search([("session_key", "=", created["session_key"])]))
        leftover = Session.create(
            {
                "user_id": self.env.user.id,
                "session_key": self.Assistant._new_session_key(),
                "name": "New conversation",
                "messages_json": "[]",
            }
        )
        listed = self.Assistant.action_ai_list_sessions()
        self.assertFalse(
            any(item["session_key"] == leftover.session_key for item in listed)
        )
        self.assertFalse(leftover.exists())

    def test_pending_confirm_requires_existing_order(self):
        missing = self.Assistant.action_ai_execute_pending(True)
        self.assertEqual(missing.get("error"), "expired")

    def test_propose_and_cancel_pending_sale_order(self):
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed")
        partner = self.env["res.partner"].create({"name": "HITL Customer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        proposed = self.Assistant.propose_confirm_sale_order(order.id)
        self.assertTrue(proposed.get("pending"), proposed)
        chip = self.Assistant._sanitize_confirm_pending({})
        self.assertEqual(chip["type"], "confirm_pending")
        cancelled = self.Assistant.action_ai_execute_pending(False)
        self.assertTrue(cancelled.get("cancelled"))
        self.assertEqual(order.state, "draft")

    def test_prepare_activity_on_partner(self):
        partner = self.env["res.partner"].create({"name": "Activity Partner"})
        result = self.Assistant.prepare_activity(
            model="res.partner",
            res_id=partner.id,
            summary="Call back",
        )
        if result.get("error") == "activity_unavailable":
            self.skipTest("mail.activity is not available")
        self.assertFalse(result.get("error"), result)
        self.assertEqual(result["res_id"], partner.id)

    def test_export_message_rejects_empty_and_unknown_format(self):
        with self.assertRaises(UserError) as empty:
            self.Assistant.action_ai_export_message(content="   ")
        self.assertIn("Nothing to export", empty.exception.args[0])
        with self.assertRaises(UserError) as missing:
            self.Assistant.action_ai_export_message(content=None)
        self.assertIn("Nothing to export", missing.exception.args[0])
        with self.assertRaises(UserError) as unknown:
            self.Assistant.action_ai_export_message(
                content="Brief",
                export_format="csv",
            )
        self.assertIn("Unsupported export format", unknown.exception.args[0])

    def test_export_message_truncates_oversized_markdown(self):
        from ..models.ai_assistant_artifacts import (
            _EXPORT_CONTENT_MAX_LEN,
        )

        oversized = "A" * (_EXPORT_CONTENT_MAX_LEN + 50)
        exported = self.Assistant.action_ai_export_message(
            content=oversized,
            title="Long briefing",
            export_format="md",
        )
        decoded = base64.b64decode(exported["datas"]).decode()
        self.assertLessEqual(len(decoded), _EXPORT_CONTENT_MAX_LEN + 80)
        self.assertNotIn("A" * (_EXPORT_CONTENT_MAX_LEN + 1), decoded)
        self.assertTrue(decoded.startswith("# Long briefing"))

    def test_export_pdf_falls_back_when_wkhtmltopdf_fails(self):
        from ..models.ai_assistant_artifacts import (
            _plain_text_to_pdf,
        )

        raw = _plain_text_to_pdf(
            "Title (draft)",
            "Short line\n" + ("x" * 120) + "\n()",
        )
        self.assertTrue(raw.startswith(b"%PDF"))

        with (
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant_artifacts"),
            mock.patch.object(
                type(self.env["ir.actions.report"]),
                "_run_wkhtmltopdf",
                side_effect=RuntimeError("wkhtmltopdf missing"),
            ),
        ):
            pdf = self.Assistant.action_ai_export_message(
                content="Fallback briefing",
                title="Plain PDF",
                export_format="pdf",
            )
        self.assertEqual(pdf["mimetype"], "application/pdf")
        self.assertTrue(base64.b64decode(pdf["datas"]).startswith(b"%PDF"))

        with mock.patch.object(
            type(self.env["ir.actions.report"]),
            "_run_wkhtmltopdf",
            return_value=b"not-a-pdf",
        ):
            garbage = self.Assistant.action_ai_export_message(
                content="Still a briefing",
                export_format="pdf",
            )
        self.assertTrue(base64.b64decode(garbage["datas"]).startswith(b"%PDF"))
        self.assertEqual(self.Assistant._html_report_to_pdf(""), b"")
