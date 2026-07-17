## Settings UI

Go to **Settings → Agno AI** (system administrators only).

By default **all fields are empty**. Leave a provider empty to let Agno use its
service environment.

### Chat LLM (BYOK)

| Field              | Purpose                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| LLM Provider       | Empty, `Ollama`, `OpenAI`, or `Google Gemini`                           |
| LLM Host / Base URL| Reachable from **Agno** (e.g. `http://ollama:11434`, `https://ollama.com`); hidden for Gemini |
| LLM Model          | **Required** when a provider is selected                                |
| LLM API Key        | **Required** for OpenAI/Gemini; **optional** for local Ollama           |

ICP keys: `ai_agno_llm_settings.provider|host|model|api_key`.

### Embeddings (BYOK)

| Field                 | Purpose                                                              |
| --------------------- | -------------------------------------------------------------------- |
| Embedder Provider     | Empty, `Ollama`, or `OpenAI`                                         |
| Embedder Host         | Reachable from **Agno**                                              |
| Embedder Model        | **Required** when a provider is selected                             |
| Embedder Dimensions   | **Required** (e.g. `768` for nomic, `1536` for text-embedding-3-small) |
| Embedder API Key      | **Required** for OpenAI; **optional** for local Ollama               |

ICP keys: `ai_agno_llm_settings.embedder_provider|host|model|api_key|dimensions`.

### Reindex knowledge bases

After changing embedder model, provider, or dimensions, use
**Reindex knowledge bases** on the same Settings page (manual confirmation).

- Calls Agno `POST /bridge/kb/reindex` with the current BYOK embedder payload.
- Rebuilds only business KBs: `support`, `legal`, `processes`, `commercial`,
  `public` (static files + warmup).
- If `ai_agno_document_page_kb` is installed, re-sends tagged `document.page`
  records via `sync_kb_pages`.
- Does **not** wipe or rebuild the `architect` KB (use
  `python -m app.ingest_odoo_kb` offline).

Requires a resolvable embedder (BYOK here or `EMBEDDER_*` on Agno) and a
configured bridge auth token (`agno_bridge_auth_token` / ICP).

## Not this module

| Secret                 | Where it lives                                      |
| ---------------------- | --------------------------------------------------- |
| `BRIDGE_AUTH_TOKEN`    | Agno env + Odoo `agno_bridge_auth_token` / bridge   |
| `AGNO_SERVICE_TOKEN`   | Agno env + `ai_agno_connector.service_token`        |
| Chat LLM env fallback  | Agno `LLM_PROVIDER` / `LLM_HOST` / `LLM_MODEL` / `LLM_API_KEY` |
| Embedder env fallback  | Agno `EMBEDDER_*`                                   |

Do not paste customer keys into `devel.yaml` / `.env` of the Agno service when
using BYOK — configure them here instead.
