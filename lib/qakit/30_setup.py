# qakit — init·doctor·build-app·dump-ui·test
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 명령: init ───────────────────────────────

def cmd_init(args):
    target = Path(args.project).expanduser().resolve()
    project = find_project(target)
    if not project:
        fail(f"{target}에서 .xcworkspace / .xcodeproj를 찾지 못했습니다.")

    name = args.name or slug(project.parent.name)
    if args.worktree:
        project = make_qa_worktree(project, args)
        args.in_project = True
        args.git_exclude = True
    if args.in_project:
        root = project.parent / "QA"
    elif args.dir:
        root = Path(args.dir).expanduser().resolve()
    else:
        root = project.parent.parent / "qa-workspaces" / name
    if (root / "qakit.yml").exists() and not args.force:
        fail(f"이미 작업공간이 있습니다: {root}", "덮어쓰려면 --force")

    info(f"프로젝트 분석 중: {project}")
    listing = json.loads(run(["xcodebuild", "-list", "-json", *project_flag(project)]).stdout)
    schemes = (listing.get("project") or listing.get("workspace") or {}).get("schemes", [])
    if not schemes:
        fail("공유된 scheme이 없습니다.", "Xcode에서 scheme을 Shared로 설정하세요.")
    scheme, configuration, bundle_id = (args.scheme, None, None)
    if scheme:
        configuration = scheme_configuration(project, scheme) or "Debug"
        bundle_id = app_bundle_id(project, scheme, configuration)
    else:
        # 앱(.app)을 빌드하는 scheme만 후보로. 패키지 의존성 scheme(예: SDK 이름)은 앱을 만들지 않는다.
        for candidate in rank_schemes(schemes, project):
            conf = scheme_configuration(project, candidate) or "Debug"
            bid = app_bundle_id(project, candidate, conf)
            if bid:
                scheme, configuration, bundle_id = candidate, conf, bid
                break
        if not scheme:
            scheme, configuration = schemes[0], "Debug"
            warn("앱을 빌드하는 scheme을 찾지 못했습니다. qakit.yml의 scheme/bundleId를 직접 입력하세요.")
    info(f"  scheme: {scheme} (후보: {', '.join(schemes)})")
    info(f"  configuration: {configuration}")
    info(f"  bundleId: {bundle_id or '(찾지 못함 — qakit.yml에 직접 입력)'}")

    root.mkdir(parents=True, exist_ok=True)
    values = {
        "NAME": name,
        "PROJECT": (os.path.relpath(project, root) if args.in_project
                    else str(project).replace(str(Path.home()), "~")),
        "SCHEME": scheme,
        "CONFIGURATION": configuration,
        "BUNDLE_ID": bundle_id or "TODO.bundle.id",
        "SIMULATOR": args.simulator or default_simulator(),
        "KIT_DIR": str(KIT_DIR),
        "WORKTREE_BASE": getattr(args, "base", None) or "develop",
    }
    copy_template(TEMPLATE_DIR, root, values, force=args.force)
    (root / "results").mkdir(exist_ok=True)
    if args.in_project and args.git_exclude:
        add_git_exclude(project.parent, root)
    update_readme(Workspace(root))
    ok(f"작업공간 생성: {root}")
    info("다음 할 일:")
    info(f"  1. {root}/qakit.yml 확인 (permissions, language)")
    info(f"  2. secrets.example.txt를 참고해 secrets.txt 작성 (로그인이 필요한 앱이면)")
    info(f"  3. cd {root} && qakit doctor && qakit build-app && qakit dump-ui")


def make_qa_worktree(project, args):
    """앱 레포에 QA 전용 워크트리를 만든다 (원래 개발 폴더와 섞이지 않게). 이미 있으면 그대로 쓴다."""
    repo = project.parent
    if git(repo, "rev-parse", "--git-dir") is None:
        fail(f"{repo}는 git 레포가 아닙니다.", "--worktree 없이 --in-project 또는 기본 작업공간을 쓰세요")
    top = Path(git(repo, "rev-parse", "--show-toplevel"))
    wt = Path(args.worktree_dir).expanduser().resolve() if args.worktree_dir else top.parent / f"{top.name}-qa"
    branch = args.branch or "qa/workspace"
    listing = git(repo, "worktree", "list", "--porcelain") or ""
    if f"worktree {wt}" in listing:
        ok(f"기존 QA 워크트리 사용: {wt}")
    else:
        if wt.exists():
            fail(f"{wt}가 이미 있지만 이 레포의 워크트리가 아닙니다.", "--worktree-dir로 다른 위치를 지정하세요")
        exists = git(repo, "rev-parse", "--verify", "--quiet", branch) is not None
        if exists:
            cmd = ["git", "-C", str(repo), "worktree", "add", str(wt), branch]
        else:
            base = args.base or ("develop" if git(repo, "rev-parse", "--verify", "--quiet", "develop") else "HEAD")
            cmd = ["git", "-C", str(repo), "worktree", "add", "-b", branch, str(wt), base]
        r = run(cmd, check=False)
        if r.returncode != 0:
            fail("워크트리 생성 실패", r.stdout[-500:])
        ok(f"QA 워크트리 생성: {wt} (브랜치 {branch}" + ("" if exists else f", {args.base or 'develop'}에서") + ")")
    copy_local_files(top, wt)
    return wt / project.relative_to(top)


LOCAL_SKIP = re.compile(r"(^|/)(xcuserdata|\.build|build|DerivedData|Derived|\.claude|\.codex|\.githooks|\.tuist|\.obsidian|QA|Pods|node_modules|\.swiftpm|SourcePackages|[^/]+\.xcodeproj|[^/]+\.xcworkspace)(/|$)|\.DS_Store$")


def copy_local_files(src_repo, wt, max_bytes=1_000_000):
    """git에 없는 로컬 설정 파일(키가 든 xcconfig, GoogleService-Info.plist 등)을 원래 폴더에서 워크트리로 복사.
    워크트리는 git에 있는 파일만 가져오므로 이게 없으면 빌드가 실패한다. 내용은 출력하지 않는다."""
    out = git(src_repo, "ls-files", "--others", "--ignored", "--exclude-standard") or ""
    copied = []
    for rel in out.splitlines():
        if LOCAL_SKIP.search(rel):
            continue
        src, dst = Path(src_repo) / rel, Path(wt) / rel
        if not src.is_file() or src.stat().st_size > max_bytes or dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    if copied:
        ok(f"git에 없는 로컬 설정 파일 {len(copied)}개를 원래 폴더에서 복사: " + ", ".join(copied[:10]))


def add_git_exclude(repo_dir, path):
    """레포의 .gitignore를 건드리지 않고 이 PC에서만 무시 (.git/info/exclude)."""
    # 워크트리에서는 --git-dir이 .git/worktrees/<이름>을 가리키지만 git은 공통 디렉터리의 info/exclude만 읽는다
    git_dir = git(repo_dir, "rev-parse", "--git-common-dir")
    if not git_dir:
        return
    exclude = (Path(repo_dir) / git_dir).resolve() / "info" / "exclude"
    rel = "/" + os.path.relpath(path, repo_dir).rstrip("/") + "/"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text() if exclude.exists() else ""
    if rel not in current.splitlines():
        exclude.write_text(current + ("" if current.endswith("\n") or not current else "\n") + rel + "\n")
        ok(f"{rel}를 이 PC의 git 무시 목록(.git/info/exclude)에 추가")


def find_project(path):
    if path.suffix in (".xcworkspace", ".xcodeproj"):
        return path
    if not path.is_dir():
        return None
    ws = [p for p in path.glob("*.xcworkspace")]
    if ws:
        return ws[0]
    pj = [p for p in path.glob("*.xcodeproj")]
    return pj[0] if pj else None


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def rank_schemes(schemes, project):
    """앱 scheme일 가능성 순: 개발용 키워드 > 프로젝트 이름과 같음 > 프로젝트에 공유된 scheme > 나머지."""
    shared = {p.stem for p in project.parent.glob("*.xcodeproj/xcshareddata/xcschemes/*.xcscheme")}
    name = project.stem.lower()

    def score(s):
        low = s.lower()
        if any(k in low for k in ("develop", "dev", "debug", "staging")):
            return 0
        if low == name:
            return 1
        if s in shared:
            return 2
        return 3
    return sorted(schemes, key=lambda s: (score(s), schemes.index(s)))


def scheme_configuration(project, scheme):
    container = project if project.suffix == ".xcodeproj" else None
    candidates = []
    if container:
        candidates.append(container / "xcshareddata" / "xcschemes" / f"{scheme}.xcscheme")
    candidates += list(project.parent.glob(f"*.xcodeproj/xcshareddata/xcschemes/{scheme}.xcscheme"))
    for c in candidates:
        if c.exists():
            node = ET.parse(c).getroot().find("LaunchAction")
            if node is not None and node.get("buildConfiguration"):
                return node.get("buildConfiguration")
    return None


def app_bundle_id(project, scheme, configuration):
    r = run(["xcodebuild", "-showBuildSettings", "-json", *project_flag(project), "-scheme", scheme,
             "-configuration", configuration, "-sdk", "iphonesimulator"], check=False)
    # 경고 문구가 섞여 나오므로(예: "Designed for [iPad,iPhone]") 줄 맨 앞의 '['부터 JSON으로 읽는다
    m = re.search(r"^\[", r.stdout or "", re.M)
    if not m:
        return None
    try:
        targets, _ = json.JSONDecoder().raw_decode(r.stdout[m.start():])
    except json.JSONDecodeError:
        return None
    for t in targets:
        s = t.get("buildSettings", {})
        if s.get("WRAPPER_EXTENSION") == "app" and s.get("PRODUCT_BUNDLE_IDENTIFIER"):
            return s["PRODUCT_BUNDLE_IDENTIFIER"]
    return None


def default_simulator():
    data = json.loads(run(["xcrun", "simctl", "list", "devices", "available", "-j"]).stdout)
    names = [d["name"] for rt, ds in sorted(data["devices"].items()) if "iOS" in rt for d in ds]
    for preferred in ("iPhone 17", "iPhone 16", "iPhone 15"):
        if preferred in names:
            return preferred
    iphones = [n for n in names if n.startswith("iPhone")]
    return iphones[-1] if iphones else "iPhone 17"


def copy_template(src, dst, values, force):
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        rel = Path(str(rel).replace("_gitignore", ".gitignore"))
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists() and not force:
            continue
        # 사용자가 작성한 테스트는 --force여도 덮어쓰지 않는다
        if target.exists() and "Flows" in rel.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", v)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


# ─────────────────────────────── 명령: doctor ───────────────────────────────

def cmd_doctor(args):
    ws = find_workspace(args.workspace)
    problems = 0

    def check(cond, good, bad, hint=None):
        nonlocal problems
        if cond:
            ok(good)
        else:
            problems += 1
            print(f"❌ {bad}" + (f"\n   → {hint}" if hint else ""))

    info(f"작업공간: {ws.root}")
    if ws.platform == "android":
        return android_doctor_ws(ws, check, lambda: problems)
    xc = run(["xcodebuild", "-version"], check=False)
    check(xc.returncode == 0, (xc.stdout or "").splitlines()[0] if xc.stdout else "", "Xcode 없음",
          "Xcode 설치 후 sudo xcode-select -s /Applications/Xcode.app")
    check(shutil.which("xcodegen"), "xcodegen 설치됨", "xcodegen 없음", "brew install xcodegen")
    check(ws.project and ws.project.exists(), f"앱 프로젝트: {ws.project}", f"앱 프로젝트 없음: {ws.project}",
          "qakit.yml의 app.project 확인")
    check(bool(ws.scheme), f"scheme: {ws.scheme}", "app.scheme 비어 있음")
    check(ws.bundle_id and "TODO" not in ws.bundle_id, f"bundleId: {ws.bundle_id}", "app.bundleId 비어 있음")

    udid, state = simulator_udid(ws.simulator)
    check(udid, f"시뮬레이터: {ws.simulator} ({state})", f"시뮬레이터 '{ws.simulator}' 없음",
          "xcrun simctl list devices available")
    if udid:
        check(app_installed(udid, ws.bundle_id), "대상 앱 설치됨", "대상 앱이 시뮬레이터에 없음", "qakit build-app")

    if ws.autoid == "inject":
        check(ws.autoid_dylib.exists(), "AutoID dylib 빌드됨", "AutoID dylib 없음",
              "qakit build-app (자동으로 빌드됨)")
    else:
        info("ℹ️  autoid: embedded — 앱에 AutoID.swift가 들어가 있어야 합니다.")

    if ws.app_dir and swiftui_enabled(ws):
        if is_qa_worktree(ws.app_dir):
            ok("SwiftUI ID 삽입: QA 워크트리 확인됨")
        elif ws.swiftui == "insert":
            check(False, "", "swiftui: insert 인데 앱 폴더가 QA 워크트리가 아님 (삽입은 워크트리에서만)",
                  "qakit init <앱> --worktree 또는 qakit.yml에 swiftui: off")
        else:
            warn("SwiftUI 소스가 있지만 앱 폴더가 QA 워크트리가 아니라 SwiftUI ID를 붙이지 않습니다 (qakit init --worktree)")
        check(not ws.swiftui_manifest.exists(), "SwiftUI ID 삽입 복원 상태 정상",
              "이전 SwiftUI ID 삽입이 복원되지 않음 (워크트리 소스가 바뀐 채)", "qakit swiftui-ids --restore")
        if not SWIFTUI_IDS_BIN.exists():
            info("ℹ️  swiftui-ids 도구는 첫 qakit build-app 때 빌드됩니다 (몇 분)")

    st = worktree_status(ws) if ws.app_dir else None
    if st and st["ref"]:
        if st["behind"]:
            warn(f"QA 워크트리({st['branch']})가 {st['ref']}보다 {st['behind']}커밋 뒤처짐 → qakit worktree-update"
                 + (" (test/run 전에 자동으로 가져옴)" if ws.worktree_update == "auto" else ""))
        else:
            ok(f"QA 워크트리({st['branch']})가 {st['ref']} 기준 최신")
    if ws.secrets_path.exists():
        keys = sorted(ws.secrets().keys())
        example = ws.root / "secrets.example.txt"
        needed = sorted(Workspace.parse_keys(example)) if example.exists() else []
        missing = [k for k in needed if k not in keys]
        check(not missing, f"secrets: {', '.join(keys) or '(비어 있음)'}",
              f"secrets에 키 누락: {', '.join(missing)}", f"{ws.secrets_path}에 추가")
    else:
        warn(f"secrets 파일 없음: {ws.secrets_path} (로그인이 필요 없으면 무시)")

    check(ws.runner_dir.joinpath("project.yml").exists(), "Runner 준비됨", "Runner/project.yml 없음", "qakit init --force")
    print()
    if problems:
        fail(f"문제 {problems}개", "위 → 안내대로 고친 뒤 다시 qakit doctor")
    ok("모두 정상")


def _parse_keys(path):
    keys = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.append(line.split("=", 1)[0].strip())
    return keys


Workspace.parse_keys = staticmethod(_parse_keys)


# ─────────────────────────────── 명령: build-app ───────────────────────────────

def cmd_build_app(args):
    ws = find_workspace(args.workspace)
    with sim_lock(ws, "qakit build-app"):   # 설치하면 실행 중인 앱이 꺼지므로
        cmd_build_app_ws(ws)


def cmd_build_app_ws(ws):
    if ws.platform == "android":
        return android_build_app(ws)
    ws.results_dir.mkdir(exist_ok=True)
    ensure_autoid(ws)
    udid = ws.device["udid"] if ws.device else ensure_booted(ws)

    info(f"앱 빌드 중: {ws.scheme} ({ws.configuration}, {ws.build})" + (" · 실기기용" if ws.device else "")
         + " — 처음엔 몇 분 걸립니다")
    log_path = ws.results_dir / "build-app.log"
    cmd = ["xcodebuild", "build", *project_flag(ws.project), "-scheme", ws.scheme,
           "-configuration", ws.configuration,
           # -sdk는 주지 않는다: 모든 타깃의 SDK를 덮어써서 Swift 매크로 플러그인(macOS 실행 파일)까지
           # 시뮬레이터용으로 빌드돼 "produced malformed response"로 실패한다. -destination이 SDK를 정한다.
           "-destination", "generic/platform=iOS" if ws.device else "generic/platform=iOS Simulator",
           "-derivedDataPath", str(ws.app_build_dir)]
    if ws.device:
        cmd += ["-allowProvisioningUpdates", f"DEVELOPMENT_TEAM={device_team(ws)}"]
    state = app_state(ws)
    before = git(ws.app_dir, "status", "--porcelain", "--", *app_pathspec(ws))
    # SwiftUI 소스에 ID를 끼워 넣고 빌드한 뒤, 무슨 일이 있어도(실패·Ctrl-C) 원래대로 되돌린다
    manifest = swiftui_insert(ws)
    try:
        # 앱 레포의 Package.resolved를 고치지 않는다 (QA는 앱 레포를 수정하지 않음)
        r = run(cmd + ["-onlyUsePackageVersionsFromResolvedFile"], check=False)
        if r.returncode != 0 and "resolved" in (r.stdout or "").lower() and "error:" in (r.stdout or ""):
            warn("Package.resolved 고정 빌드 실패 → 고정 없이 다시 빌드 (앱 레포의 Package.resolved가 바뀔 수 있음)")
            r = run(cmd, check=False)
    finally:
        swiftui_restore(ws, manifest)
    log_path.write_text(r.stdout or "", encoding="utf-8")
    after = git(ws.app_dir, "status", "--porcelain", "--", *app_pathspec(ws))
    if before is not None and after != before:
        changed = sorted(set((after or "").splitlines()) - set((before or "").splitlines()))
        warn("빌드 중 앱 레포 파일이 바뀌었습니다 (QA가 만든 변경일 수 있음): " + ", ".join(c[3:] for c in changed))
    if r.returncode != 0:
        errors = [l for l in (r.stdout or "").splitlines() if "error:" in l]
        fail("앱 빌드 실패", "\n   ".join(dict.fromkeys(errors[:15])) or f"로그: {log_path}")

    app_path = find_built_app(ws)
    if not app_path:
        fail(f"빌드 결과에서 {ws.bundle_id} 앱을 찾지 못했습니다.", "qakit.yml의 bundleId/configuration 확인")
    if ws.device:
        if ws.autoid == "inject":
            embed_autoid(app_path, ws.autoid_dylib)
        device_install(ws, app_path)
        ok(f"설치: {app_path.name} → {ws.device['name']}")
        if ws.permissions:
            info("ℹ️  실기기는 권한을 미리 허용할 수 없습니다 → 처음 한 번 기기에서 허용하거나 시나리오가 팝업을 누르게 하세요 ("
                 + ", ".join(map(str, ws.permissions)) + ")")
        state["installedOn"] = udid
        save_state(ws, ws.state_name, state)
        return
    run(["xcrun", "simctl", "install", udid, str(app_path)])
    ok(f"설치: {app_path.name} → {ws.simulator}")

    for perm in ws.permissions:
        r = run(["xcrun", "simctl", "privacy", udid, "grant", str(perm), ws.bundle_id], check=False)
        (ok if r.returncode == 0 else warn)(f"권한 허용: {perm}" + ("" if r.returncode == 0 else " 실패"))
    state["installedOn"] = udid
    save_state(ws, ws.state_name, state)


def find_built_app(ws):
    products = ws.app_build_dir / "Build" / "Products"
    for app in products.glob("*-iphoneos/*.app" if ws.device else "*-iphonesimulator/*.app"):
        try:
            with open(app / "Info.plist", "rb") as f:
                if plistlib.load(f).get("CFBundleIdentifier") == ws.bundle_id:
                    return app
        except (OSError, plistlib.InvalidFileException):
            continue
    return None


# ─────────────────────────────── 명령: dump-ui ───────────────────────────────

def cmd_dump_ui(args):
    ws = find_workspace(args.workspace)
    if ws.platform == "android":
        return save_ui_dump(ws, args, android_dump_ui_ws(ws, args))
    with sim_lock(ws, "qakit dump-ui"):
        _cmd_dump_ui(ws, args)


def _cmd_dump_ui(ws, args):
    extra = {"DUMP_MODE": "attach" if args.attach else "launch", "DUMP_SETTLE": str(args.settle)}
    if args.wait_id:
        extra["DUMP_WAIT_ID"] = args.wait_id
    dump = ws.results_dir / "ui-dump.txt"
    if dump.exists():
        dump.unlink()
    if has_swift_runner(ws) and not ws.device:
        success, xcresult, output = run_tests(ws, [DUMP_TEST], extra, label="dump", quiet=True)
    else:
        success, xcresult, output = run_scenario_runner(ws, "test_dump", extra, label="dump", quiet=True)
    if not dump.exists():
        print(summarize(xcresult, masker(ws.secrets())))
        fail("화면 덤프 실패")
    save_ui_dump(ws, args, masker(ws.secrets())(dump.read_text(encoding="utf-8")))


def save_ui_dump(ws, args, text):
    """덤프 텍스트를 results/ui-dump.txt와 results/dumps/에 저장하고 요약을 보여 준다 (iOS·안드로이드 공통)."""
    dump = ws.results_dir / "ui-dump.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(text, encoding="utf-8")
    # gen-ids --verify가 쓰도록 덤프를 모아 둔다
    archive = ws.results_dir / "dumps"
    archive.mkdir(exist_ok=True)
    (archive / f"ui-dump-{timestamp()}.txt").write_text(text, encoding="utf-8")
    header = [l for l in text.splitlines() if l.startswith("#")]
    for l in header[2:]:
        info(l.lstrip("# "))
    ok(f"저장: {dump}")
    if args.print:
        print(text)


# ─────────────────────────────── 명령: test ───────────────────────────────

def reset_app(ws, udid):
    """앱 재설치 + 키체인 초기화 → 처음 설치한 상태 (로그아웃)."""
    if ws.platform == "android":
        adb(udid, "shell", "pm", "clear", ws.package)   # 데이터·권한·로그인 상태를 지운다 (재설치와 같은 효과)
        ok("앱 초기화 (pm clear)")
        android_grant_permissions(ws, udid)
        return
    app_path = find_built_app(ws)
    if not app_path:
        fail("재설치할 앱 빌드가 없습니다.", "qakit build-app")
    if ws.device:
        run(["xcrun", "devicectl", "device", "uninstall", "app", "--device", ws.device["id"], ws.bundle_id], check=False)
        device_install(ws, app_path)
        ok("앱 초기화 (재설치 — 실기기는 키체인을 지울 수 없어 저장된 로그인 정보가 남을 수 있음)")
        return
    run(["xcrun", "simctl", "terminate", udid, ws.bundle_id], check=False)
    run(["xcrun", "simctl", "uninstall", udid, ws.bundle_id], check=False)
    run(["xcrun", "simctl", "keychain", udid, "reset"], check=False)
    run(["xcrun", "simctl", "install", udid, str(app_path)])
    for perm in ws.permissions:
        run(["xcrun", "simctl", "privacy", udid, "grant", str(perm), ws.bundle_id], check=False)
    ok("앱 초기화 (재설치 + 키체인 초기화)")


def cmd_test(args):
    ws = find_workspace(args.workspace)
    try:
        with sim_lock(ws, "qakit test " + " ".join(args.filters or [])):
            _cmd_test(ws, args)
    finally:
        update_readme(ws)


def _cmd_test(ws, args):
    if ws.device:
        fail("qakit test는 아직 실기기를 지원하지 않습니다.", "실기기는 시나리오로: qakit run <시나리오> --device")
    if not has_swift_runner(ws):
        fail("Swift 테스트가 없는 작업공간입니다.", "시나리오는 qakit run <시나리오>, 목록은 ls scenarios/")
    prefetch_worktree(ws)
    only = args.filters or []
    extra = {}
    auto_sync(ws)
    if args.reset:
        reset_app(ws, ws.device["udid"] if ws.device else ensure_booted(ws))
        extra["RESET"] = "1"
    info(f"테스트 실행: {', '.join(only) if only else '전체'}")
    success, xcresult, _ = run_tests(ws, only, extra, label="test")
    print()
    if success:
        ok(f"통과 — 결과: {xcresult}")
        return
    print(summarize(xcresult, masker(ws.secrets())))
    fail("실패", f"자세한 결과: {xcresult}")


