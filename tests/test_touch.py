"""터치 도우미 관리 (TouchHelper): 준비 기다리기·명령·죽으면 다시 띄우기 — 가짜 도우미로 (시뮬레이터 없이)"""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import load_qakit

q = load_qakit()

FAKE = f"""#!{sys.executable}
import sys
mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
if mode == "fail":
    sys.stderr.write("simtouch: 기기 없음\\n"); sys.exit(2)
print("ready 42 digitizer", flush=True)
n = 0
for line in sys.stdin:
    n += 1
    cmd = line.split()[0]
    if mode == "die" and n == 2:
        sys.exit(1)          # 두 번째 명령에서 죽음
    print(("ok " + cmd + " 61") if cmd in ("tap", "ping", "swipe") else ("err 모르는 명령 또는 인자 부족: " + line.strip()), flush=True)
"""


class Touch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tool = Path(self.tmp.name) / "fake-simtouch"
        self.tool.write_text(FAKE, encoding="utf-8")
        self.tool.chmod(self.tool.stat().st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.tmp.cleanup()

    def helper(self, mode):
        return q.TouchHelper(mode, tool=self.tool, ready_timeout=5)   # udid 자리에 가짜 도우미의 동작 방식

    def test_ready_and_commands(self):
        h = self.helper("ok")
        self.assertIsNone(h.start())
        self.assertEqual(h.mode, "digitizer")
        self.assertEqual(h.tap(0.5, 0.25), (True, "ok tap 61"))
        good, line = h.send("jump 1 2")
        self.assertFalse(good)
        self.assertIn("모르는 명령", line)
        h.stop()

    def test_restarts_when_helper_dies(self):
        h = self.helper("die")
        self.assertEqual(h.send("ping"), (True, "ok ping 61"))
        self.assertEqual(h.send("ping"), (True, "ok ping 61"))   # 두 번째에 죽음 → 다시 띄워 다시 보냄
        h.stop()

    def test_start_failure_reason(self):
        h = self.helper("fail")
        self.assertIn("기기 없음", h.start())
        good, why = h.send("ping")
        self.assertFalse(good)


if __name__ == "__main__":
    unittest.main()
