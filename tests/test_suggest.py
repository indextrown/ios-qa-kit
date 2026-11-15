"""실패하면 '대신 이 대상?' 제안"""
import unittest

from helpers import DUMP, load_qakit

q = load_qakit()


class Suggest(unittest.TestCase):
    def test_id_typo(self):
        lines = q.suggestion_lines("10초 안에 나타나지 않음: home_serch_button", DUMP)
        self.assertIn("대신 이 대상?", lines[0])
        self.assertTrue(lines[1].strip().startswith("→ home_search_button"))
        self.assertEqual(len(lines), 2)   # 같은 요소를 라벨로 또 제안하지 않음

    def test_dict_target_with_timeout(self):
        lines = q.suggestion_lines('10초 안에 나타나지 않음: {"id":"home_serch_button","timeout":3}', DUMP)
        self.assertIn("home_search_button", "\n".join(lines))

    def test_label_typo(self):
        lines = q.suggestion_lines('기대 조건 실패: {"visible":{"label":"Coming son popups","type":"text"}}', DUMP)
        self.assertIn('{ type: text, label: "Coming soon popups" }', "\n".join(lines))

    def test_present_means_not_a_name_problem(self):
        lines = q.suggestion_lines("10초 안에 나타나지 않음: hidden_zero_button", DUMP)   # 크기 0이라 목록엔 없지만 화면 구조엔 있음
        self.assertEqual(len(lines), 1)
        self.assertIn("이름 문제가 아님", lines[0])

    def test_unrelated_and_unknown_message(self):
        self.assertEqual(q.suggestion_lines("10초 안에 나타나지 않음: totally_unrelated_xyz", DUMP), [])
        self.assertEqual(q.suggestion_lines("앱이 죽음", DUMP), [])
        self.assertEqual(q.suggestion_lines("10초 안에 나타나지 않음: home_serch_button", ""), [])

    def test_ambiguous_label_not_suggested(self):
        dump = DUMP + '    Button "Sort" @300,700 60x30\n'   # 같은 라벨 두 개 → 하나로 정할 수 없으니 제안 안 함
        self.assertNotIn("Sort", "\n".join(q.suggestion_lines('나타나지 않음: {"label":"Sorts","type":"button"}', dump)))


if __name__ == "__main__":
    unittest.main()
