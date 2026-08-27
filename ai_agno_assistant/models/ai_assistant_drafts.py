# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import html
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from odoo.tools import html_sanitize

from odoo.addons.ai_agno_connector.tool_registry import agno_tool

_logger = logging.getLogger(__name__)


class AiAssistantDrafts(models.AbstractModel):
    # Split from ai_assistant for maintainability (drafts vs navigation).
    _inherit = "ai.assistant"  # pylint: disable=consider-merging-classes-inherited

    @api.model
    def _safe_create(self, model_name, values, log_label):
        """Create a record under a savepoint; return (record, error_dict)."""
        try:
            with self.env.cr.savepoint():
                record = self.env[model_name].create(values)
        except AccessError as exc:
            return None, {"error": "access_denied", "detail": str(exc)}
        except (UserError, ValidationError) as exc:
            return None, {"error": "validation_error", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 - structured error for the agent
            _logger.warning("AI assistant %s create failed: %s", log_label, exc)
            return None, {"error": "create_failed", "detail": str(exc)}
        return record, None

    @api.model
    def _sanitize_draft_html(self, value, limit, fallback=""):
        """Sanitize LLM-provided HTML before writing it on a business record."""
        text = value.strip() if isinstance(value, str) else ""
        text = text or fallback
        if not text:
            return ""
        return html_sanitize(
            text,
            sanitize_attributes=True,
            strip_style=True,
            strip_classes=True,
        )[:limit]

    @api.model
    def _resolve_by_id_or_name(
        self,
        Model,
        ref,
        *,
        role,
        label=None,
        name_domain=None,
        fallback_domain=None,
        pick_unique=None,
        candidate_extra=None,
        missing_detail=None,
    ):
        """Resolve a record by integer id or name search (limit 5)."""
        label = label or role.replace("_", " ")
        if ref in (None, False, ""):
            return {
                "error": f"missing_{role}",
                "detail": missing_detail or f"Provide a {label} name, reference or id.",
            }
        if isinstance(ref, int) or (isinstance(ref, str) and str(ref).isdigit()):
            record = Model.browse(int(ref)).exists()
            if not record:
                return {
                    "error": f"{role}_not_found",
                    "detail": f"No {label} with id {ref}.",
                }
            return record
        name = str(ref).strip()
        domain = (
            name_domain(name)
            if callable(name_domain)
            else (name_domain or [("name", "ilike", name)])
        )
        records = Model.search(domain, limit=5)
        if not records and callable(fallback_domain):
            records = Model.search(fallback_domain(name), limit=5)
        if not records:
            return {
                "error": f"{role}_not_found",
                "detail": f"No {label} matching {name!r}.",
            }
        if len(records) > 1 and callable(pick_unique):
            chosen = pick_unique(records, name)
            if chosen:
                return chosen
        if len(records) > 1:
            candidates = []
            for rec in records:
                item = {"id": rec.id, "name": rec.display_name}
                if callable(candidate_extra):
                    item.update(candidate_extra(rec))
                candidates.append(item)
            return {
                "error": f"{role}_ambiguous",
                "detail": f"Multiple {label}s matched; ask the user to clarify.",
                "candidates": candidates,
            }
        return records

    @agno_tool(
        "ai.assistant",
        args=("vendor_ref", "lines", "notes"),
        description="Create a draft RFQ for human review.",
    )
    @api.model
    def prepare_purchase_order(self, vendor_ref=None, lines=None, notes=None):
        """Create a draft RFQ for the requesting user and return a summary.

        Never confirms the order. The user reviews and confirms in the form.
        Requires Purchase (and Product) to be installed — soft dependency.
        """
        self._check_ai_user()
        if "purchase.order" not in self.env or "product.product" not in self.env:
            return {
                "error": "purchase_unavailable",
                "detail": "Purchase app is not available.",
            }
        partner = self._resolve_vendor(vendor_ref)
        if isinstance(partner, dict):
            return partner
        line_vals, line_error = self._prepare_po_lines(lines, partner=partner)
        if line_error:
            return line_error
        values = {
            "partner_id": partner.id,
            "order_line": [(0, 0, line) for line in line_vals],
        }
        if notes and isinstance(notes, str):
            # Price belongs on order lines (price_unit), not in notes.
            values["notes"] = notes.strip()[:2000]
        order, error = self._safe_create("purchase.order", values, "PO")
        if error:
            return error
        _logger.info(
            "AI assistant draft PO %s created by user %s (partner=%s, lines=%s)",
            order.name,
            self.env.user.login,
            partner.id,
            [line.get("product_id") for line in line_vals],
        )
        return {
            "po_id": order.id,
            "name": order.name,
            "partner": {"id": partner.id, "name": partner.display_name},
            "state": order.state,
            "currency": order.currency_id.name,
            "lines_summary": [
                {
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "qty": line.product_qty,
                    "price_unit": line.price_unit,
                }
                for line in order.order_line
            ],
            "open_record": {
                "type": "open_record",
                "model": "purchase.order",
                "res_id": order.id,
            },
        }

    @agno_tool(
        "ai.assistant",
        args=("name", "partner_ref", "description", "expected_revenue"),
        description="Create a CRM opportunity draft for human review.",
    )
    @api.model
    def prepare_opportunity(
        self,
        name=None,
        partner_ref=None,
        description=None,
        expected_revenue=None,
    ):
        """Create a CRM opportunity (draft) for human review."""
        self._check_ai_user()
        if "crm.lead" not in self.env:
            return {
                "error": "crm_unavailable",
                "detail": "CRM app is not available.",
            }
        title = (name or "").strip() if isinstance(name, str) else ""
        partner = None
        if partner_ref not in (None, False, ""):
            partner = self._resolve_partner(
                partner_ref, as_supplier=False, role="partner"
            )
            if isinstance(partner, dict):
                return partner
        if not title:
            if partner:
                title = _("%s's opportunity", partner.display_name)
            else:
                return {
                    "error": "missing_name",
                    "detail": "Provide an opportunity name or a partner.",
                }
        values = {"name": title[:128], "type": "opportunity"}
        if partner:
            values["partner_id"] = partner.id
        if description and isinstance(description, str):
            values["description"] = self._sanitize_draft_html(description, 4000)
        if expected_revenue not in (None, False, ""):
            try:
                values["expected_revenue"] = float(expected_revenue)
            except (TypeError, ValueError):
                return {
                    "error": "invalid_expected_revenue",
                    "detail": "Expected revenue must be a number.",
                }
        lead, error = self._safe_create("crm.lead", values, "opportunity")
        if error:
            return error
        return {
            "opportunity_id": lead.id,
            "name": lead.name,
            "type": lead.type,
            "partner": (
                {"id": partner.id, "name": partner.display_name} if partner else False
            ),
            "open_record": {
                "type": "open_record",
                "model": "crm.lead",
                "res_id": lead.id,
            },
        }

    @agno_tool(
        "ai.assistant",
        args=("name", "description", "partner_ref", "team_ref"),
        description="Create an OCA helpdesk ticket for human review.",
    )
    @api.model
    def prepare_helpdesk_ticket(
        self,
        name=None,
        description=None,
        partner_ref=None,
        team_ref=None,
    ):
        """Create a helpdesk ticket (OCA) for human review."""
        self._check_ai_user()
        if "helpdesk.ticket" not in self.env:
            return {
                "error": "helpdesk_unavailable",
                "detail": "Helpdesk app is not available.",
            }
        title = (name or "").strip() if isinstance(name, str) else ""
        if not title:
            return {
                "error": "missing_name",
                "detail": "Provide a ticket subject/name.",
            }
        body = description if isinstance(description, str) else ""
        body = body.strip() or f"<p>{html.escape(title)}</p>"
        values = {
            "name": title[:128],
            "description": self._sanitize_draft_html(body, 8000),
        }
        if partner_ref not in (None, False, ""):
            partner = self._resolve_partner(
                partner_ref, as_supplier=False, role="partner"
            )
            if isinstance(partner, dict):
                return partner
            values["partner_id"] = partner.id
        if team_ref not in (None, False, ""):
            if "helpdesk.ticket.team" not in self.env:
                return {
                    "error": "team_not_found",
                    "detail": "Helpdesk teams are not available.",
                }
            team = self._resolve_helpdesk_team(team_ref)
            if isinstance(team, dict):
                return team
            values["team_id"] = team.id
        ticket, error = self._safe_create("helpdesk.ticket", values, "ticket")
        if error:
            return error
        return {
            "ticket_id": ticket.id,
            "name": ticket.name,
            "partner": (
                {
                    "id": ticket.partner_id.id,
                    "name": ticket.partner_id.display_name,
                }
                if ticket.partner_id
                else False
            ),
            "team": (
                {"id": ticket.team_id.id, "name": ticket.team_id.display_name}
                if ticket.team_id
                else False
            ),
            "open_record": {
                "type": "open_record",
                "model": "helpdesk.ticket",
                "res_id": ticket.id,
            },
        }

    @agno_tool(
        "ai.assistant",
        args=("partner_ref", "lines", "notes"),
        description="Create a draft sales quotation for human review.",
    )
    @api.model
    def prepare_sale_order(self, partner_ref=None, lines=None, notes=None):
        """Create a draft sales quotation for human review."""
        self._check_ai_user()
        if "sale.order" not in self.env or "product.product" not in self.env:
            return {
                "error": "sale_unavailable",
                "detail": "Sales app is not available.",
            }
        partner = self._resolve_partner(partner_ref, as_supplier=False, role="customer")
        if isinstance(partner, dict):
            return partner
        line_vals, line_error = self._prepare_so_lines(lines)
        if line_error:
            return line_error
        values = {
            "partner_id": partner.id,
            "order_line": [(0, 0, line) for line in line_vals],
        }
        if notes and isinstance(notes, str):
            values["note"] = notes.strip()[:2000]
        order, error = self._safe_create("sale.order", values, "SO")
        if error:
            return error
        return {
            "so_id": order.id,
            "name": order.name,
            "partner": {"id": partner.id, "name": partner.display_name},
            "state": order.state,
            "currency": order.currency_id.name,
            "lines_summary": [
                {
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "qty": line.product_uom_qty,
                    "price_unit": line.price_unit,
                }
                for line in order.order_line
            ],
            "open_record": {
                "type": "open_record",
                "model": "sale.order",
                "res_id": order.id,
            },
        }

    @agno_tool(
        "ai.assistant",
        args=("project_ref", "task_ref", "unit_amount", "name", "date"),
        description="Create a draft timesheet line for human review.",
    )
    @api.model
    def prepare_timesheet(
        self,
        project_ref=None,
        task_ref=None,
        unit_amount=None,
        name=None,
        date=None,
    ):
        """Create a draft timesheet line (account.analytic.line) for review."""
        self._check_ai_user()
        if "account.analytic.line" not in self.env or "project.project" not in self.env:
            return {
                "error": "timesheet_unavailable",
                "detail": "Timesheet / Project apps are not available.",
            }
        project = None
        task = None
        if task_ref not in (None, False, ""):
            if "project.task" not in self.env:
                return {
                    "error": "timesheet_unavailable",
                    "detail": "Project tasks are not available.",
                }
            task = self._resolve_project_task(task_ref)
            if isinstance(task, dict):
                return task
            project = task.project_id
        if project_ref not in (None, False, "") and not project:
            project = self._resolve_project(project_ref)
            if isinstance(project, dict):
                return project
        if not project and not task:
            return {
                "error": "missing_project",
                "detail": "Provide a project_ref and/or task_ref.",
            }
        try:
            hours = float(unit_amount)
        except (TypeError, ValueError):
            hours = 0.0
        if hours <= 0:
            return {
                "error": "invalid_unit_amount",
                "detail": "Provide a positive unit_amount (hours).",
            }
        values = {
            "name": (
                name.strip()[:200] if isinstance(name, str) and name.strip() else "/"
            ),
            "unit_amount": hours,
            "date": date or fields.Date.context_today(self),
        }
        if project:
            values["project_id"] = project.id
        if task:
            values["task_id"] = task.id
        AnalyticLine = self.env["account.analytic.line"]
        if "employee_id" in AnalyticLine._fields:
            employee = getattr(self.env.user, "employee_id", False)
            if not employee:
                return {
                    "error": "missing_employee",
                    "detail": (
                        "The current user has no employee linked; "
                        "timesheets require an active employee."
                    ),
                }
            values["employee_id"] = employee.id
        line, error = self._safe_create("account.analytic.line", values, "timesheet")
        if error:
            return error
        return {
            "timesheet_id": line.id,
            "name": line.name,
            "unit_amount": line.unit_amount,
            "date": str(line.date),
            "project": (
                {"id": line.project_id.id, "name": line.project_id.display_name}
                if line.project_id
                else False
            ),
            "task": (
                {"id": line.task_id.id, "name": line.task_id.display_name}
                if line.task_id
                else False
            ),
            "open_record": {
                "type": "open_record",
                "model": "account.analytic.line",
                "res_id": line.id,
            },
        }

    @api.model
    def _resolve_vendor(self, vendor_ref):
        return self._resolve_partner(vendor_ref, as_supplier=True, role="vendor")

    @api.model
    def _partner_rank_domain(self, as_supplier=False):
        partner_fields = self.env["res.partner"]._fields
        if as_supplier and "supplier_rank" in partner_fields:
            return ["|", ("supplier_rank", ">", 0), ("is_company", "=", True)]
        if (
            not as_supplier
            and "customer_rank" in partner_fields
            and "supplier_rank" in partner_fields
        ):
            return [
                "|",
                "|",
                ("customer_rank", ">", 0),
                ("supplier_rank", ">", 0),
                ("is_company", "=", True),
            ]
        return [("is_company", "=", True)]

    @api.model
    def _resolve_partner(self, partner_ref, *, as_supplier=False, role="partner"):
        Partner = self.env["res.partner"]
        rank_domain = self._partner_rank_domain(as_supplier=as_supplier)
        return self._resolve_by_id_or_name(
            Partner,
            partner_ref,
            role=role,
            name_domain=lambda name: expression.AND(
                [
                    rank_domain,
                    ["|", ("name", "ilike", name), ("ref", "=ilike", name)],
                ]
            ),
            fallback_domain=lambda name: [
                "|",
                ("name", "ilike", name),
                ("display_name", "ilike", name),
            ],
        )

    @api.model
    def _resolve_helpdesk_team(self, team_ref):
        return self._resolve_by_id_or_name(
            self.env["helpdesk.ticket.team"],
            team_ref,
            role="team",
            label="helpdesk team",
        )

    @api.model
    def _resolve_project(self, project_ref):
        return self._resolve_by_id_or_name(
            self.env["project.project"],
            project_ref,
            role="project",
        )

    @api.model
    def _resolve_project_task(self, task_ref):
        return self._resolve_by_id_or_name(
            self.env["project.task"],
            task_ref,
            role="task",
        )

    @api.model
    def _parse_line_qty(self, entry, product, keys):
        raw = 0
        for key in keys:
            if entry.get(key) not in (None, False, ""):
                raw = entry.get(key)
                break
        try:
            qty = float(raw or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            return None, {
                "error": "invalid_qty",
                "detail": f"Quantity must be positive for {product.display_name}.",
            }
        return qty, None

    @api.model
    def _resolve_line_price_unit(self, entry, product, partner, qty, uom):
        """Prefer explicit line price, then vendor pricelist, then cost."""
        raw_price = entry.get("price_unit", entry.get("price"))
        if raw_price not in (None, False, ""):
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                return None, {
                    "error": "invalid_price",
                    "detail": (
                        f"Unit price must be a number for {product.display_name}."
                    ),
                }
            if price < 0:
                return None, {
                    "error": "invalid_price",
                    "detail": (
                        f"Unit price cannot be negative for {product.display_name}."
                    ),
                }
            return price, None
        if partner and hasattr(product, "_select_seller"):
            seller = product._select_seller(
                partner_id=partner,
                quantity=qty,
                uom_id=uom,
            )
            if seller:
                return float(seller.price), None
        return float(product.standard_price or 0.0), None

    @api.model
    def _prepare_po_lines(self, lines, partner=None):
        if not isinstance(lines, list) or not lines:
            return None, {
                "error": "missing_lines",
                "detail": "Provide at least one line with product and quantity.",
            }
        prepared = []
        for entry in lines[:20]:
            if not isinstance(entry, dict):
                continue
            product = self._resolve_product(
                entry.get("product_id") or entry.get("product_ref")
            )
            if isinstance(product, dict):
                return None, product
            qty, qty_error = self._parse_line_qty(
                entry, product, ("qty", "product_qty")
            )
            if qty_error:
                return None, qty_error
            uom = (
                product.uom_po_id if "uom_po_id" in product._fields else product.uom_id
            )
            price_unit, price_error = self._resolve_line_price_unit(
                entry, product, partner, qty, uom
            )
            if price_error:
                return None, price_error
            line = {
                "product_id": product.id,
                "name": product.display_name,
                "product_qty": qty,
                "product_uom": uom.id,
                "price_unit": price_unit,
                "date_planned": fields.Datetime.now(),
            }
            prepared.append(line)
        if not prepared:
            return None, {
                "error": "missing_lines",
                "detail": "Provide at least one valid purchase line.",
            }
        return prepared, None

    @api.model
    def _prepare_so_lines(self, lines):
        if not isinstance(lines, list) or not lines:
            return None, {
                "error": "missing_lines",
                "detail": "Provide at least one line with product and quantity.",
            }
        prepared = []
        for entry in lines[:20]:
            if not isinstance(entry, dict):
                continue
            product = self._resolve_product(
                entry.get("product_id") or entry.get("product_ref")
            )
            if isinstance(product, dict):
                return None, product
            qty, qty_error = self._parse_line_qty(
                entry, product, ("qty", "product_uom_qty", "product_qty")
            )
            if qty_error:
                return None, qty_error
            line = {
                "product_id": product.id,
                "product_uom_qty": qty,
            }
            raw_price = entry.get("price_unit", entry.get("price"))
            if raw_price not in (None, False, ""):
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    return None, {
                        "error": "invalid_price",
                        "detail": (
                            f"Unit price must be a number for {product.display_name}."
                        ),
                    }
                if price < 0:
                    return None, {
                        "error": "invalid_price",
                        "detail": (
                            "Unit price cannot be negative for "
                            f"{product.display_name}."
                        ),
                    }
                line["price_unit"] = price
            prepared.append(line)
        if not prepared:
            return None, {
                "error": "missing_lines",
                "detail": "Provide at least one valid sales line.",
            }
        return prepared, None

    @api.model
    def _pick_exact_default_code(self, products, name):
        exact = products.filtered(
            lambda product: (product.default_code or "").lower() == name.lower()
        )
        return exact if len(exact) == 1 else None

    @api.model
    def _resolve_product(self, product_ref):
        if "product.product" not in self.env:
            return {
                "error": "product_unavailable",
                "detail": "Product app is not available.",
            }
        return self._resolve_by_id_or_name(
            self.env["product.product"],
            product_ref,
            role="product",
            missing_detail="Provide a product name, default_code or id.",
            name_domain=lambda name: [
                "|",
                ("default_code", "=ilike", name),
                "|",
                ("barcode", "=", name),
                ("name", "ilike", name),
            ],
            pick_unique=self._pick_exact_default_code,
            candidate_extra=lambda rec: {"default_code": rec.default_code or False},
        )
