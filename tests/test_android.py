"""안드로이드 화면 덤프: uiautomator XML → qakit 덤프 줄 (기기 없이)"""
import unittest

from helpers import load_qakit

q = load_qakit()

PKG = "com.example.demo"
# XML 뷰(resource-id) + Compose(testTagsAsResourceId, testTag 없는 버튼) + 이름 없는 레이아웃이 섞인 화면. density 2.75
XML = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="{PKG}" clickable="false" enabled="true" scrollable="false" bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="" class="android.widget.LinearLayout" package="{PKG}" clickable="false" enabled="true" scrollable="false" bounds="[0,0][1080,2400]">
      <node index="0" text="로그인" resource-id="{PKG}:id/titleText" class="android.widget.TextView" package="{PKG}" clickable="false" enabled="true" scrollable="false" bounds="[55,110][1025,220]" />
      <node index="1" text="" hint="이메일" resource-id="{PKG}:id/emailInput" class="android.widget.EditText" package="{PKG}" clickable="true" enabled="true" scrollable="false" password="false" bounds="[55,275][1025,440]" />
      <node index="2" text="" hint="비밀번호" resource-id="{PKG}:id/passwordInput" class="android.widget.EditText" package="{PKG}" clickable="true" enabled="true" scrollable="false" password="true" bounds="[55,495][1025,660]" />
      <node index="3" text="로그인" resource-id="{PKG}:id/loginButton" class="android.widget.Button" package="{PKG}" clickable="true" enabled="false" scrollable="false" bounds="[55,715][1025,880]" />
      <node index="4" text="" resource-id="" class="android.view.View" package="{PKG}" clickable="false" enabled="true" scrollable="true" bounds="[0,935][1080,2400]">
        <node index="0" text="회원가입" resource-id="LoginScreen.signUp" class="android.widget.Button" package="{PKG}" clickable="true" enabled="true" scrollable="false" bounds="[55,990][1025,1155]" />
        <node index="1" text="" content-desc="닫기" resource-id="" class="android.view.View" package="{PKG}" clickable="true" enabled="true" scrollable="false" bounds="[55,1210][220,1375]" />
        <node index="2" text="" resource-id="android:id/button1" class="android.widget.Button" package="{PKG}" clickable="true" enabled="true" scrollable="false" bounds="[0,0][0,0]" />
      </node>
    </node>
  </node>
</hierarchy>"""


class AndroidDump(unittest.TestCase):
    def setUp(self):
        self.lines, self.stats = q.android_dump_lines(XML, PKG, 2.75)
        self.text = "\n".join(self.lines)

    def test_ids_and_types(self):
        self.assertIn('StaticText #titleText "로그인" @20,40 353x40', self.text)
        self.assertIn('TextField #emailInput value="이메일"', self.text)
        self.assertIn("SecureTextField #passwordInput", self.text)
        self.assertIn('Button #loginButton "로그인" (disabled)', self.text)
        self.assertIn('Button #LoginScreen.signUp "회원가입"', self.text)     # Compose testTag는 그대로
        self.assertIn("Button #android.button1", self.text)                  # 프레임워크 id는 android.<이름>
        self.assertIn('Button "닫기"', self.text)                            # 라벨 있는 클릭 가능한 View는 버튼

    def test_unnamed_layouts_collapse(self):
        self.assertTrue(self.lines[0].startswith("StaticText #titleText"))   # FrameLayout·LinearLayout은 접힘
        scroll = next(l for l in self.lines if l.lstrip().startswith("Other @"))
        child = next(l for l in self.lines if "#LoginScreen.signUp" in l)
        self.assertEqual(len(child) - len(child.lstrip()), len(scroll) - len(scroll.lstrip()) + 2)

    def test_stats(self):
        self.assertEqual(self.stats["interactive"], 6)
        self.assertEqual(self.stats["withId"], 5)
        self.assertEqual(self.stats["missing"], ['Button "닫기"'])

    def test_shared_parser_reads_android_dump(self):
        els = q.dump_elements("# qakit dump-ui\n" + self.text)
        ids = {e["id"] for e in els if e["id"]}
        self.assertTrue({"loginButton", "emailInput", "LoginScreen.signUp"} <= ids)
        login = next(e for e in q.ui_parse_dump(self.text)["elements"] if e["id"] == "loginButton")
        self.assertFalse(login["enabled"])

    def test_foreign_window_marked(self):
        lines, _ = q.android_dump_lines(XML.replace(f'package="{PKG}"', 'package="com.android.permissioncontroller"', 1),
                                        PKG, 2.75)
        self.assertEqual(lines[0], "# (다른 앱 창: com.android.permissioncontroller)")


class AndroidIds(unittest.TestCase):
    def test_short_id(self):
        self.assertEqual(q.android_short_id(f"{PKG}:id/loginButton", PKG), "loginButton")
        self.assertEqual(q.android_short_id("com.lib.other:id/chip", PKG), "chip")
        self.assertEqual(q.android_short_id("android:id/button1", PKG), "android.button1")
        self.assertEqual(q.android_short_id("HomeScreen.search", PKG), "HomeScreen.search")
        self.assertEqual(q.android_short_id("", PKG), "")


if __name__ == "__main__":
    unittest.main()
