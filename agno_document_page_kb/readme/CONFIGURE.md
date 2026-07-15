After install, open each bridge under *Settings → Technical → AI Bridges* and
set **Authentication Type** to token with the same secret as the Agno service
`BRIDGE_AUTH_TOKEN`. The field is left empty on purpose so secrets are not
committed in XML.

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
