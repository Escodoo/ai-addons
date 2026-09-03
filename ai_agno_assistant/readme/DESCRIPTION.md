System-wide AI assistant for Odoo, backed by the Agno companion service.

Users with the **Use System AI Assistant** right get a systray chat panel to:

- ask questions about ERP data (read-only tools, ACL of the current user),
  including aggregates (`read_group`) and a daily attention digest
- explain the record currently open in the form (hydrated UI context)
- open menus, window actions and records immediately (the first navigation
  action runs in the client; a chip remains to reopen). Confirmations stay
  human-in-the-loop
- prepare draft business records for human review when the matching apps
  are installed (purchase RFQ, CRM opportunity, helpdesk ticket, sales
  quotation, timesheet, partner, activity, extra order line)
- propose irreversible confirmations (draft SO / RFQ) that the user must
  accept in the panel (human-in-the-loop)
- copy a briefing or export it as Markdown / PDF without storing a file
- keep conversations server-side (per user) with the browser as a cache

The Discuss ERP bot shares the same write helpers and deep-link guidance.
