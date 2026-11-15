import unittest

from helpers import make_workspace
import scenario_tools as st


class ParseYaml(unittest.TestCase):
    def test_one_line_flow(self):
        v = st.parse_yaml('- { tap: home_search_button, expect: { visible: "검색: 입력" } }')
        self.assertEqual(v, [{"tap": "home_search_button", "expect": {"visible": "검색: 입력"}}])

    def test_nested_and_list(self):
        v = st.parse_yaml("steps:\n  - tap: { type: button, label: \"확인\", index: 1 }\n  - wait: { for: X.y, timeout: 10 }\ntags: [smoke, home]\n")
        self.assertEqual(v["steps"][0]["tap"], {"type": "button", "label": "확인", "index": 1})
        self.assertEqual(v["steps"][1]["wait"]["timeout"], 10)
        self.assertEqual(v["tags"], ["smoke", "home"])


class LoadScenario(unittest.TestCase):
    def test_use_expands_and_inherits_start(self):
        tmp, root = make_workspace({
            "steps/home.qa.yml": "name: 홈\nstart: { visible: HomeView.sortButton }\nsteps:\n  - wait: HomeView.sortButton\n",
            "scenarios/a.qa.yml": "name: A\nsteps:\n  - use: home\n  - tap: HomeView.searchButton\n",
        })
        with tmp:
            sc = st.load_scenario(st.find_scenario(root, "a"), root)
            self.assertEqual(sc["steps"][0].get("group"), "home")      # use: → group
            self.assertEqual(sc.get("start"), {"visible": "HomeView.sortButton"})   # 첫 use:의 start: 물려받음

    def test_self_recursion_is_error(self):
        tmp, root = make_workspace({"steps/loop.qa.yml": "name: L\nsteps:\n  - use: loop\n",
                                     "scenarios/b.qa.yml": "name: B\nsteps:\n  - use: loop\n"})
        with tmp, self.assertRaises(Exception):
            st.load_scenario(st.find_scenario(root, "b"), root)


class CheckIds(unittest.TestCase):
    def test_unknown_auto_ids_only(self):
        sc = {"steps": [{"tap": "HomeView.searchButton"}, {"tap": "HomeView.serchButton"}, {"tap": "snake_case_id"},
                        {"tap": "Tab.0"}, {"expect": {"visible": "MapboxView.pin"}}]}
        unknown = st.check_ids(sc, {"HomeView.searchButton"}, extra_ok=("Mapbox",))
        self.assertEqual(unknown, ["HomeView.serchButton"])   # 앱이 직접 붙인 snake_case·위치 규칙·외부 SDK는 검사 안 함


if __name__ == "__main__":
    unittest.main()
