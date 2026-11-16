"""AI QA 직접 터치 (H3): 대상 찾기·expect 조건·화면 변화 판단·도구 목록 (시뮬레이터 없이)"""
import contextlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import QAKIT, load_qakit, make_workspace

q = load_qakit()

PARSED = {"screen": {"w": 402, "h": 874}, "elements": [
    {"type": "Button", "id": "home_search_button", "labelRaw": "검색", "x": 340, "y": 60, "w": 44, "h": 44},
    {"type": "StaticText", "id": "", "labelRaw": "인기 팝업", "x": 16, "y": 120, "w": 100, "h": 20},
    {"type": "Button", "id": "", "labelRaw": "인기 팝업 더보기", "x": 300, "y": 120, "w": 80, "h": 20},
    {"type": "Cell", "id": "card", "labelRaw": "카드1", "x": 16, "y": 200, "w": 370, "h": 100},
    {"type": "Cell", "id": "card", "labelRaw": "카드2", "x": 16, "y": 320, "w": 370, "h": 100},
    {"type": "Cell", "id": "card", "labelRaw": "카드3", "x": 16, "y": 2000, "w": 370, "h": 100},   # 화면 밖
    {"type": "Button", "id": "gone", "labelRaw": "", "x": 0, "y": 0, "w": 0, "h": 0},
]}


class FindElement(unittest.TestCase):
    def test_targets(self):
        f = lambda t: q.find_element(t, PARSED)
        self.assertEqual(f("home_search_button")[0]["x"], 340)
        self.assertEqual(f({"label": "인기 팝업"})[0]["type"], "StaticText")
        self.assertEqual(f({"type": "button", "contains": "인기"})[0]["labelRaw"], "인기 팝업 더보기")
        self.assertEqual(f({"id": "card", "index": 1})[0]["labelRaw"], "카드2")
        self.assertEqual(f({"id": "card", "index": 2}), (None, "index 2 없음 (2개)"))   # 화면 밖 카드3은 세지 않음
        self.assertEqual(f("nope"), (None, "화면 구조에 없음"))
        self.assertEqual(f("gone"), (None, "화면 밖에 있음"))
        self.assertEqual(f({"index": 0})[1], "대상에 id·label·contains가 없음")

    def test_condition(self):
        self.assertEqual(q.tap_condition({"visible": "a"}), {"hittable": "a"})
        self.assertEqual(q.tap_condition({"all": [{"missing": "a"}, {"text": "b"}]}),
                         {"all": [{"not-hittable": "a"}, {"text": "b"}]})
        self.assertEqual(q.tap_condition("x"), "x")


class Change(unittest.TestCase):
    class Proc:
        def poll(self): return None

    def ring(self, sizes):
        r = q.FrameRing(None)
        r.proc = self.Proc()
        r.frames.extend((t, b"x" * n) for t, n in sizes)
        return r

    def test_changed_since(self):
        self.assertFalse(self.ring([(1, 1000), (2, 1005), (3, 1010)]).changed_since(1.5))   # 깜박임 정도
        self.assertTrue(self.ring([(1, 1000), (2, 1300)]).changed_since(1.5))
        self.assertIsNone(q.FrameRing(None).changed_since(0))   # 장면을 못 받으면 모름
        self.assertFalse(self.ring([(1, 1000)]).wait_change(time.time(), timeout=0.2))


class Gesture(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(q.gesture_step("long_press", {"target": "a.b"}), "long-press: a.b")
        self.assertEqual(q.gesture_step("long_press", {"target": {"label": "카드"}, "seconds": 2}),
                         'long-press: { on: { label: "카드" }, seconds: 2 }')
        self.assertEqual(q.gesture_step("drag", {"from": "list"}), "drag: { from: list, dir: up }")
        self.assertEqual(q.gesture_step("drag", {"from": "a", "to": "b", "seconds": 1}), "drag: { from: a, to: b, seconds: 1 }")
        self.assertEqual(q.gesture_step("drag", {"from": "a", "dir": "down", "distance": 0.5}), "drag: { from: a, dir: down, distance: 0.5 }")


class Mark(unittest.TestCase):
    def test_touch_mark(self):
        tmp, root = make_workspace()
        try:
            ws = q.Workspace(root)
            (root / ".qakit").mkdir(exist_ok=True)
            q.touch_mark(ws, "drag", 0.5, 0.8)
            q.touch_mark(ws, "drag-done", 0.5, 0.35)
            rows = [json.loads(x) for x in q.taps_path(ws).read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["kind"] for r in rows], ["drag", "drag-done"])
            self.assertEqual((rows[1]["x"], rows[1]["y"], rows[1]["sw"], rows[1]["w"]), (0.5, 0.35, 1, 0))   # 커서 = (x + w/2) / sw
        finally:
            tmp.cleanup()


class TouchCheck(unittest.TestCase):
    """qakit touch: 답이 ok여도 터치가 조용히 무시될 수 있어 누른 뒤 화면이 바뀌었는지 본다"""

    def touch(self, before, after, runner=None):
        class Helper:
            mode = "digitizer"
            def __init__(self, udid): pass
            def start(self): return None
            def send(self, line): return True, "ok tap 90"
            def stop(self): pass
        shots = iter([before, after])
        with mock.patch.object(q, "find_workspace", return_value=mock.Mock(device=None)), \
                mock.patch.object(q, "ensure_booted", return_value="UDID"), \
                mock.patch.object(q, "TouchHelper", Helper), \
                mock.patch.object(q, "screen_jpeg", side_effect=lambda *a, **k: next(shots)), \
                mock.patch.object(q, "serve_load", return_value=runner), \
                mock.patch.object(q, "serve_alive", return_value=True), \
                mock.patch.object(q.time, "sleep"), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            q.cmd_touch(mock.Mock(workspace=None, action=["tap", "0.5", "0.5"]))
        return out.getvalue()

    def test_alike(self):
        self.assertTrue(q.screens_alike(b"x" * 1000, b"x" * 1015))     # 시계·깜박임 정도
        self.assertFalse(q.screens_alike(b"x" * 1000, b"x" * 1300))    # 화면 전환

    def test_ignored_and_changed(self):
        out = self.touch(b"x" * 1000, b"x" * 1005)
        self.assertIn("화면이 그대로", out)
        self.assertNotIn("serve --stop", out)                           # 상주 실행기가 없으면 그 안내는 안 함
        self.assertIn("serve --stop", self.touch(b"x" * 1000, b"x" * 1005, runner={"pid": 1}))
        self.assertIn("터치가 먹혔습니다", self.touch(b"x" * 1000, b"x" * 1400))
        self.assertNotIn("XCUITest가 켠 앱은", self.touch(b"x" * 1000, b"x" * 1400, runner={"pid": 1}))   # 켠 방식으로 미리 경고하지 않음


class Tools(unittest.TestCase):
    def tools(self, env):
        tmp, root = make_workspace()
        try:
            p = subprocess.run([sys.executable, str(QAKIT), "-w", str(root), "mcp"], text=True, capture_output=True, timeout=30,
                               env={**os.environ, **env}, input="\n".join(json.dumps(m) for m in [
                                   {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                                   {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
                                   # 직접 터치 모드에선 조작 도구를 부르지 않는다 (진짜 시뮬레이터를 찾아 누름)
                                   + ([] if env.get("QAKIT_TOUCH") == "direct" else [
                                       {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "tap_point", "arguments": {"x": 1, "y": 1}}}])) + "\n")
            out = [json.loads(x) for x in p.stdout.splitlines()]
            return {t["name"]: t for t in out[1]["result"]["tools"]}, (out[2]["result"] if len(out) > 2 else None)
        finally:
            tmp.cleanup()

    def test_direct_only_when_asked(self):
        plain, call = self.tools({"QAKIT_TOUCH": ""})
        self.assertEqual(len(plain), 20)
        self.assertIn("long_press", plain)   # 길게 누르기·끌기는 XCUITest로도 (시나리오 단계)
        self.assertNotIn("tap_point", plain)
        self.assertNotIn("via", plain["tap"]["inputSchema"]["properties"])
        self.assertTrue(call["isError"])   # 직접 터치가 아니면 좌표 탭은 거절
        direct, _ = self.tools({"QAKIT_TOUCH": "direct"})
        self.assertEqual(len(direct), 21)
        for n in ("long_press", "drag", "tap_point"):
            self.assertIn(n, direct)
        self.assertIn("via", direct["tap"]["inputSchema"]["properties"])

    def test_ai_command_env(self):
        tmp, root = make_workspace()
        try:
            ws = q.Workspace(root)
            d = root / "results" / "ai" / "x"
            d.mkdir(parents=True)
            for direct in (False, True):
                cmd = q.ai_command("claude", ws, d, "p", 5, direct=direct)
                cfg = json.loads(Path(cmd[cmd.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
                env = next(iter(cfg["mcpServers"].values()))["env"]
                self.assertEqual(env.get("QAKIT_TOUCH"), "direct" if direct else None)
        finally:
            tmp.cleanup()

    def test_prompt(self):
        self.assertIn("직접 터치", q.ai_prompt("x", 5, False, direct=True))
        self.assertNotIn("직접 터치", q.ai_prompt("x", 5, False))


if __name__ == "__main__":
    unittest.main()
