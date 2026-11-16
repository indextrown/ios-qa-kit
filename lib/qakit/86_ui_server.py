# qakit — qakit ui 서버 (cmd_ui)
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
def cmd_ui(args):
    """결과 보기 + 시뮬레이터 라이브 화면 (로컬 웹, 127.0.0.1). docs/PLAN.md "UI 설계" U1."""
    import http.server
    import secrets as pysecrets
    import threading
    import urllib.parse
    ws = find_workspace(args.workspace)
    token = pysecrets.token_urlsafe(18)
    android = ws.platform == "android"
    # 안드로이드: 에뮬레이터 serial (꺼져 있으면 띄움). 라이브 화면·터치·녹화는 adb + 상주 실행기 화면 서버
    udid = None if ws.device else (android_serial(ws.emulator) if android else simulator_udid(ws.simulator)[0])
    screen = {"at": 0.0, "data": None, "lock": threading.Lock()}
    # 실시간 화면: simscreen 하나를 띄워 최신 JPEG를 모든 브라우저에 나눠 준다 (보는 사람이 없으면 30초 뒤 끔)
    live = {"proc": None, "frame": None, "seq": 0, "cond": threading.Condition(), "error": None, "failed_at": 0.0,
            "clients": 0, "idle_since": time.time(), "frames": [], "changed_at": 0.0, "base_size": 0}
    static = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
              ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
    if not (UI_DIR / "index.html").exists():
        fail(f"UI 빌드 결과가 없습니다: {UI_DIR}", f"cd {KIT_DIR / 'web'} && npm install && npm run build")

    # UI에서 띄우는 qakit run·do도 UI와 같은 빌드 종류로 (qakit ui --build release면 release 앱·운영 서버)
    build_args = ["--build", ws.build] if ws.build != "debug" else []
    job = {"proc": None, "lines": [], "args": None, "started": None, "ended": None, "code": None,
           "lock": threading.Lock()}

    def start_job(body, draft=None):
        """UI에서 고른 시나리오·태그·옵션으로 qakit run을 따로 띄운다 (한 번에 하나). draft: 초안 재생(U4)."""
        if aij["proc"] and aij["proc"].poll() is None:
            return None, "AI QA가 도는 중입니다 (멈춘 뒤 다시)"
        with job["lock"]:
            if job["proc"] and job["proc"].poll() is None:
                return None, "이미 실행 중입니다 (멈춘 뒤 다시)"
            names = [str(n) for n in body.get("scenarios") or [] if re.fullmatch(r"[A-Za-z0-9가-힣_.*?-]+", str(n))]
            if draft:
                names = [str(draft_path(draft))]
            tags = [str(t) for t in body.get("tags") or [] if re.fullmatch(r"[A-Za-z0-9가-힣_-]+", str(t))]
            if not names and not tags:
                return None, "실행할 시나리오나 태그를 고르세요"
            o = body.get("options") or {}
            cmd = [sys.executable, str(KIT_DIR / "bin" / "qakit"), "-w", str(ws.root), "run", *names]
            for t in tags:
                cmd += ["--tag", t]
            cmd += ["--serve"] if not ws.device else []
            cmd += ["--reuse-app"] if o.get("reuse") else []
            cmd += ["--fail-fast"] if o.get("stop") == "first" else ["--keep-going"] if o.get("stop") == "never" else []
            cmd += ["--no-precheck"] if o.get("precheck") is False else ["--precheck"] if o.get("precheck") else []
            cmd += build_args   # qakit ui --build release로 열었으면 실행도 release 앱으로
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                    env=dict(os.environ, PYTHONUNBUFFERED="1"), start_new_session=True)
            job.update(proc=proc, lines=[], args=["qakit run", *([f"(초안) {draft}"] if draft else cmd[5:5 + len(names)]), *cmd[5 + len(names):]],
                       started=time.time(), ended=None, code=None, draft=draft,
                       draftHash=hashlib.sha1(draft_path(draft).read_bytes()).hexdigest() if draft else None)

        def pump():
            for line in proc.stdout:
                with job["lock"]:
                    job["lines"].append(masker(ws.secrets())(line.rstrip("\n")))
                    del job["lines"][:-5000]
            code = proc.wait()
            with job["lock"]:
                job.update(ended=time.time(), code=code)
        threading.Thread(target=pump, daemon=True).start()
        return job["args"], None

    def stop_job():
        proc = job["proc"]
        if not proc or proc.poll() is not None:
            return False
        try:
            os.killpg(proc.pid, 2)   # Ctrl+C와 같게: 실행 중인 시나리오를 끝내고 정리
        except OSError:
            pass

        def force():
            time.sleep(10)
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, 15)
                except OSError:
                    pass
        threading.Thread(target=force, daemon=True).start()
        return True

    do_lock = threading.Lock()

    def run_do(args_, timeout=150):
        """qakit do <…> (UI 라이브 조작). 실행(U2) 중이면 거절."""
        if job["proc"] and job["proc"].poll() is None:
            return None, "시나리오 실행 중에는 조작할 수 없습니다"
        if args_ and args_[0] != "dump" and aij["proc"] and aij["proc"].poll() is None:
            return None, "AI QA가 조작하는 중에는 조작할 수 없습니다"
        if not do_lock.acquire(blocking=False):
            return None, "앞선 조작이 끝나지 않았습니다"
        try:
            r = subprocess.run([sys.executable, str(KIT_DIR / "bin" / "qakit"), "-w", str(ws.root), "do", *args_, *build_args],
                               capture_output=True, text=True, timeout=timeout,
                               env=dict(os.environ, PYTHONUNBUFFERED="1"))
            return {"code": r.returncode, "output": masker(ws.secrets())((r.stdout or "") + (r.stderr or ""))}, None
        except subprocess.TimeoutExpired:
            return None, f"{timeout}초 안에 끝나지 않음"
        finally:
            do_lock.release()

    touch = {"helper": None, "lock": threading.Lock()}

    def run_touch(body):
        """라이브 세션 손 조작을 직접 터치로 (H4, 실험) — 좌표(0~1)를 그대로 누른다. XCUITest 탭보다 빠르고 길게 누르기·끌기도.
        step(그 자리 요소의 단계 글)이 오면 탭이 된 뒤 기록 (시나리오로 옮길 수 있게 — 재생은 XCUITest)."""
        if not udid:
            return None, "직접 터치는 시뮬레이터만"
        if job["proc"] and job["proc"].poll() is None:
            return None, "시나리오 실행 중에는 조작할 수 없습니다"
        if aij["proc"] and aij["proc"].poll() is None:
            return None, "AI QA가 조작하는 중에는 조작할 수 없습니다"
        kind = body.get("kind") or "tap"
        try:
            pts = [min(max(float(body[k]), 0.0), 1.0) for k in (("x", "y", "x2", "y2") if kind == "swipe" else ("x", "y"))]
            secs = min(max(float(body.get("seconds") or {"tap": 0.06, "press": 1.0, "swipe": 0.4}[kind]), 0.03), 5.0)
        except (KeyError, TypeError, ValueError):
            return None, "좌표가 없거나 이상함 (kind: tap·press·swipe, x·y·x2·y2는 0~1)"
        cmd = {"tap": "tap {:.4f} {:.4f} {ms}", "press": "press {:.4f} {:.4f} {s}", "swipe": "swipe {:.4f} {:.4f} {:.4f} {:.4f} {s}"}[kind]
        cmd = cmd.format(*pts, ms=int(secs * 1000), s=f"{secs:.2f}")
        mark = lambda k, x, y: touch_mark(ws, k, x, y)
        mark({"tap": "tap", "press": "press", "swipe": "drag"}[kind], pts[0], pts[1])
        if not touch["lock"].acquire(timeout=10):
            return None, "앞선 터치가 끝나지 않았습니다"
        try:
            t0 = time.time()
            if android:
                good, line = android_touch(udid, kind, pts, secs)
            else:
                if touch["helper"] is None:
                    touch["helper"] = TouchHelper(udid)
                good, line = touch["helper"].send(cmd, timeout=secs + 10)
        finally:
            touch["lock"].release()
        if kind == "swipe":
            mark("drag-done", pts[2], pts[3])
        else:
            mark(kind + "-done", pts[0], pts[1])
        if not good:
            return None, f"직접 터치 실패: {line}"
        step = str(body.get("step") or "").strip()
        if step and kind == "tap" and len(step) < 500:
            do_log_write(ws, {"step": step})
        return {"ok": True, "ms": int((time.time() - t0) * 1000), "reply": line, "recorded": bool(step and kind == "tap")}, None

    def job_state(since):
        with job["lock"]:
            running = bool(job["proc"]) and job["proc"].poll() is None
            return {"running": running, "args": job["args"], "started": job["started"], "ended": job["ended"],
                    "code": job["code"], "total": len(job["lines"]), "lines": job["lines"][since:], "draft": job.get("draft")}

    def draft_path(name):
        return ws.root / ".qakit" / "drafts" / f"{name}.qa.yml"

    def make_draft(body):
        """기록 → 초안 (.qakit/drafts/<이름>.qa.yml, git 제외). 형식·ID를 검사해 함께 돌려준다."""
        name = str(body.get("name") or "").strip()
        if not SCENARIO_NAME_RE.fullmatch(name):
            return None, "이름은 영문·숫자·한글·-·_ 만 (예: home-12-banner)"
        start = str(body.get("start") or "").strip() or None
        if start and not (ws.root / "steps" / f"{start}.qa.yml").exists():
            return None, f"공통 단계가 없습니다: steps/{start}.qa.yml"
        tags = [t.strip() for t in body.get("tags") or [] if re.fullmatch(r"[A-Za-z0-9가-힣_-]+", t.strip())]
        recorded = None
        if body.get("aiSession"):   # AI QA 세션에서 통과한 단계로 (A4)
            d = ui_safe_dir(ws, str(body["aiSession"]))
            if not d or d.parent != (ws.results_dir / "ai").resolve():
                return None, "AI 세션을 찾지 못함"
            full = ai_session_info(ws, d, full=True)
            recorded = (full["stepList"], full["fromLaunch"])
        try:
            text, merged, nsteps, from_launch = build_scenario_text(
                ws, name, title=(body.get("title") or "").strip() or None,
                description=body.get("description") or None, tags=tags, start=start, recorded=recorded)
        except ValueError as e:
            return None, str(e)
        f = draft_path(name)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        try:
            scenario = scenario_tools.load_scenario(f, ws.root)
            unknown = scenario_tools.check_ids(scenario, known_ids(ws), extra_ok=ws.id_allow)
            problem = None
        except Exception as e:  # noqa: BLE001 — 형식 오류를 그대로 보여 준다
            unknown, problem = [], str(e)
        return {"name": name, "text": text, "merged": merged, "steps": nsteps, "fromLaunch": from_launch,
                "unknownIds": unknown, "problem": problem,
                "exists": (ws.root / "scenarios" / f"{name}.qa.yml").exists()}, None

    def src_path(kind, name):
        """편집할 파일: scenarios/<이름>.qa.yml 또는 steps/<이름>.qa.yml"""
        if kind not in ("scenario", "step") or not SCENARIO_NAME_RE.fullmatch(name or ""):
            return None
        return ws.root / ("scenarios" if kind == "scenario" else "steps") / f"{name}.qa.yml"

    def check_src(kind, name, text):
        """저장하지 않고 지금 글로 검사: 형식, use: 펼치기, 앱에 없는 ID. 공통 단계는 그 단계만 펼쳐 본다."""
        try:
            data = scenario_tools.parse_yaml(text)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "problem": f"YAML 형식 오류 — 괄호·따옴표·들여쓰기를 확인하세요 ({e})", "unknownIds": [], "steps": 0}
        if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
            return {"ok": False, "problem": "맨 위에 steps: 목록이 있어야 합니다", "unknownIds": [], "steps": 0}
        try:
            steps = scenario_tools._expand(data["steps"], ws.root, [f"{name}"] if kind == "step" else [f"{name}.qa.yml"])
            scenario = dict(data, steps=steps)
            if data.get("interrupts"):
                scenario["interrupts"] = scenario_tools._expand(data["interrupts"], ws.root, [f"{name}.qa.yml"])
            unknown = scenario_tools.check_ids(scenario, _known_ids(ws), extra_ok=ws.id_allow)
        except Exception as e:  # noqa: BLE001 — 없는 공통 단계 등
            return {"ok": False, "problem": str(e), "unknownIds": [], "steps": 0}
        return {"ok": not unknown, "problem": None, "unknownIds": unknown, "steps": count_steps(steps),
                "tags": data.get("tags") if isinstance(data.get("tags"), list) else []}

    def save_src(body):
        kind, name, text = body.get("kind"), str(body.get("name") or ""), body.get("text")
        f = src_path(kind, name)
        if f is None or not isinstance(text, str):
            return None, "이름은 영문·숫자·한글·-·_ 만"
        current = f.read_text(encoding="utf-8") if f.exists() else None
        if current is not None and body.get("create"):
            return None, f"이미 있습니다: {f.relative_to(ws.root)}"
        if current is None and not body.get("create"):
            return None, "파일이 없습니다"
        base = body.get("baseHash")   # 열 때의 내용 — 그사이 밖에서 바뀌었으면 덮어쓰지 않는다
        if current is not None and base != hashlib.sha1(current.encode()).hexdigest():
            return None, "편집하는 동안 파일이 밖에서 바뀌었습니다 — 다시 열어 확인하세요"
        result = check_src(kind, name, text)
        if result["problem"] and (result["problem"].startswith("YAML") or result["problem"] == "맨 위에 steps: 목록이 있어야 합니다"):
            return None, result["problem"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        update_readme(ws)
        new = f.read_text(encoding="utf-8")
        return {"saved": str(f.relative_to(ws.root)), "hash": hashlib.sha1(new.encode()).hexdigest(), "check": result}, None

    def publish_draft(body):
        """재생이 통과한 초안만 scenarios/로 옮긴다 (재생 뒤 초안이 바뀌었으면 거절)."""
        name = str(body.get("name") or "")
        f = draft_path(name)
        with job["lock"]:
            if job.get("draft") != name or job["proc"] is None or job["proc"].poll() is None or job["code"] != 0:
                return None, "먼저 이 초안을 재생해서 통과해야 저장할 수 있습니다"
            if not f.exists() or hashlib.sha1(f.read_bytes()).hexdigest() != job.get("draftHash"):
                return None, "재생한 뒤 초안이 바뀌었습니다 — 다시 재생하세요"
        target = ws.root / "scenarios" / f"{name}.qa.yml"
        if target.exists() and not body.get("force"):
            return None, f"이미 있습니다: scenarios/{name}.qa.yml (덮어쓰기를 고르세요)"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        f.unlink()
        update_readme(ws)
        return {"saved": f"scenarios/{name}.qa.yml"}, None

    def live_reader(proc):
        err = []
        threading.Thread(target=lambda: err.extend(proc.stderr.read().decode("utf-8", "replace").splitlines()), daemon=True).start()
        try:
            while True:
                head = proc.stdout.read(4)
                if len(head) < 4:
                    break
                data = proc.stdout.read(int.from_bytes(head, "big"))
                now = time.time()
                with live["cond"]:
                    # '화면이 바뀜' = 마지막으로 크게 바뀐 화면보다 JPEG 크기가 2% 넘게 다름. 커서 깜박임·작은 움직임은
                    # 2% 미만이라 빼고(시범 앱 검색 화면: 70번 모두 <2%), 화면 전환은 3~51%. 조금씩 쌓인 변화도 잡힌다.
                    base = live["base_size"]
                    if not base or abs(len(data) - base) > base * 0.02:
                        live["changed_at"], live["base_size"] = now, len(data)
                    live["frame"] = data
                    live["seq"] += 1
                    live["frames"] = [t for t in live["frames"] if now - t < 2] + [now]
                    live["cond"].notify_all()
                    idle = live["clients"] == 0 and now - live["idle_since"] > 30
                if idle:
                    proc.terminate()
        finally:
            proc.wait()
            with live["cond"]:
                if live["proc"] is proc:
                    live["proc"] = None
                    if proc.returncode not in (0, -15):   # 스스로 멈춤 = 실패 (비공개 API가 바뀌었거나 시뮬레이터 꺼짐)
                        live["error"] = next((l for l in err if l.startswith(("simscreen:", "androidframes:"))), None) \
                            or f"종료 코드 {proc.returncode}"
                        live["failed_at"] = time.time()
                live["cond"].notify_all()

    def live_start():
        """실시간 화면 도구를 띄운다. 안 되면 (False, 이유) — 30초 동안은 다시 시도하지 않는다."""
        with live["cond"]:
            if live["proc"] and live["proc"].poll() is None:
                return True, None
            if live["error"] and time.time() - live["failed_at"] < 30:
                return False, live["error"]
        if android:
            try:
                st = android_live_runner(ws, udid)
            except RuntimeError as e:   # 다른 실행이 기기를 쓰는 중 → 잠깐 뒤 다시 (실패 기록은 5초만)
                with live["cond"]:
                    live.update(error=str(e), failed_at=time.time() - 25)
                return False, live["error"]
            except SystemExit:
                with live["cond"]:
                    live.update(error="상주 실행기를 띄우지 못함 (터미널 출력 확인)", failed_at=time.time())
                return False, live["error"]
            proc = subprocess.Popen([sys.executable, str(KIT_DIR / "bin" / "qakit"), "android", "frames",
                                     "--port", str(st["framePort"])], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with live["cond"]:
                live.update(proc=proc, error=None, frame=None, idle_since=time.time())
            threading.Thread(target=live_reader, args=(proc,), daemon=True).start()
            return True, None
        tool = ensure_simscreen()
        if not tool:
            with live["cond"]:
                live.update(error="실시간 화면 도구 빌드 실패", failed_at=time.time())
            return False, live["error"]
        proc = subprocess.Popen([str(tool), udid, "--fps", "24", "--width", "600", "--quality", "0.65"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with live["cond"]:
            live.update(proc=proc, error=None, frame=None, idle_since=time.time())
        threading.Thread(target=live_reader, args=(proc,), daemon=True).start()
        return True, None

    rec = {"proc": None, "file": None, "started": None, "lock": threading.Lock()}

    def record_start():
        """라이브 세션 녹화: simctl recordVideo → results/recordings/<시각>.mp4"""
        with rec["lock"]:
            if rec["proc"] and rec["proc"].poll() is None:
                return None, "이미 녹화 중"
            out = ws.results_dir / "recordings" / (datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp4")
            out.parent.mkdir(parents=True, exist_ok=True)
            if android:
                proc = android_record_start(udid)
                time.sleep(1)
                if proc.poll() is not None:
                    return None, (proc.stderr.read().decode("utf-8", "replace").strip().splitlines() or ["녹화 시작 실패"])[-1]
                rec.update(proc=proc, file=out, started=time.time())
                return {"recording": True, "started": rec["started"]}, None
            proc = subprocess.Popen(["xcrun", "simctl", "io", udid, "recordVideo", "--codec=h264", "--force", str(out)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            err = b""
            end = time.time() + 8
            while time.time() < end:   # 첫 프레임이 처리되면 stderr에 "Recording started"
                line = proc.stderr.readline()
                err += line
                if b"Recording started" in line or not line:
                    break
            if proc.poll() is not None:
                return None, (err.decode("utf-8", "replace").strip().splitlines() or ["녹화 시작 실패"])[-1]
            threading.Thread(target=lambda: proc.stderr.read(), daemon=True).start()
            rec.update(proc=proc, file=out, started=time.time())
            return {"recording": True, "started": rec["started"]}, None

    def record_stop():
        with rec["lock"]:
            proc, out = rec["proc"], rec["file"]
            rec.update(proc=None, started=None)
        if not proc:
            return None, "녹화 중이 아님"
        if android:
            android_record_stop(udid, proc, out)   # 기기 안 파일을 마무리하고 가져온다 (최대 3분)
        else:
            proc.send_signal(signal.SIGINT)   # simctl은 SIGINT를 받아야 파일을 마무리한다
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        if not out.exists() or out.stat().st_size == 0:
            return None, "녹화 파일이 비었습니다"
        return {"dir": "recordings", "name": out.name, "bytes": out.stat().st_size}, None

    aij = {"proc": None, "engine": None, "goal": None, "started": None, "ended": None, "code": None, "events": [],
           "result": None, "dir": None, "limit": None, "stopped": None, "lock": threading.Lock()}

    def ai_start(body):
        """UI에서 AI QA 시작: 로그인된 claude/codex를 qakit 도구만 허용해 실행 (qakit은 토큰을 다루지 않음)."""
        goal = str(body.get("goal") or "").strip()
        engine = body.get("engine") or "claude"
        minutes = max(1, min(60, int(body.get("minutes") or 10)))
        turns = max(5, min(300, int(body.get("turns") or 60)))
        if not goal or len(goal) > 2000:
            return None, "목표를 적어 주세요 (2000자 이내)"
        mode = "scenario" if body.get("mode") == "scenario" else "qa"
        sc_name = str(body.get("name") or "").strip() or None
        if sc_name and not re.fullmatch(r"[a-z0-9][a-z0-9\-]*", sc_name):
            return None, "시나리오 이름은 영문 소문자·숫자·- 만 (예: login-03-empty-password)"
        sc_tags = [t.strip() for t in body.get("tags") or [] if re.fullmatch(r"[A-Za-z0-9가-힣_-]+", str(t).strip())]
        sc_start = str(body.get("start") or "").strip() or None
        context = None
        if body.get("fromSession"):   # AI QA 결과 → 시나리오
            src_dir = ui_safe_dir(ws, str(body["fromSession"]))
            if not src_dir or src_dir.parent != (ws.results_dir / "ai").resolve():
                return None, "바탕이 될 AI 세션을 찾지 못함"
            context = ai_session_context(ws, src_dir)
            mode = "scenario"
        if sc_start and not (ws.root / "steps" / f"{sc_start}.qa.yml").exists():
            return None, f"공통 단계가 없습니다: steps/{sc_start}.qa.yml"
        if not udid:
            return None, "AI QA는 지금 시뮬레이터만"
        if android:
            return None, "AI QA는 아직 iOS만 (안드로이드는 다음 단계)"
        eng = next((e for e in ai_engines() if e["id"] == engine), None)
        if not eng or not eng["ready"]:
            return None, f"{engine}: {(eng or {}).get('note', '없음')}"
        with aij["lock"]:
            if aij["proc"] and aij["proc"].poll() is None:
                return None, "이미 AI QA가 돌고 있습니다"
        if job["proc"] and job["proc"].poll() is None:
            return None, "시나리오 실행 중에는 시작할 수 없습니다"
        d = ws.results_dir / "ai" / datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({"client": eng["name"], "goal": goal, "via": "qakit ui", "minutes": minutes,
                                                 "mode": mode, "touch": "direct" if direct else "xcuitest", **({"name": sc_name} if sc_name else {}),
                                                 **({"fromSession": str(body["fromSession"])} if body.get("fromSession") else {}),
                                                 "turns": turns, "started": datetime.datetime.now().isoformat(timespec="seconds")},
                                                ensure_ascii=False), encoding="utf-8")
        read_src = mode == "scenario" and body.get("readSource", True) is not False and bool(ws.app_dir)
        direct = mode == "qa" and body.get("directTouch", True) is not False   # AI QA는 직접 터치 (tapflow 방식)
        prompt = ai_scenario_prompt(goal, minutes, sc_name, sc_tags, sc_start, source=str(ws.app_dir) if read_src else None,
                                    context=context) if mode == "scenario" \
            else ai_prompt(goal, minutes, bool(body.get("save")), direct=direct)
        cmd = ai_command(engine, ws, d, prompt, turns, read_source=read_src, direct=direct)
        try:
            proc = subprocess.Popen(cmd, cwd=str(ws.root), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=open(d / "agent.err", "w"), text=True, start_new_session=True)
        except OSError as e:
            return None, f"실행하지 못함: {e}"
        with aij["lock"]:
            aij.update(proc=proc, engine=engine, goal=goal, mode=mode, started=time.time(), ended=None, code=None, events=[],
                       result=None, dir=d, limit=minutes * 60, stopped=None)

        def reader():
            mask = masker(ws.secrets())
            with open(d / "agent.jsonl", "w", encoding="utf-8") as raw:
                for line in proc.stdout:
                    raw.write(mask(line))
                    raw.flush()
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    ev, res = ai_events(engine, obj)
                    with aij["lock"]:
                        aij["events"] += [dict(e, t=round(time.time() - aij["started"], 1), text=mask(e["text"])) for e in ev]
                        if res:
                            aij["result"] = dict(res, text=mask(res["text"]))
            proc.wait()
            with aij["lock"]:
                aij.update(ended=time.time(), code=proc.returncode)
                result = aij["result"]
                if not result:
                    err = (d / "agent.err").read_text(encoding="utf-8", errors="replace").strip()[-600:]
                    aij["events"].append({"kind": "error", "t": round(time.time() - aij["started"], 1),
                                          "text": aij["stopped"] or f"보고서 없이 끝남 (종료 코드 {proc.returncode}) {err}"})
            if result and result.get("text"):
                (d / "report.md").write_text(result["text"] + "\n", encoding="utf-8")
            with contextlib.suppress(OSError, ValueError):
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                meta.update(ended=datetime.datetime.now().isoformat(timespec="seconds"), code=proc.returncode,
                            cost=(result or {}).get("cost"), turns_used=(result or {}).get("turns"))
                (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        def watchdog():   # 시간 한도
            try:
                proc.wait(timeout=minutes * 60)
            except subprocess.TimeoutExpired:
                ai_stop(f"시간 한도 {minutes}분이 지나 멈춤")
        threading.Thread(target=reader, daemon=True).start()
        threading.Thread(target=watchdog, daemon=True).start()
        return {"started": True, "dir": results_rel(ws, d)}, None

    def ai_stop(why="멈춤 (사용자)"):
        with aij["lock"]:
            proc = aij["proc"]
            if not proc or proc.poll() is not None:
                return None, "돌고 있는 AI QA가 없음"
            aij["stopped"] = why
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGTERM)   # 에이전트와 그 아래 MCP 서버까지
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(proc.pid, signal.SIGKILL)
        return {"stopped": True}, None

    def ai_state(since):
        with aij["lock"]:
            running = bool(aij["proc"]) and aij["proc"].poll() is None
            return {"running": running, "engine": aij["engine"], "goal": aij["goal"], "started": aij["started"], "mode": aij.get("mode"),
                    "ended": aij["ended"], "code": aij["code"], "limit": aij["limit"], "stopped": aij["stopped"],
                    "dir": results_rel(ws, aij["dir"]) if aij["dir"] else None, "total": len(aij["events"]),
                    "events": aij["events"][since:], "result": aij["result"]}

    def live_stop():
        with live["cond"]:
            proc = live["proc"]
        if proc and proc.poll() is None:
            proc.terminate()

    def grab_screen():
        with screen["lock"]:
            if time.time() - screen["at"] < 0.4 and screen["data"]:
                return screen["data"]
            if android:   # 라이브 화면 프레임을 쓴다 (adb screencap은 한 장에 몇 초)
                started, _ = live_start()
                with live["cond"]:
                    if started and not live["frame"]:
                        live["cond"].wait_for(lambda: live["frame"] is not None, timeout=10)
                    data = live["frame"]
                screen.update(at=time.time(), data=data)
                return data
            tmp = Path(tempfile.mkstemp(suffix=".jpg")[1])
            try:
                r = run(["xcrun", "simctl", "io", udid, "screenshot", "--type=jpeg", str(tmp)], check=False)
                data = tmp.read_bytes() if r.returncode == 0 else None
            finally:
                tmp.unlink(missing_ok=True)
            screen.update(at=time.time(), data=data)
            return data

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send_media(self, f, ctype, extra=None):
            """영상: Range 요청을 받아 부분만 보낸다 (Safari는 Range가 없으면 영상을 재생하지 않음)."""
            size = f.stat().st_size
            m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
            start, end = 0, size - 1
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
            self.send_response(206 if m else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if m:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            with f.open("rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(left, 256 * 1024))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            data = body if isinstance(body, bytes) else (
                body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if "Cache-Control" not in (extra or {}):
                self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def authed(self):
            cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
            return cookies.get("qakit_ui") == token

        def do_POST(self):
            # 실행 요청은 쿠키 + 전용 헤더 (다른 사이트가 몰래 보내는 요청 막기)
            if not self.authed() or self.headers.get("X-Qakit-UI") != "1":
                return self.send(401, {"error": "권한 없음"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(min(length, 100_000)) or b"{}")
            except ValueError:
                return self.send(400, {"error": "JSON이 아님"})
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/run":
                args_, err = start_job(body)
                return self.send(409 if err else 200, {"error": err} if err else {"started": True, "args": args_})
            if path == "/api/job/stop":
                return self.send(200, {"stopping": stop_job()})
            if path == "/api/src/check":
                if src_path(body.get("kind"), str(body.get("name") or "")) is None:
                    return self.send(400, {"error": "잘못된 이름"})
                return self.send(200, check_src(body.get("kind"), str(body.get("name")), str(body.get("text") or "")))
            if path == "/api/src/save":
                res, err = save_src(body)
                return self.send(409 if err else 200, {"error": err} if err else res)
            if path == "/api/draft":
                res, err = make_draft(body)
                return self.send(400 if err else 200, {"error": err} if err else res)
            if path == "/api/draft/verify":
                name = str(body.get("name") or "")
                if not SCENARIO_NAME_RE.fullmatch(name) or not draft_path(name).exists():
                    return self.send(400, {"error": "초안이 없습니다 — 먼저 초안을 만드세요"})
                args_, err = start_job({}, draft=name)
                return self.send(409 if err else 200, {"error": err} if err else {"started": True})
            if path == "/api/draft/publish":
                res, err = publish_draft(body)
                return self.send(409 if err else 200, {"error": err} if err else res)
            if path == "/api/worktree/update":   # 기준 브랜치의 새 커밋을 QA 브랜치로 병합 (push 안 함)
                if (job["proc"] and job["proc"].poll() is None) or (aij["proc"] and aij["proc"].poll() is None):
                    return self.send(409, {"error": "시나리오 실행·AI QA가 끝난 뒤에 최신화하세요"})
                base = str(body.get("base") or "").strip()
                if base and not re.fullmatch(r"[A-Za-z0-9._/#*\-]+", base):
                    return self.send(400, {"error": "브랜치 이름이 이상합니다"})
                r = subprocess.run([sys.executable, str(KIT_DIR / "bin" / "qakit"), "-w", str(ws.root), "worktree-update",
                                    *(["--from", base] if base else [])], capture_output=True, text=True, timeout=180)
                out = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout or "") + (r.stderr or "")).strip()
                return self.send(200, {"ok": r.returncode == 0, "output": masker(ws.secrets())(out),
                                       "status": worktree_info(Workspace(ws.root))})
            if path == "/api/worktree/config":   # qakit.yml worktree.base·update
                base = body.get("base")
                mode = body.get("mode")
                if base is not None and not re.fullmatch(r"[A-Za-z0-9._/#*\-]+", str(base)):
                    return self.send(400, {"error": "브랜치 이름이 이상합니다"})
                if mode is not None and mode not in ("auto", "warn", "off"):
                    return self.send(400, {"error": "update는 auto·warn·off"})
                set_worktree_config(ws, base=base, mode=mode)
                fresh = Workspace(ws.root)
                ws.worktree_base, ws.worktree_update = fresh.worktree_base, fresh.worktree_update
                return self.send(200, worktree_info(ws))
            if path in ("/api/ai/start", "/api/ai/stop"):
                res, err = ai_start(body) if path.endswith("start") else ai_stop()
                return self.send(409 if err else 200, {"error": err} if err else res)
            if path in ("/api/record/start", "/api/record/stop"):
                if not udid:
                    return self.send(404, {"error": "녹화는 시뮬레이터만"})
                res, err = record_start() if path.endswith("start") else record_stop()
                return self.send(409 if err else 200, {"error": err} if err else res)
            if path == "/api/touch":
                res, err = run_touch(body)
                return self.send(409 if err else 200, {"error": err} if err else res)
            if path == "/api/do":
                step = str(body.get("step") or "").strip()
                if not step or len(step) > 2000:
                    return self.send(400, {"error": "단계가 비었거나 너무 김"})
                res, err = run_do([step] if step not in ("launch", "reset") else [step])
                return self.send(409 if err else 200, {"error": err} if err else res)
            return self.send(404, {"error": "없는 주소"})

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            if q.get("token") == token:   # 처음 여는 링크의 토큰 → 쿠키로 바꾸고 주소에서 뺀다
                return self.send(302, b"", "text/plain", {
                    "Set-Cookie": f"qakit_ui={token}; HttpOnly; SameSite=Strict; Path=/", "Location": url.path or "/"})
            cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
            if cookies.get("qakit_ui") != token:
                return self.send(401, "qakit ui: 터미널에 나온 링크(토큰 포함)로 여세요", "text/plain; charset=utf-8")
            path = url.path
            try:
                if path == "/":
                    return self.send(200, (UI_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path.startswith("/assets/"):
                    f = (UI_DIR / path.lstrip("/")).resolve()
                    if UI_DIR.resolve() in f.parents and f.is_file() and f.suffix in static:
                        return self.send(200, f.read_bytes(), static[f.suffix], {"Cache-Control": "public, max-age=31536000, immutable"})
                    return self.send(404, {"error": "없는 파일"})
                if path == "/api/info":
                    state = app_state(ws)
                    sim = None if ws.device else (f"Android 에뮬레이터 {ws.emulator}" if android else ws.simulator)
                    return self.send(200, {"name": ws.name, "simulator": sim, "platform": ws.platform,
                                           "device": ws.device["name"] if ws.device else None,
                                           "bundleId": ws.package if android else ws.bundle_id, "kit": kit_version(), "precheck": ws.precheck,
                                           "app": {k: state.get(k) for k in ("branch", "commit", "dirtyFiles")}})
                if path == "/api/runs":
                    return self.send(200, ui_runs(ws, int(q.get("limit", 300))))
                if path == "/api/run":
                    detail = ui_run_detail(ws, q.get("dir"))
                    return self.send(200, detail) if detail else self.send(404, {"error": "결과 폴더 없음"})
                if path == "/api/file":
                    d = ui_safe_dir(ws, q.get("dir"))
                    f = (d / q.get("name", "")).resolve() if d else None
                    if not f or d not in f.parents or not f.is_file():
                        return self.send(404, {"error": "파일 없음"})
                    extra = {"Content-Disposition": f'attachment; filename="{f.name}"'} if q.get("download") else None
                    if f.suffix in (".png", ".jpg"):
                        return self.send(200, f.read_bytes(), "image/png" if f.suffix == ".png" else "image/jpeg", extra)
                    if f.suffix == ".mp4":
                        return self.send_media(f, "video/mp4", extra)
                    return self.send(200, masker(ws.secrets())(f.read_text(encoding="utf-8", errors="replace")),
                                     "text/plain; charset=utf-8")
                if path == "/api/scenarios":
                    return self.send(200, ui_scenarios(ws))
                if path == "/api/job":
                    return self.send(200, job_state(int(q.get("from", 0))))
                if path == "/api/elements":
                    res, err = run_do(["dump", "--settle", "0.3"])
                    if err:
                        return self.send(409, {"error": err})
                    if res["code"] != 0:
                        return self.send(500, {"error": res["output"][-400:]})
                    return self.send(200, dict(ui_parse_dump(res["output"]), platform=ws.platform))
                if path == "/api/src":
                    if q.get("list"):
                        return self.send(200, {
                            "scenario": sorted(f.name[:-len(".qa.yml")] for f in (ws.root / "scenarios").glob("*.qa.yml")),
                            "step": sorted(f.name[:-len(".qa.yml")] for f in (ws.root / "steps").glob("*.qa.yml"))})
                    f = src_path(q.get("kind"), q.get("name", ""))
                    if f is None or not f.exists():
                        return self.send(404, {"error": "파일 없음"})
                    text = f.read_text(encoding="utf-8")
                    return self.send(200, {"text": text, "hash": hashlib.sha1(text.encode()).hexdigest(),
                                           "path": str(f.relative_to(ws.root))})
                if path == "/api/ids":
                    term = q.get("q", "").lower()
                    ids = sorted(known_ids(ws))   # 안드로이드는 저장된 덤프에서 본 ID
                    hits = [i for i in ids if term in i.lower()] if term else ids
                    return self.send(200, {"total": len(ids), "ids": hits[:80]})
                if path == "/api/steps-files":
                    return self.send(200, sorted(f.name[:-len(".qa.yml")] for f in (ws.root / "steps").glob("*.qa.yml")))
                if path == "/api/do-steps":
                    steps, from_launch = do_log_read(ws)
                    return self.send(200, {"steps": steps, "fromLaunch": from_launch})
                if path == "/api/taps":   # since=-1: 지금 끝 위치만 (지난 기록은 안 보냄)
                    p = taps_path(ws)
                    size = p.stat().st_size if p.exists() else 0
                    since = int(q.get("since", "-1") or -1)
                    if since < 0 or since == size:
                        return self.send(200, {"offset": size, "taps": []})
                    if since > size:
                        since = 0
                    with p.open("rb") as f:
                        f.seek(since)
                        chunk = f.read(size - since)
                    end = chunk.rfind(b"\n") + 1   # 쓰는 중인 마지막 줄은 다음에
                    taps = []
                    for line in chunk[:end].decode("utf-8", "replace").splitlines():
                        try:
                            taps.append(json.loads(line))
                        except ValueError:
                            pass
                    return self.send(200, {"offset": since + end, "taps": taps[-20:]})
                if path == "/api/worktree":
                    return self.send(200, worktree_info(ws, fetch=bool(q.get("fetch"))))
                if path == "/api/coverage":
                    return self.send(200, coverage(ws))
                if path == "/api/ai/sessions":
                    return self.send(200, ai_sessions(ws))
                if path == "/api/ai/session":
                    d = ui_safe_dir(ws, q.get("dir"))
                    if not d or d.parent != (ws.results_dir / "ai").resolve():
                        return self.send(404, {"error": "AI 세션 없음"})
                    return self.send(200, ai_session_info(ws, d, full=True))
                if path == "/api/ai/engines":
                    return self.send(200, ai_engines())
                if path == "/api/ai/job":
                    return self.send(200, ai_state(int(q.get("since", 0) or 0)))
                if path == "/api/ai":   # 가장 최근 AI 세션 (qakit mcp) — 활동 기록·지금 하는 일·보고한 문제
                    root = ws.results_dir / "ai"
                    sessions = sorted([d for d in root.iterdir() if d.is_dir()], reverse=True) if root.is_dir() else []
                    if not sessions:
                        return self.send(200, {"session": None})
                    d = sessions[0]
                    rows = []
                    for line in (d / "log.jsonl").read_text(encoding="utf-8").splitlines() if (d / "log.jsonl").exists() else []:
                        with contextlib.suppress(ValueError):
                            rows.append(json.loads(line))
                    now_ = meta = None
                    with contextlib.suppress(OSError, ValueError):
                        now_ = json.loads((d / "now.json").read_text(encoding="utf-8"))
                    with contextlib.suppress(OSError, ValueError):
                        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                    alive = True
                    pid = (now_ or meta or {}).get("pid")
                    if pid:
                        try:
                            os.kill(int(pid), 0)
                        except (OSError, ValueError):
                            alive = False   # MCP 서버가 끝남 (AI 세션 종료)
                    if now_ and not alive:
                        now_ = None
                    last = rows[-1]["at"] if rows else (meta or {}).get("started")
                    recent = bool(last) and (datetime.datetime.now() - datetime.datetime.fromisoformat(last)).total_seconds() < 120
                    issues = []
                    with contextlib.suppress(OSError):
                        for line in (d / "issues.jsonl").read_text(encoding="utf-8").splitlines():
                            with contextlib.suppress(ValueError):
                                r = json.loads(line)
                                issues.append({k: r.get(k) for k in ("n", "title", "severity", "screenshot")})
                    since = int(q.get("since", 0) or 0)
                    return self.send(200, {"session": d.name, "dir": results_rel(ws, d), "client": (meta or {}).get("client"),
                                           "active": bool(now_) or (alive and recent), "now": now_, "total": len(rows),
                                           "rows": rows[since:][-100:], "issues": issues})
                if path == "/api/record":
                    with rec["lock"]:
                        on = bool(rec["proc"] and rec["proc"].poll() is None)
                        return self.send(200, {"recording": on, "started": rec["started"] if on else None})
                if path == "/api/stream-status":
                    with live["cond"]:
                        running = bool(live["proc"] and live["proc"].poll() is None)
                        return self.send(200, {"running": running, "error": None if running else live["error"],
                                               "fps": round(len(live["frames"]) / 2, 1) if running else 0,
                                               "changedAt": live["changed_at"] if running else None, "now": time.time()})
                if path == "/api/stream":   # MJPEG (multipart/x-mixed-replace) — <img>가 그대로 보여 준다
                    if not udid:
                        return self.send(404, {"error": "실시간 화면은 시뮬레이터만"})
                    started, why = live_start()
                    if not started:
                        return self.send(503, {"error": why})
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=qakitframe")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    with live["cond"]:
                        live["clients"] += 1
                    seq = -1
                    try:
                        while True:
                            with live["cond"]:
                                live["cond"].wait_for(lambda: live["seq"] != seq or live["proc"] is None, timeout=5)
                                if live["proc"] is None:
                                    break
                                frame, seq = live["frame"], live["seq"]
                            if frame:
                                self.wfile.write(b"--qakitframe\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                                 + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        with live["cond"]:
                            live["clients"] -= 1
                            live["idle_since"] = time.time()
                    return
                if path == "/api/screen":
                    if not udid:
                        return self.send(404, {"error": "라이브 화면은 시뮬레이터만 (실기기는 아직)"})
                    data = grab_screen()
                    return self.send(200, data, "image/jpeg") if data else self.send(503, {"error": "스크린샷 실패 (시뮬레이터가 꺼짐?)"})
                return self.send(404, {"error": "없는 주소"})
            except BrokenPipeError:
                pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    ok(f"qakit ui: {url}")
    info("실행 기록·시나리오 실행·시뮬레이터 라이브 화면. 끝내려면 Ctrl+C")
    if not args.no_open:
        run(["open", url], check=False)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        stop_job()   # UI를 끄면 UI에서 시작한 실행도 멈춘다
        live_stop()
        if aij["proc"] and aij["proc"].poll() is None:
            ai_stop("qakit ui 종료")
        if rec["proc"]:
            record_stop()
        if touch["helper"]:
            touch["helper"].stop()
        server.server_close()


def simulator_viewer_app():
    """시뮬레이터 화면 앱: Xcode 27+는 Device Hub, 이전은 Simulator. 없으면 None."""
    dev = Path(run(["xcode-select", "-p"], check=False).stdout.strip() or "/Applications/Xcode.app/Contents/Developer")
    for cand in (dev.parent / "Applications" / "DeviceHub.app", dev / "Applications" / "Simulator.app"):
        if cand.exists():
            return cand
    return None


def cmd_show(args):
    """시뮬레이터 화면을 띄우고 대상 앱을 실행한다 (로그인 등 사람이 직접 만질 때)."""
    ws = find_workspace(args.workspace)
    if ws.device:
        fail("qakit show는 시뮬레이터용입니다. 실기기는 기기 화면을 직접 보세요.")
    udid = ensure_booted(ws)
    viewer = simulator_viewer_app()
    if viewer:
        run(["open", str(viewer), "--args", "-CurrentDeviceUDID", udid], check=False)
        ok(f"{viewer.stem} 열림 → {ws.simulator}")
    else:
        warn("시뮬레이터 화면 앱(Device Hub / Simulator)을 찾지 못했습니다. Xcode 설치를 확인하세요")
    if args.no_launch:
        return
    if not app_installed(udid, ws.bundle_id):
        fail(f"시뮬레이터에 {ws.bundle_id}가 설치되어 있지 않습니다.", "qakit build-app")
    r = run(["xcrun", "simctl", "launch", udid, ws.bundle_id], check=False)
    if r.returncode == 0:
        ok(f"{ws.bundle_id} 실행")
    else:
        warn(f"앱을 실행하지 못했습니다: {(r.stdout or '').strip()[-200:]}")
    info("상주 실행기나 테스트가 도는 동안에는 화면을 만지지 마세요 (입력이 섞임)")


def cmd_do(args):
    """시나리오 단계 하나를 상주 실행기로 바로 실행 (없으면 띄운다). 통과한 단계는 기록해 두었다가 save로 시나리오 초안을 만든다."""
    ws = find_workspace(args.workspace)
    if args.step[0] == "steps" and len(args.step) == 1:
        return do_steps(ws)
    if args.step[0] == "save":
        if len(args.step) != 2:
            fail("저장할 시나리오 이름이 필요합니다.", "예) qakit do save home-12-banner")
        return do_save(ws, args.step[1], force=args.force, title=args.title, tags=args.tag, start=args.start)
    udid = _serve_udid(ws)
    text = " ".join(args.step).strip()
    if not text:
        fail("실행할 단계가 필요합니다.", "예) qakit do 'tap: home_search_button'  ·  qakit do dump")
    path, body = SERVE_COMMANDS.get(text), {}
    if path == "/dump":
        body = {"settle": args.settle}
    if path is None:
        path = "/step"
        try:
            step = scenario_tools.parse_yaml(text)
        except Exception as e:  # noqa: BLE001 — 사용자 입력 오류를 그대로 보여 준다
            fail(f"단계를 읽지 못했습니다: {e}", "시나리오 단계 문법 그대로: 'tap: X', 'wait: { for: X, timeout: 10 }'")
        if isinstance(step, list) and len(step) == 1:
            step = step[0]
        if not isinstance(step, dict):
            fail(f"단계는 '이름: 값' 형식이어야 합니다: {text}")
        try:
            steps = scenario_tools._expand([step], ws.root, ["qakit do"])   # use: 공통 단계 펼치기
        except ValueError as e:
            fail(str(e))
        body = steps[0] if len(steps) == 1 else {"group": "qakit do", "steps": steps}

    t0 = time.time()
    with sim_lock(ws, f"qakit do {text[:40]}"):
        before = (serve_load(udid) or {}).get("pid")
        st = serve_ensure(ws, udid)
        fresh = st.get("pid") != before   # 이번에 실행기를 새로 띄웠나
        try:
            res = serve_request(st, path, body, timeout=args.timeout)
        except ServeTimeout:
            serve_stop(udid, quiet=True, force=True)
            fail(f"{args.timeout}초 안에 끝나지 않아 상주 실행기를 멈췄습니다 (다음 명령 때 다시 띄움).",
                 "앱이 계속 움직이는 화면(애니메이션)이면 XCUITest가 멈출 수 있습니다. --timeout 으로 늘릴 수 있습니다")
        except ConnectionError as e:
            serve_stop(udid, quiet=True)
            fail(f"상주 실행기에 연결하지 못했습니다: {e}", "다시 실행하면 새로 띄웁니다")

    secs = (res.get("durationMs") or 0) / 1000
    for f in save_serve_files(ws, res):
        info(f"덤프 저장: {f}")
    total = time.time() - t0
    # 실행기 시간만 보이면 첫 명령(실행기 시작)이 짧아 보인다 → 새로 띄웠으면 명령 전체 시간도
    extra_time = f" · 실행기 시작 포함 전체 {total:.0f}초" if fresh else ""
    dump = res.get("dump")
    if res.get("ok"):
        if path == "/launch":
            do_log_write(ws, {"event": "launch"}, reset=True)   # 새 기록 시작
        elif path == "/step" and not getattr(args, "no_record", False):
            do_log_write(ws, {"step": text})
        if path == "/dump" and dump:
            text_out = masker(ws.secrets())(dump)
            (ws.results_dir).mkdir(exist_ok=True)
            (ws.results_dir / "ui-dump.txt").write_text(text_out, encoding="utf-8")
            print(text_out, end="" if text_out.endswith("\n") else "\n")
        elif path == "/ping":
            ok(f"응답 {secs:.2f}초 · 앱 상태 {res.get('appState')}{extra_time}")
        else:
            ok(f"{secs:.1f}초{extra_time}")
        return
    msg = masker(ws.secrets())(res.get("message") or "실패")
    print(f"❌ {msg}  ({secs:.1f}초{extra_time})")
    if dump:
        out = ws.results_dir / "do-fail-dump.txt"
        ws.results_dir.mkdir(exist_ok=True)
        out.write_text(masker(ws.secrets())(dump), encoding="utf-8")
        for line in suggestion_lines(res.get("message") or "", dump):
            print(masker(ws.secrets())(line))
        print(f"   실패 시점 화면 구조: {out}")
    sys.exit(1)


