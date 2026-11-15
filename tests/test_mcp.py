"""qakit mcp: 단계 글 만들기, JSON-RPC (시뮬레이터 없이)"""
import json
import subprocess
import sys
import unittest

from helpers import QAKIT, load_qakit, make_workspace

q = load_qakit()


class McpYaml(unittest.TestCase):
    def test_values(self):
        self.assertEqual(q.mcp_yaml("home_search_button"), "home_search_button")
        self.assertEqual(q.mcp_yaml({"id": "a.b", "index": 0}), "{ id: a.b, index: 0 }")
        self.assertEqual(q.mcp_yaml({"type": "text", "label": "검색: 해 보기"}), '{ type: text, label: "검색: 해 보기" }')
        self.assertEqual(q.mcp_yaml("true"), '"true"')   # YAML에서 다른 값으로 읽히는 글자는 따옴표
        self.assertEqual(q.mcp_yaml({"all": [{"visible": "a"}, {"missing": "b"}]}), "{ all: [{ visible: a }, { missing: b }] }")


class Protocol(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = make_workspace()
        self.p = subprocess.Popen([sys.executable, str(QAKIT), "-w", str(self.root), "mcp"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.n = 0

    def tearDown(self):
        self.p.stdin.close()
        self.p.wait(timeout=10)
        self.p.stdout.close()
        self.tmp.cleanup()

    def rpc(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if not notify:
            self.n += 1
            msg["id"] = self.n
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        return None if notify else json.loads(self.p.stdout.readline())

    def test_session(self):
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test"}})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("get_testing_guide", init["result"]["instructions"])
        self.rpc("notifications/initialized", notify=True)   # 알림에는 답하지 않는다 (다음 줄이 다음 응답)
        tools = {t["name"]: t for t in self.rpc("tools/list")["result"]["tools"]}
        self.assertEqual(len(tools), 15)
        self.assertIn("why", tools["tap"]["inputSchema"]["properties"])
        self.assertNotIn("why", tools["screen"]["inputSchema"]["properties"])
        guide = self.rpc("tools/call", {"name": "get_testing_guide", "arguments": {}})["result"]
        self.assertFalse(guide["isError"])
        bad = self.rpc("tools/call", {"name": "report_issue", "arguments": {
            "title": "t", "severity": "낮음", "steps": [], "expected": "", "actual": "", "reproduced": False}})["result"]
        self.assertTrue(bad["isError"])   # 재현하지 않은 보고는 받지 않음
        bad_name = self.rpc("tools/call", {"name": "save_scenario", "arguments": {"name": "Bad Name", "title": "x"}})["result"]
        self.assertTrue(bad_name["isError"])
        self.assertEqual(self.rpc("nope")["error"]["code"], -32601)
        # 도구 호출 기록
        logs = list((self.root / "results" / "ai").glob("*/log.jsonl"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(len(logs[0].read_text(encoding="utf-8").splitlines()), 3)

    def test_old_protocol_and_parse_error(self):
        self.assertEqual(self.rpc("initialize", {"protocolVersion": "2024-11-05"})["result"]["protocolVersion"], "2024-11-05")
        self.p.stdin.write("not json\n")
        self.p.stdin.flush()
        self.assertEqual(json.loads(self.p.stdout.readline())["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
