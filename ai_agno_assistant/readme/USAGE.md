1. Grant the group **Use System AI Assistant** to the relevant users.
2. Open the comments icon in the systray and ask a question, for example:
   - "How many open RFQs do we have?"
   - "Open the purchase RFQ list"
   - "Create a purchase order for product Desk, 10 units, vendor Azure Interior"
   - "Create an opportunity for Acme about renewal"
   - "Open a helpdesk ticket: printer offline"
   - "Prepare a quotation for customer Acme, 2 units of Desk"
   - "Log 1.5 hours on project Website Redesign"
3. When a draft record is prepared (RFQ, opportunity, ticket, quotation or
   timesheet), the form opens so you can review and confirm it in Odoo.
   Draft helpers only work when the matching business app is installed.
4. Closing the panel keeps the last messages in the browser (per user). Use
   the trash icon to clear the conversation.
5. Optionally chat with the Discuss ERP bot for longer conversations; answers
   may include `/web#…` links to open records.

## Extending draft helpers

New `prepare_*` / navigation helpers on `ai.assistant` are **not** reachable
from Agno until they are also allowlisted and dispatched in
`ai_agno_connector` (`ALLOWED_MODEL_METHODS` + `_dispatch`) and registered as
tools in the Agno `AssistantTools` toolkit. See the Usage section of
`ai_agno_connector` for the full checklist.
