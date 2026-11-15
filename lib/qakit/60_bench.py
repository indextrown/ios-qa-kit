# qakit — 성능 측정 (run --bench)
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 성능 측정 (run --bench) ───────────────────────────────

def sim_app_pid(udid, bundle_id):
    """시뮬레이터에서 실행 중인 앱의 PID (Mac에서 보이는 프로세스 번호와 같다)."""
    out = run(["xcrun", "simctl", "spawn", udid, "launchctl", "list"], check=False).stdout or ""
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].startswith(f"UIKitApplication:{bundle_id}[") and parts[0].strip().isdigit():
            return int(parts[0])
    return None


def _cpu_seconds(pid):
    """프로세스가 지금까지 쓴 CPU 시간(초). ps의 time 열 ([[dd-]hh:]mm:ss.cc)."""
    r = run(["ps", "-o", "time=,rss=", "-p", str(pid)], check=False)
    if r.returncode != 0 or not r.stdout.strip():
        return None, None
    cpu, rss = r.stdout.split()[:2]
    days, _, rest = cpu.rpartition("-")
    total = 0.0
    for part in rest.split(":"):
        total = total * 60 + float(part)
    return total + (int(days) * 86400 if days else 0), int(rss) / 1024.0


# 함수별 CPU: macOS 기본 명령 sample로 SAMPLE_INTERVAL_MS마다 앱의 호출 스택을 찍는다 (권한 불필요).
# 측정이 1분 이하면 전체를, 더 길면 SAMPLE_EVERY초마다 SAMPLE_WINDOW초씩 찍는다.
# 1ms로 찍으면 찍는 동안 앱 CPU가 7%p쯤 올라가 CPU·메모리 기록이 흐려진다 (10ms는 1%p 안팎)
SAMPLE_INTERVAL_MS = 10
SAMPLE_WINDOW = 20
SAMPLE_EVERY = 180
# 스택 맨 위가 이 함수면 그 스레드는 잠자며 기다리는 중 (CPU를 쓰지 않음)
SAMPLE_IDLE = {
    "__workq_kernreturn", "__psynch_cvwait", "__psynch_mutexwait", "mach_msg2_trap", "mach_msg_trap",
    "semaphore_wait_trap", "semaphore_timedwait_trap", "__accept", "__select", "__pselect", "__semwait_signal",
    "kevent", "kevent64", "kevent_id", "__ulock_wait", "__ulock_wait2", "poll", "__sigsuspend", "__wait4",
    "__recvfrom", "__recvmsg", "__sleep", "nanosleep", "read", "__read_nocancel", "recv", "start_wqthread",
}
# 앱 코드 목록에서 뺄 것: 어떤 동작이든 거쳐 가는 시작점·접착 코드
SAMPLE_APP_SKIP = ("main", "static AppDelegate.$main()", "static UIApplicationDelegate.main()")
SAMPLE_APP_SKIP_PREFIX = ("thunk for ", "partial apply for ", "protocol witness for ", "DYLD-STUB$$", "__swift_",
                          "merged ", "reabstraction thunk")
_SAMPLE_LINE = re.compile(r"^([ +|!:]*?)(\d+) (.+)$")


def sample_windows(seconds):
    """측정 시간 → [(시작 초, 길이 초)]."""
    if seconds <= 60:
        return [(0, int(seconds))]
    return [(t, min(SAMPLE_WINDOW, int(seconds) - t)) for t in range(0, int(seconds), SAMPLE_EVERY)
            if int(seconds) - t >= 5]


def parse_sample(path):
    """sample 결과의 호출 트리 → 대기를 뺀 'CPU를 쓴' 샘플 집계.
    self: 스택 맨 위(직접 CPU를 쓴) 함수별 개수, app: 앱 함수별로 그 아래 호출까지 포함한 개수."""
    lines = Path(path).read_text(errors="replace").splitlines()
    binary = next((l.split()[1] for l in lines[:5] if l.startswith("Process:")), "app")
    try:
        lines = lines[lines.index("Call graph:") + 1:]
    except ValueError:
        return None
    depth, count, name, lib, src, parent = [], [], [], [], [], []
    stack = []
    for line in lines:
        if not line.strip():
            break
        m = _SAMPLE_LINE.match(line)
        if not m:
            continue
        d, rest = len(m.group(1)), m.group(3)
        fn, _, tail = rest.partition("  (in ")
        while stack and depth[stack[-1]] >= d:
            stack.pop()
        parent.append(stack[-1] if stack else None)
        stack.append(len(depth))
        depth.append(d)
        count.append(int(m.group(2)))
        name.append(fn.strip())
        lib.append(tail.split(")", 1)[0] if tail else "")
        src.append(rest.rsplit("]  ", 1)[1].strip() if "]  " in rest else "")
    n = len(depth)
    active = list(count)                      # 자기 자신 = 개수 − 자식 개수 합
    for i in range(n):
        if parent[i] is not None:
            active[parent[i]] -= count[i]
    for i in range(n):
        if not lib[i] or name[i] in SAMPLE_IDLE:
            active[i] = 0                     # 스레드 머리줄 / 잠자며 대기
    incl = list(active)                       # 아래 호출까지 포함한 CPU 샘플
    for i in reversed(range(n)):
        if parent[i] is not None:
            incl[parent[i]] += incl[i]
    self_counts, app_counts, app_src = {}, {}, {}
    for i in range(n):
        if active[i]:
            key = name[i] if name[i] != "???" else f"??? ({lib[i]})"
            self_counts[(key, lib[i])] = self_counts.get((key, lib[i]), 0) + active[i]
        if incl[i] and lib[i] == binary and name[i] not in SAMPLE_APP_SKIP \
                and not name[i].startswith(SAMPLE_APP_SKIP_PREFIX):
            a = parent[i]                     # 재귀로 위에 같은 함수가 있으면 두 번 세지 않는다
            while a is not None and name[a] != name[i]:
                a = parent[a]
            if a is None:
                app_counts[name[i]] = app_counts.get(name[i], 0) + incl[i]
                if src[i] and not src[i].startswith("/<compiler"):
                    app_src.setdefault(name[i], src[i])
    return {"active": sum(active), "self": self_counts, "app": app_counts, "src": app_src, "binary": binary}


def sample_top(files, limit=10):
    """여러 sample 결과를 합쳐 상위 목록."""
    total, selfc, appc, srcs, binary = 0, {}, {}, {}, "app"
    for f in files:
        r = parse_sample(f)
        if not r:
            continue
        total += r["active"]
        binary = r["binary"]
        for k, v in r["self"].items():
            selfc[k] = selfc.get(k, 0) + v
        for k, v in r["app"].items():
            appc[k] = appc.get(k, 0) + v
        for k, v in r["src"].items():
            srcs.setdefault(k, v)
    if not total:
        return None
    pct = lambda v: v * 100.0 / total
    return {
        "active": total, "binary": binary,
        "self": [(fn, "앱" if lb == binary else lb, pct(v)) for (fn, lb), v in
                 sorted(selfc.items(), key=lambda x: -x[1])[:limit]],
        "app": [(fn, srcs.get(fn, ""), pct(v)) for fn, v in sorted(appc.items(), key=lambda x: -x[1])[:limit]],
    }


BENCH_UNITS = {"s": 1, "초": 1, "m": 60, "분": 60, "h": 3600, "시간": 3600}
BENCH_MIN_SECONDS = 5


def parse_duration(text):
    """'30s'·'5분'·'1h30m'·'1시간30분'·'0.5m' → 초. 단위가 없거나 형식이 틀리면 ValueError."""
    s = str(text).strip().lower().replace(" ", "")
    parts = re.findall(r"(\d+(?:\.\d+)?)(시간|초|분|h|m|s)", s)
    if not s or not parts or "".join(n + u for n, u in parts) != s:
        raise ValueError(text)
    return sum(float(n) * BENCH_UNITS[u] for n, u in parts)


def short_duration(sec):
    """폴더 이름용: 90 → '1m30s', 3600 → '1h'."""
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return "".join(f"{v}{u}" for v, u in ((h, "h"), (m, "m"), (s, "s")) if v) or "0s"


def human_duration(sec):
    """5400 → '1시간 30분', 30 → '30초'."""
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    out = [f"{h}시간"] * bool(h) + [f"{m}분"] * bool(m) + [f"{s}초"] * bool(s)
    return " ".join(out) or "0초"


def _mmss(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    return f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{sec // 60}:{sec % 60:02d}"


def _progress(msg, final=False):
    """터미널이면 한 줄을 덮어쓰며 갱신, 아니면 줄마다."""
    if sys.stdout.isatty():
        print("\r\033[K" + msg, end="\n" if final else "", flush=True)
    else:
        print(msg, flush=True)


class BenchSession(threading.Thread):
    """시나리오가 끝나고 앱을 켜 둔 동안: 1초마다 CPU·메모리 기록 + sample로 함수별 CPU 기록."""

    def __init__(self, ws, udid, seconds, base, profile=True):
        super().__init__(daemon=True)
        self.ws, self.udid, self.seconds, self.base, self.profile = ws, udid, seconds, base, profile
        self.stop = threading.Event()       # xcodebuild가 끝나면 (실패 등) 기다리지 않는다
        self.summary = None

    def run(self):
        ready, done = Path(f"{self.base}.ready"), Path(f"{self.base}.done")
        while not ready.exists():
            if self.stop.wait(1):
                return
        try:
            self.summary = self.measure()
        finally:
            done.write_text("done")

    def measure(self):
        ws, seconds = self.ws, self.seconds
        pid = sim_app_pid(self.udid, ws.bundle_id)
        if not pid:
            return {"error": "실행 중인 앱의 PID를 찾지 못함"}
        info(f"📈 성능 측정 시작: {ws.bundle_id} (PID {pid}), {human_duration(seconds)} — Mac 절전 방지 중")
        caffeinate = subprocess.Popen(["caffeinate", "-dimsu", "-t", str(int(seconds) + 120)])
        samples, sampler = [], None
        if self.profile:
            windows = sample_windows(seconds)
            t_start = time.monotonic()

            def take_samples():
                for idx, (t, dur) in enumerate(windows):
                    if self.stop.wait(max(0, t_start + t - time.monotonic())):
                        return
                    out = Path(f"{self.base}-sample.txt" if len(windows) == 1 else f"{self.base}-sample-{idx + 1:02d}.txt")
                    subprocess.run(["sample", str(pid), str(dur), str(SAMPLE_INTERVAL_MS), "-mayDie", "-file", str(out)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if out.exists():
                        samples.append(out)
            sampler = threading.Thread(target=take_samples, daemon=True)
            sampler.start()
        # 1초마다 CPU 사용률(누적 CPU 시간의 증가량 / 경과 시간)과 메모리
        rows = []
        start = time.monotonic()
        prev_cpu, prev_t = _cpu_seconds(pid)[0], start
        every = 1 if sys.stdout.isatty() else (10 if seconds <= 120 else 60)   # 진행 표시 간격(초)
        while time.monotonic() - start < seconds:
            time.sleep(1)
            cpu, rss = _cpu_seconds(pid)
            now = time.monotonic()
            if cpu is None:
                rows.append((now - start, None, None))
                break   # 앱 종료
            pct = (cpu - prev_cpu) / (now - prev_t) * 100 if prev_cpu is not None else 0.0
            rows.append((now - start, pct, rss))
            prev_cpu, prev_t = cpu, now
            if len(rows) % every == 0:
                valid = [c for _, c, _ in rows if c is not None]
                _progress(f"📈 성능 측정 중 {_mmss(now - start)} / {_mmss(seconds)} · CPU 지금 {pct:.0f}% · "
                          f"평균 {sum(valid) / len(valid):.0f}% · 메모리 {rss:.0f}MB")
        _progress(f"📈 성능 측정 완료 {_mmss(time.monotonic() - start)} / {_mmss(seconds)}", final=True)
        csv = Path(f"{self.base}-cpu.csv")
        csv.write_text("seconds,cpu_percent,memory_mb\n" + "".join(
            f"{s:.0f},{'' if c is None else f'{c:.1f}'},{'' if m is None else f'{m:.1f}'}\n" for s, c, m in rows))
        result = {"pid": pid, "csv": str(csv), "samples": len(rows)}
        if not self.profile:
            result["profile_skipped"] = "--no-profile로 실행함"
        cpus = sorted(c for _, c, _ in rows if c is not None)
        mems = [m for _, _, m in rows if m is not None]
        if cpus:
            result.update(cpu_avg=sum(cpus) / len(cpus), cpu_max=cpus[-1],
                          cpu_p95=cpus[min(len(cpus) - 1, int(len(cpus) * 0.95))])
        if mems:
            result.update(mem_start=mems[0], mem_end=mems[-1], mem_max=max(mems))
        if rows and rows[-1][1] is None:
            result["error"] = f"측정 중 앱이 종료됨 ({rows[-1][0]:.0f}초)"
        # sample은 찍은 뒤 함수 이름을 붙이는(심볼 정리) 데 시간이 조금 더 걸린다
        if sampler:
            t0 = time.monotonic()
            while sampler.is_alive() and time.monotonic() - t0 < 300:
                _progress(f"🔎 함수별 CPU 기록 정리 중 {_mmss(time.monotonic() - t0)}")
                sampler.join(1 if sys.stdout.isatty() else 15)
            _progress(f"🔎 함수별 CPU 기록 정리 끝 ({_mmss(time.monotonic() - t0)})", final=True)
            result["samples_files"] = [str(f) for f in samples]
            result["sample_windows"] = sample_windows(seconds)
            result["sample_top"] = sample_top(samples) if samples else None
        caffeinate.terminate()
        return result


def write_call_tree(path, top, title, min_pct=0.5):
    """Time Profiler 샘플로 만든 호출 트리를 읽기 쉬운 텍스트로 (시뮬레이터의 bench-sample.txt에 해당)."""
    total, rename, binary = top["active"], top.get("rename") or {}, top.get("binary")
    lines = [f"# 호출 트리 — {title}",
             f"# 샘플 {total:,}개 (1ms마다 CPU를 쓰던 스택). 바깥(시작점) → 안쪽(실제로 CPU를 쓴 곳) 순서",
             f"# 비율 = 그 함수와 그 아래에서 쓴 CPU / 전체. {min_pct}% 미만은 생략. [앱] = 앱 코드",
             ""]

    def label(frame_):
        fn, lib = frame_
        fn = rename.get(fn, fn)
        where = "앱" if lib == binary else (lib or "?")
        return (fn if len(fn) <= 110 else fn[:107] + "…") + f"  [{where}]"

    def walk(node, prefix, chain=False):
        items = sorted(node.items(), key=lambda kv: -kv[1][0])
        items = [(k, v) for k, v in items if v[0] * 100.0 / total >= min_pct]
        single = len(items) == 1
        for i, (frame_, (count, children)) in enumerate(items):
            last = i == len(items) - 1
            pct_ = f"{count * 100.0 / total:5.1f}%"
            if single and chain:
                # 한 갈래로만 이어지면 들여쓰지 않고 바로 아래에 (시작점 쪽의 긴 사슬이 오른쪽으로 밀리지 않게)
                lines.append(f"{prefix}   {pct_}  {label(frame_)}")
                walk(children, prefix, chain=True)
            else:
                lines.append(f"{prefix}{'└─ ' if last else '├─ '}{pct_}  {label(frame_)}")
                walk(children, prefix + ("   " if last else "│  "), chain=True)
    walk(top["tree"], "")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def xctrace_export(trace, schema, out=None, tries=4):
    """xctrace export로 표 하나를 꺼낸다. 막 녹화한 기록은 첫 export가 빈 결과로 끝날 때가 있어(심볼 정리 중) 다시 시도한다.
    out을 주면 파일로 쓰고 True/False, 아니면 XML 글자(없으면 "")."""
    xpath = f'/trace-toc/run[@number="1"]/data/table[@schema="{schema}"]'
    for i in range(tries):
        if out:
            with open(out, "w") as f:
                r = subprocess.run(["xcrun", "xctrace", "export", "--input", str(trace), "--xpath", xpath],
                                   stdout=f, stderr=subprocess.DEVNULL)
            if r.returncode == 0 and Path(out).stat().st_size > 0:
                with open(out, errors="replace") as f:
                    if "<row" in f.read(4_000_000):   # 큰 기록도 앞부분만 본다
                        return True
        else:
            r = run(["xcrun", "xctrace", "export", "--input", str(trace), "--xpath", xpath], check=False)
            if r.returncode == 0 and "<row" in (r.stdout or ""):
                return r.stdout
        time.sleep(2 * (i + 1))
    return False if out else ""


def atos_names(dsym, load_addr, addresses):
    """앱 주소 → 함수 이름 (dSYM + atos). 기기 전체 녹화는 앱 함수 이름이 안 붙어 직접 붙인다."""
    dwarf = next((Path(dsym) / "Contents" / "Resources" / "DWARF").glob("*"), None) if dsym else None
    if not dwarf or not load_addr or not addresses:
        return {}
    addrs, names = sorted(addresses), {}
    for i in range(0, len(addrs), 500):
        chunk = addrs[i:i + 500]
        r = run(["xcrun", "atos", "-o", str(dwarf), "-arch", "arm64", "-l", load_addr, *chunk], check=False)
        for a, line in zip(chunk, (r.stdout or "").splitlines()):
            name = re.sub(r" \(in [^)]*\)( \([^)]*\))?$", "", line.strip())
            if name and not name.startswith("0x"):
                names[a] = name
    return names


def time_profile_analyze(trace, app_binary, seconds, limit=10, pid=None, dsym=None):
    """Time Profiler 기록(.trace) → 1초 단위 CPU %, 직접 CPU를 쓴 함수, 앱 코드 기준(부른 것 포함) 상위 목록.
    xctrace export의 XML은 같은 값을 id로 한 번 쓰고 다음부터 ref로 가리킨다 → 값을 캐시하며 한 줄씩 읽는다."""
    xml = Path(f"{trace}.xml")
    if not xctrace_export(trace, "time-profile", out=xml):
        xml.unlink(missing_ok=True)
        return None
    cache = {}

    def val(el, conv=lambda e: e.text):
        if el is None:
            return None
        if el.get("ref"):
            return cache.get(el.get("ref"))
        v = conv(el)
        if el.get("id"):
            cache[el.get("id")] = v
        return v

    loads = {}

    def binary(e):
        if e.get("name") and e.get("load-addr"):
            loads.setdefault(e.get("name"), e.get("load-addr"))
        return e.get("name") or ""

    def frame(el):
        b = el.find("binary")
        return (el.get("name") or "?", val(b, binary) or "")

    def backtrace(el):
        inner = el.find("backtrace") if el.tag == "tagged-backtrace" else el
        if inner is not el and inner is not None:
            return val(inner, lambda e: [val(fr, frame) for fr in e.findall("frame")])
        return [val(fr, frame) for fr in el.findall("frame")]

    per_sec, selfc, appc, total, t0 = {}, {}, {}, 0, None
    tree = {}   # 호출 트리: {(함수, 바이너리): [개수, {자식}]} — 바깥(시작점)에서 안쪽(실제로 CPU를 쓴 곳)으로
    try:
        for _, el in ET.iterparse(str(xml), events=("end",)):
            if el.tag != "row":
                continue
            t = val(el.find("sample-time"), lambda e: int(e.text or 0))
            w = val(el.find("weight"), lambda e: int(e.text or 0)) or 1_000_000
            bt_el = el.find("tagged-backtrace")
            bt_el = bt_el if bt_el is not None else el.find("backtrace")
            stack = val(bt_el, backtrace) if bt_el is not None else None
            proc = val(el.find("process"), lambda e: e.get("fmt") or "")
            el.clear()
            if t is None:
                continue
            if pid and proc and not proc.endswith(f"({pid})"):
                continue   # 기기 전체 녹화: 대상 앱 샘플만
            t0 = t if t0 is None else t0
            sec = int((t - t0) / 1e9)
            per_sec[sec] = per_sec.get(sec, 0) + w
            if not stack:
                continue
            total += 1
            node, prev = tree, None
            for fn_, lib_ in reversed(stack[-80:] if len(stack) > 80 else stack):   # 바깥 → 안쪽
                if fn_.startswith("0x") and lib_ != app_binary:
                    fn_ = f"({lib_} 내부)"        # 이름 없는 라이브러리 내부 함수는 이어지면 한 줄로
                if (fn_, lib_) == prev and fn_.endswith(" 내부)"):
                    continue
                prev = (fn_, lib_)
                entry = node.setdefault(prev, [0, {}])
                entry[0] += 1
                node = entry[1]
            fn, lib = stack[0]
            key = (fn if fn != "???" else f"??? ({lib})", lib)
            selfc[key] = selfc.get(key, 0) + 1
            seen = set()
            for name, b in stack:
                if b == app_binary and name not in seen and name not in SAMPLE_APP_SKIP \
                        and not name.startswith(SAMPLE_APP_SKIP_PREFIX):
                    seen.add(name)
                    appc[name] = appc.get(name, 0) + 1
    except ET.ParseError:
        pass
    finally:
        xml.unlink(missing_ok=True)
    if not total:
        return None
    # 앱 함수가 주소(0x…)로만 남았으면 dSYM으로 이름을 붙인다 (같은 함수의 여러 주소는 하나로 합친다)
    unresolved = {fn for fn, b in selfc if b == app_binary and fn.startswith("0x")} | {fn for fn in appc if fn.startswith("0x")}
    names = atos_names(dsym, loads.get(app_binary), unresolved)
    if names:
        merged_self, merged_app = {}, {}
        for (fn, lb), v in selfc.items():
            key = (names.get(fn, fn), lb)
            merged_self[key] = merged_self.get(key, 0) + v
        for fn, v in appc.items():
            merged_app[names.get(fn, fn)] = max(merged_app.get(names.get(fn, fn), 0), v)
        selfc, appc = merged_self, {fn: v for fn, v in merged_app.items()
                                     if fn not in SAMPLE_APP_SKIP and not fn.startswith(SAMPLE_APP_SKIP_PREFIX)}
    pct = lambda v: v * 100.0 / total
    rename = names if names else {}
    cpu = [per_sec.get(i, 0) / 1e7 for i in range(min(int(seconds), (max(per_sec) + 1) if per_sec else 0))]
    return {
        "cpu": cpu, "active": total, "symbolicated": bool(names) or not unresolved,
        "tree": tree, "rename": rename, "binary": app_binary,
        "self": [(fn, "앱" if lb == app_binary else lb, pct(v)) for (fn, lb), v in
                 sorted(selfc.items(), key=lambda x: -x[1])[:limit]],
        "app": [(fn, "", pct(v)) for fn, v in sorted(appc.items(), key=lambda x: -x[1])[:limit]],
    }


def activity_memory(trace, pid):
    """Activity Monitor 기록 → 앱 메모리(MB, physical footprint = Xcode 메모리 게이지와 같은 기준) 1초 단위 목록."""
    text = xctrace_export(trace, "activity-monitor-process-live")
    if "<" not in text:
        return []
    try:
        root = ET.fromstring(text[text.index("<"):])
    except ET.ParseError:
        return []
    cols = [c.findtext("mnemonic") for c in root.iter("col")]
    cache, per_sec, t0 = {}, {}, None

    def val(e):
        if e.get("ref"):
            return cache.get(e.get("ref"), (None, None))
        v = (e.text, e.get("fmt"))
        if e.get("id"):
            cache[e.get("id")] = v
        return v
    for row in root.iter("row"):
        d = dict(zip(cols, (val(c) for c in row)))
        proc = (d.get("process") or (None, ""))[1] or ""
        mem = (d.get("memory-physical-footprint") or (None, None))[0]
        start = (d.get("start") or (None, None))[0]
        if not proc.endswith(f"({pid})") or not mem or not start:
            continue
        t = int(start)
        t0 = t if t0 is None else t0
        per_sec[int((t - t0) / 1e9)] = int(mem) / 1024 / 1024
    return [per_sec[k] for k in sorted(per_sec)]


class DeviceBenchSession(threading.Thread):
    """실기기: 실행기가 '[qakit-bench] ready'를 출력하면 앱에 Time Profiler를 붙여 그 시간 동안 녹화하고 분석한다.
    (실기기 앱은 Mac 프로세스가 아니라 ps·sample을 쓸 수 없다. CPU %도 Time Profiler 샘플로 계산한다)"""

    def __init__(self, ws, seconds, base, app_binary):
        super().__init__(daemon=True)
        self.ws, self.seconds, self.base, self.app_binary = ws, seconds, base, app_binary
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.summary = None

    def on_line(self, line):
        if "[qakit-bench] ready" in line:
            self.ready.set()

    def run(self):
        while not self.ready.wait(1):
            if self.stop.is_set():
                return
        self.summary = self.measure()

    def measure(self):
        ws, seconds = self.ws, self.seconds
        pid = None
        for _ in range(10):
            pid = device_app_pid(ws)
            if pid:
                break
            time.sleep(1)
        if not pid:
            return {"error": "기기에서 실행 중인 앱을 찾지 못함"}
        info(f"📈 성능 측정 시작: {ws.device['name']} · {ws.bundle_id} (PID {pid}), {human_duration(seconds)} — Time Profiler")
        trace = Path(f"{self.base}.trace")
        log = Path(f"{self.base}-xctrace.log")

        def record(target):
            shutil.rmtree(trace, ignore_errors=True)
            # Activity Monitor를 같이 넣어 앱 메모리도 1초마다 기록한다 (Time Profiler는 메모리를 기록하지 않음)
            return subprocess.Popen(["xcrun", "xctrace", "record", "--template", "Time Profiler",
                                     "--instrument", "Activity Monitor",
                                     "--device", ws.device["udid"], *target,
                                     "--time-limit", f"{int(seconds)}s", "--output", str(trace), "--no-prompt"],
                                    stdout=open(log, "w"), stderr=subprocess.STDOUT)
        # 앱 하나에만 붙인다 (기록이 작다). 무선 연결에서는 앱을 못 찾는 경우가 있어 → 기기 전체를 녹화하고 앱 샘플만 고른다
        self.whole_device = False
        xt = record(["--attach", str(pid)])
        start, began, every = time.monotonic(), None, 1 if sys.stdout.isatty() else 15
        while xt.poll() is None or (not self.whole_device and "Cannot find process" in
                                    (log.read_text(errors="replace") if log.exists() else "")):
            text = log.read_text(errors="replace") if log.exists() else ""
            if not self.whole_device and "Cannot find process" in text:
                xt.wait()
                info("ℹ️  무선 연결이라 앱에만 붙지 못함 → 기기 전체를 녹화하고 앱 샘플만 골라냅니다 (기록이 1분에 200MB 안팎)")
                self.whole_device = True
                xt = record(["--all-processes"])
                time.sleep(1)
                continue
            now = time.monotonic()
            if began is None and "Ctrl-C to stop the recording" in text:
                began = now
            if began is None and now - start > 90:
                xt.send_signal(2)
                break
            if began is not None and "Recording completed" not in text:
                _progress(f"📈 성능 측정 중 {_mmss(min(now - began, seconds))} / {_mmss(seconds)} (Time Profiler 녹화)")
            elif "Recording completed" in text:
                _progress(f"🧹 측정 완료 → Time Profiler 저장 중 {_mmss(now - began - seconds)}")
            if now - start > seconds + 600:
                xt.send_signal(2)
                break
            time.sleep(every)
        try:
            xt.wait(timeout=120)
        except subprocess.TimeoutExpired:
            xt.kill()
            xt.wait()
        _progress("📈 성능 측정 끝", final=True)
        text = log.read_text(errors="replace") if log.exists() else ""
        result = {"pid": pid, "device": ws.device["name"]}
        if xt.returncode != 0 or not trace.exists() or began is None:
            shutil.rmtree(trace, ignore_errors=True)
            result["trace_error"] = (text.strip().splitlines() or ["(출력 없음)"])[-1]
            return result
        log.unlink(missing_ok=True)
        result["trace"] = str(trace)
        info("🔎 Time Profiler 기록에서 CPU 사용률·함수 정리 중…")
        app_path = find_built_app(ws)
        dsym = app_path.with_name(app_path.name + ".dSYM") if app_path else None
        top = time_profile_analyze(trace, self.app_binary, seconds, pid=pid if self.whole_device else None,
                                   dsym=dsym if dsym and dsym.exists() else None)
        # 녹화가 중간에 끊겼는지 (예: 무선 연결이 끊김)
        toc = run(["xcrun", "xctrace", "export", "--input", str(trace), "--toc"], check=False).stdout or ""
        dur = re.search(r"<duration>([\d.]+)</duration>", toc)
        why = re.search(r"<end-reason>([^<]+)</end-reason>", toc)
        if dur and float(dur.group(1)) < seconds * 0.9:
            result["error"] = (f"녹화가 {float(dur.group(1)):.0f}초 만에 끝남 ({why.group(1) if why else '이유 모름'})"
                               + (" — 무선 연결은 테스트와 녹화를 같이 하면 끊길 수 있음 → 케이블로 연결해 다시"
                                  if ws.device.get("transport") != "wired" else ""))
        if not top:
            result["error"] = "Time Profiler 기록에 앱 샘플이 없음"
            return result
        cpus = top["cpu"]
        mems = activity_memory(trace, pid)
        csv = Path(f"{self.base}-cpu.csv")
        csv.write_text("seconds,cpu_percent,memory_mb\n" + "".join(
            f"{i + 1},{c:.1f},{(f'{mems[i]:.1f}' if i < len(mems) else '')}\n" for i, c in enumerate(cpus)))
        if mems:
            result.update(mem_start=mems[0], mem_end=mems[-1], mem_max=max(mems))
        s = sorted(cpus)
        result.update(csv=str(csv), samples=len(cpus), cpu_avg=sum(cpus) / len(cpus), cpu_max=s[-1],
                      cpu_p95=s[min(len(s) - 1, int(len(s) * 0.95))],
                      calltree=str(write_call_tree(Path(f"{self.base}-calltree.txt"), top,
                                                   f"{ws.bundle_id} · {ws.device['name']} · {human_duration(seconds)}")),
                      top=top, top_raw=str(trace),
                      top_how="Time Profiler, 1ms 간격, 측정 전체" + (" · 무선이라 기기 전체 녹화에서 앱만 골라냄" if self.whole_device else ""))
        return result


def write_bench_summary(base, seconds, scenario, ws, s):
    where = f"실기기 {ws.device['name']} ({ws.device['model']}, iOS {ws.device['os']})" if ws.device else f"시뮬레이터 {ws.simulator}"
    lines = [f"# 성능 측정 요약", f"시나리오: {scenario}", f"앱: {ws.bundle_id} ({ws.configuration}, {ws.build}) · {where}",
             f"측정: {human_duration(seconds)} (시나리오 마지막 화면에서 그대로)", ""]
    if s.get("error"):
        lines.append(f"⚠️ {s['error']}")
    if "cpu_avg" in s:
        lines += [f"CPU 평균 {s['cpu_avg']:.1f}%  ·  p95 {s['cpu_p95']:.1f}%  ·  최대 {s['cpu_max']:.1f}%  "
                  f"(100% = 코어 1개, 샘플 {s['samples']}개)",
                  *([f"메모리 시작 {s['mem_start']:.0f}MB → 끝 {s['mem_end']:.0f}MB (최대 {s['mem_max']:.0f}MB)"]
                    if "mem_start" in s else []),
                  f"1초 단위 기록: {s['csv']}"]
    top, wins = s.get("sample_top"), s.get("sample_windows") or []
    if s.get("top"):
        top = s["top"]
        lines += ["", f"함수별 CPU ({s['top_how']}) — 샘플 {top['active']:,}개 기준", "직접 CPU를 쓴 함수 (스택 맨 위):"]
        short = lambda t: t if len(t) <= 90 else t[:87] + "…"
        lines += [f"  {pct:5.1f}%  {short(fn)}  [{lb}]" for fn, lb, pct in top["self"]]
        if top["app"]:
            lines.append("앱 코드 기준 (그 함수가 부른 것까지 포함):")
            lines += [f"  {pct:5.1f}%  {short(fn)}" for fn, _, pct in top["app"]]
        if s.get("calltree"):
            lines.append(f"호출 트리 (텍스트): {s['calltree']}")
        lines.append(f"Time Profiler 기록: {s['top_raw']} (Instruments로 열기: open <파일>)")
    elif s.get("trace_error"):
        lines += ["", f"Time Profiler 녹화 실패: {s['trace_error']}"]
    elif top:
        covered = sum(d for _, d in wins)
        how = "측정 전체" if len(wins) == 1 else f"{_mmss(SAMPLE_EVERY)}마다 {SAMPLE_WINDOW}초씩 {len(wins)}번, 합계 {human_duration(covered)}"
        lines += ["", f"함수별 CPU (sample, {SAMPLE_INTERVAL_MS}ms 간격, {how}) — 기다리는 스레드는 빼고 CPU를 쓴 샘플 {top['active']:,}개 기준",
                  "직접 CPU를 쓴 함수 (스택 맨 위):"]
        short = lambda t: t if len(t) <= 90 else t[:87] + "…"
        lines += [f"  {pct:5.1f}%  {short(fn)}  [{lb}]" for fn, lb, pct in top["self"]]
        if top["app"]:
            lines.append("앱 코드 기준 (그 함수가 부른 것까지 포함):")
            lines += [f"  {pct:5.1f}%  {short(fn)}" + (f"  — {src}" if src else "") for fn, src, pct in top["app"]]
        files = s.get("samples_files") or []
        lines.append(f"원본 호출 트리: {files[0] if len(files) == 1 else Path(files[0]).parent / 'bench-sample-*.txt'}")
    elif s.get("profile_skipped"):
        lines += ["", "함수별 CPU: 건너뜀 (" + s["profile_skipped"] + ")"]
    elif "sample_top" in s:
        lines += ["", "함수별 CPU: sample 기록을 얻지 못함"]
    lines.append("")
    lines.append("주의: 실기기 측정. Time Profiler를 붙인 동안이라 약간의 부하가 더해진다." if ws.device else
                 "주의: 시뮬레이터(Mac CPU) 측정이라 실제 기기와 절대값이 다르다. 같은 조건끼리 비교할 때 쓴다.")
    path = Path(f"{base}-summary.txt")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, lines


def _cmd_run(ws, args, name):
    prefetch_worktree(ws)
    path, scenario = load_checked_scenario(ws, name, strict=not args.no_check)
    overrides = {}
    for item in args.var or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            fail(f"--var 형식이 잘못됐습니다: {item!r}", '예) --var ship="ULTRA FOREST"')
        overrides[key.strip()] = value
    if overrides:
        scenario["vars"] = dict(scenario.get("vars") or {}, **overrides)
        info("변수: " + ", ".join(f"{k}={v}" for k, v in overrides.items()))
    if args.reuse_app:
        scenario["launch"] = "reuse"
    if scenario.get("launch") == "reuse" and not scenario.get("start"):
        warn("앱 재사용(launch: reuse)은 시나리오에 start: (시작 화면 조건)가 있어야 합니다 → 이번에는 앱을 다시 켭니다")
    out = ws.root / ".qakit" / "scenarios" / (path.name.replace(".qa.yml", "") + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(scenario_tools.to_json(scenario), encoding="utf-8")
    auto_sync(ws)
    extra = {"SCENARIO_JSON": str(out)}
    if args.reset or scenario.get("reset") is True:
        reset_app(ws, ensure_booted(ws))
        extra["RESET"] = "1"
    bench = None
    run_dir = None
    if args.bench:
        try:
            bench_seconds = int(round(parse_duration(args.bench)))
        except ValueError:
            fail(f"--bench {args.bench}: 시간에 단위를 붙이세요.",
                 "예) --bench 30s (30초) / --bench 30m (30분) / --bench 1h (1시간) / --bench 1h30m · 30초 · 5분도 됨")
        if bench_seconds < BENCH_MIN_SECONDS:
            fail(f"--bench는 {BENCH_MIN_SECONDS}초 이상이어야 합니다 (입력: {human_duration(bench_seconds)}).")
        run_dir = new_run_dir(ws, f"bench-{short_duration(bench_seconds)}", path.name.replace(".qa.yml", ""))
        base = run_dir / "bench"
        extra["BENCH_SIGNAL"] = str(base)
        extra["BENCH_SECONDS"] = str(bench_seconds)
        profile = not args.no_profile
        if ws.device:
            if ws.device.get("transport") != "wired":
                warn("무선 연결입니다. 무선에서는 Time Profiler가 앱에 붙지 못하고, 기기 전체 녹화는 테스트와 같이 돌면 "
                     "몇 초 만에 끊깁니다 (2026-11 확인) → 측정은 케이블로 연결해서 하세요. 일단 시도합니다.")
            # 실기기: CPU %와 함수 목록을 모두 Time Profiler로 잰다 (ps·sample은 Mac 프로세스에만 됨)
            if args.no_profile:
                warn("실기기는 Time Profiler로만 잴 수 있어 --no-profile을 무시합니다")
            profile = True
            extra["BENCH_SIGNAL"] = "device"
            extra["BENCH_LEAD"] = "45"   # Time Profiler가 붙는 데 걸리는 시간만큼 더 둔다
            app_path = find_built_app(ws)
            binary = "app"
            if app_path:
                with open(app_path / "Info.plist", "rb") as f:
                    binary = plistlib.load(f).get("CFBundleExecutable", binary)
            bench = DeviceBenchSession(ws, bench_seconds, base, binary)
        else:
            bench = BenchSession(ws, ensure_booted(ws), bench_seconds, base, profile=profile)
        bench.start()
        info(f"성능 측정 예약: 시나리오가 끝나면 {human_duration(bench_seconds)} 동안 "
             + ("CPU + 함수별 CPU (Time Profiler)" if ws.device else
                "CPU·메모리" + (" + 함수별 CPU(sample)" if profile else "")) + " 기록")
    info(f"시나리오 실행: {scenario.get('name')} ({path.name})")
    if not bench and not args.no_serve:
        udid = ws.device["udid"] if ws.device else ensure_booted(ws)
        if args.serve or serve_ready_for(ws, udid):
            if extra.get("RESET"):
                serve_stop(udid, quiet=True)   # 재설치로 앱 데이터 경로가 바뀌므로 실행기를 새로 띄운다
            run_via_serve(ws, udid, out, path, scenario, args.timeout)
            return
    video = RunVideo(ws, None if (bench or ws.device) else ensure_booted(ws))
    success, xcresult = False, None
    try:
        success, xcresult, _ = run_scenario_runner(ws, "test_run", extra, label="run",
                                                   on_line=bench.on_line if isinstance(bench, DeviceBenchSession) else None,
                                                   history_name=path.name.replace(".qa.yml", ""), run_dir=run_dir)
    finally:
        if bench:
            bench.stop.set()
        video_path = video.finish(success, Path(xcresult).parent if xcresult else None)
    if bench:
        # 실기기는 실행기가 끝난 뒤에도 Time Profiler 저장·분석이 남아 있을 수 있다
        bench.join(timeout=bench_seconds + 900 if ws.device else 300)
        for suffix in (".ready", ".done"):   # 실행기와 주고받은 신호 파일
            Path(f"{base}{suffix}").unlink(missing_ok=True)
        if bench.summary:
            summary_path, lines = write_bench_summary(base, bench_seconds, scenario.get("name"), ws, bench.summary)
            print()
            for line in lines[4:-1]:
                if line:
                    print("  " + line)
            ok(f"성능 측정 요약: {summary_path}")
        elif success:
            warn("성능 측정이 시작되지 않았습니다 (시나리오가 측정 단계까지 가지 못함)")
    print()
    if success:
        ok(f"통과 — 결과: {xcresult}")
        return
    text = summarize(xcresult, masker(ws.secrets()))
    if video_path:
        text += f"\n   영상 (마지막 {RunVideo.KEEP_SECONDS}초): {video_path}"
    print(text)
    cause = re.search(r"원인: (.*)", text)
    last = re.search(r"마지막 단계:\s*(?:\n\s*-\s*)?(.*)", text)
    if cause:
        LAST_FAILURE["sig"] = (cause.group(1).strip(), last.group(1).strip() if last else "")
        LAST_FAILURE["message"] = cause.group(1).strip()
    if not Path(xcresult).exists():   # 실행기가 테스트를 시작하지 못함 (빌드·설치·연결)
        fail("실패 (실행 환경 문제: 결과 파일 없음)", f"로그: {Path(xcresult).parent / 'output.log'}", code=2)
    fail("실패", f"자세한 결과: {xcresult}", code=1)


