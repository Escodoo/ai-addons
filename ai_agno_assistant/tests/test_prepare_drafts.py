# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestPrepareDrafts(TransactionCase):
    """Soft-gated draft helpers (CRM, helpdesk, sale, timesheet)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Assistant = cls.env["ai.assistant"]
        cls.ai_group = cls.env.ref("ai_agno_assistant.group_system_ai_user")
        cls.env.user.groups_id = [(4, cls.ai_group.id)]
        partner_vals = {"name": "AI Draft Partner Unique XYZ"}
        if "customer_rank" in cls.env["res.partner"]._fields:
            partner_vals["customer_rank"] = 1
        cls.partner = cls.env["res.partner"].create(partner_vals)

    def _require_models(self, *models, reason):
        """Skip when optional apps are missing (local runs without soft deps)."""
        if any(model not in self.env for model in models):  # pragma: no cover
            self.skipTest(reason)

    def test_prepare_opportunity_creates_draft(self):
        self._require_models("crm.lead", reason="CRM app is not installed")
        result = self.Assistant.prepare_opportunity(
            name="AI Opportunity Unique XYZ",
            partner_ref=self.partner.id,
            description="Prospect from assistant",
            expected_revenue=1500,
        )
        self.assertNotIn("error", result)
        lead = self.env["crm.lead"].browse(result["opportunity_id"])
        self.assertTrue(lead.exists())
        self.assertEqual(lead.type, "opportunity")
        self.assertEqual(lead.partner_id, self.partner)
        self.assertEqual(result["open_record"]["model"], "crm.lead")

    def test_prepare_opportunity_missing_name(self):
        self._require_models("crm.lead", reason="CRM app is not installed")
        result = self.Assistant.prepare_opportunity()
        self.assertEqual(result.get("error"), "missing_name")

    def test_prepare_opportunity_title_from_partner(self):
        self._require_models("crm.lead", reason="CRM app is not installed")
        result = self.Assistant.prepare_opportunity(partner_ref=self.partner.id)
        self.assertNotIn("error", result)
        lead = self.env["crm.lead"].browse(result["opportunity_id"])
        self.assertIn(self.partner.display_name, lead.name)

    def test_prepare_opportunity_invalid_revenue(self):
        self._require_models("crm.lead", reason="CRM app is not installed")
        result = self.Assistant.prepare_opportunity(
            name="Bad revenue",
            expected_revenue="not-a-number",
        )
        self.assertEqual(result.get("error"), "invalid_expected_revenue")

    def test_prepare_opportunity_partner_not_found(self):
        self._require_models("crm.lead", reason="CRM app is not installed")
        result = self.Assistant.prepare_opportunity(
            name="Orphan opportunity",
            partner_ref=999999999,
        )
        self.assertEqual(result.get("error"), "partner_not_found")

    def test_prepare_opportunity_unavailable(self):
        with mock.patch.object(
            type(self.env),
            "__contains__",
            new=lambda _env, model: model != "crm.lead",
        ):
            result = self.Assistant.prepare_opportunity(name="X")
        self.assertEqual(result.get("error"), "crm_unavailable")

    def test_prepare_helpdesk_ticket_creates_draft(self):
        self._require_models("helpdesk.ticket", reason="Helpdesk app is not installed")
        result = self.Assistant.prepare_helpdesk_ticket(
            name="AI Ticket Unique XYZ",
            description="Printer offline",
            partner_ref=self.partner.id,
        )
        self.assertNotIn("error", result)
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertTrue(ticket.exists())
        self.assertEqual(ticket.partner_id, self.partner)
        self.assertEqual(result["open_record"]["model"], "helpdesk.ticket")

    def test_prepare_helpdesk_ticket_missing_name(self):
        self._require_models("helpdesk.ticket", reason="Helpdesk app is not installed")
        result = self.Assistant.prepare_helpdesk_ticket(description="x")
        self.assertEqual(result.get("error"), "missing_name")

    def test_prepare_helpdesk_ticket_with_team(self):
        self._require_models("helpdesk.ticket", reason="Helpdesk app is not installed")
        self._require_models(
            "helpdesk.ticket.team", reason="Helpdesk teams are not available"
        )
        team = self.env["helpdesk.ticket.team"].create(
            {"name": "AI Draft Team Unique XYZ"}
        )
        result = self.Assistant.prepare_helpdesk_ticket(
            name="Ticket with team",
            team_ref=team.id,
        )
        self.assertNotIn("error", result)
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.team_id, team)
        self.assertEqual(result["team"]["id"], team.id)

    def test_prepare_helpdesk_ticket_team_not_found(self):
        self._require_models("helpdesk.ticket", reason="Helpdesk app is not installed")
        self._require_models(
            "helpdesk.ticket.team", reason="Helpdesk teams are not available"
        )
        result = self.Assistant.prepare_helpdesk_ticket(
            name="Missing team",
            team_ref=999999999,
        )
        self.assertEqual(result.get("error"), "team_not_found")

    def test_prepare_helpdesk_ticket_unavailable(self):
        with mock.patch.object(
            type(self.env),
            "__contains__",
            new=lambda _env, model: model != "helpdesk.ticket",
        ):
            result = self.Assistant.prepare_helpdesk_ticket(name="X")
        self.assertEqual(result.get("error"), "helpdesk_unavailable")

    def test_prepare_sale_order_creates_draft(self):
        self._require_models(
            "sale.order",
            "product.product",
            reason="Sales/Product apps are not installed",
        )
        product = self.env["product.product"].create(
            {
                "name": "AI SO Product Unique XYZ",
                "default_code": "AI-SO-XYZ",
                "type": "consu",
                "sale_ok": True,
                "list_price": 20.0,
            }
        )
        result = self.Assistant.prepare_sale_order(
            partner_ref=self.partner.id,
            lines=[{"product_id": product.id, "qty": 2, "price_unit": 21.5}],
            notes="Ship next week",
        )
        self.assertNotIn("error", result)
        order = self.env["sale.order"].browse(result["so_id"])
        self.assertTrue(order.exists())
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_id, self.partner)
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_uom_qty, 2)
        self.assertEqual(result["open_record"]["model"], "sale.order")

    def test_prepare_sale_order_missing_lines(self):
        self._require_models(
            "sale.order",
            "product.product",
            reason="Sales/Product apps are not installed",
        )
        result = self.Assistant.prepare_sale_order(partner_ref=self.partner.id)
        self.assertEqual(result.get("error"), "missing_lines")

    def test_prepare_sale_order_invalid_qty_and_price(self):
        self._require_models(
            "sale.order",
            "product.product",
            reason="Sales/Product apps are not installed",
        )
        product = self.env["product.product"].create(
            {
                "name": "AI SO Qty Product Unique XYZ",
                "type": "consu",
                "sale_ok": True,
                "list_price": 10.0,
            }
        )
        result = self.Assistant.prepare_sale_order(
            partner_ref=self.partner.id,
            lines=[{"product_id": product.id, "qty": 0}],
        )
        self.assertEqual(result.get("error"), "invalid_qty")
        result = self.Assistant.prepare_sale_order(
            partner_ref=self.partner.id,
            lines=[
                {
                    "product_id": product.id,
                    "qty": 1,
                    "price_unit": "bad",
                }
            ],
        )
        self.assertEqual(result.get("error"), "invalid_price")

    def test_prepare_sale_order_unavailable(self):
        with mock.patch.object(
            type(self.env),
            "__contains__",
            new=lambda _env, model: model not in ("sale.order", "product.product"),
        ):
            result = self.Assistant.prepare_sale_order(
                partner_ref=self.partner.id,
                lines=[{"product_id": 1, "qty": 1}],
            )
        self.assertEqual(result.get("error"), "sale_unavailable")

    def _ensure_user_employee(self):
        """Timesheets require an active employee on the current user."""
        self._require_models("hr.employee", reason="HR employees are not available")
        employee = self.env.user.employee_id
        if not employee:
            employee = self.env["hr.employee"].create(
                {
                    "name": self.env.user.name,
                    "user_id": self.env.user.id,
                    "company_id": self.env.company.id,
                }
            )
        return employee

    def test_prepare_timesheet_creates_draft(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet/Project apps are not installed",
        )
        self._ensure_user_employee()
        project = self.env["project.project"].create(
            {"name": "AI Timesheet Project Unique XYZ"}
        )
        result = self.Assistant.prepare_timesheet(
            project_ref=project.id,
            unit_amount=1.5,
            name="AI timesheet entry",
        )
        self.assertNotIn("error", result)
        line = self.env["account.analytic.line"].browse(result["timesheet_id"])
        self.assertTrue(line.exists())
        self.assertEqual(line.project_id, project)
        self.assertEqual(line.unit_amount, 1.5)
        self.assertEqual(result["open_record"]["model"], "account.analytic.line")

    def test_prepare_timesheet_missing_project(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet/Project apps are not installed",
        )
        result = self.Assistant.prepare_timesheet(unit_amount=1)
        self.assertEqual(result.get("error"), "missing_project")

    def test_prepare_timesheet_invalid_hours(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet/Project apps are not installed",
        )
        project = self.env["project.project"].create(
            {"name": "AI Timesheet Hours Unique XYZ"}
        )
        result = self.Assistant.prepare_timesheet(
            project_ref=project.id,
            unit_amount=0,
        )
        self.assertEqual(result.get("error"), "invalid_unit_amount")

    def test_prepare_timesheet_by_task(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            "project.task",
            reason="Timesheet/Project apps are not installed",
        )
        self._ensure_user_employee()
        project = self.env["project.project"].create(
            {"name": "AI Timesheet Task Project Unique XYZ"}
        )
        task = self.env["project.task"].create(
            {
                "name": "AI Timesheet Task Unique XYZ",
                "project_id": project.id,
            }
        )
        result = self.Assistant.prepare_timesheet(
            task_ref=task.id,
            unit_amount=2,
            name="From task",
        )
        self.assertNotIn("error", result)
        line = self.env["account.analytic.line"].browse(result["timesheet_id"])
        self.assertEqual(line.task_id, task)
        self.assertEqual(line.project_id, project)

    def test_prepare_timesheet_project_not_found(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet/Project apps are not installed",
        )
        result = self.Assistant.prepare_timesheet(
            project_ref=999999999,
            unit_amount=1,
        )
        self.assertEqual(result.get("error"), "project_not_found")

    def test_prepare_timesheet_unavailable(self):
        with mock.patch.object(
            type(self.env),
            "__contains__",
            new=lambda _env, model: model
            not in ("account.analytic.line", "project.project"),
        ):
            result = self.Assistant.prepare_timesheet(
                project_ref=1,
                unit_amount=1,
            )
        self.assertEqual(result.get("error"), "timesheet_unavailable")

    def test_resolve_partner_missing_and_ambiguous(self):
        result = self.Assistant._resolve_partner(None, role="customer")
        self.assertEqual(result.get("error"), "missing_customer")
        self.env["res.partner"].create(
            {"name": "AI Ambiguous Partner Alpha", "is_company": True}
        )
        self.env["res.partner"].create(
            {"name": "AI Ambiguous Partner Beta", "is_company": True}
        )
        result = self.Assistant._resolve_partner(
            "AI Ambiguous Partner", as_supplier=False, role="partner"
        )
        self.assertEqual(result.get("error"), "partner_ambiguous")
        self.assertGreaterEqual(len(result.get("candidates") or []), 2)

    def test_resolve_product_unavailable(self):
        with mock.patch.object(
            type(self.env),
            "__contains__",
            new=lambda _env, model: model != "product.product",
        ):
            result = self.Assistant._resolve_product("X")
        self.assertEqual(result.get("error"), "product_unavailable")

    def test_safe_create_error_paths(self):
        Partner = type(self.env["res.partner"])
        with mock.patch.object(Partner, "create", side_effect=AccessError("nope")):
            record, error = self.Assistant._safe_create(
                "res.partner", {"name": "X"}, "partner"
            )
        self.assertFalse(record)
        self.assertEqual(error.get("error"), "access_denied")

        with mock.patch.object(Partner, "create", side_effect=UserError("bad")):
            record, error = self.Assistant._safe_create(
                "res.partner", {"name": "X"}, "partner"
            )
        self.assertEqual(error.get("error"), "validation_error")

        with (
            mock.patch.object(Partner, "create", side_effect=RuntimeError("boom")),
            mute_logger("odoo.addons.ai_agno_assistant.models.ai_assistant_drafts"),
        ):
            record, error = self.Assistant._safe_create(
                "res.partner", {"name": "X"}, "partner"
            )
        self.assertEqual(error.get("error"), "create_failed")

    def test_prepare_opportunity_create_error(self):
        self._require_models("crm.lead", reason="CRM app is not installed")
        Lead = type(self.env["crm.lead"])
        with mock.patch.object(Lead, "create", side_effect=AccessError("nope")):
            result = self.Assistant.prepare_opportunity(name="Blocked")
        self.assertEqual(result.get("error"), "access_denied")

    def test_prepare_helpdesk_ticket_team_by_name(self):
        self._require_models("helpdesk.ticket", reason="Helpdesk app is not installed")
        self._require_models(
            "helpdesk.ticket.team", reason="Helpdesk teams are not available"
        )
        team = self.env["helpdesk.ticket.team"].create(
            {"name": "AI Draft Team By Name Unique XYZ"}
        )
        result = self.Assistant.prepare_helpdesk_ticket(
            name="Ticket by team name",
            team_ref="AI Draft Team By Name Unique XYZ",
        )
        self.assertNotIn("error", result)
        ticket = self.env["helpdesk.ticket"].browse(result["ticket_id"])
        self.assertEqual(ticket.team_id, team)

        self.env["helpdesk.ticket.team"].create(
            {"name": "AI Ambiguous Team Alpha Unique"}
        )
        self.env["helpdesk.ticket.team"].create(
            {"name": "AI Ambiguous Team Beta Unique"}
        )
        result = self.Assistant.prepare_helpdesk_ticket(
            name="Ambiguous team",
            team_ref="AI Ambiguous Team",
        )
        self.assertEqual(result.get("error"), "team_ambiguous")
        result = self.Assistant.prepare_helpdesk_ticket(
            name="Missing team name",
            team_ref="Definitely Missing Team ZZZ999",
        )
        self.assertEqual(result.get("error"), "team_not_found")

    def test_prepare_helpdesk_ticket_team_model_missing(self):
        self._require_models("helpdesk.ticket", reason="Helpdesk app is not installed")
        with mock.patch.object(
            type(self.env),
            "__contains__",
            new=lambda _env, model: model != "helpdesk.ticket.team",
        ):
            result = self.Assistant.prepare_helpdesk_ticket(
                name="No team model",
                team_ref="Support",
            )
        self.assertEqual(result.get("error"), "team_not_found")

    def test_prepare_sale_order_skips_non_dict_lines(self):
        self._require_models(
            "sale.order",
            "product.product",
            reason="Sales/Product apps are not installed",
        )
        result = self.Assistant.prepare_sale_order(
            partner_ref=self.partner.id,
            lines=["skip-me"],
        )
        self.assertEqual(result.get("error"), "missing_lines")
        product = self.env["product.product"].create(
            {
                "name": "AI SO Neg Price Unique XYZ",
                "type": "consu",
                "sale_ok": True,
            }
        )
        result = self.Assistant.prepare_sale_order(
            partner_ref=self.partner.id,
            lines=[{"product_id": product.id, "qty": 1, "price_unit": -1}],
        )
        self.assertEqual(result.get("error"), "invalid_price")

    def test_prepare_timesheet_missing_employee(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet/Project apps are not installed",
        )
        AnalyticLine = self.env["account.analytic.line"]
        if "employee_id" not in AnalyticLine._fields:  # pragma: no cover
            self.skipTest("Timesheet employee_id is not available")
        project = self.env["project.project"].create(
            {"name": "AI Timesheet Missing Employee Unique XYZ"}
        )
        with mock.patch.object(
            type(self.env.user),
            "employee_id",
            new_callable=mock.PropertyMock,
            return_value=False,
        ):
            result = self.Assistant.prepare_timesheet(
                project_ref=project.id,
                unit_amount=1,
            )
        self.assertEqual(result.get("error"), "missing_employee")

    def test_prepare_timesheet_invalid_hours_non_numeric(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet/Project apps are not installed",
        )
        project = self.env["project.project"].create(
            {"name": "AI Timesheet Bad Hours Unique XYZ"}
        )
        result = self.Assistant.prepare_timesheet(
            project_ref=project.id,
            unit_amount="abc",
        )
        self.assertEqual(result.get("error"), "invalid_unit_amount")

    def test_prepare_timesheet_task_unavailable(self):
        self._require_models(
            "account.analytic.line",
            "project.project",
            reason="Timesheet/Project apps are not installed",
        )
        original = type(self.env).__contains__

        def _contains(_env, model):
            if model == "project.task":
                return False
            return original(_env, model)

        with mock.patch.object(type(self.env), "__contains__", new=_contains):
            result = self.Assistant.prepare_timesheet(
                task_ref=1,
                unit_amount=1,
            )
        self.assertEqual(result.get("error"), "timesheet_unavailable")

    def test_resolve_project_and_task_by_name(self):
        self._require_models(
            "project.project",
            "project.task",
            reason="Project app is not installed",
        )
        project = self.env["project.project"].create(
            {"name": "AI Resolve Project Unique XYZ"}
        )
        found = self.Assistant._resolve_project("AI Resolve Project Unique XYZ")
        self.assertEqual(found, project)
        self.assertEqual(
            self.Assistant._resolve_project("Missing Project ZZZ999").get("error"),
            "project_not_found",
        )
        self.env["project.project"].create({"name": "AI Ambiguous Project Alpha"})
        self.env["project.project"].create({"name": "AI Ambiguous Project Beta"})
        self.assertEqual(
            self.Assistant._resolve_project("AI Ambiguous Project").get("error"),
            "project_ambiguous",
        )
        task = self.env["project.task"].create(
            {
                "name": "AI Resolve Task Unique XYZ",
                "project_id": project.id,
            }
        )
        found_task = self.Assistant._resolve_project_task("AI Resolve Task Unique XYZ")
        self.assertEqual(found_task, task)
        self.assertEqual(
            self.Assistant._resolve_project_task("Missing Task ZZZ999").get("error"),
            "task_not_found",
        )
        self.assertEqual(
            self.Assistant._resolve_project_task(999999999).get("error"),
            "task_not_found",
        )
        self.env["project.task"].create(
            {
                "name": "AI Ambiguous Task Alpha",
                "project_id": project.id,
            }
        )
        self.env["project.task"].create(
            {
                "name": "AI Ambiguous Task Beta",
                "project_id": project.id,
            }
        )
        self.assertEqual(
            self.Assistant._resolve_project_task("AI Ambiguous Task").get("error"),
            "task_ambiguous",
        )

    def test_resolve_partner_by_name_and_fallback(self):
        company = self.env["res.partner"].create(
            {"name": "AI Resolve Company Unique XYZ", "is_company": True}
        )
        found = self.Assistant._resolve_partner(
            "AI Resolve Company Unique XYZ", as_supplier=False, role="partner"
        )
        self.assertEqual(found, company)
        contact = self.env["res.partner"].create(
            {"name": "AI Resolve Contact Display Unique", "is_company": False}
        )
        found = self.Assistant._resolve_partner(
            "AI Resolve Contact Display Unique", as_supplier=False, role="partner"
        )
        self.assertEqual(found, contact)
        self.assertEqual(
            self.Assistant._resolve_partner(
                "Missing Partner ZZZ999", as_supplier=False, role="partner"
            ).get("error"),
            "partner_not_found",
        )
