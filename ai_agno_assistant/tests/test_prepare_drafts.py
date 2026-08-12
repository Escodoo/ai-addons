# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


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

    def test_prepare_opportunity_creates_draft(self):
        if "crm.lead" not in self.env:
            self.skipTest("CRM app is not installed")
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
        if "crm.lead" not in self.env:
            self.skipTest("CRM app is not installed")
        result = self.Assistant.prepare_opportunity()
        self.assertEqual(result.get("error"), "missing_name")

    def test_prepare_opportunity_title_from_partner(self):
        if "crm.lead" not in self.env:
            self.skipTest("CRM app is not installed")
        result = self.Assistant.prepare_opportunity(partner_ref=self.partner.id)
        self.assertNotIn("error", result)
        lead = self.env["crm.lead"].browse(result["opportunity_id"])
        self.assertIn(self.partner.display_name, lead.name)

    def test_prepare_opportunity_invalid_revenue(self):
        if "crm.lead" not in self.env:
            self.skipTest("CRM app is not installed")
        result = self.Assistant.prepare_opportunity(
            name="Bad revenue",
            expected_revenue="not-a-number",
        )
        self.assertEqual(result.get("error"), "invalid_expected_revenue")

    def test_prepare_opportunity_partner_not_found(self):
        if "crm.lead" not in self.env:
            self.skipTest("CRM app is not installed")
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
        if "helpdesk.ticket" not in self.env:
            self.skipTest("Helpdesk app is not installed")
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
        if "helpdesk.ticket" not in self.env:
            self.skipTest("Helpdesk app is not installed")
        result = self.Assistant.prepare_helpdesk_ticket(description="x")
        self.assertEqual(result.get("error"), "missing_name")

    def test_prepare_helpdesk_ticket_with_team(self):
        if "helpdesk.ticket" not in self.env:
            self.skipTest("Helpdesk app is not installed")
        if "helpdesk.ticket.team" not in self.env:
            self.skipTest("Helpdesk teams are not available")
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
        if "helpdesk.ticket" not in self.env:
            self.skipTest("Helpdesk app is not installed")
        if "helpdesk.ticket.team" not in self.env:
            self.skipTest("Helpdesk teams are not available")
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
        if "sale.order" not in self.env or "product.product" not in self.env:
            self.skipTest("Sales/Product apps are not installed")
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
        if "sale.order" not in self.env or "product.product" not in self.env:
            self.skipTest("Sales/Product apps are not installed")
        result = self.Assistant.prepare_sale_order(partner_ref=self.partner.id)
        self.assertEqual(result.get("error"), "missing_lines")

    def test_prepare_sale_order_invalid_qty_and_price(self):
        if "sale.order" not in self.env or "product.product" not in self.env:
            self.skipTest("Sales/Product apps are not installed")
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
        if "hr.employee" not in self.env:
            self.skipTest("HR employees are not available")
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
        if "account.analytic.line" not in self.env or "project.project" not in self.env:
            self.skipTest("Timesheet/Project apps are not installed")
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
        if "account.analytic.line" not in self.env or "project.project" not in self.env:
            self.skipTest("Timesheet/Project apps are not installed")
        result = self.Assistant.prepare_timesheet(unit_amount=1)
        self.assertEqual(result.get("error"), "missing_project")

    def test_prepare_timesheet_invalid_hours(self):
        if "account.analytic.line" not in self.env or "project.project" not in self.env:
            self.skipTest("Timesheet/Project apps are not installed")
        project = self.env["project.project"].create(
            {"name": "AI Timesheet Hours Unique XYZ"}
        )
        result = self.Assistant.prepare_timesheet(
            project_ref=project.id,
            unit_amount=0,
        )
        self.assertEqual(result.get("error"), "invalid_unit_amount")

    def test_prepare_timesheet_by_task(self):
        if (
            "account.analytic.line" not in self.env
            or "project.project" not in self.env
            or "project.task" not in self.env
        ):
            self.skipTest("Timesheet/Project apps are not installed")
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
        if "account.analytic.line" not in self.env or "project.project" not in self.env:
            self.skipTest("Timesheet/Project apps are not installed")
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
