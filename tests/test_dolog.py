"""launch가 기록을 비우기 전에 남기기·되살리기 (6)"""
import unittest

from helpers import load_qakit, make_workspace

q = load_qakit()


class DoLog(unittest.TestCase):
    def setUp(self):
        self.tmp, root = make_workspace()
        self.ws = q.Workspace(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_and_restore(self):
        q.do_log_write(self.ws, {"event": "launch"}, reset=True)   # 빈 기록은 남기지 않음
        self.assertEqual(q.do_log_prev(self.ws), [])
        q.do_log_write(self.ws, {"step": "tap: a"})
        q.do_log_write(self.ws, {"step": "tap: b"})
        q.do_log_write(self.ws, {"event": "launch"}, reset=True)
        prev = q.do_log_prev(self.ws)
        self.assertEqual([p["steps"] for p in prev], [["tap: a", "tap: b"]])
        self.assertEqual(q.do_log_read(self.ws), ([], True))
        q.do_log_write(self.ws, {"step": "tap: c"})
        steps, err = q.do_log_restore(self.ws, prev[0]["name"])
        self.assertIsNone(err)
        self.assertEqual(steps, ["tap: a", "tap: b"])
        self.assertEqual([p["steps"] for p in q.do_log_prev(self.ws)], [["tap: c"]])   # 지금 기록은 이전 기록으로
        self.assertIsNotNone(q.do_log_restore(self.ws, "../x")[1])

    def test_keep(self):
        for i in range(q.DO_LOG_KEEP + 3):
            q.do_log_write(self.ws, {"step": f"tap: s{i}"})
            q.do_log_write(self.ws, {"event": "launch"}, reset=True)
        self.assertEqual(len(q.do_log_prev(self.ws)), q.DO_LOG_KEEP)


if __name__ == "__main__":
    unittest.main()
