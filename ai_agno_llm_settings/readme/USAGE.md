1. Install **Agno LLM Settings** (`ai_agno_llm_settings`).
2. Open **Settings → Agno AI**.
3. Chat LLM: leave the provider empty to use the Agno service env, **or** select
   a provider, set model + API key (host is suggested automatically), and save.
4. Embedder: same pattern under **Embeddings (BYOK)**. Set dimensions to match
   the model (e.g. `1024` for `qwen3-embedding:0.6b`).
5. The next Agno bridge / KB call includes `_odoo.llm` and/or `_odoo.embedder`
   only when the corresponding provider is set.
6. Stored `ai.bridge.execution` payloads mask API keys as `***`.
7. After changing embedder model, provider, or dimensions, click
   **Reindex knowledge bases** (confirm the dialog). That calls Agno to wipe and
   rebuild `support`, `legal`, `processes`, `commercial`, and `public`, then
   re-syncs tagged `document.page` records when `ai_agno_document_page_kb` is
   installed. The **architect** knowledge base is never modified; rebuild it
   offline with `python -m app.ingest_odoo_kb` when needed.
