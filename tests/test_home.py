"""D1: 도구 폴더는 읽기만 — 쓰는 곳(QAKIT_HOME) 정하기와 빌드용 소스 사본"""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import QAKIT, load_qakit

q = load_qakit()


class WorkDir(unittest.TestCase):
    def test_choice(self):
        with mock.patch.dict(os.environ, {"QAKIT_HOME": "/tmp/qh"}):
            self.assertEqual(q._work_dir(), Path("/tmp/qh").resolve())
        with mock.patch.dict(os.environ, {"QAKIT_HOME": ""}):
            with mock.patch.object(q.os, "access", return_value=True):
                self.assertEqual(q._work_dir(), q.KIT_DIR)          # git 설치: 지금처럼
            with mock.patch.object(q.os, "access", return_value=False):
                self.assertEqual(q._work_dir(), Path.home() / "Library" / "Application Support" / "qakit")


class Mirror(unittest.TestCase):
    def test_mirror(self):
        with tempfile.TemporaryDirectory() as t:
            src, dst = Path(t) / "src", Path(t) / "dst"
            (src / "a" / "build").mkdir(parents=True)
            (src / "a" / "x.kt").write_text("1")
            (src / "a" / "build" / "junk").write_text("skip")
            (src / "run.sh").write_text("#!/bin/sh\n")
            (src / "run.sh").chmod(0o755)
            q._mirror(src, dst)
            self.assertEqual((dst / "a" / "x.kt").read_text(), "1")
            self.assertFalse((dst / "a" / "build").exists())            # 빌드 결과는 복사하지 않음
            self.assertTrue((dst / "run.sh").stat().st_mode & stat.S_IXUSR)   # 실행 권한 그대로 (gradlew)
            (dst / "a" / "build").mkdir()
            (dst / "a" / "build" / "out.apk").write_text("keep")
            (src / "a" / "x.kt").unlink()
            (src / "a" / "y.kt").write_text("2")
            q._mirror(src, dst)
            self.assertFalse((dst / "a" / "x.kt").exists())             # 원본에서 지운 것은 지움
            self.assertEqual((dst / "a" / "y.kt").read_text(), "2")
            self.assertEqual((dst / "a" / "build" / "out.apk").read_text(), "keep")   # 사본의 빌드 결과는 둠


if __name__ == "__main__":
    unittest.main()
