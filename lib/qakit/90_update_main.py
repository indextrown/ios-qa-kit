# qakit — update·main (명령 정의)
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 명령: update ───────────────────────────────

def cmd_update(args):
    """설치한 도구 폴더를 원격의 최신으로 받는다 (git fast-forward만). 명령·스킬은 링크라 그대로 바뀐다."""
    repo = KIT_DIR
    if ".app/Contents/" in str(repo):   # 맥 앱 안 도구 (위에 저장소가 있어도 그건 앱이 아님)
        fail("맥 앱 안의 qakit은 앱을 새 버전으로 바꿔 업데이트합니다.",
             "https://github.com/indextrown/qa-kit/releases 에서 새 버전 받기")
    if git(repo, "rev-parse", "--git-dir") is None:
        fail(f"{repo}는 git 저장소가 아닙니다.", "git clone으로 설치한 경우만 qakit update를 쓸 수 있습니다")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        fail(f"브랜치 {branch}에 연결된 원격 브랜치가 없습니다.", f"git -C {repo} branch -u origin/main")
    if branch != "main":
        warn(f"설치 폴더가 {branch} 브랜치입니다. 배포 버전은 main입니다 (개발 중이 아니면 git -C {repo} switch main)")

    old_version = kit_version()
    info(f"확인 중: {repo} ({branch}, {old_version})")
    r = run(["git", "-C", str(repo), "fetch", "--tags", "--quiet"], check=False)
    if r.returncode != 0:
        fail("원격 저장소에서 받지 못했습니다 (네트워크·권한 확인)", (r.stdout or "")[-400:])

    behind = int(git(repo, "rev-list", "--count", "HEAD..@{u}") or 0)
    ahead = int(git(repo, "rev-list", "--count", "@{u}..HEAD") or 0)
    if behind == 0:
        ok(f"이미 최신입니다: qakit {old_version} ({branch})")
        if ahead:
            info(f"   로컬에만 있는 커밋 {ahead}개가 있습니다")
        return
    new_version = (git(repo, "show", "@{u}:VERSION") or "?").strip()
    info(f"새 버전: {old_version} → {new_version} (커밋 {behind}개)")
    for line in (git(repo, "log", "--oneline", "--no-merges", "HEAD..@{u}") or "").splitlines()[:20]:
        print(f"   {line}")
    if args.check:
        info("받으려면: qakit update")
        return

    dirty = [l for l in (git(repo, "status", "--porcelain", "--untracked-files=no") or "").splitlines() if l.strip()]
    if dirty:
        fail("설치 폴더에 고친 파일이 있어 업데이트하지 않습니다: " + ", ".join(l[3:] for l in dirty[:5]),
             f"git -C {repo} status 로 확인 (버려도 되면 git -C {repo} checkout -- .)")
    if ahead:
        fail(f"설치 폴더에 원격에 없는 커밋이 {ahead}개 있어 빨리 감기(fast-forward)가 안 됩니다.",
             f"git -C {repo} log @{{u}}..HEAD 로 확인")
    r = run(["git", "-C", str(repo), "merge", "--ff-only", "--quiet", "@{u}"], check=False)
    if r.returncode != 0:
        fail("업데이트 실패", (r.stdout or "")[-400:])
    kit_version.cache_clear()   # 한 명령 안에서 기억해 둔 옛 버전 대신 받은 뒤의 버전을 읽는다
    ok(f"업데이트 완료: qakit {kit_version()}")

    # 레포 이름 변경(ios-qa-kit → qa-kit)으로 끊어진 옛 스킬 링크를 새 이름으로 옮긴다
    migrate_old_skill_links()
    # 명령·스킬 링크가 이 폴더를 가리키는지 (다른 폴더를 가리키면 업데이트가 반영되지 않는다)
    links = [link for link, _, _ in skill_links()]
    elsewhere = [str(l) for l in links if l.is_symlink() and not Path(os.path.realpath(l)).is_relative_to(repo.resolve())]
    if elsewhere:
        warn("다른 폴더를 가리키는 링크가 있습니다: " + ", ".join(elsewhere) + f" → {repo}/bin/qakit install-skill")
    info("AutoID·swiftui-ids 도구는 다음 build-app 때 바뀐 것만 자동으로 다시 빌드됩니다.")


# ─────────────────────────────── main ───────────────────────────────

TIMED_FUNCTIONS = ("find_workspace", "ensure_booted", "sim_lock", "load_checked_scenario", "generate_ids", "auto_sync",
                   "follow_worktree", "swiftui_list", "serve_ready_for", "serve_ensure", "serve_request", "run_via_serve",
                   "app_state", "update_readme", "run_scenario_runner", "record_history", "kit_version",
                   "known_ids", "id_sources_fingerprint", "_git_quiet_fetch")


def enable_timing():
    """QAKIT_TIMING=1: 주요 단계에 걸린 시간을 끝에 출력한다 (느려졌을 때 어디인지 보기)."""
    import atexit
    start = time.time()
    rows = []
    depth = [0]

    def wrap(name, fn):
        if isinstance(fn, type) or not callable(fn):
            return fn
        is_cm = name == "sim_lock"

        def timed(*a, **k):
            depth[0] += 1
            t = time.time()
            try:
                return fn(*a, **k)
            finally:
                depth[0] -= 1
                rows.append((t - start, depth[0], name, time.time() - t))

        if is_cm:
            @contextlib.contextmanager
            def timed_cm(*a, **k):
                t = time.time()
                with fn(*a, **k) as v:
                    rows.append((t - start, depth[0], "sim_lock(잡기)", time.time() - t))
                    yield v
            return timed_cm
        return timed

    for name in TIMED_FUNCTIONS:
        if name in globals():
            globals()[name] = wrap(name, globals()[name])

    def report():
        print(f"\n── qakit 단계별 시간 (전체 {time.time() - start:.2f}초)", file=sys.stderr)
        for at, d, name, secs in sorted(rows):
            if secs >= 0.05:
                print(f"  {at:6.2f}s  {'  ' * d}{name} {secs:.2f}초", file=sys.stderr)
    atexit.register(report)


class _VersionAction(argparse.Action):
    """qakit --version. git 브랜치는 이 옵션을 줄 때만 읽는다 (예전엔 명령마다 git을 띄웠다).
    저장소가 아닌 설치(맥 앱 번들)는 브랜치를 붙이지 않는다 — git 오류 문구가 브랜치 자리에 찍히던 것."""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        version = (KIT_DIR / "VERSION").read_text().strip() if (KIT_DIR / "VERSION").exists() else "dev"
        branch = git(KIT_DIR, "rev-parse", "--abbrev-ref", "HEAD")
        print(f"qakit {version}" + (f" ({branch})" if branch and branch != "HEAD" else ""))
        parser.exit()


def main():
    if os.environ.get("QAKIT_TIMING"):
        enable_timing()
    parser = argparse.ArgumentParser(prog="qakit", description="AI용 XCUITest 도구")
    parser.add_argument("--version", action=_VersionAction, help="버전(과 설치 폴더의 git 브랜치) 표시")
    parser.add_argument("-w", "--workspace", help="작업공간 경로 (기본: 현재 폴더에서 qakit.yml 탐색)")
    parser.add_argument("--app", help="앱 경로 일시 지정 (다른 워크트리/브랜치 폴더 검증용)")
    parser.add_argument("--build", choices=["debug", "release"], default="debug",
                        help="빌드 종류 (기본 debug = qakit.yml app.configuration, release = app.release.configuration 기본 Release)")
    device_help = "실기기에서 실행: select(방향키로 고르기, 값 생략 시) · last(지난번 기기) · <기기 이름>"
    parser.add_argument("--device", nargs="?", const="select", default=None, metavar="기기", help=device_help)
    parser.add_argument("--secrets", help="비밀값 파일 직접 지정 (기본: qakit.yml의 secrets). 계정을 바꿔 돌릴 때")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="작업공간 생성")
    p.add_argument("project", help="앱 프로젝트 경로 (.xcodeproj/.xcworkspace 또는 그 폴더)")
    p.add_argument("--name", help="작업공간 이름 (기본: 프로젝트 폴더 이름)")
    p.add_argument("--dir", help="작업공간 경로 (기본: <프로젝트 상위>/qa-workspaces/<이름>)")
    p.add_argument("--scheme", help="scheme 직접 지정")
    p.add_argument("--simulator", help="시뮬레이터 이름")
    p.add_argument("--force", action="store_true", help="템플릿 파일 덮어쓰기 (Flows/ 테스트는 유지)")
    p.add_argument("--in-project", action="store_true", help="앱 프로젝트 안 QA/ 폴더에 만들기")
    p.add_argument("--git-exclude", action="store_true", help="QA/를 이 PC에서만 git 무시 (.git/info/exclude)")
    p.add_argument("--worktree", action="store_true",
                   help="QA 전용 워크트리(<레포>-qa, 브랜치 qa/workspace)를 만들고 그 안 QA/에 작업공간 생성 (권장)")
    p.add_argument("--worktree-dir", help="워크트리 위치 직접 지정")
    p.add_argument("--branch", help="워크트리 브랜치 (기본 qa/workspace)")
    p.add_argument("--base", help="새 브랜치를 딸 기준 (기본 develop, 없으면 HEAD)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("install-skill", help="AI 스킬(Claude Code·Codex)과 qakit 명령 설치")
    p.add_argument("--uninstall", action="store_true", help="설치한 링크 제거")
    p.set_defaults(func=cmd_install_skill)

    p = sub.add_parser("serve", help="상주 실행기: 실행기를 띄워 두고 qakit do로 바로 실행 (시뮬레이터)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--stop", action="store_true", help="멈추기")
    g.add_argument("--status", action="store_true", help="상태 보기")
    p.add_argument("--idle", type=int, default=1800, help="명령이 없으면 스스로 끝내는 시간(초, 기본 1800)")
    p.add_argument("--no-launch", action="store_true", help="시작할 때 앱을 띄우지 않음")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("do", help="시나리오 단계 하나를 바로 실행 (상주 실행기, 없으면 띄움). 예) qakit do 'tap: X' / dump / launch / reset")
    p.add_argument("step", nargs="+",
                   help="단계(시나리오 문법) 또는 dump · launch · ping · reset · steps(기록 보기) · save <이름>(기록으로 시나리오 초안) · restore [이름](launch로 비운 이전 기록 되살리기)")
    p.add_argument("--force", action="store_true", help="save: 같은 이름의 시나리오가 있어도 덮어씀")
    p.add_argument("--no-record", action="store_true", help="통과해도 기록하지 않음 (확인용 — AI QA 직접 터치가 씀)")
    p.add_argument("--title", help="save: 시나리오 제목 (name:)")
    p.add_argument("--tag", action="append", help="save: 태그 (여러 번)")
    p.add_argument("--start", metavar="공통단계", help="save: 맨 앞에 use: <공통단계> (예: home)")
    p.add_argument("--timeout", type=int, default=120, help="이 시간(초) 안에 안 끝나면 실행기를 멈춤 (기본 120)")
    p.add_argument("--settle", type=float, default=0.5, help="dump 전에 기다릴 시간(초)")
    p.set_defaults(func=cmd_do)

    p = sub.add_parser("touch", help="시뮬레이터에 터치 신호를 직접 넣기 (확인용, AI QA 직접 터치). 좌표는 화면 대비 0~1. 누른 뒤 화면이 그대로면 알림. 예) qakit touch tap 0.5 0.9")
    p.add_argument("action", nargs="+", help="tap x y [ms] · press x y 초 · swipe x1 y1 x2 y2 초 · ping")
    p.set_defaults(func=cmd_touch)

    p = sub.add_parser("coverage", help="앱 ID 중 시나리오가 쓰는 것 (화면별). --unused: 안 쓴 ID까지, --json")
    p.add_argument("--unused", action="store_true", help="화면마다 안 쓴 ID도 보여 줌")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_coverage)

    p = sub.add_parser("mcp", help="AI(Claude Code·Codex)가 앱을 직접 QA하는 MCP 서버 (stdio). install --claude|--codex로 등록")
    p.add_argument("action", nargs="?", choices=["serve", "install"], default="serve")
    p.add_argument("--claude", action="store_true", help="install: 작업공간 .mcp.json에 등록 (Claude Code)")
    p.add_argument("--codex", action="store_true", help="install: codex mcp add (없으면 config.toml 내용 출력)")
    p.set_defaults(func=cmd_mcp)

    p = sub.add_parser("ui", help="결과 보기 + 시뮬레이터 라이브 화면 (로컬 웹 127.0.0.1, 브라우저로 엶)")
    p.add_argument("--port", type=int, default=0, help="포트 (기본: 빈 포트)")
    p.add_argument("--no-open", action="store_true", help="브라우저를 열지 않고 주소만 출력")
    p.set_defaults(func=cmd_ui)

    p = sub.add_parser("show", help="시뮬레이터 화면(Device Hub / Simulator)을 띄우고 앱 실행 — 로그인 등 직접 만질 때")
    p.add_argument("--no-launch", action="store_true", help="앱은 실행하지 않음")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("update", help="도구를 최신 버전으로 받기 (설치 폴더 git fast-forward)")
    p.add_argument("--check", action="store_true", help="새 버전이 있는지만 확인")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("doctor", help="환경 점검")
    p.add_argument("--system", action="store_true", help="작업공간 없이 이 맥의 도구만 (Xcode·xcodegen·AI·안드로이드)")
    p.add_argument("--json", action="store_true", help="--system 결과를 JSON으로 (맥 앱이 읽음)")
    p.add_argument("--timeout", type=int, default=DOCTOR_TIMEOUT,
                   help=f"바깥 도구(xcodebuild·simctl 등) 하나를 기다리는 최대 초 (기본 {DOCTOR_TIMEOUT}) — 넘기면 그 항목만 '확인 못 함'")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("build-app", help="대상 앱 빌드 + 설치 + 권한 허용")
    p.set_defaults(func=cmd_build_app)

    p = sub.add_parser("swiftui-ids", help="SwiftUI ID 삽입 도구: 목록 보기 / 손으로 삽입 / 복원")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="삽입될 ID 목록 (소스 수정 없음)")
    g.add_argument("--insert", action="store_true", help="워크트리 소스에 삽입한 채 둔다 (diff 확인용. 끝나면 --restore)")
    g.add_argument("--restore", action="store_true", help="삽입을 되돌린다")
    p.set_defaults(func=cmd_swiftui_ids)

    p = sub.add_parser("sync", help="앱 변경 반영: 재빌드·설치 + ID 재생성 + 테스트 코드 컴파일 확인")
    p.add_argument("--rebuild", action="store_true", help="변경이 없어도 앱 재빌드")
    p.add_argument("--skip-build", action="store_true", help="앱 빌드 생략 (ID 재생성·컴파일 확인만)")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("worktree-update", help="QA 워크트리를 따라갈 브랜치(기본 develop)의 최신 커밋으로 (merge, push 안 함)")
    p.add_argument("--from", dest="base", help="따라갈 브랜치 (기본: qakit.yml worktree.base, 없으면 develop)")
    p.add_argument("--check", action="store_true", help="뒤처졌는지만 확인")
    p.set_defaults(func=cmd_worktree_update)

    p = sub.add_parser("gen-ids", help="앱 소스에서 ID 상수(QAIDs.swift) 생성")
    p.add_argument("--verify", action="store_true", help="저장된 화면 덤프와 비교")
    p.set_defaults(func=cmd_gen_ids)

    p = sub.add_parser("dump-ui", help="화면 구조를 텍스트로 저장")
    p.add_argument("--attach", action="store_true", help="앱을 새로 띄우지 않고 지금 화면을 덤프")
    p.add_argument("--settle", type=float, default=3, help="덤프 전 대기 초 (기본 3)")
    p.add_argument("--wait-id", help="이 ID가 나타날 때까지 기다린 뒤 덤프")
    p.add_argument("--print", action="store_true", help="덤프 내용을 바로 출력")
    p.set_defaults(func=cmd_dump_ui)

    p = sub.add_parser("test", help="UI 테스트 실행")
    p.add_argument("filters", nargs="*", help="예) LoginFlowTests 또는 LoginFlowTests/test_ensureLoggedIn")
    p.add_argument("--reset", action="store_true", help="실행 전 앱 재설치 + 키체인 초기화 (로그아웃 상태)")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("run", help="시나리오 파일(.qa.yml) 실행 — Swift 테스트 없이")
    p.add_argument("scenario", nargs="*",
                   help="scenarios/<이름>.qa.yml의 이름·파일 경로, 여러 개 가능. 패턴은 따옴표로: 'home-*'. 비우면 --tag로 고름")
    p.add_argument("--tag", action="append", metavar="태그", help="이 태그가 있는 시나리오만 (여러 번 가능, 하나라도 있으면)")
    p.add_argument("--exclude-tag", action="append", metavar="태그", help="이 태그가 있는 시나리오는 뺌 (--tag보다 우선)")
    p.add_argument("--junit", metavar="파일", help="JUnit XML 보고서를 이 경로에 씀 (CI용)")
    pre = p.add_mutually_exclusive_group()
    pre.add_argument("--precheck", action="store_true", help="하나만 돌릴 때도 qakit.yml의 precheck: 단계로 먼저 확인")
    pre.add_argument("--no-precheck", action="store_true", help="여러 개 실행 전 사전 확인(precheck:)을 건너뜀")
    p.add_argument("--reset", action="store_true", help="실행 전 앱 재설치 + 키체인 초기화")
    stop = p.add_mutually_exclusive_group()
    stop.add_argument("--fail-fast", action="store_true", help="여러 개 실행: 첫 실패에서 멈춤")
    stop.add_argument("--keep-going", action="store_true",
                      help="여러 개 실행: 같은 원인으로 연속 실패해도 끝까지 (기본은 2번 연속이면 멈춤)")
    p.add_argument("--no-check", action="store_true", help="ID 정적 검사 실패해도 실행")
    p.add_argument("--bench", metavar="시간",
                   help="시나리오가 끝난 화면 그대로 이 시간 동안 CPU·메모리 + 함수별 CPU(sample) 기록. "
                        "단위 필수: 30s·5m·1h·1h30m (30초·5분·1시간도 됨)")
    p.add_argument("--no-profile", action="store_true", help="--bench에서 함수별 CPU(sample) 없이 CPU·메모리만 기록")
    p.add_argument("--var", action="append", metavar="KEY=VALUE",
                   help='시나리오 변수 지정 (vars 기본값을 덮어씀, 여러 번 가능). 예) --var ship="ULTRA FOREST"')
    g = p.add_mutually_exclusive_group()
    g.add_argument("--serve", action="store_true", help="상주 실행기로 실행 (없으면 띄움). 떠 있으면 지정하지 않아도 씀")
    g.add_argument("--no-serve", action="store_true", help="상주 실행기가 떠 있어도 xcodebuild로 실행 (상주 실행기는 멈춤)")
    p.add_argument("--timeout", type=int, default=600, help="상주 실행기로 돌 때 이 시간(초) 안에 안 끝나면 멈춤 (기본 600)")
    p.add_argument("--reuse-app", action="store_true",
                   help="앱이 이미 시작 화면(시나리오의 start: 조건)이면 다시 켜지 않음 (= launch: reuse). --reset이면 무시")
    p.add_argument("--video", choices=["fail", "always", "off"], default="fail",
                   help="화면 녹화: fail=실패하면 마지막 30초를 failure.mp4로 (기본), always=통과해도 video.mp4, off=안 함. 시뮬레이터만")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("check", help="시나리오 형식·ID 정적 검사 (실행 없이)")
    p.add_argument("scenarios", nargs="*")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("save", help="결과물 목록·해시 기록(qa.lock.json) + 보관소 복사")
    p.add_argument("-m", "--message", help="저장 메모")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("restore", help="AI 없이 복구 (생성물 재생성·앱 설치·해시 확인)")
    p.add_argument("--from", dest="from_name", help="보관소(~/.qakit/archive)의 작업공간 이름에서 복사")
    p.add_argument("--to", help="--from으로 복사할 위치 (기본: ./QA)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("readme", help="QA 폴더 README.md의 QA 목록을 지금 상태로 갱신")
    p.set_defaults(func=cmd_readme)

    p = sub.add_parser("history", help="실행 기록 보기")
    p.add_argument("-n", type=int, default=20)
    p.add_argument("--test", help="이름에 이 글자가 들어간 것만")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("summarize", help="실패 원인 요약")
    p.add_argument("xcresult", nargs="?", help="xcresult 또는 실행 폴더 (기본: 마지막 실행)")
    p.set_defaults(func=cmd_summarize)

    p = sub.add_parser("android", help="안드로이드: SDK·에뮬레이터 설치(setup), 점검, 부팅, 지금 화면 파악(screen·dump), 로그(logs)")
    asub = p.add_subparsers(dest="android_command", required=True)
    a = asub.add_parser("setup", help="JDK 17·SDK·에뮬레이터·AVD 설치 (Android Studio 불필요)")
    a.add_argument("--avd", help=f"만들 AVD 이름 (기본 {ANDROID_AVD})")
    a.add_argument("--image", help=f"시스템 이미지 (기본 {ANDROID_IMAGE})")
    a.add_argument("--device-profile", default="pixel_7", help="기기 모양 (기본 pixel_7, avdmanager list device)")
    a.set_defaults(func=cmd_android_setup)
    a = asub.add_parser("doctor", help="안드로이드 도구·AVD·연결된 기기 점검")
    a.add_argument("--timeout", type=int, default=DOCTOR_TIMEOUT,
                   help=f"바깥 도구(adb·emulator 등) 하나를 기다리는 최대 초 (기본 {DOCTOR_TIMEOUT}) — 넘기면 그 항목만 '확인 못 함'")
    a.set_defaults(func=cmd_android_doctor)
    a = asub.add_parser("boot", help="에뮬레이터 띄우기 (부팅 완료까지 기다림)")
    a.add_argument("--avd", help=f"AVD 이름 (기본 {ANDROID_AVD})")
    a.add_argument("--headless", action="store_true", help="창 없이 (CI)")
    a.add_argument("--orientation", "-o", choices=["landscape", "portrait", "auto"],
                   help="부팅 뒤 화면 방향 고정 (landscape: 가로, portrait: 세로, auto: 기기 회전 따름)")
    a.add_argument("--landscape", dest="orientation", action="store_const", const="landscape", help="= --orientation landscape")
    a.set_defaults(func=cmd_android_boot)
    a = asub.add_parser("rotate", help="실행 중인 에뮬레이터 화면 방향 바꾸기")
    a.add_argument("orientation", choices=["landscape", "portrait", "auto"])
    a.add_argument("--avd", help="여러 기기 중 이 AVD의 에뮬레이터")
    a.set_defaults(func=cmd_android_rotate)
    a = asub.add_parser("screen", help="지금 화면의 앱·Activity·Fragment (빠름)")
    a.add_argument("--avd", help="여러 기기 중 이 AVD의 에뮬레이터")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_android_screen)
    a = asub.add_parser("dump", help="지금 화면 구조를 텍스트로 (작업공간 없이, 앞에 있는 앱 기준)")
    a.add_argument("--avd", help="여러 기기 중 이 AVD의 에뮬레이터")
    a.add_argument("--package", help="이 앱 기준으로 (기본: 앞에 있는 앱)")
    a.add_argument("--settle", type=float, default=0, help="덤프 전 대기 초")
    a.add_argument("-o", "--out", help="파일로 저장")
    a.add_argument("--print", action="store_true", help="--out과 함께 화면에도 출력")
    a.add_argument("--json", action="store_true", help="요소 목록을 JSON으로")
    a.set_defaults(func=cmd_android_dump)
    a = asub.add_parser("logs", help="앱 로그 (uid로 거름) · 크래시·ANR · 네트워크(OkHttp) 요약")
    a.add_argument("--avd", help="여러 기기 중 이 AVD의 에뮬레이터")
    a.add_argument("--package", help="이 앱 (기본: 작업공간 packageName, 없으면 앞에 있는 앱)")
    a.add_argument("--since", help="최근 이만큼 (30s, 10m, 2h)")
    a.add_argument("-n", "--lines", type=int, default=300, help="--since 없을 때 마지막 몇 줄 (기본 300)")
    a.add_argument("-f", "--follow", action="store_true", help="실시간으로 계속 보기")
    a.add_argument("--level", choices=list("VDIWEF"), help="이 수준 이상만 (W: 경고·오류)")
    a.add_argument("--grep", help="이 글자(정규식)가 들어간 줄만")
    a.add_argument("--crash", action="store_true", help="크래시·ANR만 (난독화 빌드는 mapping.txt로 복원)")
    a.add_argument("--net", action="store_true", help="네트워크(OkHttp 로그) 줄만 + 실패한 요청")
    a.add_argument("--json", action="store_true", help="요약을 JSON으로")
    a.set_defaults(func=cmd_android_logs)
    a = asub.add_parser("frames", help="(qakit ui 내부용) 실행기 화면 프레임 받기")
    a.add_argument("--port", type=int, required=True)
    a.set_defaults(func=cmd_android_frames)

    # --build는 명령 앞뒤 어디에 써도 되게 (qakit run x --build release)
    for sp in sub.choices.values():
        sp.add_argument("--build", choices=["debug", "release"], default=argparse.SUPPRESS,
                        help="빌드 종류 (기본 debug)")
        sp.add_argument("--device", nargs="?", const="select", default=argparse.SUPPRESS, metavar="기기",
                        help=device_help)
    asub.choices["logs"].add_argument("--build", choices=["debug", "release"], default=argparse.SUPPRESS,
                                      help="빌드 종류 (기본 debug) — 어느 packageName의 로그인지")

    args = parser.parse_args()
    args.workspace = getattr(args, "workspace", None)
    global SECRETS_OVERRIDE, APP_OVERRIDE, BUILD_MODE, DEVICE_ARG
    BUILD_MODE = args.build
    DEVICE_ARG = args.device
    SECRETS_OVERRIDE = args.secrets
    APP_OVERRIDE = args.app
    args.func(args)


if __name__ == "__main__":
    main()
