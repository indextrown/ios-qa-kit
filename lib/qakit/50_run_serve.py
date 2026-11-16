# qakit — 시나리오 실행·상주 실행기·run·check·coverage
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── 시나리오 실행 (파일만으로) ───────────────────────────────

def scenario_runner_source_hash():
    """실행기 소스(QAKit + ScenarioRunner)의 해시. Xcode 버전은 빼서 빠르다 (상주 실행기의 재시작 판단용)."""
    h = hashlib.sha1()
    for base in (KIT_DIR / "Sources" / "QAKit", KIT_DIR / "ScenarioRunner"):
        for f in sorted(base.rglob("*")):
            if f.is_file() and ".xcodeproj" not in str(f):
                h.update(str(f.relative_to(KIT_DIR)).encode())
                h.update(f.read_bytes())
    return h.hexdigest()


def runner_source_hash(ws):
    return android_runner_hash() if ws.platform == "android" else scenario_runner_source_hash()


def ensure_scenario_runner(udid):
    """도구의 범용 시나리오 실행기를 필요할 때만 빌드한다 (앱마다 프로젝트를 만들지 않음)."""
    h = hashlib.sha1(scenario_runner_source_hash().encode())
    h.update(run(["xcodebuild", "-version"], check=False).stdout.encode())
    stamp = SCENARIO_BUILD / ".stamp"
    xctestruns = list((SCENARIO_BUILD / "Build" / "Products").glob("*.xctestrun"))
    if xctestruns and stamp.exists() and stamp.read_text() == h.hexdigest():
        return xctestruns[0]
    info("시나리오 실행기 빌드 중 (도구가 바뀌었을 때 한 번)...")
    runner = scenario_runner_src()
    run(["xcodegen", "generate", "--quiet", "--spec", str(runner / "project.yml"), "--project", str(runner)])
    r = run(["xcodebuild", "build-for-testing", "-project", str(runner / "QAScenarioRunner.xcodeproj"), "-scheme", "ScenarioTests",
             "-destination", f"id={udid}", "-derivedDataPath", str(SCENARIO_BUILD)], check=False)
    if r.returncode != 0:
        errors = [l for l in (r.stdout or "").splitlines() if "error:" in l]
        fail("시나리오 실행기 빌드 실패", "\n   ".join(dict.fromkeys(errors[:10])))
    stamp.write_text(h.hexdigest())
    return list((SCENARIO_BUILD / "Build" / "Products").glob("*.xctestrun"))[0]


# ─────────────────────────────── 상주 실행기 (docs/PLAN.md) ───────────────────────────────

SERVE_DIR = Path.home() / ".qakit" / "serve"


def serve_state_file(udid):
    return SERVE_DIR / f"{udid}.json"


def serve_load(udid):
    try:
        return json.loads(serve_state_file(udid).read_text())
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


class ServeTimeout(Exception):
    pass


USBMUXD_SOCKET = "/var/run/usbmuxd"


def _usbmux_call(msg, timeout=5):
    """usbmuxd에 plist 메시지 하나를 보내고 (소켓, 응답)을 돌려준다. Connect가 성공하면 그 소켓이 곧 기기 포트와의 연결이다."""
    import plistlib
    import socket
    import struct
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(USBMUXD_SOCKET)
        body = plistlib.dumps(dict(msg, ClientVersionString="qakit", ProgName="qakit"))
        sock.sendall(struct.pack("<IIII", 16 + len(body), 1, 8, 1) + body)   # 길이, 버전 1, plist 메시지, tag
        head = b""
        while len(head) < 16:
            chunk = sock.recv(16 - len(head))
            if not chunk:
                raise ConnectionError("usbmuxd 연결이 끊김")
            head += chunk
        size = struct.unpack("<IIII", head)[0] - 16
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("usbmuxd 연결이 끊김")
            data += chunk
        return sock, plistlib.loads(data)
    except OSError as e:
        sock.close()
        raise ConnectionError(f"usbmuxd: {e}")


def usbmux_device_id(udid):
    """usbmuxd가 보는 기기 번호. 없으면 None (USB로 연결 안 됨)."""
    sock, res = _usbmux_call({"MessageType": "ListDevices"})
    sock.close()
    want = udid.replace("-", "").lower()
    for d in res.get("DeviceList", []):
        props = d.get("Properties", {})
        if str(props.get("SerialNumber", "")).replace("-", "").lower() == want:
            return d.get("DeviceID")
    return None


def usbmux_connect(udid, port, timeout):
    """기기 안 127.0.0.1:<port>로 가는 연결 (usbmuxd 포트 전달, iproxy와 같은 방식)."""
    import struct
    device_id = usbmux_device_id(udid)
    if device_id is None:
        raise ConnectionError("usbmuxd에 기기가 없음 (USB로 연결하고 잠금을 풀어 주세요)")
    big_endian_port = struct.unpack("<H", struct.pack(">H", int(port)))[0]
    sock, res = _usbmux_call({"MessageType": "Connect", "DeviceID": device_id, "PortNumber": big_endian_port})
    if res.get("Number") != 0:
        sock.close()
        raise ConnectionError(f"기기 포트 {port}에 연결 거부 (usbmuxd {res.get('Number')})")
    sock.settimeout(timeout)
    return sock


def device_tunnel_address(udid):
    """CoreDevice 터널의 기기 쪽 IPv6 주소 (Wi-Fi 실기기). 터널이 없으면 None. devicectl 명령을 한 번 보내면 터널이 열린다."""
    out = Path(tempfile.mkstemp(suffix=".json")[1])
    try:
        run(["xcrun", "devicectl", "list", "devices", "--json-output", str(out)], check=False)
        for d in json.loads(out.read_text()).get("result", {}).get("devices", []):
            if d.get("hardwareProperties", {}).get("udid") == udid or d.get("identifier") == udid:
                c = d.get("connectionProperties", {})
                if c.get("tunnelState") == "connected" and c.get("tunnelIPAddress"):
                    return c["tunnelIPAddress"]
    except (OSError, ValueError):
        pass
    finally:
        out.unlink(missing_ok=True)
    return None


def serve_request(st, path, body=None, timeout=120):
    """상주 실행기에 요청. 응답 JSON. 제한 시간을 넘기면 ServeTimeout, 연결 실패는 ConnectionError.
    시뮬레이터는 Mac의 127.0.0.1, USB 실기기(st["usbmux"])는 usbmuxd로 기기 안 127.0.0.1,
    Wi-Fi 실기기(st["host"])는 CoreDevice 터널의 기기 주소로 붙는다."""
    import http.client
    import socket

    class MuxConnection(http.client.HTTPConnection):
        def connect(self):
            self.sock = usbmux_connect(st["usbmux"], st["port"], timeout)

    data = json.dumps(body if body is not None else {}, ensure_ascii=False).encode()
    conn = (MuxConnection if st.get("usbmux") else http.client.HTTPConnection)(
        st.get("host") or "127.0.0.1", st["port"], timeout=timeout)
    try:
        conn.request("POST", path, body=data,
                     headers={"X-Qakit-Token": st["token"], "Content-Type": "application/json"})
        r = conn.getresponse()
        raw = r.read().decode("utf-8")
        try:
            return android_convert_response(json.loads(raw))
        except ValueError:
            return {"ok": False, "message": f"HTTP {r.status}"}
    except (socket.timeout, TimeoutError):
        raise ServeTimeout(path)
    except (OSError, http.client.HTTPException) as e:
        raise ConnectionError(str(e) or type(e).__name__)
    finally:
        conn.close()


def serve_alive(st):
    if not st or not _pid_alive(st.get("pid")):
        return False
    try:
        return bool(serve_request(st, "/ping", timeout=10).get("ok"))
    except (ServeTimeout, ConnectionError):
        return False


def serve_stop(udid, reason=None, quiet=False, force=False):
    """상주 실행기를 멈춘다. 없으면 아무것도 안 한다. force: 응답 없는 실행기 — 정상 종료를 기다리지 않고 바로 끝낸다."""
    st = serve_load(udid)
    if not st:
        return False
    pid = st.get("pid")
    if _pid_alive(pid):
        if reason and not quiet:
            info(f"상주 실행기를 멈춥니다 ({reason}와 같은 기기를 쓰므로)")
        if not force:
            try:
                serve_request(st, "/stop", timeout=10)
            except (ServeTimeout, ConnectionError):
                pass
        for _ in range(0 if force else 30):
            if not _pid_alive(pid):
                break
            time.sleep(1)
        if _pid_alive(pid):
            try:
                os.killpg(int(pid), 15)   # start_new_session으로 띄웠으므로 프로세스 그룹째
            except OSError:
                pass
    if st.get("platform") == "android":
        android_runner_kill(udid)   # 기기 안 실행기까지 (호스트 adb만 끝나면 기기에 남는다)
    serve_state_file(udid).unlink(missing_ok=True)
    return True


def serve_start(ws, udid, idle=1800, launch=True):
    """test_serve를 백그라운드로 띄우고 포트·토큰을 받을 때까지 기다린다."""
    if ws.platform == "android":
        return android_serve_start(ws, udid, idle=idle, launch=launch)
    SERVE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_autoid(ws)
    token = hashlib.sha1(os.urandom(32)).hexdigest()
    extra = {"SERVE_TOKEN": token, "SERVE_IDLE": int(idle), "SERVE_LAUNCH": "1" if launch else "0"}
    ready_file = SERVE_DIR / f"{udid}.runner.json"
    ready_file.unlink(missing_ok=True)
    transport = {}
    if ws.device:
        # 기기 안 실행기는 Mac 파일에 못 쓴다 → 포트를 Mac이 정하고, 준비는 /ping 해서 안다.
        # USB면 usbmuxd로 기기 안 127.0.0.1에, Wi-Fi면 CoreDevice 터널의 기기 주소에만 열고 그 주소로 붙는다.
        if not device_app_installed(ws):
            fail(f"{ws.device['name']}에 {ws.bundle_id}가 설치되어 있지 않습니다.", "qakit build-app --device ...")
        xctestrun = ensure_device_runner(device_team(ws))
        device_port = 20000 + int.from_bytes(os.urandom(2), "big") % 20000
        extra["SERVE_PORT"] = device_port
        if usbmux_device_id(udid) is not None:
            transport = {"usbmux": udid}
        else:
            tunnel = device_tunnel_address(udid)
            if not tunnel:
                fail(f"{ws.device['name']}에 연결할 길이 없습니다 (USB 아님, CoreDevice 터널 없음).",
                     "USB로 연결하거나, 같은 Wi-Fi에서 잠금을 풀고 다시 실행하세요")
            extra["SERVE_HOST"] = tunnel
            transport = {"host": tunnel}
            info(f"Wi-Fi 연결: CoreDevice 터널 {tunnel}")
    else:
        if not app_installed(udid, ws.bundle_id):
            fail(f"시뮬레이터에 {ws.bundle_id}가 설치되어 있지 않습니다.", "qakit build-app")
        xctestrun = ensure_scenario_runner(udid)
        extra["SERVE_STATE"] = ready_file
        prefs = app_prefs_path(udid, ws.bundle_id)
        if prefs:
            extra["APP_PREFS"] = prefs
    xcresult = SERVE_DIR / f"{udid}.xcresult"
    shutil.rmtree(xcresult, ignore_errors=True)
    log = SERVE_DIR / f"{udid}.log"
    cmd = ["xcodebuild", "test-without-building", "-xctestrun", str(xctestrun), "-destination", f"id={udid}",
           "-resultBundlePath", str(xcresult), "-only-testing", "ScenarioTests/ScenarioTests/test_serve"]
    info("상주 실행기 시작 중 (앱 실행 포함 1분 안팎)...")
    started_at = time.time()
    with open(log, "w") as out:
        proc = subprocess.Popen(cmd, env=test_env(ws, extra), stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)
    wait = 240 if ws.device else 180   # 실기기는 실행기 설치·실행이 더 걸린다
    deadline = time.time() + wait
    probe = dict(transport, port=extra.get("SERVE_PORT"), token=token) if ws.device else None
    while time.time() < deadline:
        if probe:
            try:
                if serve_request(probe, "/ping", timeout=5).get("ok"):
                    ready_file.write_text(json.dumps({"port": probe["port"], "token": token}))
                    break
            except (ServeTimeout, ConnectionError):
                pass
        elif ready_file.exists() and ready_file.stat().st_size:
            break
        if proc.poll() is not None:
            lines = log.read_text(errors="replace").splitlines()
            kept = SERVE_DIR / f"{udid}.failed.log"   # 다음 시작이 로그를 덮어써도 원인을 볼 수 있게
            shutil.copyfile(log, kept)
            # 실행기 메시지·오류 줄을 먼저, 그다음 끝부분
            key = [l for l in lines if "[qakit-serve]" in l or "error" in l.lower() or "failed" in l.lower()][-10:]
            tail = "\n   ".join(dict.fromkeys(key + lines[-10:]))
            fail("상주 실행기가 시작되지 않았습니다. 다시 실행하면 새로 띄웁니다.", (tail or "") + f"\n   전체 로그: {kept}")
        time.sleep(0.5)
    else:
        os.killpg(proc.pid, 15)
        fail(f"상주 실행기가 {wait}초 안에 준비되지 않았습니다.", f"로그: {log}")
    runner = json.loads(ready_file.read_text())
    st = {"udid": udid, "pid": proc.pid, "port": runner["port"], "token": runner["token"],
          "workspace": str(ws.root), "bundleId": ws.bundle_id, "runnerHash": scenario_runner_source_hash(),
          "attachOnly": not launch,   # 앱을 켜지 않고 붙기만 (화면 구조 읽기·조건 확인만 — serve --no-launch)
          "started": datetime.datetime.now().isoformat(timespec="seconds"), "log": str(log)}
    st.update(transport)
    serve_state_file(udid).write_text(json.dumps(st, ensure_ascii=False, indent=2))
    ok(f"상주 실행기 준비됨 (포트 {st['port']}, {time.time() - started_at:.0f}초)")
    return st


def serve_ready_for(ws, udid):
    """이 작업공간용 상주 실행기가 지금 바로 쓸 수 있게 떠 있는가 (qakit run이 자동으로 서버를 쓸지)."""
    st = serve_load(udid)
    return bool(st and st.get("workspace") == str(ws.root)
                and st.get("runnerHash") == runner_source_hash(ws) and serve_alive(st))


SERVE_SUMMARY = "summary.txt"   # 상주 실행기로 돈 run의 요약 (xcresult 대신)


def save_serve_files(ws, res, run_dir=None):
    """상주 실행기 응답의 파일(실기기 시나리오 dump: 단계)을 xcodebuild 경로와 같은 곳에 쓴다. 쓴 경로 목록."""
    mask = masker(ws.secrets())
    written = []
    for rel, content in (res.get("files") or {}).items():
        rel = rel if rel.endswith(".txt") else rel + ".txt"
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            continue
        for target in [ws.results_dir / rel] + ([run_dir / rel] if run_dir else []):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(mask(content), encoding="utf-8")
        written.append(ws.results_dir / rel)
    return written


def timing_summary(timings):
    """실행기 안 시간 나누기: 앱 실행 / 단계 / 그중 끼어드는 화면 확인, 오래 걸린 단계 (output.log·QAKIT_TIMING)."""
    rows = [r for r in timings or [] if r]
    launch = sum(r["seconds"] for r in rows if r.get("kind") == "launch")
    steps = sum(r["seconds"] for r in rows if r.get("kind") != "launch" and r.get("depth") == 0)
    interrupts = sum(r.get("interrupts", 0) for r in rows if r.get("kind") == "step")
    head = f"앱 실행 {launch:.1f}초 · 단계 {steps:.1f}초 (그중 끼어드는 화면 확인 {interrupts:.1f}초)"
    slow = sorted((r for r in rows if r.get("kind") == "step"), key=lambda r: -r["seconds"])[:5]
    lines = [f"  {r['seconds']:5.1f}초  {r['name'][:90]}" for r in slow]
    detail = [f"  {'  ' * r.get('depth', 0)}{r['seconds']:5.1f}초  {r['name'][:90]}"
              + (f"  (끼어드는 화면 {r['interrupts']:.1f}초)" if r.get("interrupts") else "") for r in rows]
    return head, lines, detail


def run_via_serve(ws, udid, scenario_json, path, scenario, timeout):
    """qakit run을 상주 실행기로. 결과 폴더·latest·실행 기록·실패 요약은 xcodebuild 경로와 같은 모양으로 남긴다."""
    mask = masker(ws.secrets())
    name = path.name.replace(".qa.yml", "")
    st = serve_ensure(ws, udid)
    rd = new_run_dir(ws, "run", name)
    info("상주 실행기로 실행 (xcodebuild 준비 생략)")
    video = RunVideo(ws, None if ws.device else udid)
    log_since = android_device_time(udid) if ws.platform == "android" else None
    started = time.time()
    try:
        res = serve_request(st, "/run", json.loads(scenario_json.read_text(encoding="utf-8")), timeout=timeout)
    except ServeTimeout:
        serve_stop(udid, quiet=True, force=True)
        res = {"ok": False, "env": True, "message": f"{timeout}초 안에 끝나지 않아 상주 실행기를 멈춤 (다음 실행 때 다시 띄움)"}
    except ConnectionError as e:
        serve_stop(udid, quiet=True, force=True)
        res = {"ok": False, "env": True, "message": f"상주 실행기 연결 실패: {e}"}
    seconds = round(time.time() - started, 1)
    success = bool(res.get("ok"))
    video_path = video.finish(success, rd)
    save_serve_files(ws, res, rd)
    logs = android_collect_run_logs(ws, udid, log_since, rd, mask) if log_since else None
    crashed = bool(logs and (logs["crashes"] or logs["anrs"]))

    log = [f"[qakit-note] 시나리오: {scenario.get('name')}"] + [f"[qakit-note] {n}" for n in res.get("notes") or []]
    for line in log[1:]:
        print("  " + mask(line))
    shot_path = None
    if res.get("screenshot"):
        shot_path = rd / "failure.png"
        shot_path.write_bytes(base64.b64decode(res["screenshot"]))
    if res.get("dump"):
        (rd / "failure-dump.txt").write_text(mask(res["dump"]), encoding="utf-8")
    head, slow, detail = timing_summary(res.get("timings"))
    (rd / "output.log").write_text(mask("\n".join(log + [
        f"via: qakit serve · {seconds}초 · {'통과' if success else '실패'}",
        f"message: {res.get('message', '')}", "steps:"] + [f"  - {x}" for x in res.get("steps") or []]
        + ([f"timing: {head}"] + detail if detail else []))) + "\n", encoding="utf-8")
    if detail and os.environ.get("QAKIT_TIMING"):
        print(f"  ⏱  {head}\n  오래 걸린 단계:\n" + "\n".join(slow), file=sys.stderr)
    _relink(ws.results_dir / "latest", rd)
    latest_xcresult = ws.results_dir / "latest.xcresult"   # 이 실행에는 xcresult가 없다 → 예전 결과를 가리키지 않게
    if latest_xcresult.is_symlink() or latest_xcresult.exists():
        latest_xcresult.unlink()
    state = app_state(ws)
    with open(ws.root / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "at": datetime.datetime.now().isoformat(timespec="seconds"), "kind": "run", "test": name,
            "result": "Passed" if success else "Failed", "seconds": seconds, "via": "serve", "dir": results_rel(ws, rd),
            **({"failure": "env"} if not success and res.get("env") else {}),
            **({"crash": True} if crashed else {}),
            "app": {k: state.get(k) for k in ("branch", "commit", "dirtyFiles") if k in state},
            "kit": kit_version(),
        }, ensure_ascii=False) + "\n")

    print()
    if success:
        text = f"── 결과: 통과 1 / 실패 0 / 전체 1 (상주 실행기, {seconds}초)"
        if crashed:   # 판정은 통과했지만 도중에 앱이 죽었다 (재실행으로 넘어간 경우 등)
            text += "\n⚠️  통과했지만 실행 중 앱 크래시·ANR이 있었습니다\n" + "\n".join(
                android_report_lines(logs, max_errors=0, mapping=logs.get("mapping")))
            print(mask(text))
        (rd / SERVE_SUMMARY).write_text(mask(text) + "\n", encoding="utf-8")
        ok(f"통과 ({seconds}초, 상주 실행기) — 결과: {rd}")
        return
    out = ["── 결과: 통과 0 / 실패 1 / 전체 1", f"\n❌ {name}", f"   원인: {res.get('message', '')}"]
    if crashed:
        out.append("   ↳ 실행 중 앱이 죽었습니다 (아래 크래시·ANR 참고)")
    if logs:   # 크래시·ANR·실패한 요청은 원인 바로 아래, 오류 로그는 화면 구조 뒤에
        out += android_report_lines({**logs, "errors": []}, mapping=logs.get("mapping"))
    if res.get("steps"):
        out.append("   마지막 단계:")
        out += [f"     - {x}" for x in res["steps"]]
    out += suggestion_lines(res.get("message", ""), res.get("dump"))
    if res.get("dump"):
        lines = [l.strip() for l in res["dump"].splitlines() if l.startswith("#") is False and ("#" in l or '"' in l)]
        if len(lines) > 60:   # 팝업 등 최상단 요소는 보통 끝에 있으므로 뒤쪽을 남긴다
            lines = ["...(앞 %d줄 생략)" % (len(lines) - 60)] + lines[-60:]
        out.append("   실패 시점 화면 구조 (ID/라벨 있는 요소):")
        out += ["     " + l for l in lines]
    if logs:
        out += android_report_lines({**logs, "crashes": [], "anrs": [], "http": {**logs["http"], "failed": []}})
        out.append(f"   앱 로그: {rd / 'logcat.txt'} ({logs['lines']}줄)"
                   + ("" if logs["http"]["logged"] else " — 네트워크 로그 없음 (OkHttp 로그는 보통 debug 빌드만)"))
    if shot_path:
        out.append(f"   스크린샷: {shot_path}")
    if video_path:
        out.append(f"   영상 (마지막 {RunVideo.KEEP_SECONDS}초): {video_path}")
    text = mask("\n".join(out))
    (rd / SERVE_SUMMARY).write_text(text + "\n", encoding="utf-8")   # qakit summarize가 다시 보여 준다
    print(text)
    LAST_FAILURE["sig"] = (res.get("message", ""), (res.get("steps") or [""])[-1])
    LAST_FAILURE["message"] = res.get("message", "")
    fail("실패" + (" (실행 환경 문제)" if res.get("env") else ""), f"자세한 결과: {rd}", code=2 if res.get("env") else 1)


def serve_ensure(ws, udid):
    """살아 있는 상주 실행기를 돌려준다. 없거나, 죽었거나, 실행기 코드·작업공간이 바뀌었으면 다시 띄운다."""
    st = serve_load(udid)
    if st:
        why = None
        if st.get("runnerHash") != runner_source_hash(ws):
            why = "실행기 코드가 바뀜"
        elif st.get("workspace") != str(ws.root):
            why = f"다른 작업공간({st.get('workspace')})의 실행기"
        elif not serve_alive(st):
            why = "응답 없음"
        if why is None:
            if st.get("platform") == "android":
                # 비밀값은 실행기가 시작할 때 받는다 → 그 뒤 secrets.txt를 고쳐도 옛 값으로 돌던 문제 (iOS는 매번 파일을 읽음).
                # 실행마다 지금 값을 다시 보낸다
                try:
                    serve_request(st, "/config", {"secrets": ws.secrets()}, timeout=10)
                except (ServeTimeout, ConnectionError):
                    pass
            return st
        info(f"상주 실행기를 다시 띄웁니다: {why}")
        serve_stop(udid, quiet=True)
    return serve_start(ws, udid)


def app_prefs_path(udid, bundle_id):
    """시뮬레이터 안 앱의 UserDefaults 파일 (시나리오의 pref 조건·read-pref용). 앱을 재설치하면 바뀌므로 실행 직전에 구한다."""
    r = run(["xcrun", "simctl", "get_app_container", udid, bundle_id, "data"], check=False)
    if r.returncode != 0:
        return None
    return str(Path(r.stdout.strip()) / "Library" / "Preferences" / f"{bundle_id}.plist")


def run_scenario_runner(ws, method, extra_env, label, quiet=False, history_name=None, run_dir=None, on_line=None):
    ws.results_dir.mkdir(exist_ok=True)
    ensure_autoid(ws)
    extra_env = dict(extra_env or {})
    if ws.device:
        udid = ws.device["udid"]
        if not device_app_installed(ws):
            fail(f"{ws.device['name']}에 {ws.bundle_id}가 설치되어 있지 않습니다.", "qakit build-app --device ...")
        if method != "test_serve":
            serve_stop(udid, reason=f"qakit {label}")
        xctestrun = ensure_device_runner(device_team(ws))
        # 기기 안 실행기는 Mac 파일을 못 읽는다 → 시나리오를 내용째 넘긴다
        if extra_env.get("SCENARIO_JSON"):
            extra_env["SCENARIO_B64"] = base64.b64encode(Path(extra_env.pop("SCENARIO_JSON")).read_bytes()).decode()
    else:
        udid = ensure_booted(ws)
        if not app_installed(udid, ws.bundle_id):
            fail(f"시뮬레이터에 {ws.bundle_id}가 설치되어 있지 않습니다.", "qakit build-app")
        if method != "test_serve":
            serve_stop(udid, reason=f"qakit {label}")
        xctestrun = ensure_scenario_runner(udid)
        prefs = app_prefs_path(udid, ws.bundle_id)
        if prefs:
            extra_env["APP_PREFS"] = prefs
    ts = timestamp()
    rd = run_dir or new_run_dir(ws, label, history_name)
    xcresult = rd / "result.xcresult"
    cmd = ["xcodebuild", "test-without-building", "-xctestrun", str(xctestrun),
           "-destination", f"id={udid}", "-resultBundlePath", str(xcresult),
           "-only-testing", f"ScenarioTests/ScenarioTests/{method}"]
    result = execute_xctest(ws, cmd, extra_env, label, ts, xcresult, quiet, history_name, on_line=on_line)
    if ws.device and xcresult.exists():
        extract_device_files(ws, xcresult, rd)
    return result


def id_sources_fingerprint(ws):
    """ID에 영향을 주는 것들의 지문: 앱 Swift 파일(경로·수정 시각·크기), ID 도구, SwiftUI 설정. 파일 내용은 읽지 않는다."""
    h = hashlib.sha1()
    root = ws.root.resolve()
    sources = sorted(set([str(x) for x in (ws.id_sources or [ws.app_dir])] + swiftui_sources(ws)))
    for f in sorted(set(gen_ids.iter_swift_files(sources))):
        try:
            if f.resolve().is_relative_to(root):
                continue
            st = f.stat()
        except OSError:
            continue
        h.update(f"{f}\0{st.st_mtime_ns}\0{st.st_size}\n".encode())
    for tool in (KIT_DIR / "Tools" / "gen-ids" / "gen_ids.py", SWIFTUI_IDS_DIR / "Package.swift"):
        try:
            h.update(f"{tool}\0{tool.stat().st_mtime_ns}\n".encode())
        except OSError:
            pass
    for f in sorted((SWIFTUI_IDS_DIR / "Sources").rglob("*.swift")):
        h.update(f"{f}\0{f.stat().st_mtime_ns}\n".encode())
    h.update(f"swiftui={ws.swiftui}".encode())
    return h.hexdigest()


KNOWN_IDS = {}


def known_ids(ws):
    """앱에 있는 ID 전체 (시나리오 정적 검사용). 앱 소스·도구가 지난번과 같으면 파싱하지 않고 저장해 둔 목록을 쓴다.
    한 명령 안에서는 재사용한다 (qakit run 여러 개)."""
    if str(ws.root) not in KNOWN_IDS:
        KNOWN_IDS[str(ws.root)] = android_seen_ids(ws) if ws.platform == "android" else _known_ids(ws)
    return KNOWN_IDS[str(ws.root)]


def _known_ids(ws):
    key = id_sources_fingerprint(ws)
    cached = load_state(ws, "ids-check")
    if cached and cached.get("key") == key and ws.ids_file.exists():
        return set(cached["ids"])
    trees, _ = generate_ids(ws, quiet=True)
    ids = sorted(gen_ids.all_ids(trees))
    save_state(ws, "ids-check", {"key": key, "ids": ids})
    return set(ids)


def cmd_touch(args):
    """qakit touch tap x y — 직접 터치 확인용. 터치는 답이 "ok"여도 조용히 무시될 수 있어, 누른 뒤 화면이 바뀌었는지도 본다."""
    ws = find_workspace(args.workspace)
    if ws.device:
        fail("직접 터치는 시뮬레이터만")
    udid = ensure_booted(ws)
    helper = TouchHelper(udid)
    started = time.time()
    why = helper.start()
    if why:
        fail(f"터치 도우미를 띄우지 못함: {why}", "Xcode가 바뀌었으면 비공개 API가 달라졌을 수 있습니다 (docs/private-apis.md)")
    ready = time.time() - started
    before = screen_jpeg(udid, 300)
    good, line = helper.send(" ".join(args.action))
    helper.stop()
    (ok if good else warn)(f"{line} · 도우미 준비 {ready:.1f}초 ({helper.mode})")
    if not good:
        sys.exit(1)
    time.sleep(1)
    after = screen_jpeg(udid, 300)
    if before and after and screens_alike(before, after):
        warn("1초 뒤에도 화면이 그대로입니다 — 터치가 무시됐을 수 있습니다 (누른 자리가 원래 화면을 바꾸지 않으면 괜찮음)")
        st = serve_load(udid)
        if st and serve_alive(st):
            info("   → 상주 실행기가 응답 없이 멈춰 있을 때 무시된 적이 있습니다: qakit serve --stop 뒤 다시")
        info("   → Device Hub에 한 번도 띄우지 않은 새 시뮬레이터에서는 모두 무시됐습니다 (원인 확인 중): qakit show로 띄운 뒤 다시")
        info("   → 자세히: docs/private-apis.md '손가락처럼 누르기'")
    elif before and after:
        ok("화면이 바뀜 — 터치가 먹혔습니다")


def coverage(ws):
    """앱 ID(자동 ID, 화면타입.프로퍼티) 중 시나리오가 쓰는 것. 화면 = ID 맨 앞 타입 이름.
    시나리오는 use:를 펼쳐 어디에 쓰였든(대상·조건·start) 같은 글이면 쓰임. 앱이 직접 붙인 ID는 전체를 모르므로 따로."""
    ids = known_ids(ws)
    users = {}   # ID → 시나리오 이름들

    def walk(node, name):
        if isinstance(node, dict):
            for v in node.values():
                walk(v, name)
        elif isinstance(node, list):
            for v in node:
                walk(v, name)
        elif isinstance(node, str):
            users.setdefault(node, set()).add(name)
    for f in sorted((ws.root / "scenarios").glob("*.qa.yml")):
        name = f.name[:-len(".qa.yml")]
        try:
            walk(scenario_tools.load_scenario(f, ws.root), name)
        except Exception:  # noqa: BLE001 — 형식이 깨진 시나리오는 건너뛴다 (qakit check가 알려 줌)
            continue
    screens = {}
    for i in sorted(ids):
        screens.setdefault(i.split(".")[0], []).append({"id": i, "scenarios": sorted(users.get(i, ()))})
    rows = [{"screen": k, "total": len(v), "used": sum(1 for x in v if x["scenarios"]), "ids": v} for k, v in screens.items()]
    rows.sort(key=lambda r: (r["used"] / r["total"], -r["total"], r["screen"]))
    extra = sorted(({"id": k, "scenarios": sorted(v)} for k, v in users.items()
                    if k not in ids and re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+", k)), key=lambda x: x["id"])
    used = sum(r["used"] for r in rows)
    return {"total": len(ids), "used": used, "screens": rows, "extra": extra,
            "scenarios": len(list((ws.root / "scenarios").glob("*.qa.yml")))}


def cmd_coverage(args):
    ws = find_workspace(args.workspace)
    c = coverage(ws)
    if args.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))
        return
    pct = lambda u, t: f"{(u / t * 100 if t else 0):.0f}%"
    print(f"시나리오 {c['scenarios']}개가 앱 ID {c['total']}개 중 {c['used']}개를 씁니다 ({pct(c['used'], c['total'])})\n")
    width = max((len(r["screen"]) for r in c["screens"]), default=10)
    for r in c["screens"]:
        bar = "█" * round(r["used"] / r["total"] * 10) + "·" * (10 - round(r["used"] / r["total"] * 10))
        unused = [x["id"].split(".", 1)[-1] for x in r["ids"] if not x["scenarios"]]
        print(f"  {r['screen']:<{width}}  {bar} {r['used']:>3}/{r['total']:<3}"
              + (f"  안 씀: {', '.join(unused[:4])}{' …' if len(unused) > 4 else ''}" if unused and args.unused else ""))
    if c["extra"]:
        print(f"\n그 밖에 시나리오가 쓰는 앱이 직접 붙인 ID {len(c['extra'])}개 (전체 수는 알 수 없음)")
    print("\n안 쓴 ID까지: qakit coverage --unused · UI: qakit ui → 커버리지")


def load_checked_scenario(ws, name, strict=True):
    path = scenario_tools.find_scenario(ws.root, name)
    if not path:
        listing = ", ".join(p.name for p in sorted((ws.root / "scenarios").glob("*.qa.yml"))) or "(없음)"
        fail(f"시나리오 '{name}'을(를) 찾지 못했습니다.", f"scenarios/ 목록: {listing}")
    try:
        scenario = scenario_tools.load_scenario(path, ws.root)
    except scenario_tools.YamlError as e:
        fail(f"시나리오 형식 오류: {e}")
    # 안드로이드는 앱 소스에서 ID 목록을 만들지 않으므로(덤프로 본 ID뿐) 검사하지 않는다
    unknown = [] if ws.platform == "android" else scenario_tools.check_ids(scenario, known_ids(ws), extra_ok=ws.id_allow)
    if unknown:
        import difflib
        ids = known_ids(ws)
        msg = "앱에 없는 ID: " + ", ".join(
            u + (f" (비슷한 ID: {', '.join(c)})" if (c := difflib.get_close_matches(u, ids, n=3, cutoff=0.7)) else "")
            for u in unknown)
        if strict:
            fail(msg, "앱에서 이름이 바뀌었는지 Generated/QAIDs.swift 또는 qakit dump-ui로 확인하세요")
        warn(msg)
    return path, scenario


def cmd_check(args):
    ws = find_workspace(args.workspace)
    names = args.scenarios or [p.name for p in sorted((ws.root / "scenarios").glob("*.qa.yml"))]
    hints = 0
    for n in names:
        path, scenario = load_checked_scenario(ws, n)
        ok(f"{path.name}: 단계 {count_steps(scenario['steps'])}개, ID 확인 완료")
        try:
            raw = scenario_tools.parse_yaml(path.read_text(encoding="utf-8"))
            hints += mergeable_tap_waits(raw.get("steps")) if isinstance(raw, dict) else 0
        except Exception:  # noqa: BLE001
            pass
    for f in sorted((ws.root / "steps").glob("*.qa.yml")) if not args.scenarios else []:
        try:
            raw = scenario_tools.parse_yaml(f.read_text(encoding="utf-8"))
            hints += mergeable_tap_waits(raw.get("steps")) if isinstance(raw, dict) else 0
        except Exception:  # noqa: BLE001
            pass
    if hints:
        info(f"💡 탭 바로 다음 기다림(wait) {hints}곳은 탭의 expect:로 합칠 수 있습니다 "
             "(탭이 무시되면 그 자리에서 실패). 예) - tap: X  →  expect: { visible: Y }")
    update_readme(ws, quiet=False)


def count_steps(steps):
    n = 0
    for s in steps:
        n += 1
        if isinstance(s, dict):
            for k in ("steps", "then", "else"):
                if isinstance(s.get(k), list):
                    n += count_steps(s[k])
    return n


def expand_scenario_args(ws, items):
    """시나리오 인자 → 이름 목록. 'home-*' 같은 패턴은 scenarios/의 이름에 맞춰 펼친다 (순서 유지, 중복 제거)."""
    import fnmatch
    available = [f.name[:-len(".qa.yml")] for f in sorted((ws.root / "scenarios").glob("*.qa.yml"))]
    names = []
    for item in items:
        if any(c in item for c in "*?["):
            pattern = item[:-len(".qa.yml")] if item.endswith(".qa.yml") else item
            matched = [n for n in available if fnmatch.fnmatch(n, pattern)]
            if not matched:
                fail(f"'{item}'에 맞는 시나리오가 없습니다.", "scenarios/ 목록: " + (", ".join(available) or "(없음)"))
            names += matched
        else:
            names.append(item)
    return list(dict.fromkeys(names))


def scenario_tags(ws, name):
    """시나리오 맨 위 tags: (목록 또는 글자 하나). 읽지 못하면 빈 목록."""
    path = scenario_tools.find_scenario(ws.root, name)
    try:
        data = scenario_tools.parse_yaml(path.read_text(encoding="utf-8")) if path else {}
    except Exception:  # noqa: BLE001 — 형식 오류는 실행할 때 알린다
        return []
    tags = data.get("tags") if isinstance(data, dict) else None
    return [str(t) for t in (tags if isinstance(tags, list) else [tags] if tags else [])]


def select_scenarios(ws, args):
    """이름·패턴 + --tag/--exclude-tag → 실행할 시나리오 목록. 이름이 없고 --tag만 있으면 전체에서 고른다."""
    if not args.scenario and not args.tag:
        fail("실행할 시나리오가 필요합니다.", "예) qakit run home-01  ·  qakit run 'home-*'  ·  qakit run --tag smoke")
    names = expand_scenario_args(ws, args.scenario or ["*"])
    if args.tag or args.exclude_tag:
        include, exclude = set(args.tag or []), set(args.exclude_tag or [])
        picked = []
        for n in names:
            tags = set(scenario_tags(ws, n))
            if include and not tags & include:
                continue
            if tags & exclude:
                continue
            picked.append(n)
        if not picked:
            fail("고른 태그에 맞는 시나리오가 없습니다.",
                 f"--tag {' '.join(sorted(include)) or '-'} / --exclude-tag {' '.join(sorted(exclude)) or '-'}")
        names = picked
    return names


def run_precheck(ws, args):
    """qakit.yml precheck: <공통 단계> — 여러 개 실행 전에 그 단계를 한 번 (앱을 새로 켜고) 돌려 환경을 확인한다.
    로그아웃·서버 점검처럼 모든 시나리오가 실패할 상황을 시나리오마다 기다리기 전에 잡는다. 실패하면 종료 코드 2."""
    name = ws.precheck
    f = ws.root / "steps" / f"{name}.qa.yml"
    if not f.exists():
        fail(f"qakit.yml의 precheck: {name} 공통 단계가 없습니다: {f}")
    try:
        data = scenario_tools.parse_yaml(f.read_text(encoding="utf-8")) or {}
        # 펼치기 시작점 표시는 단계 이름과 겹치지 않게 (steps/precheck.qa.yml이 "자기 자신을 부름"으로 걸리던 문제)
        steps = scenario_tools._expand([{"use": name}], ws.root, ["(qakit.yml precheck)"])
    except ValueError as e:
        fail(f"사전 확인 단계(steps/{name}.qa.yml)를 읽지 못했습니다: {e}")
    udid = ws.device["udid"] if ws.device else ensure_booted(ws)
    info(f"사전 확인: steps/{name}.qa.yml")
    started = time.time()
    st = serve_ensure(ws, udid)
    try:
        res = serve_request(st, "/run", {"name": f"사전 확인 ({name})", "steps": steps}, timeout=args.timeout)
    except ServeTimeout:
        serve_stop(udid, quiet=True, force=True)
        res = {"ok": False, "message": f"{args.timeout}초 안에 끝나지 않음"}
    except ConnectionError as e:
        res = {"ok": False, "message": f"상주 실행기 연결 실패: {e}"}
    if res.get("ok"):
        ok(f"사전 확인 통과 ({time.time() - started:.1f}초)")
        return
    if res.get("dump"):
        out = ws.results_dir / "precheck-fail-dump.txt"
        ws.results_dir.mkdir(exist_ok=True)
        out.write_text(masker(ws.secrets())(res["dump"]), encoding="utf-8")
    why = data.get("message") if isinstance(data, dict) else None
    fail(f"사전 확인 실패 → 시나리오를 돌리지 않습니다" + (f": {why}" if why else ""),
         f"원인: {res.get('message', '')}"
         + (f"\n   화면 구조: {ws.results_dir / 'precheck-fail-dump.txt'}" if res.get("dump") else "")
         + "\n   환경을 고친 뒤 다시 실행하세요. 건너뛰려면 --no-precheck", code=2)


def cmd_run(args):
    global FAIL_CODE
    FAIL_CODE = 2   # 아래에서 앱 판정 실패만 1로 끝낸다
    RUN_VIDEO["mode"] = getattr(args, "video", None) or "fail"
    ws = find_workspace(args.workspace)
    names = select_scenarios(ws, args)
    if len(names) > 1 and args.bench:
        fail("--bench는 시나리오 하나만 측정합니다.", f"예) qakit run {names[0]} --bench 1m")
    try:
        with sim_lock(ws, "qakit run " + " ".join(names)[:80]):
            if ws.precheck and not args.no_precheck and not args.bench and (len(names) > 1 or args.precheck):
                run_precheck(ws, args)
            if len(names) == 1 and not args.junit:
                _cmd_run(ws, args, names[0])
            else:
                run_many(ws, args, names)
    finally:
        update_readme(ws)


RUN_VIDEO = {"mode": "fail"}   # qakit run --video


class RunVideo:
    """실행 중 시뮬레이터 화면 녹화. 실패하면(또는 --video always) 마지막 30초를 줄여(440x960) 결과 폴더에 남기고,
    통과하면 버린다 (마무리·변환 비용은 남길 때만, 약 2초). 실기기·성능 측정 중에는 안 한다."""
    KEEP_SECONDS = 30

    def __init__(self, ws, udid):
        self.proc = None
        if RUN_VIDEO["mode"] == "off" or ws.device or not udid or ws.platform == "android":   # 안드로이드 녹화는 A6
            return
        self.raw = ws.results_dir / f".video-{os.getpid()}-{int(time.time() * 1000)}.mp4"
        self.raw.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.proc = subprocess.Popen(["xcrun", "simctl", "io", udid, "recordVideo", "--codec=h264", "--force", str(self.raw)],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.proc = None
        self.started = time.time()

    def discard(self):
        """녹화 파일과, 강제로 끝낼 때 simctl이 남기는 저장 중 임시 파일(<이름>.sb-*)까지 지운다."""
        for f in [self.raw, *self.raw.parent.glob(self.raw.name + ".sb-*")]:
            f.unlink(missing_ok=True)

    def finish(self, success, rd):
        """→ 남긴 영상 경로 또는 None"""
        if not self.proc:
            return None
        if success and RUN_VIDEO["mode"] != "always":
            self.proc.kill()
            self.proc.wait()
            self.discard()
            return None
        self.proc.send_signal(signal.SIGINT)   # simctl은 SIGINT를 받아야 파일을 마무리한다
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        if not self.raw.exists() or self.raw.stat().st_size == 0 or not rd:
            self.discard()
            return None
        out = Path(rd) / ("video.mp4" if success else "failure.mp4")
        length = time.time() - self.started
        cmd = ["avconvert", "-s", str(self.raw), "-p", "Preset960x540", "-o", str(out), "--replace"]
        if length > self.KEEP_SECONDS + 1:
            cmd += ["--start", f"{length - self.KEEP_SECONDS:.1f}"]
        r = run(cmd, check=False)
        if r.returncode == 0 and out.exists():
            self.raw.unlink(missing_ok=True)
        else:   # 줄이지 못하면 원본 그대로
            shutil.move(str(self.raw), str(out))
        return out


LAST_FAILURE = {}   # 마지막 실패의 (원인, 마지막 단계) — 여러 개 실행에서 같은 원인 연속 실패를 알아본다


def run_many(ws, args, names):
    """시나리오 여러 개를 차례로. 준비(워크트리 최신화·앱 변경 확인·ID 검사)는 한 번만, 판정·결과 폴더는 시나리오마다.
    하나가 실패해도 나머지를 돌리고, 끝에 요약. 하나라도 실패하면 종료 코드 1.
    연속한 두 시나리오가 같은 원인·같은 단계에서 실패하면 환경 문제(로그아웃·서버 점검 등)로 보고 멈춘다
    (--keep-going: 끝까지, --fail-fast: 첫 실패에서 멈춤)."""
    results = []   # (이름, 통과, 초, 실패 표시)
    started = time.time()
    stop_reason = None
    for i, name in enumerate(names, 1):
        print(f"\n━━ [{i}/{len(names)}] {name}", flush=True)
        t = time.time()
        LAST_FAILURE.clear()
        code = 0
        try:
            _cmd_run(ws, args, name)
        except SystemExit as e:
            code = 0 if e.code in (0, None) else (e.code if isinstance(e.code, int) else 1)
        passed = code == 0
        sig = None if passed else LAST_FAILURE.get("sig")
        results.append((name, passed, time.time() - t, sig, code, LAST_FAILURE.get("message", "")))
        if passed or i == len(names):
            continue
        if args.fail_fast:
            stop_reason = "--fail-fast: 첫 실패에서 멈춤"
            break
        prev = results[-2] if len(results) >= 2 else None
        if not args.keep_going and sig and prev and not prev[1] and prev[3] == sig:
            stop_reason = ("같은 원인으로 연속 2번 실패 → 환경 문제(로그아웃·서버 점검·앱 상태 등)로 보고 멈춤\n"
                           f"   원인: {sig[0]}" + (f"\n   단계: {sig[1]}" if sig[1] else ""))
            break
    skipped = names[len(results):]
    failed = [r[0] for r in results if not r[1]]
    print(f"\n── 결과: 통과 {len(results) - len(failed)} / 실패 {len(failed)}"
          + (f" / 건너뜀 {len(skipped)}" if skipped else "") + f" / 전체 {len(names)} ({time.time() - started:.1f}초)")
    for name, passed, secs, _, code, _ in results:
        print(f"   {'✅' if passed else '❌'} {name}  {secs:.1f}초" + ("  (실행 환경·설정)" if code == 2 else ""))
    for name in skipped:
        print(f"   ⏭  {name}  (돌리지 않음)")
    if stop_reason:
        warn(stop_reason)
    if args.junit:
        write_junit(Path(args.junit), ws, results, skipped, time.time() - started)
    if failed or skipped:
        hint = ("실패·건너뜀만 다시: " if skipped else "실패한 것만 다시: ") + "qakit run " + " ".join(failed + skipped)
        if skipped and not args.fail_fast:
            hint += "\n   (환경을 확인한 뒤. 같은 원인이어도 끝까지 돌리려면 --keep-going)"
        # 앱 판정 실패가 하나라도 있으면 1 (환경 문제에 회귀가 가려지지 않게), 모두 환경·설정 문제면 2
        product = any(r[4] == 1 for r in results)
        fail(f"실패 {len(failed)}개" + (f", 건너뜀 {len(skipped)}개" if skipped else ""), hint, code=1 if product else 2)


def write_junit(path, ws, results, skipped, total_seconds):
    """CI용 JUnit XML. 앱 판정 실패는 <failure>, 환경·설정 실패는 <error>, 돌리지 않은 것은 <skipped>."""
    from xml.sax.saxutils import escape, quoteattr
    mask = masker(ws.secrets())
    failures = sum(1 for r in results if r[4] == 1)
    errors = sum(1 for r in results if r[4] not in (0, 1))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<testsuites tests="{len(results) + len(skipped)}" failures="{failures}" errors="{errors}" '
             f'skipped="{len(skipped)}" time="{total_seconds:.1f}">',
             f'  <testsuite name={quoteattr("qakit " + ws.name)} tests="{len(results) + len(skipped)}" '
             f'failures="{failures}" errors="{errors}" skipped="{len(skipped)}" time="{total_seconds:.1f}">']
    for name, passed, secs, sig, code, message in results:
        open_tag = f'    <testcase classname={quoteattr("qakit." + ws.name)} name={quoteattr(name)} time="{secs:.1f}"'
        if passed:
            lines.append(open_tag + "/>")
            continue
        kind = "failure" if code == 1 else "error"
        msg = mask(message or (sig[0] if sig else "실패"))
        detail = mask("\n".join(x for x in (sig or ()) if x))
        lines += [open_tag + ">", f"      <{kind} message={quoteattr(msg)}>{escape(detail)}</{kind}>", "    </testcase>"]
    for name in skipped:
        lines.append(f'    <testcase classname={quoteattr("qakit." + ws.name)} name={quoteattr(name)} time="0">'
                     '<skipped message="같은 원인으로 연속 실패해 돌리지 않음"/></testcase>')
    lines += ["  </testsuite>", "</testsuites>"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    info(f"JUnit 보고서: {path}")


