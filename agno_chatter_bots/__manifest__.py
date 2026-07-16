# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Agno Chatter Bots",
    "summary": """Provision Discuss chatter bots and AI bridges for Agno personas""",
    "version": "18.0.1.0.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": [
        "ai_oca_bridge_chatter",
        "agno_connector",
    ],
    "data": [
        "data/ai_bridge_data.xml",
        "data/res_users_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
