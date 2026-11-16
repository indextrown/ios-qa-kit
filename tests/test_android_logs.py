"""안드로이드 로그 보고서: logcat 줄 → 크래시·ANR·오류·네트워크 (기기 없이)"""
import unittest

from helpers import load_qakit

q = load_qakit()

PKG = "com.example.demo"
APP = [
    "11-16 10:00:00.100  1000  1000 I Demo    : 시작",
    "11-16 10:00:01.000  1000  1100 I okhttp.OkHttpClient: --> GET https://api.example.com/v1/me",
    "11-16 10:00:01.010  1000  1100 I okhttp.OkHttpClient: Authorization: Bearer abc.def",
    "11-16 10:00:01.200  1000  1100 I okhttp.OkHttpClient: <-- 401 Unauthorized https://api.example.com/v1/me (190ms)",
    "11-16 10:00:02.000  1000  1200 I okhttp.OkHttpClient: --> POST https://api.example.com/v1/login",
    "11-16 10:00:02.300  1000  1200 I okhttp.OkHttpClient: <-- HTTP FAILED: java.net.SocketTimeoutException: timeout",
    "11-16 10:00:02.400  1000  1300 I okhttp.OkHttpClient: --> GET https://api.example.com/v1/ok",
    "11-16 10:00:02.500  1000  1300 I okhttp.OkHttpClient: <-- 200 OK https://api.example.com/v1/ok (80ms)",
    "11-16 10:00:03.000  1000  1000 E Demo    : 불러오기 실패 id=12",
    "11-16 10:00:04.000  1000  1000 E Demo    : 불러오기 실패 id=34",
    "11-16 10:00:05.000  1000  1000 W Demo    : 경고",
]
CRASH = [
    "11-16 10:00:06.000  2000  2000 E AndroidRuntime: FATAL EXCEPTION: main",
    f"11-16 10:00:06.000  2000  2000 E AndroidRuntime: Process: {PKG}.debug, PID: 2000",
    "11-16 10:00:06.000  2000  2000 E AndroidRuntime: java.lang.IllegalStateException: other app",
    "11-16 10:00:07.000  1000  1000 E AndroidRuntime: FATAL EXCEPTION: main",
    f"11-16 10:00:07.000  1000  1000 E AndroidRuntime: Process: {PKG}, PID: 1000",
    "11-16 10:00:07.000  1000  1000 E AndroidRuntime: java.lang.NullPointerException",
    "11-16 10:00:07.000  1000  1000 E AndroidRuntime: \tat a.b.c(SourceFile:1)",
]
SYSTEM = [
    f"11-16 10:00:08.000   500   600 E ActivityManager: ANR in {PKG} ({PKG}/.MainActivity)",
    "11-16 10:00:08.000   500   600 E ActivityManager: Reason: Input dispatching timed out",
    "11-16 10:00:08.100   500   700 I ActivityManager: 다른 줄",
    f"11-16 10:00:09.000   500   600 E ActivityManager: ANR in {PKG}.debug",
]


class AndroidLogReport(unittest.TestCase):
    def setUp(self):
        self.rep = q.android_log_report(APP, CRASH, SYSTEM, PKG)

    def test_crash_only_this_app(self):
        self.assertEqual(len(self.rep["crashes"]), 1)
        self.assertIn("NullPointerException", "\n".join(self.rep["crashes"][0]))

    def test_anr_block(self):
        self.assertEqual(len(self.rep["anrs"]), 1)
        self.assertEqual(len(self.rep["anrs"][0]), 2)   # ANR 줄 + 같은 스레드의 Reason

    def test_errors_grouped_by_shape(self):
        self.assertEqual(self.rep["errors"][0][0], 2)   # id 숫자만 다른 두 줄 → 하나
        self.assertEqual(len(self.rep["errors"]), 1)     # W·HTTP 줄은 빠짐

    def test_http(self):
        h = self.rep["http"]
        self.assertEqual(h["requests"], 3)
        self.assertEqual(len(h["failed"]), 2)
        self.assertIn("401", h["failed"][0])
        self.assertIn("POST https://api.example.com/v1/login", h["failed"][1])   # 실패 줄에 같은 스레드의 요청

    def test_report_lines(self):
        text = "\n".join(q.android_report_lines(self.rep))
        self.assertIn("앱 크래시", text)
        self.assertIn("ANR", text)
        self.assertIn("실패한 요청 2개 / 전체 3개", text)

    def test_redact(self):
        self.assertNotIn("abc.def", q.log_redact(APP[2]))
        self.assertEqual(q.log_redact('{"accessToken":"xyz","name":"a"}'), '{"accessToken":"•••","name":"a"}')
        self.assertIn("refresh_token=•••&x=1", q.log_redact("GET /t?refresh_token=abc&x=1"))


if __name__ == "__main__":
    unittest.main()
