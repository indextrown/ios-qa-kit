"""커버리지: 앱 ID 중 시나리오가 쓰는 것 (use: 펼침 포함)"""
import unittest
from unittest import mock

from helpers import load_qakit, make_workspace

q = load_qakit()


class Coverage(unittest.TestCase):
    def test_counts(self):
        tmp, root = make_workspace({
            "steps/home.qa.yml": "name: 홈\nsteps:\n  - wait: HomeView.sortButton\n",
            "scenarios/a.qa.yml": "name: A\nsteps:\n  - use: home\n  - tap: { id: HomeView.searchButton, index: 0 }\n  - tap: home_custom_button\n",
            "scenarios/b.qa.yml": "name: B\nstart: { visible: LoginView.loginButton }\nsteps:\n  - expect: { visible: HomeView.searchButton }\n",
            "scenarios/broken.qa.yml": "name: X\nsteps:\n  - use: nope\n",
        })
        ids = {"HomeView.searchButton", "HomeView.sortButton", "HomeView.alarmButton", "LoginView.loginButton", "LoginView.idField"}
        with tmp, mock.patch.object(q, "known_ids", return_value=ids):
            c = q.coverage(q.Workspace(root))
        self.assertEqual((c["total"], c["used"], c["scenarios"]), (5, 3, 3))
        home = next(s for s in c["screens"] if s["screen"] == "HomeView")
        self.assertEqual((home["total"], home["used"]), (3, 2))
        by_id = {x["id"]: x["scenarios"] for s in c["screens"] for x in s["ids"]}
        self.assertEqual(by_id["HomeView.searchButton"], ["a", "b"])   # 대상 객체 안 id, expect 안
        self.assertEqual(by_id["HomeView.sortButton"], ["a"])           # use: 로 펼친 공통 단계
        self.assertEqual(by_id["LoginView.loginButton"], ["b"])         # start:
        self.assertEqual(by_id["HomeView.alarmButton"], [])
        self.assertEqual([x["id"] for x in c["extra"]], ["home_custom_button"])   # 앱이 직접 붙인 ID
        self.assertEqual(c["screens"][0]["screen"], "LoginView")        # 덜 쓴 화면이 먼저 (1/2 < 2/3)


if __name__ == "__main__":
    unittest.main()
