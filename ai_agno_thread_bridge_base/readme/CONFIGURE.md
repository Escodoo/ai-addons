Set the bearer token expected by Agno `BRIDGE_AUTH_TOKEN` on thread-analysis
bridges.

**Preferred:** set `agno_bridge_auth_token` in `odoo.conf` (same value as Agno
`BRIDGE_AUTH_TOKEN`). On Doodba use `conf.d/03-agno.conf` + `.docker/odoo.env`;
without Doodba, set the literal under `[options]` (see `ai_agno_connector`
CONFIGURE). The post-init hook copies it onto bridges whose `auth_token` is
still empty.

**Optional override:** system parameter
`ai_agno_thread_bridge_base.bridge_auth_token` (wins over `odoo.conf`). Shared by
child modules (`ai_agno_thread_bridge_crm`, `agno_thread_bridge_helpdesk_mgmt`).

**Manual:** open *Settings → Technical → AI Bridges* and paste the token on
**Agno Partner Analysis** (and other thread bridges).

Default URL (from the Odoo container): `http://agno:8000/bridge/odoo`.

Also keep `agno_service_token` / `ai_agno_connector.service_token` aligned with
`AGNO_SERVICE_TOKEN` so the analysis agent can query Odoo through `/agno/rpc`.
