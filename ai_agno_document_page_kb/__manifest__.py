# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Agno Document Page Knowledge Base",
    "summary": """Sync document.page records to Agno knowledge bases via AI bridges""",
    "version": "18.0.1.6.1",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": [
        "ai_oca_bridge_document_page",
        "document_page_tag",
        "ai_agno_connector",
    ],
    "data": [
        "data/document_page_tag_data.xml",
        "data/ai_bridge_data.xml",
    ],
    "demo": [
        "demo/document_page_demo.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
