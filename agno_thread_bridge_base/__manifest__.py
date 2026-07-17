# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Agno Thread Bridge Base",
    "summary": """Base Agno thread bridges for Odoo base models (Partner Analysis)""",
    "version": "18.0.1.1.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": [
        "ai_oca_bridge",
        "agno_connector",
    ],
    "data": [
        "data/ai_bridge_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
