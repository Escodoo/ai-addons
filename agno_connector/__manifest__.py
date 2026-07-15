# Copyright 2026 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Agno Connector",
    "summary": """RPC gateway that runs AI agent queries with the
    identity of the requesting user, enforcing ACLs and record rules""",
    "version": "18.0.1.0.0",
    "development_status": "Beta",
    "category": "Technical",
    "author": "Escodoo",
    "maintainers": ["marcelsavegnago"],
    "website": "https://github.com/Escodoo/ai-addons",
    "license": "AGPL-3",
    "depends": ["ai_oca_bridge"],
    "post_load": "post_load",
    "installable": True,
}
