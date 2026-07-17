Set authentication tokens for Agno ↔ Odoo.

## Preferred (Doodba)

Add to `odoo/custom/conf.d/03-agno.conf` (already present with placeholders):

```ini
[options]
agno_bridge_auth_token = $BRIDGE_AUTH_TOKEN
agno_service_token = $AGNO_SERVICE_TOKEN
```

Doodba expands `$VAR` into `/opt/odoo/auto/odoo.conf` at container start.

| Environment | Where to set the real values |
| ----------- | ---------------------------- |
| test / prod | `.docker/odoo.env` (`BRIDGE_AUTH_TOKEN`, `AGNO_SERVICE_TOKEN`) |
| devel       | Literal values in `conf.d/03-agno.conf` locally (do not commit secrets), or ICP override below |

`agno_service_token` is checked on every `/agno/rpc` call.

`agno_bridge_auth_token` is the shared `odoo.conf` key consumed by the Agno
bridge modules (`agno_chatter_bots`, `agno_thread_bridge_*`,
`agno_document_page_kb`). See each module's CONFIGURE for how they apply it
and for their optional ICP overrides.

## Without Doodba (plain `odoo.conf`)

Put the same keys under `[options]` in your Odoo config file (no `$VAR`
expansion required):

```ini
[options]
agno_bridge_auth_token = YOUR_BRIDGE_AUTH_TOKEN
agno_service_token = YOUR_AGNO_SERVICE_TOKEN
```

Use the same secret values as Agno `BRIDGE_AUTH_TOKEN` and `AGNO_SERVICE_TOKEN`.
Restart Odoo after changing the file. Do not commit real secrets into git.

## Optional ICP override

System parameters win over `odoo.conf` when set:

| Key                                 | Purpose                                                           |
| ----------------------------------- | ----------------------------------------------------------------- |
| `ai_agno_connector.service_token`      | Bearer token expected on `/agno/rpc` (`Authorization: Bearer …`). |
| `ai_agno_connector.max_records`        | Cap on records returned by `search_read` (default `80`).          |
| `ai_agno_connector.allow_unsigned_rpc` | Dev only. Set to `True` to allow unsigned requests (see next).    |
| `ai_agno_connector.unsigned_user_id`   | Dev only. User id accepted when unsigned RPC is enabled.          |

Secrets are **not** written into ICP from `odoo.conf`. In production leave
unsigned RPC keys empty.
