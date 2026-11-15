"""AI QA: 에이전트 출력 읽기, 세션 요약, 통과 단계 → 시나리오 초안"""
import json
import unittest

from helpers import load_qakit, make_workspace

q = load_qakit()


def row(tool, ok, summary="", args=None, why=None):
    return json.dumps({"at": "2026-01-01T10:00:00", "tool": tool, "args": args or {}, "ok": ok, "seconds": 1,
                       "summary": summary, **({"why": why} if why else {})}, ensure_ascii=False)


class Events(unittest.TestCase):
    def test_claude_stream(self):
        ev, _ = q.ai_events("claude", {"type": "system", "subtype": "init", "model": "m",
                                       "mcp_servers": [{"name": "qakit", "status": "connected"}], "tools": ["mcp__qakit__tap", "Bash"]})
        self.assertEqual(ev[0]["kind"], "info")
        self.assertIn("도구 1개", ev[0]["text"])
        ev, _ = q.ai_events("claude", {"type": "system", "subtype": "init", "mcp_servers": [{"name": "qakit", "status": "failed"}]})
        self.assertEqual(ev[0]["kind"], "error")
        ev, _ = q.ai_events("claude", {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "화면을 읽겠습니다"},
            {"type": "tool_use", "name": "mcp__qakit__tap", "input": {"target": "a", "why": "열기"}}]}})
        self.assertEqual([e["kind"] for e in ev], ["text", "tool"])
        self.assertEqual(ev[1]["why"], "열기")
        self.assertNotIn("why", ev[1]["text"])
        _, res = q.ai_events("claude", {"type": "result", "result": "보고서", "total_cost_usd": 0.1, "num_turns": 3, "is_error": False})
        self.assertEqual((res["text"], res["turns"]), ("보고서", 3))


class Session(unittest.TestCase):
    def test_steps_after_last_launch_ok_only(self):
        tmp, root = make_workspace()
        with tmp:
            d = root / "results" / "ai" / "2026-01-01_10-00-00"
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"client": "Claude Code", "goal": "검색 QA", "started": "2026-01-01T10:00:00",
                                                     "ended": "2026-01-01T10:01:30", "cost": 0.2}), encoding="utf-8")
            (d / "log.jsonl").write_text("\n".join([
                row("launch", True), row("tap", True, "단계: tap: old_step\n✅"),
                row("launch", True), row("tap", True, "단계: { tap: a, expect: { visible: b } }\n✅ 1초"),
                row("tap", False, "단계: tap: typo\n❌"), row("screen", True, "화면 …"),
                row("type_text", True, '단계: type: { into: c, text: "x" }\n✅'),
                row("save_scenario", True, "저장", {"name": "search-01"}),
            ]) + "\n", encoding="utf-8")
            (d / "issues.jsonl").write_text(json.dumps({"n": 1, "title": "문구 잘림"}, ensure_ascii=False) + "\n", encoding="utf-8")
            ws = q.Workspace(root)
            s = q.ai_session_info(ws, d)
            self.assertEqual((s["goal"], s["seconds"], s["calls"], s["failed"], s["issues"], s["steps"], s["saved"]),
                             ("검색 QA", 90, 8, 1, 1, 2, ["search-01"]))
            full = q.ai_session_info(ws, d, full=True)
            self.assertEqual(full["stepList"], ["{ tap: a, expect: { visible: b } }", 'type: { into: c, text: "x" }'])
            self.assertTrue(full["fromLaunch"])
            text, merged, n, from_launch = q.build_scenario_text(ws, "x", title="T", start="home",
                                                                 recorded=(full["stepList"], True))
            self.assertIn("AI QA 세션에서", text)
            self.assertIn("  - use: home", text)
            self.assertEqual(n, 3)   # use: home + 2단계


if __name__ == "__main__":
    unittest.main()
