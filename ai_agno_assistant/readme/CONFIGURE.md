1. Install this module together with `ai_agno_connector` and a running Agno
   service that exposes `/bridge/assistant/chat` and
   `/bridge/assistant/chat/stream`. The bridge record stays pointed at
   `/chat`; the systray stream proxy appends `/stream` itself.
2. Set the bridge auth token via ICP `ai_agno_assistant.bridge_auth_token`
   or `odoo.conf` `agno_bridge_auth_token` (copied onto the bridge on install).
3. Ensure `/agno/rpc` service token and Agno `AGNO_SERVICE_TOKEN` /
   `BRIDGE_AUTH_TOKEN` match your deployment.
4. Optionally install `ai_agno_llm_settings` so Settings → Agno AI can send
   BYOK `_odoo.llm` / `_odoo.llm_profiles` / `_odoo.embedder`. Without that
   module, Agno uses its container `LLM_*` and `EMBEDDER_*`.
