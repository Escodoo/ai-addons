Provisions an Agno **thread** bridge for CRM leads and opportunities
(`crm.lead` → `POST /bridge/odoo`).

Depends on `ai_agno_thread_bridge_base` for the shared auth-token ICP and field
rewrite helpers.

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)), which exposes the
AgentOS endpoints and the `/agno/rpc` gateway consumed here.
