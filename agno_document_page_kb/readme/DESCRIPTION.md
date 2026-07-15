This module wires Odoo Knowledge (`document.page`) into Agno knowledge bases
through `ai.bridge` records.

It creates content tags (`support`, `legal`, `processes`, `commercial`,
`public`) and create / write / unlink bridges per tag that call the Agno
AgentOS HTTP endpoints for upsert and delete. Only content pages that carry
the matching tag are synced.

Tags map to **knowledge bases** (content), not to Discuss bots. Agno agents
(`ops`, `support`, `sales`, `web`) choose which bases to search.

A post-install hook rewrites each bridge domain and field list so the filters
stay correct after `ai.bridge` recomputes stored fields on install.
