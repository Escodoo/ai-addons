1. Install this module together with `ai_agno_connector` and a running Agno
   service that exposes `/bridge/assistant/chat`.
2. Set the bridge auth token via ICP `ai_agno_assistant.bridge_auth_token`
   or `odoo.conf` `agno_bridge_auth_token` (copied onto the bridge on install).
3. Ensure `/agno/rpc` service token and Agno `AGNO_SERVICE_TOKEN` /
   `BRIDGE_AUTH_TOKEN` match your deployment.
