# Copyright 2026 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Agno System AI Assistant",
    "summary": "Global systray AI assistant to query data, open screens and "
    "prepare optional draft business records",
    "version": "18.0.1.0.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": [
        "mail",
        "web",
        "ai_oca_bridge",
        "ai_oca_bridge_provider",
        "ai_oca_bridge_request_timeout",
        "ai_agno_connector",
    ],
    "data": [
        "security/ai_agno_assistant_security.xml",
        "security/ir.model.access.csv",
        "data/ai_bridge_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_agno_assistant/static/src/assistant/**/*",
        ],
        "web.assets_unit_tests": [
            "ai_agno_assistant/static/tests/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
