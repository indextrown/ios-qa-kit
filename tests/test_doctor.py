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


FAKE_ANDROID = {   # 가짜 SDK — FAKE_HANG=devices면 adb devices가, pm이면 adb shell pm path가 멈춘다 (adb 서버가 멈춘 것처럼)
    "platform-tools/adb": """case "$*" in
  "devices -l") [ "$FAKE_HANG" = devices ] && exec /bin/sleep 30
    printf 'List of devices attached\\nemulator-5554          device product:sdk model:sdk_gphone device:emu64a\\n' ;;
  *"emu avd name") printf 'qakit\\nOK\\n' ;;
  *"pm path"*) [ "$FAKE_HANG" = pm ] && exec /bin/sleep 30
    printf 'package:/data/app/base.apk\\n' ;;
esac""",
    "emulator/emulator": '[ "$1" = -list-avds ] && echo qakit',
}

ANDROID_YML = "name: demo\nplatform: android\napp:\n  project: app\n  packageName: com.example.demo\nemulator: qakit\n"


class AndroidDoctorTimeout(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, body in FAKE_ANDROID.items():
            p = root / "sdk" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
            p.chmod(0o755)
        (root / "jdk" / "bin").mkdir(parents=True)
        (root / "jdk" / "bin" / "java").write_text("", encoding="utf-8")
        self.env = dict(os.environ, ANDROID_HOME=str(root / "sdk"), JAVA_HOME=str(root / "jdk"),
                        ANDROID_AVD_HOME=str(root / "avd"))   # 이 맥의 AVD 설정을 읽지 않게
        for k in ("ANDROID_SDK_ROOT", "ANDROID_SERIAL", "FAKE_HANG"):
            self.env.pop(k, None)
        tmp_ws, self.ws = make_workspace({"qakit.yml": ANDROID_YML, "app/settings.gradle": ""})
        self.addCleanup(tmp_ws.cleanup)

    def qakit(self, *args, hang=None):
        env = dict(self.env, **({"FAKE_HANG": hang} if hang else {}))
        start = time.monotonic()
        r = subprocess.run([sys.executable, str(QAKIT), *args], env=env, text=True, capture_output=True, timeout=60)
        return r, time.monotonic() - start

    def test_android_doctor_adb_hangs(self):
        r, secs = self.qakit("android", "doctor", "--timeout", "1", hang="devices")
        self.assertLess(secs, 15, "멈춘 adb devices(30초)를 기다림")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("✅ AVD: qakit", r.stdout)
        self.assertIn("❌ 연결된 기기 확인 못 함 — 1초 안에 답이 없음 (adb devices)", r.stdout)
        self.assertIn("adb kill-server", r.stdout)

    def test_workspace_ok(self):
        """멈추는 것이 없으면 전과 같다 (에뮬레이터 찾기·앱 설치 확인까지)"""
        r, _ = self.qakit("-w", str(self.ws), "doctor", "--timeout", "5")
        self.assertIn("✅ 연결된 기기: emulator-5554 sdk_gphone emu64a", r.stdout)
        self.assertIn("✅ 에뮬레이터(AVD): qakit", r.stdout)
        self.assertIn("✅ 대상 앱 설치됨", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_workspace_pm_hangs(self):
        r, secs = self.qakit("-w", str(self.ws), "doctor", "--timeout", "1", hang="pm")
        self.assertLess(secs, 15)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("❌ 대상 앱 설치 확인 못 함 — 1초 안에 답이 없음 (adb shell pm path)", r.stdout)

    def test_workspace_adb_hangs_once(self):
        """adb devices가 멈췄으면 에뮬레이터 찾기에서 다시 기다리지 않는다"""
        r, secs = self.qakit("-w", str(self.ws), "doctor", "--timeout", "2", hang="devices")
        self.assertLess(secs, 15)
        self.assertEqual(r.stdout.count("확인 못 함"), 1, r.stdout)
        self.assertIn("❌ 연결된 기기 확인 못 함", r.stdout)


if __name__ == "__main__":
    unittest.main()
