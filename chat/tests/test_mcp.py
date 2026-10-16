"""Tests for the MCP server at /mcp, through the website's app on the small made-up database.

Run from the repo root:  python3 -m unittest chat.tests.test_mcp
"""
import json, os, sys, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "dashboard", "tests"))
from test_queries import make_db  # noqa: E402
from chat import tools  # noqa: E402
from web import api  # noqa: E402


class McpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = mock.patch.dict(os.environ, {"RESEARCH_DB": make_db(tempfile.mkdtemp())})
        cls.env.start()
        cls.client = TestClient(api.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.env.stop()

    def rpc(self, method, params=None, id=1):
        r = self.client.post("/mcp", json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})
        self.assertEqual(r.status_code, 200)
        return r.json()

    def call(self, name, arguments):
        return self.rpc("tools/call", {"name": name, "arguments": arguments})["result"]

    def test_initialize_agrees_a_version_and_explains_the_data(self):
        res = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "1"}})["result"]
        self.assertEqual(res["protocolVersion"], "2025-06-18")
        self.assertEqual(res["capabilities"], {"tools": {"listChanged": False}})
        self.assertIn("not a DOL finding", res["instructions"])
        self.assertIn("/#/employer/<employer_id>", res["instructions"])
        newest = self.rpc("initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"]
        self.assertEqual(newest, "2025-11-25")

    def test_lists_the_chat_tools_as_read_only(self):
        listed = self.rpc("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in listed], [t["name"] for t in tools.TOOLS])
        for t in listed:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertTrue(t["annotations"]["readOnlyHint"])

    def test_tool_calls_return_the_same_json_as_the_chat_tools(self):
        res = self.call("search_employers", {"query": "acme software"})
        self.assertFalse(res["isError"])
        hits = json.loads(res["content"][0]["text"])["matches"]
        self.assertIn("Acme Software", {h["employer_name"] for h in hits})
        con = tools.q.connect()
        try:
            self.assertEqual(json.loads(res["content"][0]["text"]),
                             json.loads(json.dumps(tools.run_tool(con, "search_employers", {"query": "acme software"}))))
        finally:
            con.close()

    def test_bad_input_is_a_tool_error_and_unknown_names_are_protocol_errors(self):
        res = self.call("get_employer", {"employer_id": 999999})
        self.assertTrue(res["isError"])
        self.assertIn("999999", res["content"][0]["text"])
        self.assertEqual(self.rpc("tools/call", {"name": "drop_tables"})["error"]["code"], -32602)
        self.assertEqual(self.rpc("resources/list")["error"]["code"], -32601)
        self.assertEqual(self.rpc("ping")["result"], {})

    def test_notifications_get_202_and_other_methods_405(self):
        r = self.client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((r.status_code, r.content), (202, b""))
        self.assertEqual(self.client.get("/mcp").status_code, 405)
        self.assertEqual(self.client.delete("/mcp").status_code, 405)
        bad = self.client.post("/mcp", content=b"{not json")
        self.assertEqual((bad.status_code, bad.json()["error"]["code"]), (400, -32700))
        batch = self.client.post("/mcp", json=[{"jsonrpc": "2.0", "id": 7, "method": "ping"},
                                               {"jsonrpc": "2.0", "method": "notifications/initialized"}]).json()
        self.assertEqual(batch, [{"jsonrpc": "2.0", "id": 7, "result": {}}])


if __name__ == "__main__":
    unittest.main()
