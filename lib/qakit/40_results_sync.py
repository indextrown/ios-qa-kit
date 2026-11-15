# qakit — summarize·앱 상태·QA 워크트리 최신화·gen-ids
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 명령: summarize ───────────────────────────────

def cmd_summarize(args):
    ws = find_workspace(args.workspace)
    target = Path(args.xcresult) if args.xcresult else ws.results_dir / "latest"
    if target.is_dir() and (target / SERVE_SUMMARY).exists() and not (target / "result.xcresult").exists():
        # 상주 실행기로 돈 run: xcresult 대신 실행 때 남긴 요약
        print((target / SERVE_SUMMARY).read_text(encoding="utf-8"), end="")
        print(f"결과 폴더: {target.resolve()}")
        return
    if (target / "result.xcresult").exists():   # 실행 폴더를 준 경우
        path = (target / "result.xcresult").resolve()
    else:
        path = target.resolve() if args.xcresult else (ws.results_dir / "latest.xcresult").resolve()
    if not path.exists():
        fail(f"결과 파일 없음: {path}", "qakit test를 먼저 실행하세요.")
    print(summarize(path, masker(ws.secrets())))


def summarize(xcresult, mask):
    if not Path(xcresult).exists():
        return "(결과 파일 없음 — 빌드 단계에서 실패했을 수 있음)"
    tree = json.loads(run(["xcrun", "xcresulttool", "get", "test-results", "tests",
                           "--path", str(xcresult)]).stdout)
    cases = []

    def walk(node):
        if node.get("nodeType") == "Test Case":
            cases.append(node)
        for c in node.get("children", []):
            walk(c)
    for n in tree.get("testNodes", []):
        walk(n)

    passed = [c for c in cases if c.get("result") == "Passed"]
    failed = [c for c in cases if c.get("result") == "Failed"]
    out = [f"── 결과: 통과 {len(passed)} / 실패 {len(failed)} / 전체 {len(cases)}"]
    if not failed:
        return "\n".join(out)

    attachments = export_attachments(xcresult)
    for c in failed:
        test_id = c.get("nodeIdentifier", c.get("name"))
        out.append(f"\n❌ {test_id}")
        reason = ""
        for child in c.get("children", []):
            if child.get("nodeType") == "Failure Message":
                reason = child.get("name") or ""
                out.append(f"   원인: {reason}")
        steps = last_steps(xcresult, test_id)
        if steps:
            out.append("   마지막 단계:")
            out += [f"     - {s}" for s in steps]
        tree_text = attachments.get(test_id, {}).get("qakit-ui-tree")
        out += suggestion_lines(reason, tree_text)
        if tree_text:
            out.append("   실패 시점 화면 구조 (ID/라벨 있는 요소):")
            compact = compact_tree(tree_text)
            if len(compact) > 60:  # 팝업 등 최상단 요소는 보통 끝에 있으므로 뒤쪽을 남긴다
                compact = ["...(앞 %d줄 생략)" % (len(compact) - 60)] + compact[-60:]
            out += ["     " + l for l in compact]
        shot = attachments.get(test_id, {}).get("qakit-screenshot-path")
        if shot:
            out.append(f"   스크린샷: {shot}")
    return mask("\n".join(out))


def export_attachments(xcresult):
    dest = Path(xcresult).parent / (Path(xcresult).stem + "-attachments")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    r = run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(xcresult),
             "--output-path", str(dest)], check=False)
    manifest = dest / "manifest.json"
    result = {}
    if r.returncode != 0 or not manifest.exists():
        return result
    for entry in json.loads(manifest.read_text()):
        tid = entry.get("testIdentifier")
        for a in entry.get("attachments", []):
            name = a.get("suggestedHumanReadableName", "")
            f = dest / a.get("exportedFileName", "")
            if name.startswith("qakit-ui-tree"):
                result.setdefault(tid, {})["qakit-ui-tree"] = f.read_text(encoding="utf-8", errors="replace")
            elif name.startswith("qakit-screenshot"):
                result.setdefault(tid, {})["qakit-screenshot-path"] = str(f)
    return result


def last_steps(xcresult, test_id, limit=8):
    r = run(["xcrun", "xcresulttool", "get", "test-results", "activities", "--path", str(xcresult),
             "--test-id", test_id, "--compact"], check=False)
    if r.returncode != 0:
        return []
    titles = []

    def walk(acts, depth):
        for a in acts:
            t = (a.get("title") or "").strip()
            noise = re.match(r"^(Find|Check|Wait for|Synthesize|Requesting|Get |Snapshot|Collecting|Added attachment|"
                             r"kXCT|qakit-|Capturing|Start Test|Set Up|Tear Down|Debug description|App UI hierarchy|UI Snapshot)", t)
            if t and not noise:
                titles.append(("  " * min(depth, 3)) + t)
            walk(a.get("childActivities", []), depth + 1)
    try:
        for run_ in json.loads(r.stdout).get("testRuns", []):
            walk(run_.get("activities", []), 0)
    except json.JSONDecodeError:
        return []
    return titles[-limit:]


# 실패하면 "대신 이 대상" 제안 — 실패 시점 화면에서 비슷하고, 그 화면에 하나만 있는 요소 (AI 없이)
DUMP_TYPE = {"Button": "button", "StaticText": "text", "Text": "text", "Image": "image", "Cell": "cell",
             "TextField": "textfield", "SecureTextField": "securetextfield", "Switch": "switch", "Other": "other",
             "CollectionView": "collectionview", "ScrollView": "scrollview", "Table": "table"}
FAIL_TARGET_RE = re.compile(r"(?:나타나지 않음|찾지 못함|기대 조건 실패|기대 효과가 나타나지 않음[^:]*): (.+)$", re.M)


def dump_elements(text):
    """화면 구조 텍스트(qakit 덤프 또는 XCUITest debugDescription) → [{type, id, label}]."""
    els = [{"type": e["type"], "id": e["id"], "label": e["labelRaw"]} for e in ui_parse_dump(text)["elements"]]
    if els:
        return els
    for raw in text.splitlines():
        m = re.match(r"^\s*(\w[\w ]*?), 0x[0-9a-f]+, .*$", raw)
        if not m:
            continue
        i = re.search(r"identifier: '((?:[^'\\]|\\.)*)'", raw)
        lab = re.search(r"label: '((?:[^'\\]|\\.)*)'", raw)
        if i or lab:
            els.append({"type": m.group(1).strip(), "id": i.group(1) if i else None, "label": lab.group(1) if lab else None})
    return els


def failed_targets(message):
    """원인 문구 → 찾지 못한 대상들 [("id", 값) | ("label", 값, type)]."""
    m = FAIL_TARGET_RE.search(message or "")
    if not m:
        return []
    raw = m.group(1).strip()
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(("id", v))
        elif isinstance(v, dict):
            if "id" in v and isinstance(v["id"], str):
                out.append(("id", v["id"]))
            elif "label" in v or "contains" in v:
                out.append(("label", v.get("label") or v.get("contains"), v.get("type")))
            else:
                for k in ("visible", "exists", "hittable", "for", "target", "on", "not"):
                    if k in v:
                        walk(v[k])
                for k in ("all", "any"):
                    for x in v.get(k) or []:
                        walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    try:
        walk(json.loads(raw))
    except ValueError:
        walk(raw.split(", ")[0] if raw and not raw.startswith("{") else raw)
    return out


def suggest_targets(message, dump_text, limit=3):
    """실패 대상과 비슷한 요소 → 시나리오에 쓸 대상 문자열 (실패 시점 화면에서 하나만 맞는 것만)."""
    import difflib
    els = dump_elements(dump_text or "")
    if not els:
        return []
    yq = lambda v: v if re.fullmatch(r"[A-Za-z0-9_.\-]+", v) else json.dumps(v, ensure_ascii=False)
    found, used = [], set()   # used: 이미 제안한 요소 (ID로 제안했으면 같은 요소를 라벨로 또 제안하지 않음)
    for t in failed_targets(message):
        want = (t[1] or "").lower()
        if not want:
            continue
        scored = []
        for e in els:
            for kind, val in (("id", e["id"]), ("label", e["label"])):
                if not val or val.startswith("_Tt"):
                    continue
                v = val.split("\n")[0]
                if v.lower() == want and kind == t[0]:
                    continue   # 같은 이름이 있는데 실패 = 가려졌거나 늦게 뜸 → 이름을 바꿀 문제가 아님
                r = difflib.SequenceMatcher(None, want, v.lower()).ratio()
                if want in v.lower() or v.lower() in want:
                    r = max(r, 0.75)
                if r >= 0.75:
                    scored.append((r, kind, v, e))
        best = max((x[0] for x in scored), default=0)
        for r, kind, v, e in sorted(scored, key=lambda x: -x[0]):
            if id(e) in used or r < best - 0.1:   # 가장 비슷한 것보다 한참 덜 비슷하면 빼기 (앞뒤만 같은 home_…_button 등)
                continue
            if kind == "id":
                if sum(1 for x in els if x["id"] == v) != 1:
                    continue
                sel = yq(v)
            else:
                typ = DUMP_TYPE.get(e["type"], "any")
                same = [x for x in els if (x["label"] or "").split("\n")[0] == v and DUMP_TYPE.get(x["type"], "any") == typ]
                if len(same) != 1:
                    continue
                key = "contains" if "\n" in (e["label"] or "") else "label"
                sel = f"{{ type: {typ}, {key}: {json.dumps(v, ensure_ascii=False)} }}"
            desc = f'{e["type"]}' + (f' "{(e["label"] or "").splitlines()[0][:30]}"' if e["label"] and kind == "id" else "")
            line = f"{sel}  ({desc}, 비슷함 {int(r * 100)}%)"
            if sel not in [x.split("  (")[0] for x in found]:
                found.append(line)
                used.add(id(e))
            if len(found) >= limit:
                return found
    return found


def suggestion_lines(message, dump_text):
    els = dump_elements(dump_text or "")
    text = dump_text or ""
    present = [t[1] for t in failed_targets(message) if t[1] and (
        any((e["id"] if t[0] == "id" else (e["label"] or "").split("\n")[0]) == t[1] for e in els)
        or (t[0] == "id" and re.search(r"(#|identifier: ')" + re.escape(t[1]) + r"(\s|'|$)", text, re.M)))]
    if present:   # 이름은 맞다 → 바꿀 게 아니라 가려졌거나 화면 밖이거나 늦게 뜬 것
        return [f"   '{present[0]}'은(는) 실패 시점 화면 구조에 있습니다 → 이름 문제가 아님. 가려졌거나(팝업·시트) 화면 밖이면 "
                "scroll-to·swipe, 늦게 뜨면 timeout을 늘리세요"]
    tips = suggest_targets(message, dump_text)
    if not tips:
        return []
    return ["   대신 이 대상? (실패 시점 화면에 하나만 있는 비슷한 요소):"] + [f"     → {t}" for t in tips]


def compact_tree(text):
    """XCUITest debugDescription → ID/라벨이 있는 줄만, 좌표 축약."""
    lines = []
    for raw in text.splitlines():
        m = re.match(r"^(\s*)(\w[\w ]*?), 0x[0-9a-f]+, \{\{([-\d.]+), ([-\d.]+)\}, \{([-\d.]+), ([-\d.]+)\}\}(.*)$", raw)
        if not m:
            continue
        indent, kind, x, y, w, h, rest = m.groups()
        if "identifier:" not in rest and "label:" not in rest:
            continue
        # 라벨 없는 컨테이너/이미지는 생략 (덤프가 필요하면 qakit dump-ui)
        if kind.strip() in ("Other", "Image", "ScrollView", "Window") and "label:" not in rest:
            continue
        rest = re.sub(r", (Selected|Disabled|Enabled)", r" \1", rest)
        lines.append(f"{indent}{kind}{rest} @{int(float(x))},{int(float(y))} {int(float(w))}x{int(float(h))}")
    return lines


# ─────────────────────────────── 앱 상태 / 동기화 ───────────────────────────────

def git(app_dir, *args):
    r = run(["git", "-C", str(app_dir), *args], check=False)
    return r.stdout.strip() if r.returncode == 0 else None


APP_STATE_CACHE = {}


def forget_app_state():
    """앱 커밋이 바뀌었을 때(워크트리 최신화) 다음 app_state가 다시 계산하게."""
    APP_STATE_CACHE.clear()


def app_state(ws):
    """앱 소스 상태 스냅샷: 경로, 브랜치, 커밋, 미커밋 변경 해시.
    한 번 실행 안에서는 재사용한다 (run 한 번에 세 번 불리고, 시스템이 바쁠 때 git status가 몇 초씩 걸린다)."""
    key = (str(ws.app_dir), str(ws.project), ws.scheme, ws.configuration)
    if key not in APP_STATE_CACHE:
        APP_STATE_CACHE[key] = _app_state(ws)
    return dict(APP_STATE_CACHE[key])


def _app_state(ws):
    d = ws.app_dir
    state = {"appPath": str(ws.project), "scheme": ws.scheme, "configuration": ws.configuration}
    branch = git(d, "rev-parse", "--abbrev-ref", "HEAD")
    if branch is not None:
        state["branch"] = branch
        state["commit"] = git(d, "rev-parse", "--short", "HEAD")
        spec = app_pathspec(ws)
        # 앱 파일만의 내용 해시 (QA 폴더 등 제외 경로는 빠진다) — QA만 바뀐 커밋으로는 다시 빌드하지 않게
        state["appTree"] = app_tree_hash(ws, "HEAD")
        status = git(d, "status", "--porcelain", "--untracked-files=normal", "--", *spec) or ""
        diff = git(d, "diff", "HEAD", "--", *spec) or ""
        state["dirty"] = hashlib.sha1((status + diff).encode()).hexdigest()[:12] if status else ""
        state["dirtyFiles"] = len(status.splitlines()) if status else 0
    else:
        # git이 아니면 Swift 파일 수정 시각으로
        h = hashlib.sha1()
        for f in sorted(gen_ids.iter_swift_files([d])):
            h.update(f"{f}:{f.stat().st_mtime}".encode())
        state["sourceHash"] = h.hexdigest()[:12]
    return state


def app_tree_hash(ws, rev):
    """그 커밋에서 앱 파일만의 내용 해시 (작업공간인 QA 폴더 등 제외 경로는 뺀다). QA만 바뀐 커밋은 같은 값."""
    excluded = [x.split(")", 1)[1].rstrip("/") + "/" for x in app_pathspec(ws) if x.startswith(":(exclude)")]
    listing = git(ws.app_dir, "ls-tree", "-r", rev)
    if listing is None:
        return None
    tree = "\n".join(l for l in listing.splitlines()
                     if not any(l.split("\t", 1)[-1].startswith(e) for e in excluded))
    return hashlib.sha1(tree.encode()).hexdigest()[:12]


def app_pathspec(ws):
    """작업공간이 앱 레포 안(QA 폴더)이면 앱 변경 감지에서 제외한다."""
    try:
        rel = ws.root.relative_to(ws.app_dir)
        return [".", f":(exclude){rel}"]
    except ValueError:
        return ["."]


SAME_KEYS = ("appPath", "scheme", "configuration", "appTree", "dirty", "sourceHash")


def load_state(ws, name):
    f = ws.state_dir / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else None


def save_state(ws, name, data):
    ws.state_dir.mkdir(exist_ok=True)
    data = dict(data, savedAt=datetime.datetime.now().isoformat(timespec="seconds"))
    (ws.state_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))


def describe_change(old, new):
    if not old:
        return "빌드 기록 없음"
    parts = []
    if old.get("appPath") != new.get("appPath"):
        parts.append(f"앱 경로 {Path(old.get('appPath', '')).parent.name} → {Path(new['appPath']).parent.name}")
    if old.get("branch") != new.get("branch"):
        parts.append(f"브랜치 {old.get('branch') or '(git 아님)'} → {new.get('branch') or '(git 아님)'}")
    elif old.get("commit") != new.get("commit") and old.get("appTree") != new.get("appTree"):
        parts.append(f"커밋 {old.get('commit')} → {new.get('commit')}")
    if old.get("dirty") != new.get("dirty"):
        parts.append(f"미커밋 변경 {new.get('dirtyFiles', 0)}개 파일")
    if old.get("sourceHash") != new.get("sourceHash"):
        parts.append("소스 변경")
    for k in ("scheme", "configuration"):
        if old.get(k) != new.get(k):
            parts.append(f"{k} {old.get(k)} → {new.get(k)}")
    return ", ".join(parts)


def app_changed(ws):
    old = load_state(ws, ws.state_name)
    new = app_state(ws)
    def same(k):
        if k == "appTree" and old and "appTree" not in old:
            # 예전 기록(appTree 없음): 그 커밋의 앱 파일 해시를 구해 비교한다
            return bool(old.get("commit")) and app_tree_hash(ws, old["commit"]) == new.get("appTree")
        return old.get(k) == new.get(k)
    changed = not old or not all(same(k) for k in SAME_KEYS)
    return changed, describe_change(old, new) if changed else "", new


# ─────────────────────────────── QA 워크트리 최신화 ───────────────────────────────
# 원칙: QA 워크트리 브랜치(qa/workspace)는 그대로 유지한다. 사용자가 명시적으로 요청하지 않는 한
# 다른 브랜치로 병합하지 않고 push하지 않는다. 따라갈 브랜치(develop)가 앞서 있으면 그 커밋을 QA 쪽으로 가져온다.

PREFETCH = {}


def prefetch_worktree(ws):
    """test/run 시작 때 QA 워크트리의 git fetch를 미리 백그라운드로 시작한다 (ID 검사와 동시에).
    follow_worktree가 그 결과를 기다려 쓴다. 매번 가져오는 것은 같고, 기다리는 시간만 겹친다."""
    import threading
    if ws.worktree_update == "off" or APP_OVERRIDE or not ws.app_dir or not is_qa_worktree(ws.app_dir):
        return
    base = ws.worktree_base
    key = (str(ws.app_dir), None if "*" in base else base)
    if key not in PREFETCH and key not in FETCHED:
        t = threading.Thread(target=_git_fetch_now, args=key, daemon=True)
        t.start()
        PREFETCH[key] = t


FETCHED = set()


def _git_quiet_fetch(repo_dir, branch):
    """branch가 None이면 origin 전체를 가져온다 (패턴으로 브랜치를 고를 때). 미리 시작한 fetch가 있으면 그것을 기다린다."""
    FETCHED.add((str(repo_dir), branch))
    t = PREFETCH.pop((str(repo_dir), branch), None)
    if t:
        t.join(timeout=35)
        return
    _git_fetch_now(str(repo_dir), branch)


def _git_fetch_now(repo_dir, branch):
    if not git(repo_dir, "remote"):
        return
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "--quiet", "--prune", "origin", *([branch] if branch else [])],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        pass


def latest_matching_branch(repo_dir, pattern):
    """release/* 같은 패턴에 맞는 브랜치 중 버전이 가장 높은 것 (원격·로컬 모두 보고, origin/ 은 뗀다)."""
    out = git(repo_dir, "for-each-ref", "--sort=-version:refname", "--format=%(refname)",
              f"refs/remotes/origin/{pattern}", f"refs/heads/{pattern}") or ""
    names = []
    for ref in out.splitlines():
        name = ref.removeprefix("refs/remotes/origin/").removeprefix("refs/heads/")
        if name not in names:
            names.append(name)
    if not names:
        return None
    def key(n):
        return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", n)]
    return max(names, key=key)


def worktree_status(ws, base=None, fetch=True):
    """QA 워크트리가 따라갈 브랜치보다 몇 커밋 뒤처졌는지. QA 워크트리가 아니면 None."""
    d = ws.app_dir
    if not d or APP_OVERRIDE or not is_qa_worktree(d):
        return None
    base = base or ws.worktree_base
    if fetch:
        _git_quiet_fetch(d, None if "*" in base else base)
    if "*" in base:   # 예) release/* → 버전이 가장 높은 release 브랜치
        base = latest_matching_branch(d, base) or base
    refs = [r for r in (f"origin/{base}", base) if git(d, "rev-parse", "--verify", "--quiet", r) is not None]
    ref = refs[0] if refs else None
    for other in refs[1:]:   # 로컬이 원격보다 앞서 있으면 로컬을 쓴다
        if git(d, "merge-base", "--is-ancestor", ref, other) is not None:
            ref = other
    branch = git(d, "rev-parse", "--abbrev-ref", "HEAD")
    behind = int(git(d, "rev-list", "--count", f"HEAD..{ref}") or 0) if ref else 0
    return {"base": base, "ref": ref, "branch": branch, "behind": behind}


def update_worktree(ws, base=None, check_only=False, strict=True):
    """따라갈 브랜치의 새 커밋을 QA 워크트리로 가져온다 (merge, push 안 함). strict=False면 실패해도 경고만."""
    def stop(msg, hint=None):
        if strict:
            fail(msg, hint)
        warn(msg + (f" → {hint}" if hint else ""))
        return False

    st = worktree_status(ws, base)
    if st is None:
        return stop("앱 폴더가 QA 워크트리가 아닙니다.", "qakit init <앱> --worktree 로 만든 작업공간에서 실행하세요")
    if not st["ref"]:
        return stop(f"따라갈 브랜치 '{st['base']}'를 찾지 못했습니다.", "qakit.yml의 worktree.base 또는 --from <브랜치>")
    d, ref, branch, n = ws.app_dir, st["ref"], st["branch"], st["behind"]
    if n == 0:
        if strict:
            ok(f"QA 워크트리({branch})가 {ref} 기준 최신입니다")
        return True
    if check_only:
        warn(f"QA 워크트리({branch})가 {ref}보다 {n}커밋 뒤처져 있습니다 → qakit worktree-update")
        return True
    dirty = git(d, "status", "--porcelain", "--untracked-files=no", "--", *app_pathspec(ws))
    if dirty:
        return stop(f"QA 워크트리({branch})가 {ref}보다 {n}커밋 뒤처졌지만, 앱 소스에 미커밋 변경이 있어 가져오지 않았습니다.",
                    "변경을 커밋하거나 정리한 뒤 qakit worktree-update")
    if ws.swiftui_manifest.exists():
        return stop("SwiftUI ID 삽입이 복원되지 않은 상태라 가져오지 않았습니다.", "qakit swiftui-ids --restore 후 다시")
    before = git(d, "rev-parse", "--short", "HEAD")
    info(f"🔄 QA 워크트리({branch})가 {ref}보다 {n}커밋 뒤처짐 → {ref}에서 가져와 최신화 (QA 브랜치 유지, push 안 함)")
    r = run(["git", "-C", str(d), "merge", "--no-edit", "-m",
             f"Merge {ref} into {branch} (qakit worktree-update)", ref], check=False)
    if r.returncode != 0:
        run(["git", "-C", str(d), "merge", "--abort"], check=False)
        conflicts = [l for l in (r.stdout or "").splitlines() if "CONFLICT" in l][:5]
        return stop(f"{ref}를 가져오다 충돌이 나서 되돌렸습니다." + ("\n   " + "\n   ".join(conflicts) if conflicts else ""),
                    f"직접 해결: git -C {d} merge {ref}")
    forget_app_state()
    ok(f"{ref}의 {n}커밋을 가져옴 ({before} → {git(d, 'rev-parse', '--short', 'HEAD')}). 다음 test/run이 앱을 다시 빌드합니다")
    return True


def follow_worktree(ws):
    """test/run 전에: QA 워크트리가 따라갈 브랜치보다 뒤처졌으면 가져온다 (qakit.yml worktree.update)."""
    if ws.worktree_update == "off":
        return
    update_worktree(ws, check_only=ws.worktree_update == "warn", strict=False)


def worktree_info(ws, fetch=False):
    """UI용: QA 워크트리 상태 + 가져올 커밋·고를 브랜치. QA 워크트리가 아니면 {"worktree": False}."""
    st = worktree_status(ws, fetch=fetch)
    if st is None:
        return {"worktree": False}
    d, ref = ws.app_dir, st["ref"]
    fmt = "%h\x1f%s\x1f%an\x1f%cr"
    incoming = []
    if ref and st["behind"]:
        for line in (git(d, "log", f"--format={fmt}", "-n", "15", f"HEAD..{ref}") or "").splitlines():
            h, subj, author, when = (line.split("\x1f") + ["", "", "", ""])[:4]
            incoming.append({"hash": h, "subject": subj, "author": author, "when": when})
    head = (git(d, "log", "-1", f"--format={fmt}") or "").split("\x1f")
    branches = []
    for line in (git(d, "for-each-ref", "--sort=-committerdate", "--count=60", "--format=%(refname:short)\x1f%(committerdate:relative)",
                     "refs/remotes/origin") or "").splitlines():
        name, when = (line.split("\x1f") + [""])[:2]
        name = name.removeprefix("origin/")
        if name and name not in ("HEAD", "origin") and name != st["branch"]:
            branches.append({"name": name, "when": when})
    dirty = bool(git(d, "status", "--porcelain", "--untracked-files=no", "--", *app_pathspec(ws)))
    return dict(st, worktree=True, configured=ws.worktree_base, mode=ws.worktree_update, dirty=dirty, incoming=incoming,
                head={"hash": head[0], "subject": head[1] if len(head) > 1 else "", "when": head[3] if len(head) > 3 else ""},
                branches=branches, appDir=str(d))


def set_worktree_config(ws, base=None, mode=None):
    """qakit.yml의 worktree.base·update만 고친다 (나머지 줄·주석 그대로). 없으면 worktree: 블록에 넣는다."""
    p = ws.config_path
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"^worktree:\s*(#.*)?$", l))
    except StopIteration:
        lines += ["\nworktree:\n"]
        start = len(lines) - 1
    end = start + 1
    while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
        end += 1
    for key, val in (("base", base), ("update", mode)):
        if val is None:
            continue
        idx = next((i for i in range(start + 1, end) if re.match(rf"^\s+{key}:", lines[i])), None)
        new = f"  {key}: {val}\n"
        if idx is None:
            lines.insert(start + 1, new)
            end += 1
        else:
            comment = re.search(r"\s+#.*$", lines[idx].rstrip("\n"))
            lines[idx] = new.rstrip("\n") + (comment.group(0) if comment else "") + "\n"
    p.write_text("".join(lines), encoding="utf-8")


def cmd_worktree_update(args):
    ws = find_workspace(args.workspace)
    update_worktree(ws, base=args.base, check_only=args.check)


AUTO_SYNCED = set()


def auto_sync(ws):
    """test/run 전 앱 변경 반영. 한 명령 안에서는 한 번만 (qakit run 여러 개)."""
    if str(ws.root) in AUTO_SYNCED:
        return
    AUTO_SYNCED.add(str(ws.root))
    follow_worktree(ws)
    if ws.sync_mode == "off":
        return
    changed, why, _ = app_changed(ws)
    if not changed:
        return
    if ws.sync_mode == "warn":
        warn(f"앱이 마지막 빌드 이후 바뀌었습니다 ({why}). 최신 상태로 테스트하려면 qakit sync")
        return
    info(f"🔄 앱 변경 감지 ({why}) → 동기화")
    do_sync(ws, compile_check=False)


def cmd_sync(args):
    ws = find_workspace(args.workspace)
    do_sync(ws, compile_check=True, force_build=args.rebuild, skip_build=args.skip_build)


def do_sync(ws, compile_check=True, force_build=False, skip_build=False):
    changed, why, state = app_changed(ws)
    branch = state.get("branch")
    info(f"앱: {ws.project}" + (f"  [{branch} @ {state.get('commit')}"
                                 + (f", 미커밋 {state.get('dirtyFiles')}개" if state.get("dirty") else "") + "]"
                                 if branch else ""))
    # 1. 앱 빌드/설치
    if skip_build:
        info("1) 앱 빌드 생략 (--skip-build)" + (f" — 주의: 설치된 앱과 소스가 다름 ({why})" if changed else ""))
    elif changed or force_build:
        info(f"1) 앱 재빌드: {why or '요청'}")
        cmd_build_app_ws(ws)
    else:
        ok("1) 설치된 앱이 최신")
    # 2. ID 재생성
    info("2) ID 상수 재생성")
    generate_ids(ws, quiet=False)
    # 3. 테스트 코드 컴파일 확인
    broken = False
    if compile_check:
        info("3) 테스트 코드 컴파일 확인")
        udid = ensure_booted(ws)
        ensure_runner(ws)
        r = run(["xcodebuild", "build-for-testing", "-project", str(ws.runner_project),
                 "-scheme", RUNNER_SCHEME, "-destination", f"id={udid}",
                 "-derivedDataPath", str(ws.build_dir / "runner")], check=False)
        if r.returncode == 0:
            ok("   테스트 코드 정상")
        else:
            errors = list(dict.fromkeys(l.strip() for l in r.stdout.splitlines() if "error:" in l))
            id_errors = [e for e in errors if "QAID" in e]
            print(f"❌ 테스트 코드 컴파일 실패 {len(errors)}건" + (f" (ID 변경 때문 {len(id_errors)}건)" if id_errors else ""))
            for e in errors[:15]:
                print("   " + re.sub(r"^.*/Runner/", "Runner/", e))
            print("   → 위 Page/Flow에서 바뀐 ID를 새 QAID로 고치세요 (2)의 삭제/추가 목록 참고)")
            broken = True
    # 4. 브랜치 안내
    workspace_branch = git(ws.root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch and workspace_branch and workspace_branch != branch:
        if git(ws.root, "rev-parse", "--verify", "--quiet", branch) is not None:
            warn(f"작업공간 브랜치({workspace_branch})가 앱 브랜치({branch})와 다릅니다. "
                 f"같은 이름의 작업공간 브랜치가 있습니다: git -C {ws.root} switch {branch}")
    if broken:
        fail("동기화는 됐지만 테스트 코드 수정이 필요합니다.")
    ok("동기화 완료")


# ─────────────────────────────── 명령: gen-ids ───────────────────────────────

def cmd_swiftui_ids(args):
    ws = find_workspace(args.workspace)
    if args.restore:
        if not ws.swiftui_manifest.exists():
            ok("복원할 삽입이 없습니다 (manifest 없음)")
            return
        swiftui_restore(ws, ws.swiftui_manifest)
        ok("SwiftUI ID 삽입을 되돌렸습니다")
    elif args.insert:
        manifest = swiftui_insert(ws)
        if manifest is None:
            warn("SwiftUI 소스가 없거나 swiftui: off 입니다")
        else:
            ok(f"삽입한 채 둡니다. 확인 뒤: qakit swiftui-ids --restore  (git -C {ws.app_dir} diff 로 보기)")
    else:
        if ws.swiftui == "off":
            warn("qakit.yml: swiftui: off")
        items = swiftui_list(ws)
        for x in items:
            rel = os.path.relpath(x["file"], ws.app_dir)
            print(f'{x["id"]}\t{x["kind"]}{"  (호출부 ID가 우선)" if x.get("overridable") else ""}\t{rel}:{x["line"]}')
        info(f"SwiftUI ID {len(items)}개")


def cmd_gen_ids(args):
    ws = find_workspace(args.workspace)
    trees, model = generate_ids(ws, quiet=False)
    if args.verify:
        verify_ids(ws, trees, model)


def generate_ids(ws, quiet=True):
    sources = ws.id_sources or [ws.app_dir]
    trees, model, nfiles = gen_ids.build(sources, exclude=[ws.root])
    swiftui = swiftui_list(ws)
    if swiftui:
        gen_ids.merge_ids(trees, [x["id"] for x in swiftui], kind="swiftui")
    ids = sorted(gen_ids.all_ids(trees))
    state = app_state(ws)
    note = f"앱: {ws.project.parent.name}" + (f" [{state.get('branch')} @ {state.get('commit')}]" if state.get("branch") else "")
    ws.ids_file.parent.mkdir(parents=True, exist_ok=True)
    ws.ids_file.write_text(gen_ids.render_swift(trees, note), encoding="utf-8")

    prev = load_state(ws, "ids")
    prev_ids = set(prev["ids"]) if prev else None
    save_state(ws, "ids", {"ids": ids, "app": note})
    if quiet:
        return trees, model
    info(f"   소스 {nfiles}개 → ID {len(ids)}개" + (f" (SwiftUI {len(swiftui)}개 포함)" if swiftui else "") + f" → {ws.ids_file.relative_to(ws.root)}")
    if prev_ids is not None:
        added = sorted(set(ids) - prev_ids)
        removed = sorted(prev_ids - set(ids))
        if not added and not removed:
            ok("   ID 변경 없음")
        else:
            info(f"   ID 변경: 추가 {len(added)}, 삭제 {len(removed)}")
            for x in removed[:30]:
                print(f"     - {x}")
            for x in added[:30]:
                print(f"     + {x}")
            if len(removed) > 30 or len(added) > 30:
                print("     ...(일부 생략)")
            used = used_ids(ws)
            broken = sorted(used & set(removed))
            if broken:
                warn(f"   테스트에서 쓰던 ID가 삭제됨: {', '.join(broken)}")
    return trees, model


def used_ids(ws):
    """테스트 코드에 문자열로 직접 쓴 ID (QAID 상수로 바꾸지 않은 것)."""
    found = set()
    for f in (ws.runner_dir / "UITests").rglob("*.swift") if has_swift_runner(ws) else []:
        if "Generated" in f.parts:
            continue
        found |= set(re.findall(r'"([A-Z]\w*(?:\.\w+)+)"', f.read_text(encoding="utf-8", errors="replace")))
    return found


def verify_ids(ws, trees, model):
    dumps = sorted((ws.results_dir / "dumps").glob("*.txt"))
    if (ws.results_dir / "ui-dump.txt").exists():
        dumps.append(ws.results_dir / "ui-dump.txt")
    if not dumps:
        fail("비교할 화면 덤프가 없습니다.", "qakit dump-ui 를 화면별로 몇 번 실행한 뒤 다시 시도하세요.")
    matched, missing, external = gen_ids.verify(gen_ids.all_ids(trees), model, dumps, gen_ids.id_types(trees))
    info(f"검증 (덤프 {len(dumps)}개): 일치 {len(matched)}, 불일치 {len(missing)}, 앱 소스 밖·위치 규칙·선언 타입 차이 {len(external)}")
    for x in missing:
        print(f"   ❌ 런타임에만 있음: {x}")
    if missing:
        fail("생성 ID와 런타임 ID가 다릅니다.", "AutoID 규칙과 gen_ids.py 규칙 차이 — 도구 버그로 보고하세요.")
    ok("생성 ID가 런타임 ID와 일치")


