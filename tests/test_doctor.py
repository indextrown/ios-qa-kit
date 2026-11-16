"""qakit doctor 시간 제한: 바깥 도구(simctl 등)가 멈춰도 --timeout초 안에 끝나고, 그 항목만 '확인 못 함'(unknown)
— 없는 것과 구분한다. 가짜 xcodebuild·xcode-select·xcodegen과 멈추는 xcrun을 PATH 앞에 두고 돌린다 (리눅스 CI에서도)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import QAKIT, make_workspace

FAKE = {
    "xcodebuild": 'echo "Xcode 99.0"; echo "Build version 99A1"',
    "xcode-select": "echo /Applications/Xcode.app/Contents/Developer",
    "xcodegen": "echo xcodegen",
    "xcrun": "exec /bin/sleep 30",   # 시뮬레이터 서비스가 뜨는 중이라 simctl이 멈춘 것처럼
}


class DoctorTimeout(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        for name, body in FAKE.items():
            p = fake_bin / name
            p.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
            p.chmod(0o755)
        (root / "jdk" / "bin").mkdir(parents=True)
        (root / "jdk" / "bin" / "java").write_text("", encoding="utf-8")   # java_home을 부르지 않게
        self.env = dict(os.environ, PATH=f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}", JAVA_HOME=str(root / "jdk"))

    def qakit(self, *args):
        start = time.monotonic()
        r = subprocess.run([sys.executable, str(QAKIT), *args], env=self.env, text=True, capture_output=True, timeout=60)
        return r, time.monotonic() - start

    def test_system_json(self):
        r, secs = self.qakit("doctor", "--system", "--json", "--timeout", "1")
        self.assertLess(secs, 15, "멈춘 simctl(30초)을 기다림")
        d = json.loads(r.stdout)
        rows = {c["key"]: c for c in d["checks"]}
        self.assertEqual((rows["xcode"]["ok"], rows["xcode"]["unknown"]), (True, False))
        self.assertEqual((rows["simulator"]["ok"], rows["simulator"]["unknown"]), (False, True))
        self.assertIn("1초 안에 답이 없음 (xcrun simctl list)", rows["simulator"]["detail"])
        self.assertEqual((d["problems"], d["unknown"]), (0, 1))   # 확인 못 한 것은 '없음'으로 세지 않는다

    def test_system_text(self):
        r, secs = self.qakit("doctor", "--system", "--timeout", "1")
        self.assertLess(secs, 15)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("⚠️  iOS 시뮬레이터: 확인 못 함", r.stdout)
        self.assertIn("필수 항목 1개를 1초 안에 확인하지 못함", r.stderr)

    def test_workspace(self):
        tmp, ws = make_workspace()
        self.addCleanup(tmp.cleanup)
        r, secs = self.qakit("-w", str(ws), "doctor", "--timeout", "1")
        self.assertLess(secs, 15)
        self.assertIn("✅ Xcode 99.0", r.stdout)
        self.assertIn("❌ 시뮬레이터 확인 못 함 — 1초 안에 답이 없음 (xcrun simctl list)", r.stdout)


if __name__ == "__main__":
    unittest.main()
