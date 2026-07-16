After install, set the bearer token expected by Agno `BRIDGE_AUTH_TOKEN` on
each chatter bridge.

**Preferred (Doodba):** set system parameter
`agno_chatter_bots.bridge_auth_token` to the same value as `BRIDGE_AUTH_TOKEN`
*before* installing (or clearing bridge tokens and upgrading). The post-init
hook copies it onto bridges whose `auth_token` is still empty.

**Manual:** open *Settings → Technical → AI Bridges*, set Authentication Type
to token, and paste `BRIDGE_AUTH_TOKEN` on each Agno Chatter bridge.

Default URLs (reachable from the Odoo container):

| User (login)   | Bridge              | URL                                         |
| -------------- | ------------------- | ------------------------------------------- |
| Bot ERP (`bot.erp`)           | Agno Chatter ERP     | `http://agno:8000/bridge/chatter/erp`       |
| Bot Ops (`bot.ops`)           | Agno Chatter Ops     | `http://agno:8000/bridge/chatter/ops`       |
| Bot Suporte (`bot.suporte`)   | Agno Chatter Support | `http://agno:8000/bridge/chatter/support`   |
| Bot Comercial (`bot.comercial`) | Agno Chatter Sales | `http://agno:8000/bridge/chatter/sales`     |
| Bot Website (`bot.website`)   | Agno Chatter Web     | `http://agno:8000/bridge/chatter/web`       |

There is **no** Architect bot in this module. Create it manually only if needed
for Discuss; the AgentOS UI already exposes an architect agent.

Also ensure `agno_connector.service_token` matches Agno `AGNO_SERVICE_TOKEN` so
personas with Odoo tools can call `/agno/rpc`.
