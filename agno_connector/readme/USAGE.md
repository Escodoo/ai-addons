1. Install this module and configure `agno_connector.service_token`.
2. Point an `ai.bridge` URL at your external AI service. When Odoo executes
   the bridge, the payload includes a signed user identity under `_odoo`.
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
