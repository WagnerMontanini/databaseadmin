# -*- coding: utf-8 -*-
##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################
import json
import secrets

from regression.python_test_utils import test_utils

from pgadmin.browser.server_groups.servers.databases.tests import (
    utils as database_utils,
)
from pgadmin.tools.sqleditor.tests.execute_query_test_utils import async_poll
from pgadmin.utils.route import BaseTestGenerator


class TestDownloadFormatsQueryTool(BaseTestGenerator):
    """
    Validate download formats for query tool: TSV/JSON/JSONL.
    """

    scenarios = [
        (
            "Download TSV with valid query",
            dict(
                sql='SELECT 1 as "A",2 as "B",3 as "C"',
                download_format="tsv",
            ),
        ),
        (
            "Download JSON with valid query",
            dict(
                sql='SELECT 1 as "A",2 as "B",3 as "C"',
                download_format="json",
            ),
        ),
        (
            "Download JSONL with valid query",
            dict(
                sql='SELECT 1 as "A",2 as "B",3 as "C"',
                download_format="jsonl",
            ),
        ),
    ]

    def setUp(self):
        self._db_name = "download_results_" + str(secrets.choice(range(10000, 65535)))
        self._sid = self.server_information["server_id"]

        self._did = test_utils.create_database(self.server, self._db_name)

    def initiate_sql_query_tool(self, trans_id, sql_query):
        """
        Initiate query tool execution at least once, so downloading can work
        from the async cursor.
        """
        url = "/sqleditor/query_tool/start/{0}".format(trans_id)
        response = self.tester.post(
            url, data=json.dumps({"sql": sql_query}), content_type="html/json"
        )
        self.assertEqual(response.status_code, 200)

        return async_poll(
            tester=self.tester, poll_url="/sqleditor/poll/{0}".format(trans_id)
        )

    def runTest(self):
        db_con = database_utils.connect_database(
            self, test_utils.SERVER_GROUP, self._sid, self._did
        )
        if not db_con["info"] == "Database connected.":
            raise Exception("Could not connect to the database.")

        # Initialize query tool
        trans_id = str(secrets.choice(range(1, 9999999)))
        init_url = "/sqleditor/initialize/sqleditor/{0}/{1}/{2}/{3}".format(
            trans_id, test_utils.SERVER_GROUP, self._sid, self._did
        )
        response = self.tester.post(
            init_url, data=json.dumps({"dbname": self._db_name})
        )
        self.assertEqual(response.status_code, 200)

        poll_res = self.initiate_sql_query_tool(trans_id, self.sql)
        self.assertEqual(poll_res.status_code, 200)

        download_url = "/sqleditor/query_tool/download/{0}".format(trans_id)
        payload = {
            "query": self.sql,
            "format": self.download_format,
            "filename": "test.{0}".format(self.download_format),
            "query_commited": False,
        }
        download_resp = self.tester.post(download_url, data=payload)
        self.assertEqual(download_resp.status_code, 200)

        content = download_resp.data.decode("utf-8")
        headers = dict(download_resp.headers)

        if self.download_format == "tsv":
            self.assertIn("text/tab-separated-values", headers["Content-Type"])
            self.assertIn('"A"\t"B"\t"C"', content)
            self.assertIn("1\t2\t3", content)
        elif self.download_format == "json":
            self.assertIn("application/json", headers["Content-Type"])
            data = json.loads(content)
            self.assertTrue(isinstance(data, list))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["A"], 1)
            self.assertEqual(data[0]["B"], 2)
            self.assertEqual(data[0]["C"], 3)
        else:
            # jsonl
            self.assertIn("application/x-ndjson", headers["Content-Type"])
            lines = [l for l in content.splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["A"], 1)
            self.assertEqual(row["B"], 2)
            self.assertEqual(row["C"], 3)

        # Close query tool
        close_url = "/sqleditor/close/{0}".format(trans_id)
        response = self.tester.delete(close_url)
        self.assertEqual(response.status_code, 200)

        database_utils.disconnect_database(self, self._sid, self._did)

    def tearDown(self):
        main_conn = test_utils.get_db_connection(
            self.server["db"],
            self.server["username"],
            self.server["db_password"],
            self.server["host"],
            self.server["port"],
            self.server["sslmode"],
        )
        test_utils.drop_database(main_conn, self._db_name)
