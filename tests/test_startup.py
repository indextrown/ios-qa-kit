"""시작 캐시 (bin/qakit): lib/qakit/*.py 컴파일 결과를 .pyc로 다시 쓰고, 원본이 바뀌면 다시 컴파일하고,
맥 앱 번들 안에는 아무것도 쓰지 않는다 (쓰면 서명이 깨진다). --version은 그 옵션을 줄 때만 git을 부른다."""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import load_qakit

KIT = Path(__file__).resolve().parent.parent
VERSION = (KIT / "VERSION").read_text().strip()


def copy_kit(dst):
    """qakit이 뜨는 데 필요한 것만 복사 (bin, lib, Tools, VERSION) → 복사본의 bin/qakit"""
    ignore = shutil.ignore_patterns("__pycache__", ".build")
    for name in ("bin", "lib", "Tools"):
        shutil.copytree(KIT / name, dst / name, ignore=ignore)
    shutil.copy2(KIT / "VERSION", dst / "VERSION")
    return dst / "bin" / "qakit"


class StartupCache(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()   # 맥은 /var → /private/var: qakit이 realpath로 찾으니 맞춘다
        self.home = self.root / "home"
        # 사용자 캐시 폴더(~/Library/Caches, ~/.cache, 맥 기본 Python의 com.apple.python)도 임시 폴더 안으로
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX", "XDG_CACHE_HOME")}
        self.env["HOME"] = str(self.home)

    def qakit(self, script, *python_args):
        r = subprocess.run([sys.executable, *python_args, str(script), "--version"],
                           env=self.env, text=True, capture_output=True, timeout=120)
        return r

    def test_reuses_and_recompiles(self):
        """두 번째부터 .pyc를 읽고, 원본을 고치면(크기가 같아도) 다시 컴파일한다. 오류 위치는 원본 파일."""
        script = copy_kit(self.root / "kit")
        base = self.root / "kit" / "lib" / "qakit" / "00_base.py"
        original = base.read_text(encoding="utf-8")
        mtime = base.stat().st_mtime_ns

        def write(extra, seconds):
            base.write_text(original + extra, encoding="utf-8")
            os.utime(base, ns=(mtime, mtime + seconds * 10**9))   # .pyc는 초 단위 수정 시각으로 비교한다

        write('\nprint("probe-1")\n', 1)
        self.assertIn("probe-1", self.qakit(script).stdout)            # 처음: 컴파일하고 .pyc를 남긴다
        r = self.qakit(script, "-v")
        self.assertTrue(f"matches {base}" in r.stderr, "두 번째 실행이 .pyc를 읽지 않음")   # python -v: "<pyc> matches <원본>"
        self.assertIn("probe-1", r.stdout)
        write('\nprint("probe-2")\n', 2)                                # 크기는 같고 수정 시각만 다르다
        self.assertIn("probe-2", self.qakit(script).stdout)
        write("\n1 / 0\n", 3)
        line = (original + "\n1 / 0\n").splitlines().index("1 / 0") + 1
        for _ in range(2):                                              # .pyc에서 읽어도 원본 파일·줄을 가리킨다
            err = self.qakit(script).stderr
            self.assertTrue(f'File "{base}", line {line}' in err, err[-1500:])

    def test_app_bundle_writes_nothing_inside(self):
        """맥 앱 번들 안 도구 폴더: .pyc는 사용자 캐시 폴더에 두고 번들은 그대로.
        저장소가 아니니 --version에 브랜치(예전엔 git 오류 문구)가 붙지 않는다."""
        app = self.root / "QA Kit.app"
        script = copy_kit(app / "Contents" / "Resources" / "kit")
        base = app / "Contents" / "Resources" / "kit" / "lib" / "qakit" / "00_base.py"
        for args in ((), ("-v",)):
            r = self.qakit(script, *args)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertEqual(r.stdout.strip(), f"qakit {VERSION}")
        self.assertTrue(f"matches {base}" in r.stderr, "두 번째 실행이 .pyc를 읽지 않음")
        self.assertEqual([str(p) for p in app.rglob("__pycache__")], [])
        cached = {p.name.split(".")[0] for p in self.home.rglob("*.pyc")}
        self.assertTrue({"00_base", "90_update_main", "gen_ids", "scenario_tools"} <= cached, sorted(cached))


class VersionOption(unittest.TestCase):
    def run_main(self, argv, branch):
        """branch=None이면 git이 저장소가 아니라고 실패하는 것처럼 → (출력, 띄운 명령들)"""
        q = load_qakit()
        spawned = []

        def fake_run(cmd, *args, **kwargs):
            spawned.append(cmd)
            return subprocess.CompletedProcess(cmd, 0 if branch else 128,
                                               stdout=(branch or "fatal: not a git repository") + "\n")

        out = io.StringIO()
        with mock.patch("subprocess.run", fake_run), mock.patch.object(sys, "argv", ["qakit", *argv]), \
                contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            q.main()
        return out.getvalue().strip(), spawned

    def test_branch(self):
        self.assertEqual(self.run_main(["--version"], "develop")[0], f"qakit {VERSION} (develop)")
        self.assertEqual(self.run_main(["--version"], "HEAD")[0], f"qakit {VERSION}")   # 분리된 HEAD
        self.assertEqual(self.run_main(["--version"], None)[0], f"qakit {VERSION}")     # 저장소 아님 (앱 번들)

    def test_no_process_otherwise(self):
        """다른 명령은 시작할 때 git 같은 프로세스를 띄우지 않는다 (예전엔 명령마다 브랜치를 읽었다)"""
        self.assertEqual(self.run_main(["--help"], "develop")[1], [])


if __name__ == "__main__":
    unittest.main()
