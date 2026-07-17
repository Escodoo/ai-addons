# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install setup for document.page → Agno KB bridges.

ai.bridge.domain and field_ids are stored computed fields whose compute
resets them when model_id is set. Writing them again after install keeps
the document.page → Agno sync filters intact.

Also copies the bridge auth token (ICP override or odoo.conf
agno_bridge_auth_token) onto bridges that still have an empty auth_token,
then upserts every matching content page (demo and pre-existing) into Agno.

Demo page creates may hit Agno with an empty token (HTTP 401) before this
hook runs; the post-init sync reindexes them once bridges are configured.
"""

import logging

from odoo.addons.ai_agno_connector.token_utils import (
    CONFIG_BRIDGE_AUTH_TOKEN,
    ensure_token,
)

_logger = logging.getLogger(__name__)

_ICP_KEY = "ai_agno_document_page_kb.bridge_auth_token"

# Tag xmlid → create/write/unlink bridge xmlids (one KB per tag).
_TAG_BRIDGE_PAIRS = (
    (
        "ai_agno_document_page_kb.tag_support",
        (
            "ai_agno_document_page_kb.ai_bridge_support_create",
            "ai_agno_document_page_kb.ai_bridge_support_write",
            "ai_agno_document_page_kb.ai_bridge_support_unlink",
        ),
    ),
    (
        "ai_agno_document_page_kb.tag_legal",
        (
            "ai_agno_document_page_kb.ai_bridge_legal_create",
            "ai_agno_document_page_kb.ai_bridge_legal_write",
            "ai_agno_document_page_kb.ai_bridge_legal_unlink",
        ),
    ),
    (
        "ai_agno_document_page_kb.tag_processes",
        (
            "ai_agno_document_page_kb.ai_bridge_processes_create",
            "ai_agno_document_page_kb.ai_bridge_processes_write",
            "ai_agno_document_page_kb.ai_bridge_processes_unlink",
        ),
    ),
    (
        "ai_agno_document_page_kb.tag_commercial",
        (
            "ai_agno_document_page_kb.ai_bridge_commercial_create",
            "ai_agno_document_page_kb.ai_bridge_commercial_write",
            "ai_agno_document_page_kb.ai_bridge_commercial_unlink",
        ),
    ),
    (
        "ai_agno_document_page_kb.tag_public",
        (
            "ai_agno_document_page_kb.ai_bridge_public_create",
            "ai_agno_document_page_kb.ai_bridge_public_write",
            "ai_agno_document_page_kb.ai_bridge_public_unlink",
        ),
    ),
)

_BRIDGE_XMLIDS = tuple(
    xmlid for _tag, bridge_xmlids in _TAG_BRIDGE_PAIRS for xmlid in bridge_xmlids
)


def _apply_auth_token(env):
    """Copy token (ICP or odoo.conf) onto KB bridges with empty auth_token."""
    token = ensure_token(env, _ICP_KEY, CONFIG_BRIDGE_AUTH_TOKEN)
    if not token:
        return
    for xmlid in _BRIDGE_XMLIDS:
        bridge = env.ref(xmlid, raise_if_not_found=False)
        if bridge and not bridge.auth_token:
            bridge.auth_token = token


def configure_kb_bridges(env):
    """Apply auth token and rewrite domain/field_ids on all KB bridges."""
    _apply_auth_token(env)

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


def sync_kb_pages(env):
    """Upsert matching content pages into Agno via write bridges.

    Covers demo pages created during install and any pre-existing pages that
    already carry the module tags. Skips bridges that still have no token.
    """
    Page = env["document.page"].sudo()
    for tag_xmlid, bridge_xmlids in _TAG_BRIDGE_PAIRS:
        write_bridge = env.ref(bridge_xmlids[1], raise_if_not_found=False)
        tag = env.ref(tag_xmlid, raise_if_not_found=False)
        if not write_bridge or not tag or not write_bridge.auth_token:
            continue
        pages = Page.search(
            [
                ("type", "=", "content"),
                ("tag_ids", "in", [tag.id]),
            ]
        )
        for page in pages:
            try:
                write_bridge.execute_ai_bridge(page._name, page.id)
            except Exception:
                _logger.exception(
                    "Failed to sync document.page %s via %s",
                    page.id,
                    write_bridge.name,
                )


def post_init_hook(env):
    configure_kb_bridges(env)
    sync_kb_pages(env)
