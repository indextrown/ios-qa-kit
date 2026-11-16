"""맥 앱(D2): 앱 안 도구 폴더(scripts/build-app.sh가 복사)에 qakit이 읽는 폴더·파일이 다 들어가는지"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Bundle(unittest.TestCase):
    def test_kit_has_everything_code_reads(self):
        script = (ROOT / "scripts" / "build-app.sh").read_text(encoding="utf-8")
        listed = set(re.search(r"git ls-files[^\n]*-- ([^\\\n]+)", script).group(1).split())
        used = set()
        for f in (ROOT / "lib" / "qakit").glob("*.py"):
            used |= set(re.findall(r'KIT_DIR / "([^"]+)"', f.read_text(encoding="utf-8")))
        for top in used:
            self.assertTrue(top in listed or any(x.startswith(top + "/") for x in listed),
                            f"{top}이(가) 앱 도구 폴더에 빠짐 (scripts/build-app.sh)")



class DoctorSystem(unittest.TestCase):
    def test_json(self):
        import json
        import subprocess
        import sys
        from helpers import QAKIT
        p = subprocess.run([sys.executable, str(QAKIT), "doctor", "--system", "--json"], text=True, capture_output=True, timeout=60)
        d = json.loads(p.stdout)
        keys = {r["key"] for r in d["checks"]}
        self.assertTrue({"python", "xcode", "simulator", "xcodegen", "git", "claude", "java", "adb"} <= keys)
        self.assertTrue(all(r["need"] in ("필수", "AI", "안드로이드") for r in d["checks"]))
        self.assertTrue(next(r for r in d["checks"] if r["key"] == "python")["ok"])
        # 바깥 도구가 멈추면(CI의 simctl 등) 그 항목은 unknown — '없음'(problems)과 따로 센다
        required = [r for r in d["checks"] if r["need"] == "필수" and not r["ok"]]
        self.assertEqual(d["problems"], sum(1 for r in required if not r["unknown"]))
        self.assertEqual(d["unknown"], sum(1 for r in required if r["unknown"]))


if __name__ == "__main__":
    unittest.main()
