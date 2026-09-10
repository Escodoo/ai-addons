Configure the chat LLM and knowledge embedder used by Agno bridges from Odoo
Settings (bring-your-own-key).

With no provider selected, Agno uses its container environment (`LLM_*` for
chat, `EMBEDDER_*` for embeddings).

When a customer selects a chat provider (Ollama, OpenAI, or Google Gemini),
Odoo sends `_odoo.llm` on each bridge request. Agno uses those settings only
and never mixes them with the service `.env` token (Ollama API key is optional
for local instances).

Optional **task profiles** (fast, reasoning, extract) are stored as
`agno.llm.profile` and sent as `_odoo.llm_profiles`. A bridge may override
`_odoo.llm` with **Agno LLM Profile** (for example Fast on the public web
channel). Profiles never change which knowledge base a persona can search.

When an embedder provider is selected (Ollama or OpenAI), Odoo sends
`_odoo.embedder` the same way. After changing embedder model, provider, or
dimensions, use **Reindex knowledge bases** to rebuild the business KBs
(`support`, `legal`, `processes`, `commercial`, `public`). The architect KB
is excluded; rebuild it offline with `python -m app.ingest_odoo_kb`.

Infrastructure tokens (`BRIDGE_AUTH_TOKEN` / `AGNO_SERVICE_TOKEN`) are unchanged
and remain separate.

This bridge targets the companion **Agno service**
([Escodoo/agno-odoo](https://github.com/Escodoo/agno-odoo)), which exposes the
AgentOS endpoints and the `/agno/rpc` gateway consumed here.
