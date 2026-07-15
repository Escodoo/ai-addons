Set the following `ir.config_parameter` keys (Settings → Technical → System
Parameters):

| Key                                   | Purpose                                                                 |
| ------------------------------------- | ----------------------------------------------------------------------- |
| `agno_connector.service_token`        | Bearer token expected on `/agno/rpc` (`Authorization: Bearer …`).       |
| `agno_connector.max_records`          | Cap on records returned by `search_read` (default `80`).                |
| `agno_connector.allow_unsigned_rpc`   | Dev only. Set to `True` to allow unsigned requests (see next row).      |
| `agno_connector.unsigned_user_id`     | Dev only. User id accepted when unsigned RPC is enabled.                |

In production, set a strong `agno_connector.service_token` and leave **both**
`allow_unsigned_rpc` and `unsigned_user_id` empty. Unsigned requests are
rejected unless both gates match.

The external agent must send the same service token and forward the
`user_id` / `user_hmac` / `user_hmac_ts` values from the bridge payload
(`_odoo` section) when calling `/agno/rpc?db=<dbname>`.
