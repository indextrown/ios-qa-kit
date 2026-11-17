"""UI AI를 매끄럽게: 같은 대상 여럿·가림 판단, 작업공간 사정 미리 알리기, 여러 단계 한 번에 (기기 없이)"""
import os
import unittest
from unittest import mock

from helpers import load_qakit, make_workspace

q = load_qakit()


def el(type_, label="", id_="", x=0, y=0, w=10, h=10, depth=1):
    return {"type": type_, "id": id_, "labelRaw": label, "x": x, "y": y, "w": w, "h": h, "depth": depth, "value": ""}


# 왼쪽 패널의 닫기 + 오른쪽 선박 카드의 닫기 (같은 라벨 둘), 패널 닫기 안에는 같은 라벨의 그림
SCREEN = {"screen": {"w": 1280, "h": 800}, "elements": [
    el("Other", "", "root", 0, 0, 1280, 800, 0),
    el("Cell", "", "panel", 0, 42, 349, 726, 1),
    el("Button", "close", "", 294, 46, 48, 48, 2),
    el("Other", "close", "", 302, 54, 32, 32, 3),
    el("Cell", "", "vesselCard", 1048, 45, 216, 186, 1),
    el("StaticText", "MSC", "", 1060, 56, 100, 13, 2),
    el("Button", "close", "vesselClose", 1226, 45, 48, 37, 2),
]}


class Ambiguous(unittest.TestCase):
    def test_two_close_buttons_are_not_guessed(self):
        found, why = q.find_element({"type": "button", "label": "close"}, SCREEN, strict=True)
        self.assertIsNone(found)
        self.assertIn("2개", why)
        self.assertIn("index 0", why)
        self.assertIn("#vesselClose", why)

    def test_index_picks_one(self):
        found, _ = q.find_element({"type": "button", "label": "close", "index": 1}, SCREEN, strict=True)
        self.assertEqual(found["id"], "vesselClose")

    def test_nested_same_label_counts_once(self):
        only_panel = {"screen": SCREEN["screen"], "elements": SCREEN["elements"][:4]}
        found, why = q.find_element({"label": "close"}, only_panel, strict=True)
        self.assertEqual(found["type"], "Button", why)

    def test_not_strict_keeps_old_behaviour(self):
        found, _ = q.find_element({"type": "button", "label": "close"}, SCREEN)
        self.assertEqual(found["x"], 294)


class Covered(unittest.TestCase):
    def test_popup_button_over_target(self):
        els = [el("Other", "", "", 0, 0, 400, 800, 0),
               el("Button", "저장", "save", 100, 700, 200, 48, 1),
               el("Button", "확인", "ok", 150, 690, 100, 60, 1)]   # 나중에 그려진 작은 버튼이 저장 가운데를 덮음
        self.assertEqual(q.covered_by(els, 1, {"w": 400, "h": 800}), 2)

    def test_child_and_big_frames_are_not_cover(self):
        els = [el("Button", "저장", "save", 100, 700, 200, 48, 1),
               el("StaticText", "저장", "", 180, 710, 40, 20, 2),            # 자식
               el("Cell", "panel", "panel", 0, 0, 400, 800, 1)]           # 화면 전체 틀
        self.assertIsNone(q.covered_by(els, 0, {"w": 400, "h": 800}))


class Context(unittest.TestCase):
    def test_lists_steps_scenarios_and_secret_keys_only(self):
        files = {"steps/north-up.qa.yml": "# 해도를 North Up으로\nsteps:\n  - tap: menu\n",
                 "scenarios/first-login.qa.yml": "name: 처음 로그인\nsteps:\n  - tap: a\n",
                 "secrets.txt": "EMAIL=me@example.com\nPASSWORD=hunter2\n"}
        tmp, root = make_workspace(files)
        with tmp:
            ws = q.find_workspace(str(root))
            text = q.ai_workspace_context(ws)
        self.assertIn("use: north-up — 해도를 North Up으로", text)
        self.assertIn("first-login", text)
        self.assertIn("EMAIL", text)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("me@example.com", text)

    def test_command_carries_context(self):
        tmp, root = make_workspace({"steps/home.qa.yml": "name: 홈까지\nsteps:\n  - tap: a\n"})
        with tmp:
            ws = q.find_workspace(str(root))
            d = root / "ai"
            d.mkdir()
            cmd = q.ai_command("claude", ws, d, "hi", 10, chat={"id": "x", "resume": False})
            sys_prompt = cmd[cmd.index("--append-system-prompt") + 1]
            self.assertIn("use: home", sys_prompt)
            cmd = q.ai_command("claude", ws, d, "hi", 10)
            self.assertIn("use: home", cmd[cmd.index("--append-system-prompt") + 1])


class Steps(unittest.TestCase):
    def test_steps_stop_at_first_failure(self):
        tmp, root = make_workspace()
        with tmp:
            s = q.McpSession(q.find_workspace(str(root)))
            ran = []

            def fake_do(line):
                ran.append(line)
                return (line != "tap: b"), f"done {line}"
            with mock.patch.object(s, "do", side_effect=fake_do), mock.patch.dict(os.environ, {"QAKIT_AI_AUTOSCREEN": "0"}):
                out, err = s.call("step", {"steps": ["tap: a", "tap: b", "tap: c"]})
        self.assertTrue(err)
        self.assertEqual(ran, ["tap: a", "tap: b"])
        self.assertIn("남은 1단계", out[0]["text"])


if __name__ == "__main__":
    unittest.main()
