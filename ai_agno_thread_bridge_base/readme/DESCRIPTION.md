Foundation module for Agno **thread** bridges (`usage=thread` →
`POST /bridge/odoo`).

It provisions Partner Analysis on `res.partner` and exposes post-install helpers
(`apply_auth_token`, `set_bridge_fields`) so domain-specific modules
(`ai_agno_thread_bridge_helpdesk_mgmt`, sale, account, …) can share the same
auth token ICP and field-list rewrite pattern.

Discuss bots live in `ai_agno_chatter_bots`; Knowledge sync lives in
`ai_agno_document_page_kb`.
