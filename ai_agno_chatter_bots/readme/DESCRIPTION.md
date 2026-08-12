This module provisions Discuss AI bots and matching `ai.bridge` records for the
Agno chatter personas used in a Doodba / AgentOS stack.

On install it creates one internal user and one chatter bridge per business
channel (`erp`, `ops`, `hr`, `finance`, `support`, `sales`, `marketing`,
`web`).
Each user has
`ai_bridge_id` pointing at its bridge so Discuss routes messages to
`/bridge/chatter/<agent_key>` on the Agno service.

The `erp` persona can query ERP data, suggest `/web#…` deep links, and (with
`ai_agno_assistant` installed) prepare draft purchase orders for human review.

The Architect persona is intentionally **not** created here (dev / AgentOS
only). Knowledge-base sync for `document.page` lives in `ai_agno_document_page_kb`.

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)), which exposes the
AgentOS endpoints and the `/agno/rpc` gateway consumed here.
