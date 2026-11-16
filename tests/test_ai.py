"""AI QA: 에이전트 출력 읽기, 세션 요약, 통과 단계 → 시나리오 초안"""
import json
import unittest
from unittest import mock

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


class ScenarioFromQa(unittest.TestCase):
    def test_command_reads_source_only_when_asked(self):
        tmp, root = make_workspace()
        with tmp:
            (root / "qakit.yml").write_text("name: t\napp:\n  project: ../App.xcodeproj\n  bundleId: x\n", encoding="utf-8")
            ws = q.Workspace(root)
            d = root / "results" / "ai" / "s"
            d.mkdir(parents=True)
            plain = q.ai_command("claude", ws, d, "p", 10)
            self.assertEqual(plain[plain.index("--tools") + 1], "")          # 기본 도구 모두 끔
            self.assertNotIn("--add-dir", plain)
            src = q.ai_command("claude", ws, d, "p", 10, read_source=True)
            self.assertEqual(src[src.index("--tools") + 1], "Read,Grep,Glob")   # 읽기 도구만 (셸·수정 없음)
            self.assertNotIn("Bash", " ".join(src))
            self.assertEqual(src[src.index("--permission-mode") + 1], "dontAsk")
            deny = src[src.index("--disallowedTools") + 1]              # 비밀값 파일은 읽기 거부
            for pat in ("Read(**/secrets*)", "Read(**/keystore/**)", "Read(**/.env)", f"Read(/{ws.secrets_path})", f"Read(/{ws.root}/**)"):
                self.assertIn(pat, deny)
            self.assertIn("앱 소스 읽기", src[src.index("--append-system-prompt") + 1])
            self.assertEqual(q.ai_cwd(ws, True), ws.app_dir)               # 앱 폴더에서 실행 → 작업공간은 읽기 범위 밖
            self.assertEqual(q.ai_cwd(ws, False), ws.root)

    def test_prompt_and_context(self):
        p = q.ai_scenario_prompt("x", 10, source="/app", context="- 그때 목표: 검색")
        self.assertIn("앱 소스(읽기만, 고칠 수 없음): /app", p)
        self.assertIn("시나리오의 근거는 실제 화면", p)
        self.assertIn("바탕이 될 AI QA 결과", p)
        self.assertIn("- 그때 목표: 검색", p)
        self.assertNotIn("앱 소스(", q.ai_scenario_prompt("x", 10))

    def test_session_context(self):
        tmp, root = make_workspace()
        with tmp:
            d = root / "results" / "ai" / "2026-01-01_10-00-00"
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"goal": "검색 QA"}), encoding="utf-8")
            (d / "log.jsonl").write_text(row("launch", True) + "\n" + row("tap", True, "단계: tap: a\n✅") + "\n", encoding="utf-8")
            (d / "issues.jsonl").write_text(json.dumps({"n": 1, "title": "문구 잘림", "severity": "낮음"}, ensure_ascii=False) + "\n", encoding="utf-8")
            (d / "report.md").write_text("## 확인한 것\n- 검색 열림\n", encoding="utf-8")
            c = q.ai_session_context(q.Workspace(root), d)
            for must in ("그때 목표: 검색 QA", "  tap: a", "문구 잘림 (낮음)", "## 확인한 것"):
                self.assertIn(must, c)

    def test_find_ids_tool(self):
        tmp, root = make_workspace()
        with tmp, mock.patch.object(q, "known_ids", return_value={"HomeView.searchButton", "HomeView.sortButton", "LoginView.idField"}):
            content, err = q.McpSession(q.Workspace(root)).call("find_ids", {"query": "home"})
        self.assertFalse(err)
        self.assertIn("HomeView.searchButton", content[0]["text"])
        self.assertNotIn("LoginView", content[0]["text"])
