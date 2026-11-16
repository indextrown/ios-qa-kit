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
SCENARIO_PROJECT = KIT_DIR / "ScenarioRunner" / "QAScenarioRunner.xcodeproj"
SCENARIO_BUILD = KIT_DIR / ".build" / "scenario-runner"
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
        self.app_override = False
        self.device = None   # --device로 고른 실기기 (None = 시뮬레이터)
        # 빌드 종류: debug(기본) = app.configuration / release = app.release.configuration (기본 Release)
        self.build = BUILD_MODE or "debug"
        self.state_name = "installed"
        if self.build == "release":
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
        return KIT_DIR / ".build" / ("autoid-device" if self.device else "autoid") / "QAAutoID.dylib"

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

def run(cmd, check=True, capture=True, cwd=None, env=None):
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.STDOUT if capture else None)
    if check and result.returncode != 0:
        out = (result.stdout or "")[-3000:]
        fail(f"명령 실패 ({result.returncode}): {' '.join(map(str, cmd[:4]))} ...\n{out}")
    return result


def masker(secrets):
    values = sorted({v for v in secrets.values() if v and len(v) >= 3}, key=len, reverse=True)

    def mask(text):
        for v in values:
            text = text.replace(v, "•••")
        return text
    return mask


def timestamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


