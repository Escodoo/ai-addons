# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAgnoInternalTeams(TransactionCase):
    def test_internal_team_bridges_point_at_team_urls(self):
        commercial = self.env.ref(
            "ai_agno_internal_teams.ai_bridge_team_commercial_review"
        )
        finance = self.env.ref("ai_agno_internal_teams.ai_bridge_team_finance_ops")
        self.assertEqual(commercial.provider, "agno")
        self.assertTrue(commercial.url.endswith("/bridge/team/commercial-review"))
        self.assertTrue(finance.url.endswith("/bridge/team/finance-ops"))
        self.assertNotIn("/bridge/chatter/web", commercial.url)
        self.assertNotIn("/bridge/chatter/support", finance.url)
