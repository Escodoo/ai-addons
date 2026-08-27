This module exposes a sessionless RPC gateway (`/agno/rpc`, read/write cursor)
so external AI agents (for example an Agno AgentOS service) can query Odoo
**as the user that triggered the AI bridge**, respecting that user's ACLs and
record rules.

It extends `ai.bridge.execution` to sign the requesting user identity in the
bridge payload. The gateway verifies that signature before impersonating the
user, so a compromised agent (or any bridge-token holder) cannot forge an
arbitrary `user_id`.

Only a small allowlist of read-only ORM methods is exposed
(`search_read`, `search_count`, `fields_get`). In addition, typed helpers on
dedicated models may be allowlisted (for example `ai.assistant` methods
`find_navigation`, `prepare_purchase_order`, `prepare_opportunity`,
`prepare_helpdesk_ticket`, `prepare_sale_order`, `prepare_timesheet`) — never
generic `create` / `write` / `unlink`. Sensitive models (`ir.*` plus a credential allowlist), credential field
names, and domain paths that traverse those models are blocked regardless
of the caller's own rights. Extra models can be blocked via ICP.

When adding a new assistant helper, update this allowlist together with the
Agno `AssistantTools` toolkit (see Usage).

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)), which exposes the
AgentOS endpoints and the `/agno/rpc` gateway consumed here.
