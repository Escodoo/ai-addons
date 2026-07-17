This module exposes a sessionless RPC gateway (`/agno/rpc`) so external AI
agents (for example an Agno AgentOS service) can query Odoo **as the user that
triggered the AI bridge**, respecting that user's ACLs and record rules.

It extends `ai.bridge.execution` to sign the requesting user identity in the
bridge payload. The gateway verifies that signature before impersonating the
user, so a compromised agent (or any bridge-token holder) cannot forge an
arbitrary `user_id`.

Only a small allowlist of read-only ORM methods is exposed
(`search_read`, `search_count`, `fields_get`). Sensitive models and credential
field names are blocked regardless of the caller's own rights.
