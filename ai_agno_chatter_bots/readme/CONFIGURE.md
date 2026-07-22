After install, set the bearer token expected by Agno `BRIDGE_AUTH_TOKEN` on
each chatter bridge.

**Preferred:** set `agno_bridge_auth_token` in `odoo.conf` (same value as Agno
`BRIDGE_AUTH_TOKEN`). On Doodba this is usually `conf.d/03-agno.conf` with
`$BRIDGE_AUTH_TOKEN` from `.docker/odoo.env`; without Doodba, put the literal
key under `[options]` (see `ai_agno_connector` CONFIGURE). The post-init hook
copies it onto bridges whose `auth_token` is still empty.

**Optional override:** system parameter `ai_agno_chatter_bots.bridge_auth_token`
(wins over `odoo.conf`).

**Manual:** open *Settings → Technical → AI Bridges*, set Authentication Type
to token, and paste `BRIDGE_AUTH_TOKEN` on each Agno Chatter bridge.

Default URLs (reachable from the Odoo container):

| User (login)   | Bridge              | URL                                         |
| -------------- | ------------------- | ------------------------------------------- |
| Bot ERP (`bot.erp`)           | Agno Chatter ERP     | `http://agno:8000/bridge/chatter/erp`       |
| Bot Ops (`bot.ops`)           | Agno Chatter Ops     | `http://agno:8000/bridge/chatter/ops`       |
| Bot Suporte (`bot.suporte`)   | Agno Chatter Support | `http://agno:8000/bridge/chatter/support`   |
| Bot Comercial (`bot.comercial`) | Agno Chatter Sales | `http://agno:8000/bridge/chatter/sales`     |
| Bot Marketing (`bot.marketing`) | Agno Chatter Marketing | `http://agno:8000/bridge/chatter/marketing` |
| Bot Website (`bot.website`)   | Agno Chatter Web     | `http://agno:8000/bridge/chatter/web`       |

There is **no** Architect bot in this module. Create it manually only if needed
for Discuss; the AgentOS UI already exposes an architect agent.

Also ensure `agno_service_token` / `ai_agno_connector.service_token` matches Agno
`AGNO_SERVICE_TOKEN` so personas with Odoo tools can call `/agno/rpc`.
