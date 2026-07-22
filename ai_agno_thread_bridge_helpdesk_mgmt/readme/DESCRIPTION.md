Provisions an Agno **thread** bridge for OCA `helpdesk_mgmt` tickets
(`helpdesk.ticket` → `POST /bridge/odoo`).

Depends on `ai_agno_thread_bridge_base` for the shared auth-token ICP and field
rewrite helpers. Install only when `helpdesk_mgmt` is part of the stack.

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)), which exposes the
AgentOS endpoints and the `/agno/rpc` gateway consumed here.
