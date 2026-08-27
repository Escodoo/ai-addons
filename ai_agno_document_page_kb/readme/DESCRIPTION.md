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
rewrites each bridge domain / field list, then schedules an upsert of matching content pages (demo and pre-existing)
into Agno. The upsert runs through ``queue_job`` when that module is
installed, so module installation does not wait on HTTP. Writes on tagged
pages use the same queue when available.

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)), which exposes the
AgentOS endpoints and the `/agno/rpc` gateway consumed here.
