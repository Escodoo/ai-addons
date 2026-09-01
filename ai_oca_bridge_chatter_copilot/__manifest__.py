# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "AI OCA Bridge Chatter Copilot",
    "summary": """Let AI bridges answer gateway and livechat conversations
    with human handoff""",
    "version": "18.0.1.0.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": [
        "ai_oca_bridge_chatter",
        "mail_gateway",
        "im_livechat",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_oca_bridge_chatter_copilot/static/src/core/common/*.esm.js",
        ],
    },
    "installable": True,
}
