After install, set the bearer token expected by Agno `BRIDGE_AUTH_TOKEN` on
each document.page knowledge-base bridge.

**Preferred (Doodba):** set system parameter
`agno_document_page_kb.bridge_auth_token` to the same value as `BRIDGE_AUTH_TOKEN`
*before* installing (or clearing bridge tokens and upgrading). The post-init
hook copies it onto bridges whose `auth_token` is still empty.

**Manual:** open *Settings → Technical → AI Bridges*, set Authentication Type
to token, and paste `BRIDGE_AUTH_TOKEN` on each Document Page → Agno KB bridge.

Default bridge URLs (reachable from the Odoo container in a Doodba stack):

| Tag          | Upsert URL                                     | Delete URL                                     |
| ------------ | ---------------------------------------------- | ---------------------------------------------- |
| `support`    | `http://agno:8000/bridge/kb/support/upsert`    | `http://agno:8000/bridge/kb/support/delete`    |
| `legal`      | `http://agno:8000/bridge/kb/legal/upsert`      | `http://agno:8000/bridge/kb/legal/delete`      |
| `processes`  | `http://agno:8000/bridge/kb/processes/upsert`  | `http://agno:8000/bridge/kb/processes/delete`  |
| `commercial` | `http://agno:8000/bridge/kb/commercial/upsert` | `http://agno:8000/bridge/kb/commercial/delete` |
| `public`     | `http://agno:8000/bridge/kb/public/upsert`     | `http://agno:8000/bridge/kb/public/delete`     |

Adjust the host or path if your Agno service is exposed differently. Keep the
bridge domains filtered to content pages with the matching tag.

Discuss / livechat bots are configured separately (one `ai.bridge` chatter URL
per agent: `/bridge/chatter/ops`, `/support`, `/sales`, `/web`). Website
livechat wiring to `/bridge/chatter/web` is a later integration step.
