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
helpers must be listed explicitly: decorate the `ai.assistant` method with
`@agno_tool` (name, allowed kwargs, description). `_dispatch` then forwards
only those kwargs. A static fallback allowlist remains for the generic
read methods.

`GET /agno/tools` (same bearer token as `/agno/rpc`) returns the catalog.
The Agno service consumes it on boot so `AssistantTools` and prompt
fragments stay in sync without a matching edit in four places.

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

1. **Odoo `ai_agno_assistant`** — implement `@api.model` helper on
   `ai.assistant` with `@agno_tool` (draft-only, ACL-aware, JSON-serializable
   dict with a stable `*_unavailable` / `*_ambiguous` error shape).
2. **Agno service** — add a thin wrapper on `AssistantTools` if the method
   needs extra validation; the catalog + prompt fragment are loaded from
   `GET /agno/tools` on boot.
3. **Tests** — cover the allowlist/dispatch path in `ai_agno_connector` /
   `ai_agno_assistant`, and the tool RPC wiring in Agno.

If the decorator is missing, the agent gets `method_not_allowed` from Odoo.
