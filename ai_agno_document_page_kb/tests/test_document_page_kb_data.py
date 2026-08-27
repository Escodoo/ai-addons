# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAgnoDocumentPageKbData(TransactionCase):
    def test_configure_applies_token_when_empty(self):
        from ..hooks import configure_kb_bridges, post_init_hook

        bridge = self.env.ref("ai_agno_document_page_kb.ai_bridge_support_create")
        bridge.auth_token = False
        self.env["ir.config_parameter"].sudo().set_param(
            "ai_agno_document_page_kb.bridge_auth_token", "test-bridge-token"
        )
        with patch(
            "odoo.addons.ai_agno_document_page_kb.hooks.schedule_kb_sync"
        ) as mock_sched:
            configure_kb_bridges(self.env)
            self.assertEqual(bridge.auth_token, "test-bridge-token")
            mock_sched.assert_not_called()

            bridge.auth_token = "keep-me"
            self.env["ir.config_parameter"].sudo().set_param(
                "ai_agno_document_page_kb.bridge_auth_token", "other-token"
            )
            post_init_hook(self.env)
            self.assertEqual(bridge.auth_token, "keep-me")
            mock_sched.assert_called_once()

    def test_sync_kb_pages_calls_write_bridges(self):
        from ..hooks import sync_kb_pages

        write_bridge = self.env.ref("ai_agno_document_page_kb.ai_bridge_support_write")
        write_bridge.auth_token = "sync-token"
        tag = self.env.ref("ai_agno_document_page_kb.tag_support")
        page = self.env["document.page"].create(
            {
                "name": "Support page for sync test",
                "type": "content",
                "tag_ids": [(6, 0, [tag.id])],
                "content": "<p>Sync me</p>",
            }
        )
        with patch.object(
            type(write_bridge), "execute_ai_bridge", return_value=None
        ) as mock_execute:
            sync_kb_pages(self.env)
            mock_execute.assert_any_call(page._name, page.id)

    def test_sync_kb_pages_logs_and_continues_on_execute_error(self):
        from ..hooks import sync_kb_pages

        write_bridge = self.env.ref("ai_agno_document_page_kb.ai_bridge_support_write")
        write_bridge.auth_token = "sync-token"
        tag = self.env.ref("ai_agno_document_page_kb.tag_support")
        self.env["document.page"].create(
            {
                "name": "Support page for sync failure test",
                "type": "content",
                "tag_ids": [(6, 0, [tag.id])],
                "content": "<p>Fail me</p>",
            }
        )
        with (
            patch.object(
                type(write_bridge),
                "execute_ai_bridge",
                side_effect=RuntimeError("bridge down"),
            ),
            patch("odoo.addons.ai_agno_document_page_kb.hooks._logger") as mock_logger,
        ):
            sync_kb_pages(self.env)
            mock_logger.exception.assert_called()

    def test_sync_kb_pages_skips_bridges_without_token(self):
        from ..hooks import _TAG_BRIDGE_PAIRS, sync_kb_pages

        write_bridges = self.env["ai.bridge"]
        for _tag_xmlid, bridge_xmlids in _TAG_BRIDGE_PAIRS:
            bridge = self.env.ref(bridge_xmlids[1])
            bridge.auth_token = False
            write_bridges |= bridge
        with patch.object(
            type(write_bridges), "execute_ai_bridge", return_value=None
        ) as mock_execute:
            sync_kb_pages(self.env)
            mock_execute.assert_not_called()

    def test_schedule_kb_sync_runs_inline_without_queue_job(self):
        from ..hooks import schedule_kb_sync

        with patch(
            "odoo.addons.ai_agno_document_page_kb.hooks.sync_kb_pages"
        ) as mock_sync:
            result = schedule_kb_sync(self.env)
        if "queue.job" in self.env:
            self.assertEqual(result, "queued")
            mock_sync.assert_not_called()
        else:
            self.assertEqual(result, "sync")
            mock_sync.assert_called_once()

    def test_execute_ai_bridge_skips_delay_without_queue_job(self):
        bridge = self.env.ref("ai_agno_document_page_kb.ai_bridge_support_write")
        if "queue.job" in self.env:
            self.assertTrue(bridge._should_delay_agno_kb_sync())
            self.assertFalse(
                bridge.with_context(agno_kb_sync_now=True)._should_delay_agno_kb_sync()
            )
        else:
            self.assertFalse(bridge._should_delay_agno_kb_sync())
