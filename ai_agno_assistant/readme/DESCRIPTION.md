System-wide AI assistant for Odoo, backed by the Agno companion service.

Users with the **Use System AI Assistant** right get a systray chat panel to:

- ask questions about ERP data (read-only tools, ACL of the current user)
- open menus, window actions and records from typed client actions
- prepare draft business records for human review when the matching apps
  are installed (purchase RFQ, CRM opportunity, helpdesk ticket, sales
  quotation, timesheet). The assistant summarizes the draft and asks
  whether to open it, so creating a record never takes the user away from
  the current screen. There is no hard dependency on those apps; each
  helper returns a structured `*_unavailable` error when the model is
  missing.
- keep a short per-user chat history in the browser across panel close/reopen

The Discuss ERP bot shares the same write helpers and deep-link guidance.
