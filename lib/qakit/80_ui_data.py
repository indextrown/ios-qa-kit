# qakit — qakit ui가 읽는 결과·시나리오 데이터
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 명령: ui (docs/PLAN.md "UI 설계") ───────────────────────────────

UI_DIR = KIT_DIR / "ui" / "dist"   # web/(React) 빌드 결과 — 저장소에 커밋, Node 없이 서빙
RUN_DIR_RE = re.compile(r"^(\d\d)-(\d\d)-(\d\d)_([a-z]+(?:-[0-9a-z]+)?)(?:_(.+))?$")


def ui_history(ws, limit=20000):
    try:
        lines = (ws.root / "history.jsonl").read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def ui_runs(ws, limit=300):
    """결과 폴더(results/<날짜>/<시-분-초>_<종류>_<이름>) + 실행 기록 → 최근 실행 목록."""
    hist = ui_history(ws)
    by_dir = {r["dir"]: r for r in hist if r.get("dir")}
    by_test = {}
    for r in hist:
        try:
            by_test.setdefault(r.get("test"), []).append((datetime.datetime.fromisoformat(r["at"]), r))
        except (KeyError, ValueError, TypeError):
            pass
    dirs = []
    for day in ws.results_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"):
        dirs += [d for d in day.iterdir() if d.is_dir() and RUN_DIR_RE.match(d.name)]
    dirs.sort(key=lambda d: (d.parent.name, d.name), reverse=True)
    out = []
    for d in dirs[:limit]:
        m = RUN_DIR_RE.match(d.name)
        kind, rest = m.group(4), m.group(5) or ""
        name, _, device = rest.partition("_")
        rel = f"{d.parent.name}/{d.name}"
        start = datetime.datetime.fromisoformat(f"{d.parent.name}T{m.group(1)}:{m.group(2)}:{m.group(3)}")
        row = by_dir.get(rel)
        if row is None:   # 예전 기록(dir 없음): 같은 이름, 시작 뒤 실행 시간 안에 끝난 기록
            for at, r in by_test.get(name, []):
                if start <= at <= start + datetime.timedelta(seconds=float(r.get("seconds") or 0) + 600):
                    row = r
                    break
        result = row.get("result") if row else None
        summary = d / SERVE_SUMMARY
        if result is None and summary.exists():
            result = "Passed" if "통과 1 / 실패 0" in summary.read_text(encoding="utf-8")[:200] else "Failed"
        out.append({"dir": rel, "kind": kind, "name": name or kind, "device": device or None,
                    "start": start.isoformat(), "result": result or "unknown",
                    "seconds": row.get("seconds") if row else None,
                    "via": (row or {}).get("via") or ("serve" if summary.exists() else
                                                      "xcodebuild" if (d / "result.xcresult").exists() else None),
                    "app": (row or {}).get("app"), "kit": (row or {}).get("kit"),
                    "screenshot": (d / "failure.png").exists()})
    return out


def ui_safe_dir(ws, rel):
    d = (ws.results_dir / (rel or "")).resolve()
    if ws.results_dir.resolve() not in d.parents or not d.is_dir():
        return None
    return d


def ui_timings(log_text):
    """output.log의 timing: 아래 → [{depth, seconds, name, interrupts}]"""
    rows, on = [], False
    for line in log_text.splitlines():
        if line.startswith("timing:"):
            on = True
            continue
        if on:
            m = re.match(r"^  ((?:  )*)\s*([\d.]+)초  (.*?)(?:  \(끼어드는 화면 ([\d.]+)초\))?$", line)
            if not m:
                break
            rows.append({"depth": len(m.group(1)) // 2, "seconds": float(m.group(2)), "name": m.group(3),
                         "interrupts": float(m.group(4)) if m.group(4) else 0})
    return rows


def ui_run_detail(ws, rel):
    d = ui_safe_dir(ws, rel)
    if d is None:
        return None
    mask = masker(ws.secrets())
    read = lambda f: mask(f.read_text(encoding="utf-8", errors="replace")) if f.exists() else None
    summary = read(d / SERVE_SUMMARY)
    if summary is None and (d / "result.xcresult").exists():
        try:
            summary = summarize(d / "result.xcresult", mask)
        except Exception as e:  # noqa: BLE001 — 결과 파일이 깨졌어도 나머지는 보여 준다
            summary = f"(요약을 만들지 못함: {e})"
    log = read(d / "output.log") or ""
    images = [str(f.relative_to(d)) for f in sorted(d.rglob("*.png")) if "result.xcresult" not in f.parts]
    videos = [str(f.relative_to(d)) for f in sorted(d.rglob("*.mp4"))]
    dumps = [str(f.relative_to(d)) for f in sorted(d.rglob("*.txt")) if f.name != SERVE_SUMMARY
             and "result.xcresult" not in f.parts]
    timing_head = next((l[len("timing: "):] for l in log.splitlines() if l.startswith("timing: ")), None)
    return {"dir": rel, "summary": summary, "log": "\n".join(log.splitlines()[-400:]),
            "timingHead": timing_head, "timings": ui_timings(log), "images": images, "videos": videos, "dumps": dumps,
            "files": sorted(f.name for f in d.iterdir())}


DUMP_LINE_RE = re.compile(
    r'^(?P<indent> *)(?P<type>[A-Za-z0-9]+)(?: #(?P<id>\S+))?(?: "(?P<label>.*?)")?(?: value="(?P<value>.*?)")?'
    r'(?P<flags>(?: \((?:disabled|selected)\))*) @(?P<x>-?\d+),(?P<y>-?\d+) (?P<w>\d+)x(?P<h>\d+)$', re.M | re.S)


def ui_parse_dump(text):
    """qakit do dump 텍스트 → 요소 목록 (라벨에 줄바꿈이 있어도). 화면 크기는 Application 프레임."""
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    elements, screen = [], None
    for m in DUMP_LINE_RE.finditer(body):
        e = {"type": m["type"], "id": m["id"], "label": (m["label"] or "").replace("\n", " ") or None,
             "labelRaw": m["label"],
             "value": m["value"], "x": int(m["x"]), "y": int(m["y"]), "w": int(m["w"]), "h": int(m["h"]),
             "depth": len(m["indent"]) // 2,
             "enabled": "(disabled)" not in (m["flags"] or ""), "selected": "(selected)" in (m["flags"] or "")}
        if e["type"] == "Application" and screen is None:
            screen = {"w": e["w"], "h": e["h"]}
            continue
        if e["w"] > 0 and e["h"] > 0 and (e["id"] or e["label"]):
            elements.append(e)
    return {"screen": screen, "elements": elements}


def ui_scenarios(ws):
    hist = [r for r in ui_history(ws) if r.get("kind") == "run"]
    by_test = {}
    for r in hist:
        by_test.setdefault(r.get("test"), []).append(r)
    out = []
    for f in sorted((ws.root / "scenarios").glob("*.qa.yml")):
        name = f.name[:-len(".qa.yml")]
        try:
            text = f.read_text(encoding="utf-8")
            data = scenario_tools.parse_yaml(text) or {}
        except Exception:  # noqa: BLE001
            text, data = "", {}
        desc = []
        for line in text.splitlines()[1:4]:
            if not line.startswith("#"):
                break
            desc.append(line.lstrip("# ").strip())
        tags = data.get("tags") if isinstance(data, dict) else None
        recent = by_test.get(name, [])[-10:]
        results = ["pass" if r.get("result") == "Passed" else "env" if r.get("failure") == "env" else "fail" for r in recent]
        judged = [x for x in results if x != "env"]   # 환경 실패(실행기·연결 등)는 불안정 판정에서 뺀다
        out.append({"name": name, "title": (data.get("name") if isinstance(data, dict) else None) or name,
                    "description": " ".join(desc), "tags": tags if isinstance(tags, list) else ([tags] if tags else []),
                    "recent": results, "last": recent[-1] if recent else None,
                    "flaky": len(set(judged)) > 1})
    return out


