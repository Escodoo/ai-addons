# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install hook to force bridge filters and field lists.

ai.bridge.domain and field_ids are stored computed fields whose compute
resets them when model_id is set. Writing them again after install keeps
the document.page → Agno sync filters intact.
"""

# Tag xmlid → create/write/unlink bridge xmlids (one KB per tag).
_TAG_BRIDGE_PAIRS = (
    (
        "agno_document_page_kb.tag_support",
        (
            "agno_document_page_kb.ai_bridge_support_create",
            "agno_document_page_kb.ai_bridge_support_write",
            "agno_document_page_kb.ai_bridge_support_unlink",
        ),
    ),
    (
        "agno_document_page_kb.tag_legal",
        (
            "agno_document_page_kb.ai_bridge_legal_create",
            "agno_document_page_kb.ai_bridge_legal_write",
            "agno_document_page_kb.ai_bridge_legal_unlink",
        ),
    ),
    (
        "agno_document_page_kb.tag_processes",
        (
            "agno_document_page_kb.ai_bridge_processes_create",
            "agno_document_page_kb.ai_bridge_processes_write",
            "agno_document_page_kb.ai_bridge_processes_unlink",
        ),
    ),
    (
        "agno_document_page_kb.tag_commercial",
        (
            "agno_document_page_kb.ai_bridge_commercial_create",
            "agno_document_page_kb.ai_bridge_commercial_write",
            "agno_document_page_kb.ai_bridge_commercial_unlink",
        ),
    ),
    (
        "agno_document_page_kb.tag_public",
        (
            "agno_document_page_kb.ai_bridge_public_create",
            "agno_document_page_kb.ai_bridge_public_write",
            "agno_document_page_kb.ai_bridge_public_unlink",
        ),
    ),
)


def post_init_hook(env):
    field_refs = [
        "document_page.field_document_page__content",
        "document_page.field_document_page__display_name",
        "document_page.field_document_page__draft_name",
    ]
    field_ids = [env.ref(xmlid).id for xmlid in field_refs]

    for tag_xmlid, bridge_xmlids in _TAG_BRIDGE_PAIRS:
        tag = env.ref(tag_xmlid)
        domain = f"[('type', '=', 'content'), ('tag_ids', 'in', [{tag.id}])]"
        for bridge_xmlid in bridge_xmlids:
            bridge = env.ref(bridge_xmlid)
            vals = {"domain": domain}
            if bridge.usage != "ai_thread_unlink":
                vals["field_ids"] = [(6, 0, field_ids)]
            bridge.write(vals)
