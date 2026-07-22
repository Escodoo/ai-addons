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

4. Allowed methods: `search_read`, `search_count`, `fields_get`.

Responses are formatted for LLM context (datetimes in the user timezone,
monetary values with currency, HTML as plain text, long strings truncated).
Blocked models (for example `res.users`, `ir.config_parameter`) and fields
whose names contain `password`, `token`, `secret`, or `api_key` are never
returned.
