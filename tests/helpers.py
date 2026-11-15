"""테스트 공통: bin/qakit을 모듈로 불러오기, 임시 작업공간 만들기 (시뮬레이터·앱 없이)."""
import importlib.machinery
import importlib.util
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
QAKIT = KIT / "bin" / "qakit"
sys.path.insert(0, str(KIT / "Tools" / "scenario"))


def load_qakit():
    if "qakit_mod" in sys.modules:
        return sys.modules["qakit_mod"]
    loader = importlib.machinery.SourceFileLoader("qakit_mod", str(QAKIT))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("qakit_mod", loader))
    loader.exec_module(mod)
    sys.modules["qakit_mod"] = mod
    return mod


def make_workspace(files=None):
    """qakit.yml + scenarios/ + steps/ 가 있는 임시 작업공간 → Path (TemporaryDirectory는 호출한 쪽이 지운다)."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / "qakit.yml").write_text("name: demo\napp:\n  bundleId: com.example.demo\nsimulator: iPhone 17\n", encoding="utf-8")
    (root / "scenarios").mkdir()
    (root / "steps").mkdir()
    for rel, text in (files or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp, root


# qakit 덤프 꼴의 화면 구조 (예시 앱)
DUMP = """# qakit dump-ui
Application "Demo" @0,0 402x874
  Other #MainTabView.row @0,0 402x874
    Button #home_search_button "Search" @261,72 45x45
    Button #home_alarm_button "Bell" @306,75 40x40
    StaticText "Coming soon popups" @15,600 200x20
    StaticText "For you" @15,133 95x17
    Button "Sort" @300,820 60x30
    Button #hidden_zero_button @0,0 0x0
"""
