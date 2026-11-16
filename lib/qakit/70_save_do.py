# qakit — 저장·복구·기록·install-skill·serve·do
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 저장 · 복구 · 기록 ───────────────────────────────

def user_files(root):
    for entry in USER_FILES:
        p = root / entry
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.name != ".DS_Store":
                    yield f


def file_hash(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def cmd_save(args):
    """결과물(시나리오·Swift·노트·설정)의 목록과 해시를 qa.lock.json에 남기고 보관소에 복사한다."""
    ws = find_workspace(args.workspace)
    update_readme(ws, quiet=False)
    files = {str(f.relative_to(ws.root)): file_hash(f) for f in user_files(ws.root)}
    state = app_state(ws)
    lock = {
        "name": ws.name,
        "savedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "message": args.message or "",
        "kit": kit_version(),
        "app": {k: state.get(k) for k in ("branch", "commit") if k in state},
        "files": files,
    }
    (ws.root / "qa.lock.json").write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    dest_root = ARCHIVE_DIR / ws.name
    snap = dest_root / lock["savedAt"].replace(":", "")
    for target in (snap, dest_root / "latest"):
        if target.exists():
            shutil.rmtree(target)
        for rel in list(files) + ["qa.lock.json"]:
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ws.root / rel, target / rel)
    snaps = sorted(p for p in dest_root.iterdir() if p.is_dir() and p.name != "latest")
    for old in snaps[:-20]:
        shutil.rmtree(old)
    ok(f"저장: 파일 {len(files)}개 → qa.lock.json, 보관소 {dest_root}/latest")
    tracked = git(ws.root, "ls-files", "--error-unmatch", "qa.lock.json")
    if tracked is not None:
        info("ℹ️  이 폴더는 git으로 관리 중입니다. 커밋은 평소처럼: git add QA && git commit")


def cmd_restore(args):
    """AI 없이 복구: (보관소에서 파일 복사) → 생성물 다시 만들기 → 해시 확인 → 앱 설치 확인."""
    if args.from_name:
        src = ARCHIVE_DIR / args.from_name / "latest"
        if not src.exists():
            names = ", ".join(p.name for p in ARCHIVE_DIR.iterdir()) if ARCHIVE_DIR.exists() else "(없음)"
            fail(f"보관소에 '{args.from_name}'이(가) 없습니다.", f"보관소 목록: {names}")
        dest = Path(args.to).expanduser().resolve() if args.to else Path.cwd() / "QA"
        if (dest / "qakit.yml").exists() and not args.force:
            fail(f"이미 작업공간이 있습니다: {dest}", "덮어쓰려면 --force")
        for f in src.rglob("*"):
            if f.is_file():
                (dest / f.relative_to(src)).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest / f.relative_to(src))
        ok(f"보관소 → {dest}")
        args.workspace = str(dest)
    ws = find_workspace(args.workspace)
    lock_path = ws.root / "qa.lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        missing, changed = [], []
        for rel, h in lock.get("files", {}).items():
            f = ws.root / rel
            if not f.exists():
                missing.append(rel)
            elif file_hash(f) != h:
                changed.append(rel)
        if missing:
            warn(f"저장 기록에 있는데 없는 파일 {len(missing)}개: " + ", ".join(missing[:10]))
        if changed:
            info(f"ℹ️  저장 이후 바뀐 파일 {len(changed)}개: " + ", ".join(changed[:10]))
        if not missing:
            ok(f"결과물 {len(lock.get('files', {}))}개 확인 (저장: {lock.get('savedAt')}, 앱 {lock.get('app', {}).get('branch')}@{lock.get('app', {}).get('commit')})")
    else:
        warn("qa.lock.json이 없습니다 (qakit save로 만든 적 없음). 있는 파일로 복구합니다.")
    if has_swift_runner(ws):
        refresh_runner_template(ws)
    generate_ids(ws, quiet=False)
    udid = ensure_booted(ws)
    changed_app, why, _ = app_changed(ws)
    if changed_app or not app_installed(udid, ws.bundle_id):
        info(f"앱 빌드·설치: {why or '설치 안 됨'}")
        cmd_build_app_ws(ws)
    if not ws.secrets_path.exists() and (ws.root / "secrets.example.txt").exists():
        warn(f"secrets.txt가 없습니다 (보안상 저장·복구하지 않음). {ws.secrets_path}에 다시 넣으세요.")
    update_readme(ws)
    scen = sorted((ws.root / "scenarios").glob("*.qa.yml"))
    ok("복구 완료 — AI 없이 바로 실행할 수 있습니다:")
    for p in scen[:10]:
        info(f"   qakit run {p.name.replace('.qa.yml', '')}")
    if has_swift_runner(ws):
        info("   qakit test   (Swift 테스트)")


def cmd_history(args):
    ws = find_workspace(args.workspace)
    f = ws.root / "history.jsonl"
    if not f.exists():
        fail("실행 기록이 없습니다.", "qakit run / qakit test를 실행하면 쌓입니다.")
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.test:
        rows = [r for r in rows if args.test in r.get("test", "")]
    for r in rows[-args.n:]:
        mark = {"Passed": "✅", "Failed": "❌", "Skipped": "⏭"}.get(r.get("result"), "•")
        app = r.get("app", {})
        print(f"{r.get('at','')}  {mark} {r.get('test',''):<45} {r.get('seconds',0):>6}s  "
              f"앱 {app.get('branch','-')}@{app.get('commit','-')}  [{r.get('kind')}]")


# ─────────────────────────────── 명령: install-skill ───────────────────────────────

OLD_SKILL_NAMES = ("ios-qa-kit",)   # 레포 이름이 ios-qa-kit이던 때의 스킬 이름 (v0.38 이하)


def skill_links():
    skill = KIT_DIR / "skills" / "qa-kit"
    return [
        (Path.home() / ".claude" / "skills" / "qa-kit", skill, "Claude Code 스킬"),
        (Path.home() / ".agents" / "skills" / "qa-kit", skill, "Codex 스킬"),
        (Path.home() / ".local" / "bin" / "qakit", KIT_DIR / "bin" / "qakit", "qakit 명령"),
    ]


def old_skill_links():
    """이 도구의 옛 스킬 폴더(…/skills/ios-qa-kit)를 가리키는 링크. 이름 변경 뒤에는 대개 끊어진 링크다."""
    found = []
    for old in OLD_SKILL_NAMES:
        for base, label in ((Path.home() / ".claude" / "skills", "Claude Code 스킬"),
                            (Path.home() / ".agents" / "skills", "Codex 스킬")):
            link = base / old
            if not link.is_symlink():
                continue
            dest = Path(os.readlink(link))
            if dest.name == old and dest.parent.name == "skills":   # 다른 도구가 같은 이름을 쓰면 두고 본다
                found.append((link, label))
    return found


def migrate_old_skill_links():
    """옛 이름(ios-qa-kit) 스킬 링크를 지우고 새 이름(qa-kit) 링크를 만든다. 옮긴 것이 있으면 True."""
    found = old_skill_links()
    for link, label in found:
        link.unlink()
        new = link.parent / "qa-kit"
        if not new.exists() and not new.is_symlink():
            new.symlink_to(KIT_DIR / "skills" / "qa-kit")
        ok(f"옮김: {label} {link} → {new}  (이제 /qa-kit, $qa-kit으로 부릅니다)")
    return bool(found)


def cmd_install_skill(args):
    """스킬을 Claude Code·Codex에, qakit을 PATH에 심볼릭 링크로 설치 (도구 레포 수정이 바로 반영됨)."""
    if args.uninstall:
        for link, label in old_skill_links():
            link.unlink()
            ok(f"제거: {label} ({link})")
    else:
        migrate_old_skill_links()
    for link, target, label in skill_links():
        if args.uninstall:
            if link.is_symlink():
                link.unlink()
                ok(f"제거: {label} ({link})")
            continue
        if link.is_symlink():
            if Path(os.path.realpath(link)) == target.resolve():
                ok(f"이미 설치됨: {label} → {link}")
                continue
            link.unlink()
        elif link.exists():
            warn(f"건너뜀: {link}가 이미 있습니다 (링크 아님). 직접 확인하세요.")
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        ok(f"설치: {label} → {link}")
    if not args.uninstall and str(Path.home() / ".local" / "bin") not in os.environ.get("PATH", ""):
        warn("~/.local/bin이 PATH에 없습니다. 셸 설정에 추가하세요: export PATH=\"$HOME/.local/bin:$PATH\"")


# ─────────────────────────────── 명령: serve · do ───────────────────────────────

def _serve_udid(ws):
    return ws.device["udid"] if ws.device else ensure_booted(ws)


def cmd_serve(args):
    ws = find_workspace(args.workspace)
    udid = _serve_udid(ws)
    st = serve_load(udid)
    if args.status:
        if st and serve_alive(st):
            stale = st.get("runnerHash") != scenario_runner_source_hash()
            where = f"실기기 {ws.device['name']} ({'USB' if st.get('usbmux') else 'Wi-Fi'})" if ws.device else ws.simulator
            ok(f"상주 실행기 실행 중: {where} · 포트 {st['port']} · {st['started']} 시작 · {st['workspace']}"
               + (" (실행기 코드가 바뀜 → 다음 명령 때 다시 띄움)" if stale else ""))
        else:
            info("상주 실행기 없음" + (" (기록만 남아 있어 정리함)" if st else ""))
            if st:
                serve_stop(udid, quiet=True)
        return
    if args.stop:
        if serve_stop(udid):
            ok("상주 실행기를 멈췄습니다")
        else:
            info("상주 실행기 없음")
        return
    with sim_lock(ws, "qakit serve"):
        if st and serve_alive(st) and st.get("workspace") == str(ws.root) \
                and st.get("runnerHash") == scenario_runner_source_hash():
            ok(f"이미 실행 중입니다 (포트 {st['port']}). 멈추려면 qakit serve --stop")
            return
        serve_stop(udid, quiet=True)
        serve_start(ws, udid, idle=args.idle, launch=not args.no_launch)
    info("이제 qakit do '<단계>' 로 바로 실행합니다. 예) qakit do 'tap: <ID>'  ·  qakit do dump")


SERVE_COMMANDS = {"dump": "/dump", "launch": "/launch", "ping": "/ping", "reset": "/reset"}


def taps_path(ws, trim=False):
    """실행기가 누르는 자리를 한 줄씩 남기는 파일. 커지면(256KB) 비운다 — UI는 읽은 위치가 줄면 처음부터 읽는다."""
    p = ws.root / ".qakit" / "taps.jsonl"
    if trim:
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > 256 * 1024:
            p.write_text("", encoding="utf-8")
    return p


def do_log_path(ws):
    return ws.root / ".qakit" / "do-steps.jsonl"


def do_log_read(ws):
    """마지막 qakit do launch 이후 통과한 단계 (launch 기록이 없으면 처음부터). (단계 글자 목록, launch부터인지)"""
    steps, from_launch = [], False
    try:
        lines = do_log_path(ws).read_text(encoding="utf-8").splitlines()
    except OSError:
        return steps, from_launch
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") == "launch":
            steps, from_launch = [], True
        elif row.get("step"):
            steps.append(row["step"])
    return steps, from_launch


def touch_mark(ws, kind, x, y):
    """직접 터치 커서 기록 (taps.jsonl, 화면 대비 0~1 좌표 그대로 — sw=sh=1, 크기 0)"""
    row = {"t": round(time.time(), 3), "kind": kind, "x": round(x, 4), "y": round(y, 4), "w": 0, "h": 0, "sw": 1, "sh": 1}
    with contextlib.suppress(OSError):
        with open(taps_path(ws), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


DO_LOG_KEEP = 10   # launch로 비우기 전 기록을 몇 개까지 남기나


def do_log_prev_dir(ws):
    return ws.root / ".qakit" / "do-steps-prev"


def do_log_backup(ws):
    """지금 기록에 단계가 있으면 .qakit/do-steps-prev/<시각>.jsonl로 남긴다 (오래된 것부터 지워 DO_LOG_KEEP개). → 이름 또는 None"""
    steps, _ = do_log_read(ws)
    if not steps:
        return None
    d = do_log_prev_dir(ws)
    d.mkdir(parents=True, exist_ok=True)
    name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    n = 1
    while (d / f"{name}.jsonl").exists():
        n += 1
        name = f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}-{n}"
    shutil.copyfile(do_log_path(ws), d / f"{name}.jsonl")
    for old in sorted(d.glob("*.jsonl"))[:-DO_LOG_KEEP]:
        old.unlink(missing_ok=True)
    return name


def do_log_prev(ws):
    """남겨 둔 이전 기록 (새 것부터): [{name, steps: [단계], count}]"""
    out = []
    for f in sorted(do_log_prev_dir(ws).glob("*.jsonl"), reverse=True):
        steps = []
        with contextlib.suppress(OSError):
            for line in f.read_text(encoding="utf-8").splitlines():
                with contextlib.suppress(ValueError):
                    row = json.loads(line)
                    if row.get("event") == "launch":
                        steps = []
                    elif row.get("step"):
                        steps.append(row["step"])
        out.append({"name": f.stem, "steps": steps, "count": len(steps)})
    return out


def do_log_restore(ws, name):
    """이전 기록 하나를 지금 기록으로 (지금 기록에 단계가 있으면 그것도 이전 기록으로 남김). → (단계 목록, 오류)"""
    src = do_log_prev_dir(ws) / f"{name}.jsonl"
    if not re.fullmatch(r"[0-9_-]+", name or "") or not src.is_file():
        return None, f"이전 기록이 없습니다: {name}"
    data = src.read_bytes()
    src.unlink()
    do_log_backup(ws)
    do_log_path(ws).write_bytes(data)
    return do_log_read(ws)[0], None


def do_log_write(ws, row, reset=False):
    f = do_log_path(ws)
    f.parent.mkdir(parents=True, exist_ok=True)
    if reset:
        do_log_backup(ws)   # 앱 다시 켜기(launch)가 기록을 비우기 전에 남긴다
    with open(f, "w" if reset else "a", encoding="utf-8") as out:
        out.write(json.dumps(dict(row, at=datetime.datetime.now().isoformat(timespec="seconds")), ensure_ascii=False) + "\n")


def merge_tap_wait(steps):
    """[tap, wait] 이어진 두 단계를 탭의 expect 하나로 합친다 (탭이 무시되면 그 자리에서 실패).
    합칠 수 있는 것: tap(+timeout)만 있는 단계 바로 다음, wait 하나만 있는 단계. (합친 목록, 합친 수)"""
    out, merged, i = [], 0, 0
    while i < len(steps):
        a = steps[i]
        b = steps[i + 1] if i + 1 < len(steps) else None
        if (isinstance(a, dict) and "tap" in a and set(a) <= {"tap", "timeout"}
                and isinstance(b, dict) and set(b) == {"wait"}):
            w = b["wait"]
            target, timeout = (w.get("for"), w.get("timeout")) if isinstance(w, dict) and "for" in w else (w, None)
            m = dict(a, expect={"visible": target})
            if timeout is not None:
                m["expect-timeout"] = timeout
            out.append(m)
            merged += 1
            i += 2
            continue
        out.append(a)
        i += 1
    return out, merged


def mergeable_tap_waits(node):
    """시나리오(펼치기 전)의 steps·then·else·repeat 안에서 [tap, wait]로 합칠 수 있는 곳 수 (qakit check 안내용)."""
    n = 0
    if isinstance(node, list):
        n += merge_tap_wait(node)[1]
        for x in node:
            n += mergeable_tap_waits(x)
    elif isinstance(node, dict):
        for k in ("steps", "then", "else"):
            if isinstance(node.get(k), list):
                n += mergeable_tap_waits(node[k])
        if isinstance(node.get("repeat"), dict):
            n += mergeable_tap_waits(node["repeat"].get("steps"))
    return n


def flow_text(value):
    """단계 값을 YAML 한 줄({ … } 형식)로."""
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k}: {flow_text(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[ " + ", ".join(flow_text(v) for v in value) + " ]"
    text = str(value).lower() if isinstance(value, bool) else str(value)
    if (text == "" or text != text.strip() or text[0] in "{[\"'&*!|>%@`#-"
            or any(c in text for c in ",{}[]#") or ": " in text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def do_restore(ws, name=None):
    """qakit do restore [이름]: 앱을 다시 켜며(launch) 비운 이전 기록 보기·되살리기"""
    prev = do_log_prev(ws)
    if not name:
        if not prev:
            info("남겨 둔 이전 기록이 없습니다 (launch가 단계가 있는 기록을 비울 때 남깁니다).")
            return
        info(f"이전 기록 {len(prev)}개 (새 것부터) — 되살리기: qakit do restore <이름>")
        for p in prev:
            print(f"  {p['name']}  단계 {p['count']}개" + (f"  · {p['steps'][0][:60]}" if p["steps"] else ""))
        return
    steps, err = do_log_restore(ws, name)
    if err:
        fail(err, "qakit do restore 로 목록 보기")
    ok(f"이전 기록을 되살렸습니다: 단계 {len(steps)}개 (원래 기록은 이전 기록으로 남김)")


def do_steps(ws):
    """qakit do steps: 기록된 단계 보기."""
    steps, from_launch = do_log_read(ws)
    if not steps:
        info("기록된 단계가 없습니다. qakit do launch 뒤 단계를 실행하면 통과한 단계가 쌓입니다.")
        return
    info(("qakit do launch 이후" if from_launch else "기록 처음부터") + f" 통과한 단계 {len(steps)}개:")
    for i, st in enumerate(steps, 1):
        print(f"  {i:2}. {st}")
    print("   → 시나리오로: qakit do save <이름>")


SCENARIO_NAME_RE = re.compile(r"[A-Za-z0-9가-힣_.-]+")


def build_scenario_text(ws, name, title=None, description=None, tags=None, start=None, recorded=None):
    """qakit do 기록(또는 recorded=(단계 목록, launch부터인지) — AI 세션) → 시나리오 글. 탭 바로 다음 기다림은 탭의 expect로 합친다.
    (글, 합친 수, 단계 수, launch부터인지). 기록이 없으면 ValueError."""
    steps, from_launch = recorded if recorded is not None else do_log_read(ws)
    if not steps:
        raise ValueError("기록된 단계가 없습니다 (앱을 다시 켠 뒤 통과한 단계만 기록됩니다)")
    parsed = []
    for st in steps:
        try:
            v = scenario_tools.parse_yaml(st)
            parsed.append(v[0] if isinstance(v, list) and len(v) == 1 else v)
        except Exception:  # noqa: BLE001 — 기록된 글자를 그대로 쓴다
            parsed.append(st)
    body, merged, i = [], 0, 0
    if start:
        body.append(f"  - use: {start}")
    while i < len(steps):
        pair = merge_tap_wait(parsed[i:i + 2])
        if len(parsed) > i + 1 and pair[1] == 1:
            m = pair[0][0]
            tap_text = steps[i].strip()
            body.append(f"  - {tap_text}" if not tap_text.startswith("{") else f"  - tap: {flow_text(m['tap'])}")
            if tap_text.startswith("{") and "timeout" in m:
                body.append(f"    timeout: {m['timeout']}")
            body.append(f"    expect: {flow_text(m['expect'])}")
            if "expect-timeout" in m:
                body.append(f"    expect-timeout: {m['expect-timeout']}")
            merged += 1
            i += 2
            continue
        first, *rest = steps[i].splitlines()
        body.append(f"  - {first}")
        body += [f"    {line}" for line in rest]
        i += 1
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    head = [f"name: {flow_text(title) if title else name}"]
    head += [f"# {line}" for line in (description or "").splitlines() if line.strip()] or [
        f"# ({'AI QA 세션에서 통과한 단계로' if recorded is not None else 'qakit do 기록에서'} 만든 초안, {stamp}) 무엇을 확인하는지 1~2줄로 바꿔 쓰고, 판정(expect)을 더한다."]
    if tags:
        head.append("tags: [" + ", ".join(flow_text(t) for t in tags) + "]")
    return "\n".join(head + ["steps:"] + body) + "\n", merged, len(steps) + (1 if start else 0) - merged, from_launch


def do_save(ws, name, force=False, title=None, tags=None, start=None):
    """qakit do save <이름>: 기록된 단계로 scenarios/<이름>.qa.yml 초안을 쓰고 바로 검사한다."""
    if not SCENARIO_NAME_RE.fullmatch(name or ""):
        fail(f"시나리오 이름으로 쓸 수 없습니다: {name!r}", "영문·숫자·한글·-·_ 만. 예) qakit do save home-12-banner")
    if start and not (ws.root / "steps" / f"{start}.qa.yml").exists():
        fail(f"공통 단계가 없습니다: steps/{start}.qa.yml")
    target = ws.root / "scenarios" / f"{name}.qa.yml"
    if target.exists() and not force:
        fail(f"이미 있습니다: {target}", "덮어쓰려면 --force")
    try:
        text, merged, nsteps, from_launch = build_scenario_text(ws, name, title=title, tags=tags, start=start)
    except ValueError as e:
        fail(str(e), "qakit do launch 뒤 단계를 실행하세요")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    ok(f"시나리오 초안: {target} (단계 {nsteps}개"
       + (f", 탭 다음 기다림 {merged}곳을 탭의 expect로 합침" if merged else "") + ")")
    if not from_launch:
        warn("qakit do launch 뒤의 기록이 아닙니다. 시나리오는 앱을 새로 켜고 시작하므로 앞부분(진입 단계)이 빠졌을 수 있습니다")
    load_checked_scenario(ws, str(target), strict=False)
    ok("형식·ID 검사 통과 → 다듬은 뒤 qakit run " + name)


