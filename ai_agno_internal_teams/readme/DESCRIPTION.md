Provisions two **internal** Agno crew bridges:

- Commercial Review → `POST /bridge/team/commercial-review` (sales + legal)
- Finance Ops → `POST /bridge/team/finance-ops` (finance + ops)

These are not Discuss bots and must never be wired to website livechat or
customer support. External personas (`web`, `support`) stay single-agent so
internal knowledge bases are not exposed.

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)).
