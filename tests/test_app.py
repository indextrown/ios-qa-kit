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


if __name__ == "__main__":
    unittest.main()
