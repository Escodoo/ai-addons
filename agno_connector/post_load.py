# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import http

_logger = logging.getLogger(__name__)


def post_load():
    """Resolve the database from the ``db`` query parameter on /agno/rpc.

    Sessionless requests (auth="none") cannot resolve a database when the
    server exposes more than one, so addon controllers would return 404.
    Same approach used by OCA queue_job for /queue_job/runjob.
    """
    _logger.info(
        "Apply Request._get_session_and_dbname monkey patch to capture db"
        " on /agno/rpc requests"
    )
    _get_session_and_dbname_orig = http.Request._get_session_and_dbname

    def _get_session_and_dbname(self):
        session, dbname = _get_session_and_dbname_orig(self)
        if (
            not dbname
            and self.httprequest.path == "/agno/rpc"
            and self.httprequest.args.get("db")
        ):
            dbname = self.httprequest.args["db"]
        return session, dbname

    http.Request._get_session_and_dbname = _get_session_and_dbname
