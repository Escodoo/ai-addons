# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Agno Thread Bridge Helpdesk Mgmt",
    "summary": """Agno thread bridge for OCA helpdesk_mgmt tickets""",
    "version": "18.0.1.0.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": [
        "agno_thread_bridge_base",
        "helpdesk_mgmt",
    ],
    "data": [
        "data/ai_bridge_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
