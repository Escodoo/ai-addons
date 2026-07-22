# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge Provider",
    "summary": """Mark which AI runtime each AI bridge targets
    so integrations can scope their behaviour per bridge""",
    "version": "18.0.1.0.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": ["ai_oca_bridge"],
    "data": [
        "views/ai_bridge_views.xml",
    ],
    "installable": True,
}
