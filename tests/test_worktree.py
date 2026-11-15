"""QA 워크트리 최신화: 임시 git 저장소(앱 + 연결 워크트리)에서 상태·가져올 커밋·병합 (사용자 저장소는 건드리지 않음)"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import load_qakit

q = load_qakit()


def git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
                        "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "HOME": str(d)})


class Worktree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        app = base / "App"
        app.mkdir()
        git(app, "init", "-q", "-b", "main")
        (app / "App.xcodeproj").mkdir()
        (app / "a.swift").write_text("let a = 1\n")
        git(app, "add", ".")
        git(app, "commit", "-q", "-m", "first")
        git(app, "branch", "develop")
        git(app, "worktree", "add", "-q", "-b", "qa/workspace", str(base / "App-qa"), "main")
        # develop에 새 커밋 2개 (QA 브랜치가 따라가야 할 것)
        git(app, "switch", "-q", "develop")
        for i in (2, 3):
            (app / f"f{i}.swift").write_text(f"let f = {i}\n")
            git(app, "add", ".")
            git(app, "commit", "-q", "-m", f"feature {i}")
        self.qa = base / "App-qa" / "QA"
        self.qa.mkdir()
        (self.qa / "qakit.yml").write_text("name: t\napp:\n  project: ../App.xcodeproj\n  bundleId: x\nworktree:\n  base: develop\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_info_and_update(self):
        ws = q.Workspace(self.qa)
        info = q.worktree_info(ws)
        self.assertTrue(info["worktree"])
        self.assertEqual((info["branch"], info["base"], info["behind"]), ("qa/workspace", "develop", 2))
        self.assertEqual([c["subject"] for c in info["incoming"]], ["feature 3", "feature 2"])
        self.assertIn("develop", [b["name"] for b in info["branches"]] + [info["ref"]])
        self.assertTrue(q.update_worktree(ws, strict=False))   # 병합 (push 없음)
        after = q.worktree_info(q.Workspace(self.qa))
        self.assertEqual(after["behind"], 0)
        self.assertEqual(after["head"]["subject"], "feature 3")   # QA 브랜치에 자기 커밋이 없으면 앞으로 당겨짐 (병합 커밋 없음)

    def test_dirty_app_source_blocks_update(self):
        (self.qa.parent / "a.swift").write_text("let a = 2\n")   # 앱 소스에 커밋 안 한 변경
        ws = q.Workspace(self.qa)
        self.assertTrue(q.worktree_info(ws)["dirty"])
        self.assertFalse(q.update_worktree(ws, strict=False))
        self.assertEqual(q.worktree_info(ws)["behind"], 2)   # 그대로

    def test_not_a_worktree(self):
        tmp = tempfile.TemporaryDirectory()
        with tmp:
            root = Path(tmp.name)
            (root / "qakit.yml").write_text("name: t\napp:\n  project: ./X.xcodeproj\n  bundleId: x\n")
            self.assertEqual(q.worktree_info(q.Workspace(root)), {"worktree": False})


if __name__ == "__main__":
    unittest.main()
