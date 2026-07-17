# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Agno LLM Settings",
    "summary": (
        "Bring-your-own-key LLM and embedder settings for Agno "
        "(Ollama / OpenAI / Gemini)"
    ),
    "version": "18.0.1.5.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": [
        "ai_agno_connector",
        "base",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
}
