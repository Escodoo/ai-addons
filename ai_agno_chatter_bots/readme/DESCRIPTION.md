This module provisions Discuss AI bots and matching `ai.bridge` records for the
Agno chatter personas used in a Doodba / AgentOS stack.

On install it creates one internal user and one chatter bridge per business
channel (`erp`, `ops`, `support`, `sales`, `marketing`, `web`). Each user has
`ai_bridge_id` pointing at its bridge so Discuss routes messages to
`/bridge/chatter/<agent_key>` on the Agno service.

The Architect persona is intentionally **not** created here (dev / AgentOS
only). Knowledge-base sync for `document.page` lives in `ai_agno_document_page_kb`.
