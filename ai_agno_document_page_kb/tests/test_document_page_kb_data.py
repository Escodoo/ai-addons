# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import Mock, patch

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

    def _without_queue_job(self):
        real_contains = type(self.env).__contains__

        def without_queue(env, name):
            if name == "queue.job":
                return False
            return real_contains(env, name)

        return patch.object(type(self.env), "__contains__", without_queue)

    def test_schedule_kb_sync_runs_inline_without_queue_job(self):
        from ..hooks import schedule_kb_sync

        with (
            self._without_queue_job(),
            patch(
                "odoo.addons.ai_agno_document_page_kb.hooks.sync_kb_pages"
            ) as mock_sync,
        ):
            result = schedule_kb_sync(self.env)
        self.assertEqual(result, "sync")
        mock_sync.assert_called_once()

    def test_schedule_kb_sync_queues_when_delay_available(self):
        from ..hooks import schedule_kb_sync

        delayed = Mock()
        page_sudo = Mock()
        page_model = Mock()
        page_model.with_delay = Mock()
        page_model.sudo.return_value = page_sudo
        page_sudo.with_delay.return_value = delayed

        class FakeEnv:
            def __contains__(self, name):
                return name == "queue.job"

            def __getitem__(self, name):
                if name != "document.page":
                    raise KeyError(name)
                return page_model

        result = schedule_kb_sync(FakeEnv())
        page_sudo.with_delay.assert_called_once_with(
            channel="root.agno_kb",
            description="Agno KB reindex",
        )
        delayed._agno_sync_all_kb_pages.assert_called_once_with()
        self.assertEqual(result, "queued")

    def test_agno_sync_all_kb_pages_calls_sync(self):
        with patch(
            "odoo.addons.ai_agno_document_page_kb.hooks.sync_kb_pages"
        ) as mock_sync:
            result = self.env["document.page"]._agno_sync_all_kb_pages()
        mock_sync.assert_called_once_with(self.env)
        self.assertTrue(result)

    def test_should_delay_agno_kb_sync_branches(self):
        bridge = self.env.ref("ai_agno_document_page_kb.ai_bridge_support_write")
        other = self.env["ai.bridge"].create(
            {
                "name": "Non KB Bridge",
                "model_id": self.env.ref("base.model_res_partner").id,
                "url": "https://example.com/bridge",
                "auth_type": "none",
                "usage": "none",
                "result_kind": "immediate",
                "result_type": "none",
            }
        )
        with self._without_queue_job():
            self.assertFalse(bridge._should_delay_agno_kb_sync())

        real_contains = type(self.env).__contains__

        def with_queue(env, name):
            if name == "queue.job":
                return True
            return real_contains(env, name)

        with (
            patch.object(type(self.env), "__contains__", with_queue),
            patch.object(type(bridge), "with_delay", create=True),
        ):
            self.assertTrue(bridge._should_delay_agno_kb_sync())
            self.assertFalse(
                bridge.with_context(agno_kb_sync_now=True)._should_delay_agno_kb_sync()
            )
            self.assertFalse(other._should_delay_agno_kb_sync())

    def test_execute_ai_bridge_queues_when_delay_enabled(self):
        bridge = self.env.ref("ai_agno_document_page_kb.ai_bridge_support_write")
        delayed = Mock()
        delayed.with_context.return_value = delayed
        delayed.execute_ai_bridge.return_value = "queued-job"
        with (
            patch.object(type(bridge), "_should_delay_agno_kb_sync", return_value=True),
            patch.object(type(bridge), "with_delay", return_value=delayed, create=True),
        ):
            result = bridge.execute_ai_bridge("document.page", 1)
        delayed.with_context.assert_called_once_with(agno_kb_sync_now=True)
        delayed.execute_ai_bridge.assert_called_once_with("document.page", 1)
        self.assertEqual(result, "queued-job")

    def test_execute_ai_bridge_runs_super_when_not_delayed(self):
        bridge = self.env.ref("ai_agno_document_page_kb.ai_bridge_support_write")
        parent = next(
            cls
            for cls in type(bridge).__mro__[1:]
            if "execute_ai_bridge" in cls.__dict__
        )
        with (
            patch.object(
                type(bridge), "_should_delay_agno_kb_sync", return_value=False
            ),
            patch.object(
                parent, "execute_ai_bridge", return_value="done"
            ) as mock_super,
        ):
            result = bridge.execute_ai_bridge("document.page", 1)
        mock_super.assert_called_once()
        self.assertEqual(result, "done")
