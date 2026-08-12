1. Install this module and configure `ai_agno_connector.service_token`.
2. Point an `ai.bridge` URL at your Agno service and set **Provider** to
   `Agno` on that record. Only then does Odoo sign the user identity under
   `_odoo`. Keep other providers (e.g. `Generic`) for third-party bridges so
   they keep the upstream behaviour. Optionally raise **Request Timeout**
   (from `ai_oca_bridge_request_timeout`) for slow LLM-backed endpoints.
3. The agent calls `POST /agno/rpc?db=<dbname>` with:

   - Header `Authorization: Bearer <service_token>`
   - JSON body with `user_id`, `user_hmac`, `user_hmac_ts`, `model`, `method`,
     and method-specific arguments (`domain`, `fields`, `limit`, …)

4. Allowed read methods on any non-blocked model: `search_read`,
   `search_count`, `fields_get`.

Responses are formatted for LLM context (datetimes in the user timezone,
monetary values with currency, HTML as plain text, long strings truncated).
Blocked models (for example `res.users`, `ir.config_parameter`) and fields
whose names contain `password`, `token`, `secret`, or `api_key` are never
returned.

## Typed model allowlist (`ALLOWED_MODEL_METHODS`)

`/agno/rpc` never exposes generic `create` / `write` / `unlink`. Extra write
helpers must be listed explicitly in
`controllers/main.py` → `ALLOWED_MODEL_METHODS` **and** dispatched with an
explicit argument map in `_dispatch`.

Current assistant surface (`model=ai.assistant`):

| Method | Role |
| ------ | ---- |
| `find_navigation` | Resolve menus/actions the user can open |
| `prepare_purchase_order` | Draft RFQ |
| `prepare_opportunity` | Draft CRM opportunity |
| `prepare_helpdesk_ticket` | Draft OCA helpdesk ticket |
| `prepare_sale_order` | Draft sales quotation |
| `prepare_timesheet` | Draft timesheet line |

These methods are implemented in `ai_agno_assistant` and called by the Agno
service toolkit `AssistantTools` (`app/tools/assistant_tools.py` in
[Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)).

### Checklist when adding a new `prepare_*` (or similar) helper

Keep all layers in sync in the same change set (separate commits per addon /
repo):

1. **Odoo `ai_agno_assistant`** — implement `@api.model` helper on
   `ai.assistant` (draft-only, ACL-aware, return a JSON-serializable dict with
   a stable `*_unavailable` / `*_ambiguous` error shape when needed).
2. **This module (`ai_agno_connector`)** — add the method name to
   `ALLOWED_MODEL_METHODS["ai.assistant"]` and a dedicated branch in
   `_dispatch` that passes only known kwargs (do not forward the raw JSON
   body).
3. **Agno service** — register a tool on `AssistantTools`, call
   `_rpc_sync("<method>", …)`, and document the tool in
   `app/prompts/assistant.py` (systray) and `app/prompts/chatter.py` (`erp`
   persona) when the agent should use it.
4. **Tests** — cover the allowlist/dispatch path in
   `ai_agno_connector` / `ai_agno_assistant`, and the tool RPC wiring in Agno.

If any of those layers is missing, the agent either gets `method_not_allowed`
from Odoo or invents unsafe workarounds in the prompt.
