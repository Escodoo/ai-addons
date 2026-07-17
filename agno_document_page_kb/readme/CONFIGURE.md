Set the bearer token expected by Agno `BRIDGE_AUTH_TOKEN` on each
document.page knowledge-base bridge.

**Preferred:** set `agno_bridge_auth_token` in `odoo.conf` (same value as Agno
`BRIDGE_AUTH_TOKEN`). On Doodba use `conf.d/03-agno.conf` + `.docker/odoo.env`;
without Doodba, set the literal under `[options]` (see `ai_agno_connector`
CONFIGURE). The post-init hook copies it onto bridges whose `auth_token` is
still empty, rewrites each bridge domain / field list, then upserts every
matching content page (`type=content` + tag) into Agno — including demo pages
and pages that already existed before install.

**Optional override:** system parameter
`agno_document_page_kb.bridge_auth_token` (wins over `odoo.conf`).

Demo page creates may return HTTP 401 while bridges still have an empty token;
the post-init sync reindexes them afterwards. Without conf/ICP token, post-init
skips the sync.

**Manual:** open *Settings → Technical → AI Bridges*, set Authentication Type
to token, and paste `BRIDGE_AUTH_TOKEN` on each Document Page → Agno KB bridge.
Then edit/save pages (or upgrade with the token configured) to index them.

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
