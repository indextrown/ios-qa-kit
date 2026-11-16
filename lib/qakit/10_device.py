# qakit — 시뮬레이터·실기기
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 시뮬레이터 ───────────────────────────────

def simulator_udid(name_or_udid):
    data = json.loads(run(["xcrun", "simctl", "list", "devices", "available", "-j"]).stdout)
    candidates = []
    for runtime, devices in data["devices"].items():
        if "iOS" not in runtime:
            continue
        for d in devices:
            if d["udid"] == name_or_udid:
                return d["udid"], d["state"]
            if d["name"] == name_or_udid:
                candidates.append((runtime, d))
    if not candidates:
        return None, None
    runtime, d = sorted(candidates, key=lambda c: c[0])[-1]  # 가장 최신 iOS
    return d["udid"], d["state"]


BOOTED = {}


def ensure_booted(ws):
    """시뮬레이터 udid (꺼져 있으면 부팅). 한 번 실행 안에서는 재사용한다."""
    if ws.platform == "android":   # 안드로이드: 에뮬레이터 serial (꺼져 있으면 띄움)
        key = "android:" + ws.emulator
        if key not in BOOTED:
            BOOTED[key] = android_serial(ws.emulator)
        return BOOTED[key]
    if ws.simulator not in BOOTED:
        BOOTED[ws.simulator] = _ensure_booted(ws)
    return BOOTED[ws.simulator]


def _ensure_booted(ws):
    udid, state = simulator_udid(ws.simulator)
    if not udid:
        fail(f"시뮬레이터 '{ws.simulator}'를 찾지 못했습니다.",
             "xcrun simctl list devices available 로 이름을 확인하고 qakit.yml의 simulator를 고치세요.")
    if state != "Booted":
        info(f"시뮬레이터 부팅 중: {ws.simulator}")
        run(["xcrun", "simctl", "boot", udid], check=False)
        run(["xcrun", "simctl", "bootstatus", udid, "-b"])
    return udid


@contextlib.contextmanager
def sim_lock(ws, what):
    """시뮬레이터 하나에 qakit 실행은 한 번에 하나만. 두 실행이 같은 앱을 동시에 조작하면 입력이 섞인다.
    다른 실행이 있으면 누가 돌리는지 알려 주고 끝날 때까지 기다린다."""
    udid = ws.device["udid"] if ws.device else ensure_booted(ws)
    lock_dir = Path.home() / ".qakit" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / f"{udid}.lock"
    f = open(path, "a+")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            holder = f.read().strip() or "다른 qakit 실행"
            warn(f"이 {'기기' if ws.device else '시뮬레이터'}에서 다른 실행이 진행 중입니다 → 끝날 때까지 기다립니다\n   ({holder})")
            fcntl.flock(f, fcntl.LOCK_EX)
            ok("앞선 실행이 끝났습니다. 시작합니다.")
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()} · {what} · {ws.root} · {datetime.datetime.now():%H:%M:%S} 시작")
        f.flush()
        yield udid
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def app_installed(udid, bundle_id):
    r = run(["xcrun", "simctl", "get_app_container", udid, bundle_id], check=False)
    return r.returncode == 0


# ─────────────────────────────── 실기기 (--device) ───────────────────────────────
# 같은 네트워크(또는 케이블)로 연결된 iPhone/iPad에서 시나리오를 돌린다.
# 시뮬레이터와 다른 점: 앱·실행기를 개발자 팀으로 서명, AutoID dylib을 앱 안(Frameworks/)에 넣고 다시 서명,
# devicectl로 설치. Mac 파일을 읽고 쓸 수 없어 시나리오는 내용째(base64) 넘기고 결과는 테스트 첨부로 받는다.

DEVICE_AUTOID_PATH = "@executable_path/Frameworks/QAAutoID.dylib"


def list_devices():
    """devicectl이 아는 iOS 기기 목록 (페어링된 것)."""
    out = Path(tempfile.mkstemp(suffix=".json")[1])
    try:
        run(["xcrun", "devicectl", "list", "devices", "--json-output", str(out)], check=False)
        data = json.loads(out.read_text() or "{}")
    except (OSError, ValueError):
        data = {}
    finally:
        out.unlink(missing_ok=True)
    devices = []
    for d in (data.get("result") or {}).get("devices", []):
        hw, dp, cp = d.get("hardwareProperties", {}), d.get("deviceProperties", {}), d.get("connectionProperties", {})
        if hw.get("platform") not in ("iOS", "iPadOS") or not hw.get("udid"):
            continue
        state = cp.get("tunnelState") or "unavailable"
        transport = cp.get("transportType")
        devices.append({
            "name": dp.get("name") or hw.get("marketingName") or d.get("identifier"),
            "id": d.get("identifier"), "udid": hw.get("udid"),
            "model": hw.get("marketingName") or "", "os": dp.get("osVersionNumber") or "",
            "state": state, "transport": transport,
            "developerMode": dp.get("developerModeStatus") == "enabled",
            "available": state != "unavailable",
        })
    return devices


def device_status_text(d):
    if not d["available"]:
        return "연결 안 됨"
    if d["state"] == "connected":
        return "케이블 연결됨" if d["transport"] == "wired" else "무선 연결됨"
    return "같은 네트워크 (실행할 때 연결)"


def _last_device_file(ws):
    return ws.state_dir / "device.json"


def pick_from_list(title, rows, start=0):
    """방향키로 고르는 목록. rows = [(글자, 선택 가능)]. 고른 번호 또는 None(취소)."""
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    idx = start if rows[start][1] else next((i for i, r in enumerate(rows) if r[1]), 0)
    out = sys.stdout

    def draw(first):
        if not first:
            out.write(f"\x1b[{len(rows) + 2}F")
        out.write(f"\x1b[J{title}  (↑↓ 이동 · Enter 선택 · Esc 취소)\r\n\r\n")
        for i, (text, enabled) in enumerate(rows):
            if i == idx:
                out.write(f"  \x1b[1;36m❯ {text}\x1b[0m\r\n")
            elif not enabled:
                out.write(f"    \x1b[2m{text}\x1b[0m\r\n")
            else:
                out.write(f"    {text}\r\n")
        out.flush()

    def move(step):
        nonlocal idx
        for _ in range(len(rows)):
            idx = (idx + step) % len(rows)
            if rows[idx][1]:
                return

    try:
        tty.setraw(fd)
        out.write("\x1b[?25l")
        draw(True)
        while True:
            ch = os.read(fd, 1)
            if ch in (b"\r", b"\n"):
                return idx
            if ch in (b"q", b"\x03"):
                return None
            if ch == b"\x1b":
                seq = os.read(fd, 2) if select_ready(fd) else b""
                if seq == b"[A":
                    move(-1)
                elif seq == b"[B":
                    move(1)
                elif not seq:
                    return None
            elif ch in (b"k",):
                move(-1)
            elif ch in (b"j",):
                move(1)
            elif ch.isdigit() and 1 <= int(ch) <= len(rows) and rows[int(ch) - 1][1]:
                idx = int(ch) - 1
            draw(False)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        out.write("\x1b[?25h")
        out.flush()


def text_width(text):
    """터미널에 보이는 폭 (한글 등 넓은 글자는 2칸)."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(text))


def pad(text, width):
    return str(text) + " " * max(1, width - text_width(text))


def select_ready(fd, timeout=0.05):
    import select
    return bool(select.select([fd], [], [], timeout)[0])


def choose_device(ws, arg):
    """--device 값 → 기기 dict, 또는 None(시뮬레이터). select: 방향키 목록 / last: 지난번 기기 / 이름·UDID."""
    devices = list_devices()
    last = {}
    try:
        last = json.loads(_last_device_file(ws).read_text())
    except (OSError, ValueError):
        pass
    arg = str(arg).strip()
    if arg in ("select", "list", "?"):
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            listing = "\n   ".join(f"{d['name']}  ({d['model']}, iOS {d['os']}, {device_status_text(d)})" for d in devices)
            fail("--device select는 터미널에서만 고를 수 있습니다.",
                 f'--device "<이름>"으로 지정하세요. 기기 목록:\n   {listing or "(페어링된 기기 없음)"}')
        devices.sort(key=lambda d: (not d["available"], d["udid"] != last.get("udid"), d["name"]))
        ready = [d for d in devices if d["available"]]
        sim = {"name": "시뮬레이터", "model": ws.simulator, "sim": True}
        order = ready + [sim] + [d for d in devices if not d["available"]]   # 연결 안 된 기기는 맨 아래
        name_w = max(text_width(d["name"]) for d in order) + 2
        model_w = max(text_width(d["model"]) for d in order) + 2
        rows = []
        for d in order:
            head = pad(d["name"], name_w) + pad(d["model"], model_w)
            if d.get("sim"):
                rows.append((head + "(qakit.yml의 simulator)", True))
                continue
            tag = "   ← 지난번" if d["udid"] == last.get("udid") else ""
            rows.append((head + pad(f"iOS {d['os']}", 13) + device_status_text(d) + tag, d["available"]))
        devices = order
        choice = pick_from_list("실행할 기기를 고르세요", rows)
        if choice is None:
            fail("취소했습니다.")
        if devices[choice].get("sim"):
            return None
        device = devices[choice]
    elif arg == "last":
        device = next((d for d in devices if d["udid"] == last.get("udid")), None)
        if not device:
            fail("지난번에 고른 기기가 없거나 지금 목록에 없습니다.", "--device select로 고르세요")
    else:
        key = arg.lower()
        matches = [d for d in devices if key in (d["udid"].lower(), (d["id"] or "").lower(), d["name"].lower())]
        matches = matches or [d for d in devices if key in d["name"].lower()]
        if len(matches) != 1:
            listing = "\n   ".join(d["name"] for d in devices) or "(페어링된 기기 없음)"
            fail(f"기기 '{arg}'를 " + ("찾지 못했습니다." if not matches else "하나로 정하지 못했습니다."),
                 f"이름을 정확히 쓰거나 --device select로 고르세요. 기기 목록:\n   {listing}")
        device = matches[0]
    if not device["available"]:
        fail(f"{device['name']}이(가) 연결돼 있지 않습니다.",
             "기기 잠금을 풀고 Mac과 같은 Wi-Fi에 있는지 확인하세요 (처음엔 케이블로 한 번 연결해 Xcode에서 페어링)")
    if not device["developerMode"]:
        fail(f"{device['name']}의 개발자 모드가 꺼져 있습니다.", "기기에서 설정 › 개인정보 보호 및 보안 › 개발자 모드를 켜세요")
    ws.state_dir.mkdir(exist_ok=True)
    _last_device_file(ws).write_text(json.dumps({"udid": device["udid"], "name": device["name"]}, ensure_ascii=False))
    info(f"📱 실기기: {device['name']} ({device['model']}, iOS {device['os']}, {device_status_text(device)})")
    return device


def device_team(ws):
    """서명할 개발자 팀: qakit.yml device.team → 앱 빌드 설정의 DEVELOPMENT_TEAM (기억해 둔다)."""
    cfg = ws.cfg.get("device") or {}
    if isinstance(cfg, dict) and cfg.get("team"):
        return str(cfg["team"])
    cache = ws.state_dir / "device-team.json"
    key = f"{ws.project}|{ws.scheme}|{ws.configuration}"
    try:
        data = json.loads(cache.read_text())
        if data.get("key") == key and data.get("team"):
            return data["team"]
    except (OSError, ValueError):
        pass
    r = run(["xcodebuild", "-showBuildSettings", *project_flag(ws.project), "-scheme", ws.scheme,
             "-configuration", ws.configuration, "-destination", "generic/platform=iOS"], check=False)
    team = next((l.split("=", 1)[1].strip() for l in (r.stdout or "").splitlines()
                 if l.strip().startswith("DEVELOPMENT_TEAM =")), "")
    if not team:
        fail("실기기 서명에 쓸 개발자 팀을 찾지 못했습니다.", "qakit.yml에 device: { team: <팀 ID> }를 적으세요")
    ws.state_dir.mkdir(exist_ok=True)
    cache.write_text(json.dumps({"key": key, "team": team}))
    return team


def embed_autoid(app_path, dylib):
    """AutoID dylib을 앱의 Frameworks/에 넣고 앱과 같은 인증서·권한으로 다시 서명한다."""
    r = run(["codesign", "-dvvv", str(app_path)], check=False)
    identity = next((l.split("=", 1)[1] for l in (r.stdout or "").splitlines() if l.startswith("Authority=")), None)
    if not identity:
        fail(f"{app_path.name}의 서명 인증서를 읽지 못했습니다.", "Xcode에서 이 앱을 기기로 한 번 실행해 서명을 확인하세요")
    ent = Path(tempfile.mkstemp(suffix=".plist")[1])
    try:
        # stdout만 (stderr의 "Executable=…" 줄이 섞이면 plist가 깨진다)
        ent.write_bytes(subprocess.run(["codesign", "-d", "--entitlements", "-", "--xml", str(app_path)],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout or b"")
        fw = app_path / "Frameworks"
        fw.mkdir(exist_ok=True)
        shutil.copy2(dylib, fw / "QAAutoID.dylib")
        run(["codesign", "--force", "--sign", identity, str(fw / "QAAutoID.dylib")])
        sign = ["codesign", "--force", "--sign", identity, "--generate-entitlement-der"]
        if ent.stat().st_size > 0:
            sign += ["--entitlements", str(ent)]
        run(sign + [str(app_path)])
    finally:
        ent.unlink(missing_ok=True)


def device_install(ws, app_path):
    run(["xcrun", "devicectl", "device", "install", "app", "--device", ws.device["id"], str(app_path)])


def device_app_installed(ws):
    r = run(["xcrun", "devicectl", "device", "info", "apps", "--device", ws.device["id"],
             "--bundle-id", ws.bundle_id], check=False)
    return r.returncode == 0 and ws.bundle_id in (r.stdout or "")


def device_app_pid(ws):
    """기기에서 실행 중인 대상 앱의 PID (앱 설치 경로로 찾는다 — 이름이 같은 다른 앱과 구분)."""
    def devicectl_json(*cmd):
        out = Path(tempfile.mkstemp(suffix=".json")[1])
        try:
            run(["xcrun", "devicectl", "device", "info", *cmd, "--device", ws.device["id"],
                 "--json-output", str(out)], check=False)
            return json.loads(out.read_text() or "{}").get("result") or {}
        except (OSError, ValueError):
            return {}
        finally:
            out.unlink(missing_ok=True)
    apps = devicectl_json("apps", "--bundle-id", ws.bundle_id).get("apps") or []
    url = (apps[0].get("url") if apps else "") or ""
    prefix = url.replace("file://", "").rstrip("/").replace("/private/var/", "/var/")
    if not prefix:
        return None
    for p in devicectl_json("processes").get("runningProcesses") or []:
        exe = (p.get("executable") or "").replace("file://", "").replace("/private/var/", "/var/")
        if exe.startswith(prefix + "/"):
            return p.get("processIdentifier")
    return None


def ensure_device_runner(team):
    """시나리오 실행기를 실기기용으로 서명해서 빌드한다 (도구·팀이 바뀌었을 때만)."""
    build = KIT_DIR / ".build" / f"scenario-runner-device-{team}"
    h = hashlib.sha1(team.encode())
    for base in (KIT_DIR / "Sources" / "QAKit", KIT_DIR / "ScenarioRunner"):
        for f in sorted(base.rglob("*")):
            if f.is_file() and ".xcodeproj" not in str(f):
                h.update(str(f.relative_to(KIT_DIR)).encode())
                h.update(f.read_bytes())
    h.update(run(["xcodebuild", "-version"], check=False).stdout.encode())
    stamp = build / ".stamp"
    found = list((build / "Build" / "Products").glob("*iphoneos*.xctestrun"))
    if found and stamp.exists() and stamp.read_text() == h.hexdigest():
        return found[0]
    info("시나리오 실행기 빌드 중 (실기기용, 도구가 바뀌었을 때 한 번)...")
    run(["xcodegen", "generate", "--quiet", "--spec", str(KIT_DIR / "ScenarioRunner" / "project.yml"),
         "--project", str(KIT_DIR / "ScenarioRunner")])
    r = run(["xcodebuild", "build-for-testing", "-project", str(SCENARIO_PROJECT), "-scheme", "ScenarioTests",
             "-destination", "generic/platform=iOS", "-derivedDataPath", str(build),
             "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_STYLE=Automatic", f"DEVELOPMENT_TEAM={team}",
             "-allowProvisioningUpdates"], check=False)
    if r.returncode != 0:
        errors = [l for l in (r.stdout or "").splitlines() if "error:" in l]
        fail("시나리오 실행기 빌드 실패 (실기기)", "\n   ".join(dict.fromkeys(errors[:10])))
    stamp.write_text(h.hexdigest())
    return list((build / "Build" / "Products").glob("*iphoneos*.xctestrun"))[0]


def device_file_path(name):
    """실기기 첨부 이름 → 결과 폴더 기준 경로. qakit 첨부가 아니면 None.
    새 형식: qakit-file-<경로 16진수>. 예전 형식: qakit-file:<경로>, 그리고 xcresulttool이 ':'·'/'를 지운 qakit-filedumps<이름>."""
    name = re.sub(r"_\d+_[0-9A-F-]{36}(\.\w+)?$", "", name)   # xcresult가 붙인 꼬리 제거
    if name.endswith(".txt"):
        name = name[:-4]
    m = re.fullmatch(r"qakit-file-([0-9a-f]+)", name)
    if m:
        try:
            rel = bytes.fromhex(m.group(1)).decode("utf-8")
        except ValueError:
            return None
    elif name.startswith("qakit-file:"):
        rel = name[len("qakit-file:"):]
    elif name.startswith("qakit-filedumps"):
        rel = "dumps/" + name[len("qakit-filedumps"):]
    elif name == "qakit-fileui-dump":
        rel = "ui-dump.txt"
    else:
        return None
    return rel if rel.endswith(".txt") else rel + ".txt"


def extract_device_files(ws, xcresult, run_dir):
    """실기기 실행기가 첨부로 남긴 파일(qakit-file-<경로 16진수>)을 결과 폴더로 꺼낸다 (덤프 등)."""
    dest = Path(tempfile.mkdtemp())
    try:
        r = run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(xcresult),
                 "--output-path", str(dest)], check=False)
        manifest = dest / "manifest.json"
        if r.returncode != 0 or not manifest.exists():
            return
        mask = masker(ws.secrets())
        for entry in json.loads(manifest.read_text()):
            for a in entry.get("attachments", []):
                rel = device_file_path(a.get("suggestedHumanReadableName", ""))
                if not rel:
                    continue
                if Path(rel).is_absolute() or ".." in Path(rel).parts:
                    continue
                for target in (ws.results_dir / rel, run_dir / rel):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(mask((dest / a["exportedFileName"]).read_text(encoding="utf-8", errors="replace")),
                                      encoding="utf-8")
    finally:
        shutil.rmtree(dest, ignore_errors=True)




