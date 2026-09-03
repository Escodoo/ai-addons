1. Grant the group **Use System AI Assistant** to the relevant users.
2. Open the comments icon in the systray and ask a question, for example:
   - "What needs my attention today?"
   - "How many open RFQs do we have?"
   - "Give me an executive briefing of this week" (on screen; edit in
     later turns, then copy or export Markdown/PDF from that message)
   - "Open the purchase RFQ list" (the screen opens at once; a chip remains
     to reopen it)
   - "Create a purchase order for product Desk, 10 units, vendor Azure Interior"
   - "Create an opportunity for Acme about renewal"
   - "Open a helpdesk ticket: printer offline"
   - "Prepare a quotation for customer Acme, 2 units of Desk"
   - "Log 1.5 hours on project Website Redesign"
   - "Confirm quotation SO001" (shows a Confirm chip; nothing posts until you click)
3. When a draft record is prepared, the reply summarizes it and asks whether
   to open it. Answer "yes" (the form opens) or click the chip. The offer
   expires after
   30 minutes. Draft helpers only work when the matching business app is
   installed.
4. Analyses stay in the chat so you can request corrections. Copy the
   message, or export Markdown / PDF from the buttons on that reply.
   Those exports are generated on demand and are not stored in Odoo.
5. Closing the panel keeps the last messages. Use **New conversation** to
   start a fresh draft (it is saved only after the first message), or pick
   a recent one from the list. The trash icon permanently deletes the
   current conversation after confirmation and does not create a
   replacement entry.
6. Optionally chat with the Discuss ERP bot for longer conversations; answers
   may include `/web#…` links to open records.

## Extending draft helpers

New `prepare_*` / navigation helpers on `ai.assistant` are **not** reachable
from Agno until they are also allowlisted and dispatched in
`ai_agno_connector` (`ALLOWED_MODEL_METHODS` + `_dispatch`) and registered as
tools in the Agno `AssistantTools` toolkit. See the Usage section of
`ai_agno_connector` for the full checklist.
