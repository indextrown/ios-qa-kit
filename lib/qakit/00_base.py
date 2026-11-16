# qakit — 작업공간·설정·출력·YAML·실행 유틸
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).

import argparse
import base64
import contextlib
import collections
import fcntl
import functools
import datetime
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import uuid
import queue
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

KIT_DIR = Path(os.path.realpath(__file__)).parent.parent
sys.path.insert(0, str(KIT_DIR / "Tools" / "gen-ids"))
import gen_ids  # noqa: E402
sys.path.insert(0, str(KIT_DIR / "Tools" / "scenario"))
import scenario_tools  # noqa: E402
import qa_readme  # noqa: E402

ARCHIVE_DIR = Path.home() / ".qakit" / "archive"


def _work_dir(kit=None):
    """qakit이 빌드 결과를 쓰는 곳. 도구 폴더(KIT_DIR)는 읽기만 해도 되게 (맥 앱 번들 안에 넣으면 고칠 수 없음 — PLAN "맥 앱(DMG) 설계" D1).
    QAKIT_HOME이 있으면 거기, 도구 폴더에 쓸 수 있으면(git 설치) 지금처럼 도구 폴더, 아니면 ~/Library/Application Support/qakit.
    앱 번들 안(…/QA Kit.app/Contents/Resources/kit)은 쓸 수 있어도 쓰지 않는다 — 끌어다 놓은 앱은 내 소유라 쓰기가 되지만 서명이 깨진다."""
    kit = kit or KIT_DIR
    env = os.environ.get("QAKIT_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if ".app/Contents/" not in str(kit) and os.access(kit, os.W_OK):
        return kit
    return Path.home() / "Library" / "Application Support" / "qakit"


WORK_DIR = _work_dir()
BUILD_DIR = WORK_DIR / ".build"
SCENARIO_BUILD = BUILD_DIR / "scenario-runner"
_SRC_SKIP = {".build", "build", ".gradle", ".swiftpm", "__pycache__", ".DS_Store", ".idea", "local.properties"}


def _mirror(src, dst):
    """src 폴더를 dst로 맞춘다 (바뀐 파일만 복사, 원본에 없는 파일은 지움). 빌드 결과 폴더는 건드리지 않는다."""
    dst.mkdir(parents=True, exist_ok=True)
    names = {n for n in os.listdir(src) if n not in _SRC_SKIP and not n.endswith(".xcodeproj")}
    for n in os.listdir(dst):
        if n not in names and n not in _SRC_SKIP and not n.endswith(".xcodeproj"):
            p = dst / n
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
    for n in names:
        s, d = src / n, dst / n
        if s.is_dir():
            if d.exists() and not d.is_dir():
                d.unlink()
            _mirror(s, d)
        else:
            st = s.stat()
            if d.is_dir():
                shutil.rmtree(d)
            if not d.exists() or d.stat().st_size != st.st_size or int(d.stat().st_mtime) != int(st.st_mtime):
                shutil.copy2(s, d)


def writable_src(*names):
    """빌드 도구가 소스 폴더 안에 쓰는 것(xcodegen 프로젝트·SwiftPM·Gradle)을 위해 쓸 수 있는 소스 위치.
    도구 폴더에 쓸 수 있으면 그대로, 아니면 WORK_DIR/src에 그 부분만 복사해 둔다. → 루트 경로"""
    if WORK_DIR == KIT_DIR:
        return KIT_DIR
    root = WORK_DIR / "src"
    for n in names:
        s = KIT_DIR / n
        if s.is_dir():
            _mirror(s, root / n)
        elif s.exists():
            root.mkdir(parents=True, exist_ok=True)
            d = root / n
            if not d.exists() or d.read_bytes() != s.read_bytes():
                shutil.copy2(s, d)
    return root


def scenario_runner_src():
    """xcodegen·xcodebuild를 돌릴 시나리오 실행기 폴더 (패키지 QAKit = 그 위 폴더의 Package.swift·Sources)"""
    return writable_src("Package.swift", "Sources", "ScenarioRunner") / "ScenarioRunner"
# 사람/AI가 만든 결과물 (save·restore 대상). 나머지는 qakit이 다시 만든다.
USER_FILES = ["README.md", "qakit.yml", "NOTES.md", "AGENTS.md", "CLAUDE.md", "secrets.example.txt", ".gitignore",
              "history.jsonl", "scenarios", "steps", "Runner/UITests/Pages", "Runner/UITests/Flows"]
TEMPLATE_DIR = KIT_DIR / "templates" / "workspace"
RUNNER_SCHEME = "UITests"
DUMP_TEST = "UITests/QAKitDumpTests/test_dump"


# ─────────────────────────────── 출력 ───────────────────────────────

def info(msg):
    print(msg, flush=True)


def ok(msg):
    print(f"✅ {msg}", flush=True)


def warn(msg):
    print(f"⚠️  {msg}", flush=True)


FAIL_CODE = 1   # qakit run은 2로 바꾼다: 앱 판정 실패(1)가 아닌 실패는 환경·설정 문제(2)


def fail(msg, hint=None, code=None):
    with contextlib.suppress(OSError, ValueError):
        sys.stdout.flush()   # 파이프로 받을 때(AI·앱) 앞서 찍은 줄보다 오류가 먼저 나오지 않게
    print(f"❌ {msg}", file=sys.stderr, flush=True)
    if hint:
        print(f"   → {hint}", file=sys.stderr, flush=True)
    sys.exit(FAIL_CODE if code is None else code)


# ─────────────────────────────── YAML (부분 집합) ───────────────────────────────
# qakit.yml에 필요한 만큼만: 들여쓰기 중첩 맵, 스칼라, [a, b] 인라인 리스트, 주석.

def parse_yaml(text):
    root = {}
    stack = [(-1, root)]
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = re.sub(r"\s+#.*$", "", raw) if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*:\s*(.*)$", line)
        if not m:
            raise ValueError(f"qakit.yml {lineno}번째 줄을 읽을 수 없음: {raw}")
        key, value = m.group(1), m.group(2).strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value)
    return root


def parse_scalar(value):
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [parse_scalar(v.strip()) for v in inner.split(",")] if inner else []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value in ("true", "yes"):
        return True
    if value in ("false", "no"):
        return False
    return value


# ─────────────────────────────── 작업공간 ───────────────────────────────

class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config_path = self.root / "qakit.yml"
        try:
            self.cfg = parse_yaml(self.config_path.read_text(encoding="utf-8"))
        except ValueError as e:
            fail(str(e))
        app = self.cfg.get("app") or {}
        self.name = self.cfg.get("name") or self.root.name
        self.project = expand(app.get("project", ""), self.root)
        self.scheme = app.get("scheme", "")
        self.configuration = app.get("configuration", "Debug")
        self.bundle_id = app.get("bundleId", "")
        self.simulator = str(self.cfg.get("simulator", "iPhone 17"))
        self.platform = str(self.cfg.get("platform", "ios")).lower()   # ios | android
        if self.platform not in ("ios", "android"):
            fail(f"qakit.yml platform은 ios 또는 android여야 합니다: {self.platform}")
        # 안드로이드: app.project = Gradle 루트 폴더, app.module(기본 app), app.variant(기본 debug), app.packageName
        self.module = str(app.get("module", "app"))
        self.variant = str(app.get("variant", "debug"))
        self.package = str(app.get("packageName", "")) if self.platform == "android" else ""
        self.emulator = str(self.cfg.get("emulator", ANDROID_AVD))   # AVD 이름
        self.orientation = str(self.cfg.get("orientation") or "")   # 안드로이드 화면 방향: landscape · portrait · auto
        self.keyboard = str(self.cfg.get("keyboard") or "hide")   # 안드로이드 소프트 키보드: hide(기본) · show
        self.language = self.cfg.get("language")
        self.locale = self.cfg.get("locale")
        perms = self.cfg.get("permissions") or []
        self.permissions = perms if isinstance(perms, list) else [perms]
        self.secrets_path = expand(self.cfg.get("secrets", "./secrets.txt"), self.root)
        self.autoid = self.cfg.get("autoid", "inject")
        self.precheck = self.cfg.get("precheck")   # 여러 개 실행 전 사전 확인할 공통 단계 이름 (steps/<이름>.qa.yml)
        self.swiftui = str(self.cfg.get("swiftui", "auto"))  # auto | insert | off — SwiftUI 소스에 ID 삽입(QA 워크트리 빌드 중)
        self.sync_mode = self.cfg.get("sync", "auto")  # auto | warn | off
        wt = self.cfg.get("worktree") or {}
        wt = wt if isinstance(wt, dict) else {}
        self.worktree_base = str(wt.get("base", "develop"))     # QA 워크트리가 따라갈 브랜치
        self.worktree_update = str(wt.get("update", "auto"))    # auto | warn | off
        ids = self.cfg.get("ids") or {}
        srcs = ids.get("sources") if isinstance(ids, dict) else None
        self.id_sources = [expand(x, self.root) for x in (srcs if isinstance(srcs, list) else [srcs] if srcs else [])]
        allow = ids.get("allow") if isinstance(ids, dict) else None   # 검사하지 않을 ID 접두어 (외부 SDK 화면 등)
        self.id_allow = tuple(str(x) for x in (allow if isinstance(allow, list) else [allow] if allow else []))
        self.app_override = False
        self.device = None   # --device로 고른 실기기 (None = 시뮬레이터)
        # 빌드 종류: debug(기본) = app.configuration / release = app.release.configuration (기본 Release)
        self.build = BUILD_MODE or "debug"
        self.state_name = "installed"
        if self.build == "release" and self.platform == "android":
            # 안드로이드 release: app.release.variant(기본 release)·packageName(기본 debug와 같음)
            rel = app.get("release") or {}
            rel = rel if isinstance(rel, dict) else {}
            self.variant = str(rel.get("variant", "release"))
            self.package = str(rel.get("packageName") or self.package)
            self.state_name = "installed-release"
        elif self.build == "release":
            rel = app.get("release") or {}
            rel = rel if isinstance(rel, dict) else {}
            self.configuration = str(rel.get("configuration", "Release"))
            self.bundle_id = rel.get("bundleId") or self._release_bundle_id()
            self.state_name = "installed-release"
        self.runner_dir = self.root / "Runner"
        self.build_dir = self.root / ".build"
        self.results_dir = self.root / "results"

    def _release_bundle_id(self):
        """release 빌드의 bundle ID: qakit.yml에 없으면 프로젝트에서 읽고 .qakit/release.json에 기억한다."""
        cache = self.root / ".qakit" / "release.json"
        key = f"{self.project}|{self.scheme}|{self.configuration}"
        try:
            data = json.loads(cache.read_text())
            if data.get("key") == key and data.get("bundleId"):
                return data["bundleId"]
        except (OSError, ValueError):
            pass
        bid = app_bundle_id(self.project, self.scheme, self.configuration) if self.project else None
        if not bid:
            fail(f"release 빌드({self.configuration})의 bundle ID를 찾지 못했습니다.",
                 "qakit.yml에 app.release.bundleId 또는 app.release.configuration을 적으세요")
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps({"key": key, "bundleId": bid}, ensure_ascii=False))
        return bid

    @property
    def app_dir(self):
        if not self.project:
            return None
        return self.project if self.platform == "android" else self.project.parent   # 안드로이드는 Gradle 루트 폴더

    @property
    def app_build_dir(self):
        # 앱 경로별로 빌드 폴더를 나눈다 (워크트리/브랜치 폴더를 오가도 서로 덮어쓰지 않게)
        suffix = "-device" if self.device else ""
        if not self.app_override:
            return self.build_dir / ("app" + suffix)
        return self.build_dir / ("app-" + slug(str(self.app_dir.name)) + suffix)

    @property
    def state_dir(self):
        return self.root / ".qakit"

    @property
    def ids_file(self):
        return self.runner_dir / "UITests" / "Generated" / "QAIDs.swift"

    @property
    def runner_project(self):
        return self.runner_dir / "QARunner.xcodeproj"

    @property
    def autoid_dylib(self):
        return BUILD_DIR / ("autoid-device" if self.device else "autoid") / "QAAutoID.dylib"

    @property
    def swiftui_manifest(self):
        """SwiftUI ID 삽입 중 원본을 보관하는 파일. 남아 있으면 복원이 안 된 것."""
        return self.state_dir / "swiftui-ids.json"

    def secrets(self):
        if not self.secrets_path.exists():
            return {}
        result = {}
        for raw in self.secrets_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = re.sub(r"\s+#.*$", "", value).strip()
            result[key.strip()] = value
        return result


def expand(path, base):
    if not path:
        return None
    p = Path(os.path.expanduser(str(path)))
    return (p if p.is_absolute() else (base / p)).resolve()


SECRETS_OVERRIDE = None
APP_OVERRIDE = None
BUILD_MODE = None   # --build debug|release
DEVICE_ARG = None   # --device select|last|<이름>


def find_workspace(explicit):
    ws = _find_workspace(explicit)
    if SECRETS_OVERRIDE:
        ws.secrets_path = Path(SECRETS_OVERRIDE).expanduser().resolve()
    if APP_OVERRIDE:
        project = find_project(Path(APP_OVERRIDE).expanduser().resolve())
        if not project:
            fail(f"--app {APP_OVERRIDE}에서 .xcodeproj/.xcworkspace를 찾지 못했습니다.")
        if project.resolve() != (ws.project.resolve() if ws.project else None):
            ws.project = project.resolve()
            ws.app_override = True
            info(f"ℹ️  앱 경로 일시 지정: {ws.project}")
    if DEVICE_ARG:
        ws.device = choose_device(ws, DEVICE_ARG)
        if ws.device:
            ws.state_name += f"-device-{ws.device['udid']}"
    return ws


def _find_workspace(explicit):
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not (root / "qakit.yml").exists():
            fail(f"{root}에 qakit.yml이 없습니다.", "qakit init <앱 프로젝트>로 작업공간을 먼저 만드세요.")
        return Workspace(root)
    cur = Path.cwd().resolve()
    for d in [cur, *cur.parents]:
        if (d / "qakit.yml").exists():
            return Workspace(d)
    fail("qakit.yml을 찾지 못했습니다.", "작업공간 폴더에서 실행하거나 -w <작업공간>을 지정하세요.")


# ─────────────────────────────── 실행 유틸 ───────────────────────────────

def run(cmd, check=True, capture=True, cwd=None, env=None, timeout=None):
    """timeout(초)을 넘기면 그 명령을 끝내고 subprocess.TimeoutExpired (xcrun은 도구로 exec하므로 도구가 끝난다)"""
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.STDOUT if capture else None, timeout=timeout)
    if check and result.returncode != 0:
        out = (result.stdout or "")[-3000:]
        fail(f"명령 실패 ({result.returncode}): {' '.join(map(str, cmd[:4]))} ...\n{out}")
    return result


def limited(fn, *args):
    """fn(*args) → (결과, 시간을 넘겼는지). 안에서 run(..., timeout=)이 시간을 넘기면 (None, True) — doctor가 그 항목만 "확인 못 함"으로"""
    try:
        return fn(*args), False
    except subprocess.TimeoutExpired:
        return None, True


def masker(secrets):
    values = sorted({v for v in secrets.values() if v and len(v) >= 3}, key=len, reverse=True)

    def mask(text):
        for v in values:
            text = text.replace(v, "•••")
        return text
    return mask


def timestamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


