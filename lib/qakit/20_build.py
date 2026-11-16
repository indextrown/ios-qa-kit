# qakit — 빌드·테스트 실행 공통
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 빌드 ───────────────────────────────

def project_flag(project):
    return ["-workspace" if str(project).endswith(".xcworkspace") else "-project", str(project)]


def ensure_autoid(ws):
    if ws.autoid != "inject":
        return
    src = KIT_DIR / "AutoID"
    dylib = ws.autoid_dylib
    newest_src = max(p.stat().st_mtime for p in src.iterdir())
    if not dylib.exists() or dylib.stat().st_mtime < newest_src:
        info("AutoID dylib 빌드 중..." + (" (실기기용)" if ws.device else ""))
        run([str(KIT_DIR / "scripts" / "build-autoid.sh"), str(dylib.parent), "device" if ws.device else "simulator"])


SWIFTUI_IDS_DIR = KIT_DIR / "Tools" / "swiftui-ids"
# git 설치는 지금처럼 패키지 안 .build (옮기면 SwiftSyntax를 다시 몇 분 빌드), 아니면 WORK_DIR
SWIFTUI_IDS_SCRATCH = SWIFTUI_IDS_DIR / ".build" if WORK_DIR == KIT_DIR else BUILD_DIR / "swiftui-ids"
SWIFTUI_IDS_BIN = SWIFTUI_IDS_SCRATCH / "release" / "swiftui-ids"


def ensure_swiftui_ids():
    """swiftui-ids 도구를 소스가 바뀌었을 때만 빌드한다 (처음엔 SwiftSyntax 컴파일로 몇 분).
    수정 시각이 아니라 소스 해시로 판단한다 (git checkout·복사로 시각이 흔들려도 다시 빌드하지 않게)."""
    h = hashlib.sha1()
    for f in sorted([SWIFTUI_IDS_DIR / "Package.swift"] + list((SWIFTUI_IDS_DIR / "Sources").rglob("*.swift"))):
        h.update(str(f.relative_to(SWIFTUI_IDS_DIR)).encode())
        h.update(f.read_bytes())
    digest = h.hexdigest()
    stamp = SWIFTUI_IDS_BIN.with_suffix(".stamp")
    if not SWIFTUI_IDS_BIN.exists() or not stamp.exists() or stamp.read_text().strip() != digest:
        info("swiftui-ids 도구 빌드 중... (처음엔 SwiftSyntax 컴파일로 몇 분 걸립니다)")
        pkg = writable_src("Tools/swiftui-ids") / "Tools" / "swiftui-ids"   # Package.resolved를 고칠 수 있게
        r = run(["swift", "build", "-c", "release", "--package-path", str(pkg), "--scratch-path", str(SWIFTUI_IDS_SCRATCH)], check=False)
        if r.returncode != 0 or not SWIFTUI_IDS_BIN.exists():
            fail("swiftui-ids 빌드 실패", (r.stdout or "")[-800:])
        stamp.write_text(digest)
    return SWIFTUI_IDS_BIN


def ensure_swift_tool(name):
    """Tools/<name>/<name>.swift 한 파일짜리 도구를 소스가 바뀌었을 때만 swiftc로 빌드 (몇 초). 안 되면 None."""
    src = KIT_DIR / "Tools" / name / f"{name}.swift"
    out = (KIT_DIR / "Tools" / name / ".build" / name) if WORK_DIR == KIT_DIR else BUILD_DIR / "tools" / name / name
    if not src.exists():
        return None
    digest = hashlib.sha1(src.read_bytes()).hexdigest()
    stamp = out.with_suffix(".stamp")
    if not out.exists() or not stamp.exists() or stamp.read_text().strip() != digest:
        out.parent.mkdir(parents=True, exist_ok=True)
        r = run(["xcrun", "swiftc", "-O", str(src), "-o", str(out)], check=False)
        if r.returncode != 0 or not out.exists():
            return None
        stamp.write_text(digest)
    return out


def ensure_simscreen():
    """시뮬레이터 화면을 바로 읽는 도구(qakit ui 실시간 화면). 빌드가 안 되면 None — UI는 스크린샷 방식으로 돌아간다."""
    return ensure_swift_tool("simscreen")


def screen_jpeg(udid, width=440):
    """시뮬레이터 화면 한 장 → 작은 JPEG 바이트 (simscreen, 안 되면 simctl 스크린샷). 못 읽으면 None."""
    tmp = Path(tempfile.mkstemp(suffix=".jpg")[1])
    try:
        tool = ensure_simscreen()
        if tool and run([str(tool), udid, "--once", str(tmp), "--width", str(width)], check=False).returncode == 0:
            return tmp.read_bytes()
        if run(["xcrun", "simctl", "io", udid, "screenshot", "--type=jpeg", str(tmp)], check=False).returncode == 0:
            return tmp.read_bytes()
        return None
    finally:
        tmp.unlink(missing_ok=True)


def screens_alike(a, b, ratio=0.02):
    """두 화면이 사실상 같은가 — JPEG 크기 차이가 ratio 이하 (qakit ui의 '화면이 바뀜' 판단과 같은 기준:
    시계·커서 깜박임은 2% 미만, 화면 전환은 3~51%)."""
    return abs(len(a) - len(b)) <= max(len(a), len(b)) * ratio


class TouchHelper:
    """시뮬레이터에 터치 신호를 직접 넣는 도우미(simtouch)를 계속 띄워 두고 한 줄 명령을 보낸다 (AI QA 직접 터치).
    좌표는 화면 대비 0~1. XCUITest가 켠 앱에서도 보통 먹히지만, 조용히 무시될 때가 있어(멈춘 실행기, 새로 만든
    시뮬레이터 — docs/private-apis.md) 쓰는 쪽이 누른 뒤 화면 변화를 본다."""

    def __init__(self, udid, tool=None, ready_timeout=15):
        self.udid, self.tool, self.ready_timeout = udid, tool, ready_timeout
        self.proc = None
        self.mode = None
        self.lock = threading.Lock()
        self.lines = queue.Queue()

    def start(self):
        """→ None 또는 띄우지 못한 이유"""
        if self.proc and self.proc.poll() is None:
            return None
        tool = self.tool or ensure_swift_tool("simtouch")
        if not tool:
            return "터치 도우미(simtouch)를 빌드하지 못함"
        self.proc = subprocess.Popen([str(tool), self.udid], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, args=(self.proc, self.lines), daemon=True).start()
        try:
            first = self.lines.get(timeout=self.ready_timeout)
        except queue.Empty:
            first = None
        if not first or not first.startswith("ready"):
            err = (self.proc.stderr.read() if self.proc.poll() is not None else "") or ""
            self.stop()
            return (err.strip().splitlines() or [first or f"{self.ready_timeout}초 안에 준비되지 않음"])[-1]
        self.mode = first.split()[-1]
        return None

    @staticmethod
    def _read(proc, lines):
        for line in proc.stdout:
            lines.put(line.strip())
        lines.put(None)   # 끝남

    def send(self, cmd, timeout=None):
        """명령 한 줄 → (성공, 답). 도우미가 죽어 있으면 한 번 다시 띄운다."""
        with self.lock:
            for attempt in (1, 2):
                why = self.start()
                if why:
                    return False, why
                try:
                    self.proc.stdin.write(cmd.strip() + "\n")
                    self.proc.stdin.flush()
                    line = self.lines.get(timeout=timeout or 30)
                except (BrokenPipeError, OSError, queue.Empty) as e:
                    line = None
                    why = f"{type(e).__name__}"
                if line is None:   # 죽음 → 다시
                    self.stop()
                    if attempt == 2:
                        return False, why or "터치 도우미가 끝남"
                    continue
                return line.startswith("ok"), line
        return False, "?"

    def tap(self, x, y, hold_ms=60):
        return self.send(f"tap {x:.4f} {y:.4f} {hold_ms}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            with contextlib.suppress(OSError):
                self.proc.stdin.close()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


def swiftui_sources(ws):
    return [str(p) for p in (ws.id_sources or [ws.app_dir])]


def swiftui_enabled(ws):
    """swiftui: off → 안 함 / insert → 함 / auto → 앱 소스에 `import SwiftUI`가 있으면 함."""
    if ws.swiftui == "off":
        return False
    if ws.swiftui == "insert":
        return True
    for f in gen_ids.iter_swift_files(swiftui_sources(ws)):
        try:
            if ws.root in f.parents:
                continue
            with open(f, encoding="utf-8", errors="replace") as fh:
                if "import SwiftUI" in fh.read(4000):
                    return True
        except OSError:
            pass
    return False


def is_qa_worktree(app_dir):
    """앱 폴더가 git 연결 워크트리(qakit init --worktree)인가. 개발 폴더에는 소스를 고치지 않는다."""
    git_dir = git(app_dir, "rev-parse", "--git-dir")
    common = git(app_dir, "rev-parse", "--git-common-dir")
    return bool(git_dir and common and Path(app_dir, git_dir).resolve() != Path(app_dir, common).resolve())


def swiftui_insert(ws):
    """QA 워크트리의 SwiftUI 소스에 ID를 끼워 넣는다. 빌드가 끝나면 반드시 swiftui_restore. 반환: manifest 경로 또는 None"""
    if not swiftui_enabled(ws):
        return None
    if not is_qa_worktree(ws.app_dir):
        # 개발 폴더의 소스는 고치지 않는다. auto면 건너뛰고(UIKit 앱에 SwiftUI 파일이 조금 섞인 경우), insert면 실패.
        if ws.swiftui == "insert":
            fail("SwiftUI ID 삽입은 QA 워크트리에서만 합니다 (개발 폴더의 소스는 고치지 않습니다).",
                 "qakit init <앱> --worktree 로 만든 작업공간을 쓰거나, qakit.yml에 swiftui: off")
        warn("SwiftUI 소스가 있지만 앱 폴더가 QA 워크트리가 아니라 ID를 삽입하지 않습니다 (qakit init --worktree)")
        return None
    tool = ensure_swiftui_ids()
    manifest = ws.swiftui_manifest
    if manifest.exists():
        fail("이전 SwiftUI ID 삽입이 복원되지 않았습니다.", "qakit swiftui-ids --restore")
    status = git(ws.app_dir, "status", "--porcelain", "--", *app_pathspec(ws)) or ""
    dirty = [l[3:] for l in status.splitlines() if l[:2].strip() and l[:2] != "??" and l.endswith(".swift")]
    if dirty:
        fail("워크트리의 Swift 소스에 커밋되지 않은 변경이 있어 ID를 삽입하지 않습니다: " + ", ".join(dirty[:5]),
             "워크트리는 개발 브랜치와 같아야 합니다. git -C <워크트리> status 로 확인")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    r = run([str(tool), "insert", *swiftui_sources(ws), "--exclude", ws.root.name, "--manifest", str(manifest)], check=False)
    if r.returncode != 0:
        fail("SwiftUI ID 삽입 실패", (r.stdout or "")[-800:])
    info("   SwiftUI ID: " + (r.stdout or "").strip().splitlines()[-1])
    return manifest


def swiftui_restore(ws, manifest):
    if not manifest or not manifest.exists():
        return
    r = run([str(ensure_swiftui_ids()), "restore", "--manifest", str(manifest)], check=False)
    if r.returncode != 0 or manifest.exists():
        fail("SwiftUI ID 복원 실패 — 워크트리 소스가 바뀐 채 남아 있습니다.",
             f"qakit swiftui-ids --restore  (manifest: {manifest})")


def swiftui_list(ws):
    """swiftui-ids list --json → [{id, kind, view, file, line, overridable}]"""
    if not swiftui_enabled(ws):
        return []
    r = run([str(ensure_swiftui_ids()), "list", *swiftui_sources(ws), "--exclude", ws.root.name, "--json"], check=False)
    if r.returncode != 0:
        fail("swiftui-ids list 실패", (r.stdout or "")[-800:])
    text = r.stdout or ""
    return json.loads(text[text.index("["):text.rindex("]") + 1]) if "[" in text else []


RUNNER_MANAGED = ["Runner/project.yml", "Runner/Host/HostApp.swift", "Runner/UITests/QAKit/QAKitDumpTests.swift"]


def refresh_runner_template(ws):
    """템플릿이 관리하는 Runner 파일을 이 PC의 도구 경로로 다시 쓴다 (커밋해도 PC마다 경로가 달라 깨지지 않게)."""
    values = {"KIT_DIR": str(KIT_DIR), "NAME": ws.name}
    for rel in RUNNER_MANAGED:
        src = TEMPLATE_DIR / rel
        text = src.read_text(encoding="utf-8")
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", v)
        dst = ws.root / rel
        if not dst.exists() or dst.read_text(encoding="utf-8") != text:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")


def has_swift_runner(ws):
    return (ws.runner_dir / "UITests").exists()


def ensure_runner(ws):
    if not has_swift_runner(ws):
        fail("이 작업공간에는 Swift 테스트(Runner/UITests)가 없습니다.", "시나리오 파일은 qakit run <시나리오>로 실행하세요.")
    refresh_runner_template(ws)
    spec = ws.runner_dir / "project.yml"
    proj = ws.runner_project / "project.pbxproj"
    sources = [spec] + list((ws.runner_dir / "UITests").rglob("*.swift"))
    if not proj.exists() or proj.stat().st_mtime < max(p.stat().st_mtime for p in sources):
        if not shutil.which("xcodegen"):
            fail("xcodegen이 없습니다.", "brew install xcodegen")
        run(["xcodegen", "generate", "--quiet"], cwd=ws.runner_dir)


def build_runner(ws, udid, log_path):
    ensure_runner(ws)
    cmd = ["xcodebuild", "build-for-testing", "-project", str(ws.runner_project),
           "-scheme", RUNNER_SCHEME, "-destination", f"id={udid}",
           "-derivedDataPath", str(ws.build_dir / "runner")]
    r = run(cmd, check=False)
    log_path.write_text(r.stdout or "", encoding="utf-8")
    if r.returncode != 0:
        errors = [l for l in (r.stdout or "").splitlines() if "error:" in l]
        fail("테스트 코드 빌드 실패", "\n   ".join(dict.fromkeys(errors[:15])) or f"로그: {log_path}")


# ─────────────────────────────── 테스트 실행 공통 ───────────────────────────────

def test_env(ws, extra=None):
    env = os.environ.copy()

    def put(key, value):
        if value is not None:
            env[f"TEST_RUNNER_{key}"] = str(value)
    put("QA_BUNDLE_ID", ws.bundle_id)
    put("QA_AUTOID_DYLIB", (DEVICE_AUTOID_PATH if ws.device else ws.autoid_dylib) if ws.autoid == "inject" else None)
    put("QA_DEVICE", "1" if ws.device else None)
    if not ws.device:   # 누르는 자리 기록 (qakit ui 라이브 화면의 커서). 기기 안 실행기는 Mac 파일에 못 쓴다
        put("QA_TAPS_FILE", taps_path(ws, trim=True))
    put("QA_LANGUAGE", ws.language)
    put("QA_LOCALE", ws.locale)
    put("QA_RESULTS_DIR", ws.results_dir)
    put("QA_SECRETS_FILE", ws.secrets_path)
    for k, v in ws.secrets().items():
        put(f"QA_SECRET_{k}", v)
    for k, v in (extra or {}).items():
        put(f"QA_ARG_{k}", v)
    return env


def new_run_dir(ws, label, name=None):
    """실행 한 번의 결과 폴더: results/<날짜>/<시-분-초>_<종류>[_<이름>][_<실기기>]/
    예) results/2026-11-04/14-15-16_bench-1m_interpolation-setup_iphone-15/"""
    now = datetime.datetime.now()
    folder = now.strftime("%H-%M-%S") + f"_{label}" + (f"_{slug(name)}" if name and slug(name) else "")
    if ws.device:
        folder += f"_{slug(ws.device.get('model') or 'device') or 'device'}"
    d = ws.results_dir / now.strftime("%Y-%m-%d") / folder
    d.mkdir(parents=True, exist_ok=True)
    return d


def _relink(link, target):
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(os.path.relpath(target, link.parent))


def run_tests(ws, only, extra_env=None, label="test", quiet=False):
    """xcodebuild test 실행. (성공 여부, xcresult 경로, 마스킹된 출력)"""
    ws.results_dir.mkdir(exist_ok=True)
    ensure_autoid(ws)
    udid = ensure_booted(ws)
    if not app_installed(udid, ws.bundle_id):
        fail(f"시뮬레이터에 {ws.bundle_id}가 설치되어 있지 않습니다.", "qakit build-app")

    serve_stop(udid, reason=f"qakit {label}")
    ts = timestamp()
    rd = new_run_dir(ws, label, "-".join(o.split("/")[0] for o in only[:2]) if only else None)
    build_runner(ws, udid, rd / "build.log")

    xcresult = rd / "result.xcresult"
    cmd = ["xcodebuild", "test-without-building", "-project", str(ws.runner_project),
           "-scheme", RUNNER_SCHEME, "-destination", f"id={udid}",
           "-derivedDataPath", str(ws.build_dir / "runner"),
           "-resultBundlePath", str(xcresult)]
    for o in only:
        cmd += ["-only-testing", o if o.startswith("UITests/") else f"UITests/{o}"]
    if not only:
        cmd += ["-skip-testing", "UITests/QAKitDumpTests"]  # 전체 실행에서 덤프용 테스트 제외

    return execute_xctest(ws, cmd, extra_env, label, ts, xcresult, quiet)


def execute_xctest(ws, cmd, extra_env, label, ts, xcresult, quiet, history_name=None, on_line=None):
    """xcodebuild 테스트 실행 공통: 출력 마스킹·필터, 로그, latest 링크, 실행 기록."""
    mask = masker(ws.secrets())
    log_path = xcresult.parent / "output.log"
    proc = subprocess.Popen(cmd, env=test_env(ws, extra_env), text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    shown = re.compile(r"Test Case .* (passed|failed|started)|error:|\[qakit-|Executed \d+ test")
    lines = []
    with open(log_path, "w", encoding="utf-8") as log:
        for line in proc.stdout:
            line = mask(line)
            log.write(line)
            lines.append(line)
            if on_line:
                on_line(line)
            if not quiet and shown.search(line):
                print("  " + simplify_line(line.rstrip()), flush=True)
    proc.wait()

    _relink(ws.results_dir / "latest", xcresult.parent)       # 마지막 실행 폴더
    latest = ws.results_dir / "latest.xcresult"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    if xcresult.exists():
        _relink(latest, xcresult)
        if label != "dump":
            record_history(ws, xcresult, label, history_name)
    return proc.returncode == 0, xcresult, "".join(lines)


def results_rel(ws, path):
    """결과 폴더의 results/ 기준 상대 경로 (UI가 실행 기록과 결과 폴더를 잇는다)."""
    try:
        return str(Path(path).resolve().relative_to(ws.results_dir.resolve()))
    except ValueError:
        return None


def record_history(ws, xcresult, kind, scenario=None):
    """실행 기록 한 줄씩 (history.jsonl): 언제, 어느 앱 상태에서, 무엇이 통과/실패했는지."""
    try:
        tree = json.loads(run(["xcrun", "xcresulttool", "get", "test-results", "tests",
                               "--path", str(xcresult)], check=False).stdout or "{}")
    except json.JSONDecodeError:
        return
    cases = []

    def walk(node):
        if node.get("nodeType") == "Test Case":
            cases.append(node)
        for c in node.get("children", []):
            walk(c)
    for n in tree.get("testNodes", []):
        walk(n)
    state = app_state(ws)
    with open(ws.root / "history.jsonl", "a", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps({
                "at": datetime.datetime.now().isoformat(timespec="seconds"),
                "kind": kind,
                "test": scenario or c.get("nodeIdentifier", c.get("name")),
                "result": c.get("result"),
                "seconds": round(c.get("durationInSeconds", 0), 1),
                "dir": results_rel(ws, Path(xcresult).parent),
                "app": {k: state.get(k) for k in ("branch", "commit", "dirtyFiles") if k in state},
                "kit": kit_version(),
            }, ensure_ascii=False) + "\n")


def update_readme(ws, quiet=True):
    """QA 폴더 README.md의 자동 목록(시나리오·공통 단계·Swift 테스트·마지막 실행)을 갱신."""
    try:
        raw = (ws.cfg.get("app") or {}).get("project", "")   # 커밋해도 PC마다 맞도록 설정 값 그대로 (상대 경로)
        changed = qa_readme.write(ws.root, ws.name, f"테스트 대상 앱: `{raw}`")
    except Exception as e:  # README 때문에 본 작업이 실패하지 않게
        warn(f"README 갱신 실패: {e}")
        return
    if changed and not quiet:
        ok(f"README 갱신: {ws.root / 'README.md'}")


def cmd_readme(args):
    ws = find_workspace(args.workspace)
    update_readme(ws, quiet=False)
    ok(f"{ws.root / 'README.md'}")


@functools.lru_cache(maxsize=None)
def kit_version():
    v = (KIT_DIR / "VERSION").read_text().strip() if (KIT_DIR / "VERSION").exists() else "dev"
    c = git(KIT_DIR, "rev-parse", "--short", "HEAD")
    return f"{v}+{c}" if c else v


def simplify_line(line):
    line = re.sub(r"^.*Test Case '-\[UITests\.(\S+) (\S+)\]' ", r"\1/\2 ", line)
    line = line.replace(" started.", " …").replace(" passed ", " ✅ ").replace(" failed ", " ❌ ")
    return line


