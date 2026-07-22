This module wires Odoo Knowledge (`document.page`) into Agno knowledge bases
through `ai.bridge` records.

It creates content tags (`support`, `legal`, `processes`, `hr`, `commercial`,
`public`) and create / write / unlink bridges per tag that call the Agno
AgentOS HTTP endpoints for upsert and delete. Only content pages that carry
the matching tag are synced.

Tags map to **knowledge bases** (content), not to Discuss bots. Agno agents
(`ops`, `hr`, `finance`, `support`, `sales`, `marketing`, `web`) choose which
bases to search.

A post-install hook applies the bridge auth token (ICP override or odoo.conf
`agno_bridge_auth_token` from `conf.d`) to bridges with an empty token,
rewrites each bridge domain / field list, then upserts all matching content
pages (demo and pre-existing) into Agno.

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)), which exposes the
AgentOS endpoints and the `/agno/rpc` gateway consumed here.
