# qakit — qakit mcp (AI QA 도구)·AI 엔진·AI 세션
# bin/qakit이 lib/qakit/*.py를 이름 순서대로 한 이름 공간에 읽는다 (따로 import하지 않음).
# ─────────────────────────────── MCP 서버 (AI QA, A1) ───────────────────────────────
# Claude Code·Codex 같은 AI가 앱을 직접 QA하게 하는 도구 모음 (stdio JSON-RPC, 표준 라이브러리만).
# 모든 조작은 qakit do 단계(ID·라벨) — AI가 확인한 경로가 그대로 시나리오가 된다. docs/PLAN.md "AI QA 설계".

MCP_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

MCP_INSTRUCTIONS = """qakit: iOS 시뮬레이터의 앱을 ID·라벨로 조작하고 확인하는 QA 도구.
순서: get_testing_guide(처음 한 번) → launch → screen(화면 구조 읽기) → tap·type_text·swipe·wait_for·expect → screen으로 결과 확인 → 반복.
- 화면은 screen(텍스트)으로 읽는다. screenshot은 색·배치·이미지처럼 눈으로만 아는 것에만 (토큰이 많이 듦).
- 대상(target)은 screen에 나온 #ID를 우선 쓴다. ID가 없으면 { type, label } (줄바꿈 라벨은 contains). 좌표 탭은 없다.
- 비밀번호 등은 {secret:키} (작업공간 secrets.txt의 키)로만 친다. 실제 값을 묻거나 출력하지 않는다.
- 문제는 같은 단계로 한 번 더 재현한 뒤 report_issue로 남긴다. 확인된 경로는 save_scenario로 시나리오로 남긴다 (재생해서 통과해야 남음).
- 조작 도구에는 why(왜 하는지 한 줄)를 같이 준다 — 사람이 `qakit ui` 라이브 세션에서 실시간 화면·커서·활동 기록으로 지켜본다."""

MCP_GUIDE = """# qakit으로 앱 QA하기

## 무엇을 확인하나 (요청 범위 안에서)
1. 정상 경로: 요청한 기능을 처음부터 끝까지. 각 단계 뒤 기대한 화면·문구가 나오는지 expect로 확인.
2. 입력 경계: 빈 값, 아주 긴 값, 특수문자·이모지, 공백만, 잘못된 형식 (입력칸이 있으면).
3. 되돌아가기: 뒤로·닫기 뒤 이전 화면 상태가 맞는지, 같은 버튼 두 번 누르기.
4. 목록·스크롤: 끝까지 쓸어 보기 (swipe), 빈 목록 안내.
5. 문구: 오타, 잘린 글자(…), 다른 언어 섞임, 플레이스홀더가 그대로 나옴.
6. 상태 유지: 앱을 다시 켜도(launch) 남아야 할 것이 남는지.

## 여기서 확인할 수 없는 것
네트워크 끊기, 푸시 알림 수신, 결제, 카메라·사진첩 실제 촬영, 다른 앱과의 전환, 실제 기기 성능.
→ 보고서에 "확인하지 못함"으로 적는다.

## 거짓 버그 피하기
- 요소를 못 찾았다고 바로 버그가 아니다: screen으로 다시 읽고, 로딩이면 wait_for, 화면 밖이면 swipe.
- 실패 메시지의 "대신 이 대상?" 제안을 먼저 본다.
- 버그는 launch부터 같은 단계로 한 번 더 재현한 뒤 report_issue(reproduced: true).
- 서버 데이터에 따라 달라지는 것(목록 내용·개수)은 버그로 보지 않는다.

## 시나리오로 남기기
- 확인한 정상 경로는 launch부터 다시 깨끗하게 밟은 뒤 save_scenario(name, title, tags). 저장하면 앱을 새로 켜고 재생해서 통과해야 남는다.
- 이름은 화면-번호-내용 (예: login-03-empty-password). 이미 있는 시나리오는 list_scenarios로 확인.

## 보고 형식 (마지막 답변)
- 확인한 것 (통과): 항목별 한 줄
- 문제 (report_issue로 남긴 것): 제목 · 심각도 · 재현 단계 · 기대 · 실제 · 사진 경로
- 확인하지 못한 것과 이유
- 남긴 시나리오 이름"""


def mcp_scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    plain = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", s) and s not in ("true", "false", "null", "yes", "no")
    return s if plain else json.dumps(s, ensure_ascii=False)


def mcp_yaml(v):
    """JSON 값 → 한 줄 YAML (시나리오 문법). {"id": "a"} → { id: a }"""
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k}: {mcp_yaml(x)}" for k, x in v.items()) + " }"
    if isinstance(v, list):
        return "[" + ", ".join(mcp_yaml(x) for x in v) + "]"
    return mcp_scalar(v)


MCP_TARGET = {"description": "대상: screen에 나온 ID 문자열 (예: \"LoginView.loginButton\"), 또는 "
                             "{ id, index } / { type: button|text|cell|textfield|…, label } / { type, contains } 객체",
              "anyOf": [{"type": "string"}, {"type": "object"}]}
MCP_CONDITION = {"type": "object", "description": "조건: { visible: 대상 } · { exists: 대상 } · { hittable: 대상 } · "
                                                  "{ missing: 대상 } · { hidden: 대상 } · { all: [조건…] } · { any: [조건…] }. "
                                                  "tap의 expect에서 visible은 '보이고 누를 수 있음', missing·hidden은 '누를 수 없음'(위에 다른 화면이 덮음 포함)"}


MCP_WHY = {"type": "string", "description": "왜 하는지 한 줄 (사람이 qakit ui에서 지켜볼 때 보임). 예) 빈 검색어로 검색해 안내 문구 확인"}
MCP_ACTIONS = ("launch", "tap", "type_text", "swipe", "wait_for", "expect", "step", "run_scenario", "save_scenario")


def mcp_tools():
    def tool(name, desc, props=None, required=()):
        props = dict(props or {})
        if name in MCP_ACTIONS:
            props["why"] = MCP_WHY
        return {"name": name, "description": desc,
                "inputSchema": {"type": "object", "properties": props, "required": list(required)}}
    return [
        tool("get_testing_guide", "QA할 때 확인할 항목·여기서 못 하는 것·거짓 버그 피하기·보고 형식. 테스트 전에 한 번 읽는다."),
        tool("launch", "앱을 종료하고 새로 켠다. 기록(recorded_steps)도 여기서부터 새로 시작한다."),
        tool("screen", "지금 화면 구조: 요소마다 종류 #ID \"라벨\" @x,y 너비x높이. 대상(target)은 여기 나온 ID·라벨을 쓴다.",
             {"all": {"type": "boolean", "description": "true면 라벨·ID 없는 요소까지 (기본 false)"}}),
        tool("screenshot", "지금 화면 사진 (작게, JPEG). 색·배치·이미지처럼 화면 구조로 알 수 없는 것만 볼 때."),
        tool("tap", "요소를 누른다. expect를 주면 누른 뒤 그 조건이 맞아야 통과 (누르기 전에 이미 맞으면 실패).",
             {"target": MCP_TARGET, "expect": MCP_CONDITION,
              "timeout": {"type": "number", "description": "요소가 나타날 때까지 기다릴 초 (기본 10)"}}, ["target"]),
        tool("type_text", "입력칸에 글자를 친다 (기존 글자는 지움). 비밀번호는 {secret:키}.",
             {"into": MCP_TARGET, "text": {"type": "string"}}, ["into", "text"]),
        tool("swipe", "요소 위에서 쓸기 (목록 스크롤: dir up = 아래 내용 보기).",
             {"on": MCP_TARGET, "dir": {"type": "string", "enum": ["up", "down", "left", "right"]}}, ["on", "dir"]),
        tool("wait_for", "요소가 나타날 때까지 기다린다.",
             {"target": MCP_TARGET, "timeout": {"type": "number", "description": "초 (기본 10)"}}, ["target"]),
        tool("expect", "조건이 지금 맞는지 확인 (안 맞으면 실패로 돌려줌).", {"condition": MCP_CONDITION}, ["condition"]),
        tool("step", "시나리오 단계 한 줄을 그대로 실행 (위 도구로 안 되는 것: use: 공통단계, hide-keyboard, scroll-to, if 등). "
                     "예) \"use: login\", \"hide-keyboard: true\"",
             {"yaml": {"type": "string"}}, ["yaml"]),
        tool("recorded_steps", "마지막 launch 이후 통과한 단계 목록 (save_scenario가 이것으로 시나리오를 만든다)."),
        tool("list_scenarios", "이미 있는 시나리오 (이름·제목·태그·최근 결과)."),
        tool("list_common_steps", "공통 단계(steps/) 목록 — 여러 시나리오가 앞에 쓰는 경로 (예: home = 앱 켜고 홈 탭까지). "
                                  "step 도구로 \"use: <이름>\"을 실행하면 그 단계를 밟는다."),
        tool("read_scenario", "시나리오(scenarios/)나 공통 단계(steps/)의 .qa.yml 내용 — 새 시나리오를 만들 때 스타일을 맞추려고 읽는다.",
             {"name": {"type": "string"}, "kind": {"type": "string", "enum": ["scenario", "step"], "description": "기본 scenario"}},
             ["name"]),
        tool("run_scenario", "시나리오 하나를 실행하고 결과 요약 (실패하면 원인·제안·화면 구조).",
             {"name": {"type": "string"}, "reuse_app": {"type": "boolean", "description": "앱이 시작 화면이면 다시 켜지 않음"}},
             ["name"]),
        tool("save_scenario", "recorded_steps를 scenarios/<name>.qa.yml로 저장한다. 저장 뒤 앱을 새로 켜고 재생해서 "
                              "통과해야 남는다 (실패하면 .qakit/drafts/로 옮기고 원인을 돌려줌). launch부터 깨끗하게 밟은 뒤 쓴다.",
             {"name": {"type": "string", "description": "예) login-03-empty-password"},
              "title": {"type": "string", "description": "무엇을 확인하나 (한 줄)"},
              "tags": {"type": "array", "items": {"type": "string"}},
              "start": {"type": "string", "description": "맨 앞에 넣을 공통 단계 이름 (예: home)"},
              "overwrite": {"type": "boolean"}}, ["name", "title"]),
        tool("report_issue", "찾은 문제를 남긴다 (지금 화면 사진을 같이). 같은 단계로 한 번 더 재현한 뒤에만.",
             {"title": {"type": "string"}, "severity": {"type": "string", "enum": ["높음", "중간", "낮음"]},
              "steps": {"type": "array", "items": {"type": "string"}, "description": "재현 단계 (시나리오 단계 꼴)"},
              "expected": {"type": "string"}, "actual": {"type": "string"},
              "reproduced": {"type": "boolean", "description": "launch부터 같은 단계로 다시 재현했는가"}},
             ["title", "severity", "steps", "expected", "actual", "reproduced"]),
    ]


class FrameRing:
    """AI 세션 동안 시뮬레이터 화면 장면을 마지막 seconds초만 메모리에 (simscreen, 초당 10장·폭 440).
    report_issue 때 그 장면들로 mp4 (simscreen --encode). 통째 녹화보다 작고, 문제 직전만 남는다."""

    def __init__(self, udid, seconds=30):
        self.udid, self.seconds = udid, seconds
        self.frames = collections.deque()
        self.lock = threading.Lock()
        self.proc = None

    def start(self):
        if self.proc or not self.udid:
            return
        tool = ensure_simscreen()
        if not tool:
            return
        try:
            self.proc = subprocess.Popen([str(tool), self.udid, "--fps", "10", "--width", "440", "--quality", "0.6"],
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        out = self.proc.stdout
        while True:
            head = out.read(4)
            if len(head) < 4:
                return
            data = out.read(int.from_bytes(head, "big"))
            now = time.time()
            with self.lock:
                self.frames.append((now, data))
                while self.frames and now - self.frames[0][0] > self.seconds:
                    self.frames.popleft()

    def save(self, path):
        """→ 영상 길이(초) 또는 None"""
        with self.lock:
            frames = list(self.frames)
        tool = ensure_simscreen()
        if len(frames) < 2 or not tool:
            return None
        buf = b"".join(struct.pack(">dI", t, len(j)) + j for t, j in frames)
        r = subprocess.run([str(tool), "--encode", str(path)], input=buf, capture_output=True, timeout=120)
        if r.returncode != 0 or not Path(path).exists():
            return None
        return round(frames[-1][0] - frames[0][0], 1)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


class McpSession:
    """도구 호출을 qakit do / run 하위 프로세스로. 활동 기록·문제 보고는 results/ai/<시각>/"""

    def __init__(self, ws):
        self.ws = ws
        self.mask = masker(ws.secrets())
        self.dir = None
        self.client = None
        self.issues = 0
        self._udid = False   # 사진 찍을 때 처음 찾는다 (시뮬레이터가 없는 곳에서도 서버·다른 도구는 뜨게)
        self.ring = None      # 문제 보고 영상용 장면 보관 (첫 조작 때 시작)

    @property
    def udid(self):
        if self._udid is False:
            self._udid = None
            if not self.ws.device:
                with contextlib.suppress(Exception, SystemExit):
                    self._udid = simulator_udid(self.ws.simulator)[0]
        return self._udid

    def session_dir(self):
        if not self.dir:
            given = os.environ.get("QAKIT_AI_DIR")   # qakit ui에서 시작한 AI QA면 그 폴더 (에이전트 기록과 함께)
            self.dir = ws_dir = Path(given) if given else \
                self.ws.results_dir / "ai" / datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            ws_dir.mkdir(parents=True, exist_ok=True)
            meta = {}
            with contextlib.suppress(OSError, ValueError):
                meta = json.loads((ws_dir / "meta.json").read_text(encoding="utf-8"))
            meta.update({"client": meta.get("client") or self.client, "pid": os.getpid(), "kit": kit_version()})
            meta.setdefault("started", datetime.datetime.now().isoformat(timespec="seconds"))
            (ws_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return self.dir

    def now(self, tool=None, args=None):
        """지금 하는 일 (qakit ui가 'AI 조작 중'으로 보여 줌). tool=None이면 끝."""
        f = self.session_dir() / "now.json"
        if tool is None:
            f.unlink(missing_ok=True)
            return
        f.write_text(self.mask(json.dumps({"tool": tool, "args": args, "started": time.time(), "pid": os.getpid()},
                                          ensure_ascii=False)), encoding="utf-8")

    def log(self, tool, args, ok_, seconds, summary, why=None):
        row = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "tool": tool, "args": args, "ok": ok_,
               "seconds": round(seconds, 1), "summary": summary[:300], **({"why": why[:200]} if why else {})}
        with open(self.session_dir() / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(self.mask(json.dumps(row, ensure_ascii=False)) + "\n")

    def qakit(self, *args, timeout=180):
        try:
            r = subprocess.run([sys.executable, str(KIT_DIR / "bin" / "qakit"), "-w", str(self.ws.root), *args],
                               capture_output=True, text=True, timeout=timeout, env=dict(os.environ, PYTHONUNBUFFERED="1"))
        except subprocess.TimeoutExpired:
            return 124, f"{timeout}초 안에 끝나지 않음"
        text = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout or "") + (r.stderr or ""))
        return r.returncode, self.mask(text.strip())

    def do(self, step):
        code, out = self.qakit("do", step)
        return code == 0, out

    def screen(self, all_=False):
        code, out = self.qakit("do", "dump", "--settle", "0.3")
        if code != 0:
            return False, out[-1500:]
        parsed = ui_parse_dump(out)
        scr = parsed["screen"] or {}
        lines = [f"화면 {scr.get('w')}x{scr.get('h')} pt · 요소 {len(parsed['elements'])}개 (#ID가 있으면 대상으로 그 ID를 쓴다)"]
        body = [l for l in out.splitlines() if l and not l.startswith("#")] if all_ else None
        if body is not None:
            lines += body[:400]
        else:
            for e in parsed["elements"]:
                if e["type"] in ("Application", "Window"):
                    continue
                label = (e["labelRaw"] or "").replace("\n", "⏎")
                lines.append("  " * min(e["depth"], 6) + f'{e["type"]}' + (f' #{e["id"]}' if e["id"] else "")
                             + (f' "{label[:80]}"' if label else "") + (f' value="{e["value"][:40]}"' if e["value"] else "")
                             + f' @{e["x"]},{e["y"]} {e["w"]}x{e["h"]}')
            if len(lines) > 301:
                lines = lines[:301] + [f"...({len(lines) - 301}줄 생략 — 필요하면 swipe 후 다시)"]
        return True, "\n".join(lines)

    def shot(self, width=440):
        """작은 JPEG (simscreen, 안 되면 simctl)."""
        if not self.udid:
            return None
        tmp = Path(tempfile.mkstemp(suffix=".jpg")[1])
        try:
            tool = ensure_simscreen()
            if tool and run([str(tool), self.udid, "--once", str(tmp), "--width", str(width)], check=False).returncode == 0:
                return tmp.read_bytes()
            if run(["xcrun", "simctl", "io", self.udid, "screenshot", "--type=jpeg", str(tmp)], check=False).returncode == 0:
                return tmp.read_bytes()
            return None
        finally:
            tmp.unlink(missing_ok=True)

    def call(self, name, a):
        """→ (content 목록, 오류인가)"""
        if self.ring is None and name in MCP_ACTIONS and os.environ.get("QAKIT_AI_VIDEO", "1") != "0":
            self.ring = FrameRing(self.udid)
            self.ring.start()
        text = lambda t: [{"type": "text", "text": t}]
        if name == "get_testing_guide":
            return text(MCP_GUIDE), False
        if name == "launch":
            ok_, out = self.do("launch")
            return text(out), not ok_
        if name == "screen":
            ok_, out = self.screen(bool(a.get("all")))
            return text(out), not ok_
        if name == "screenshot":
            data = self.shot()
            if not data:
                return text("사진을 찍지 못함 (시뮬레이터만, 켜져 있어야 함)"), True
            return [{"type": "image", "data": base64.b64encode(data).decode(), "mimeType": "image/jpeg"}], False
        if name in ("tap", "type_text", "swipe", "wait_for", "expect", "step"):
            if name == "tap":
                target = a["target"]   # timeout·expect는 단계 키 (대상 안이 아님)
                step = {"tap": target, **({"timeout": a["timeout"]} if a.get("timeout") is not None else {}),
                        **({"expect": a["expect"]} if a.get("expect") else {})}
                line = mcp_yaml(step) if len(step) > 1 else f"tap: {mcp_yaml(target)}"
            elif name == "type_text":
                line = f"type: {mcp_yaml({'into': a['into'], 'text': a['text']})}"
            elif name == "swipe":
                line = f"swipe: {mcp_yaml({'on': a['on'], 'dir': a['dir']})}"
            elif name == "wait_for":
                line = f"wait: {mcp_yaml({'for': a['target'], 'timeout': a.get('timeout') or 10})}"
            elif name == "expect":
                line = f"expect: {mcp_yaml(a['condition'])}"
            else:
                line = str(a["yaml"]).strip()
            ok_, out = self.do(line)
            return text(f"단계: {line}\n{out}"), not ok_
        if name == "recorded_steps":
            steps, from_launch = do_log_read(self.ws)
            head = "launch 이후" if from_launch else "launch 기록 없음 (앞 상태에 기대는 단계가 섞였을 수 있음 — launch부터 다시)"
            return text(f"{head} {len(steps)}단계\n" + "\n".join(f"- {s}" for s in steps)), False
        if name == "list_scenarios":
            rows = [f"{s['name']} — {s['title']}" + (f" [{', '.join(s['tags'])}]" if s["tags"] else "")
                    + (f" 최근: {''.join('✓' if r == 'pass' else '✗' if r == 'fail' else '·' for r in s['recent'][-5:])}" if s["recent"] else "")
                    for s in ui_scenarios(self.ws)]
            return text(f"시나리오 {len(rows)}개\n" + "\n".join(rows)), False
        if name == "list_common_steps":
            rows = []
            for f in sorted((self.ws.root / "steps").glob("*.qa.yml")):
                head = {}
                with contextlib.suppress(Exception):
                    head = scenario_tools.parse_yaml(f.read_text(encoding="utf-8")) or {}
                rows.append(f"{f.name[:-len('.qa.yml')]} — {head.get('name', '')}"
                            + (f" (끝나면: {json.dumps(head['start'], ensure_ascii=False)})" if head.get("start") else ""))
            return text(f"공통 단계 {len(rows)}개 (step 도구로 \"use: <이름>\")\n" + "\n".join(rows)), False
        if name == "read_scenario":
            folder = "steps" if a.get("kind") == "step" else "scenarios"
            nm = str(a["name"]).removesuffix(".qa.yml")
            f = self.ws.root / folder / f"{nm}.qa.yml"
            if not re.fullmatch(r"[A-Za-z0-9가-힣_.\-]+", nm) or not f.exists():
                return text(f"{folder}/{nm}.qa.yml 없음"), True
            return text(self.mask(f.read_text(encoding="utf-8"))[:6000]), False
        if name == "run_scenario":
            code, out = self.qakit("run", a["name"], "--serve", *(["--reuse-app"] if a.get("reuse_app") else []), timeout=900)
            return text(out[-6000:]), code != 0
        if name == "save_scenario":
            nm = a["name"]
            if not re.fullmatch(r"[a-z0-9][a-z0-9\-]*", nm):
                return text("이름은 영문 소문자·숫자·- 만 (예: login-03-empty-password)"), True
            args_ = ["do", "save", nm, "--title", a["title"]]
            for t in a.get("tags") or []:
                args_ += ["--tag", t]
            if a.get("start"):
                args_ += ["--start", a["start"]]
            if a.get("overwrite"):
                args_ += ["--force"]
            code, out = self.qakit(*args_)
            if code != 0:
                return text(out[-3000:]), True
            code, run_out = self.qakit("run", nm, "--serve", timeout=900)   # 앱을 새로 켜고 처음부터
            if code == 0:
                return text(f"scenarios/{nm}.qa.yml 저장 — 새로 켠 앱에서 재생 통과\n{out[-1500:]}"), False
            src = self.ws.root / "scenarios" / f"{nm}.qa.yml"
            dst = self.ws.root / ".qakit" / "drafts" / f"{nm}.qa.yml"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.move(str(src), str(dst))
                update_readme(self.ws)
            return text(f"재생 실패 → 저장하지 않고 {dst.relative_to(self.ws.root)}로 옮김. 고친 뒤 launch부터 다시 기록하세요.\n"
                        + run_out[-4000:]), True
        if name == "report_issue":
            if not a.get("reproduced"):
                return text("먼저 launch부터 같은 단계로 한 번 더 재현한 뒤 reproduced: true로 보고하세요."), True
            d = self.session_dir()
            self.issues += 1
            shot = self.shot(width=600)
            shot_name = f"issue-{self.issues}.jpg"
            if shot:
                (d / shot_name).write_bytes(shot)
            video_name = f"issue-{self.issues}.mp4"
            video_len = self.ring.save(d / video_name) if self.ring else None   # 보고 직전 최대 30초
            md = [f"## {self.issues}. {a['title']} ({a['severity']})", "", "재현 단계:", *[f"1. `{s}`" for s in a["steps"]], "",
                  f"- 기대: {a['expected']}", f"- 실제: {a['actual']}"] + ([f"- 사진: ![{shot_name}]({shot_name})"] if shot else []) \
                + ([f"- 영상 (보고 직전 {video_len}초): [{video_name}]({video_name})"] if video_len else []) + [""]
            with open(d / "issues.md", "a", encoding="utf-8") as f:
                f.write(self.mask("\n".join(md)) + "\n")
            with open(d / "issues.jsonl", "a", encoding="utf-8") as f:
                f.write(self.mask(json.dumps(dict(a, n=self.issues, screenshot=shot_name if shot else None,
                                                  video=video_name if video_len else None), ensure_ascii=False)) + "\n")
            return text(f"문제 {self.issues} 기록: {results_rel(self.ws, d)}/issues.md" + (f" (사진 {shot_name})" if shot else "")
                        + (f" (영상 {video_len}초)" if video_len else "")), False
        return text(f"모르는 도구: {name}"), True


def ai_engines():
    """UI에서 고를 AI: 설치·로그인 상태. qakit은 토큰을 다루지 않고 이 CLI들을 부른다."""
    out = []
    claude = shutil.which("claude")
    if claude:
        ver = run([claude, "--version"], check=False).stdout.strip().split(" ")[0]
        auth = {}
        with contextlib.suppress(ValueError):
            auth = json.loads(run([claude, "auth", "status"], check=False).stdout or "{}")
        out.append({"id": "claude", "name": "Claude Code", "version": ver, "ready": bool(auth.get("loggedIn")),
                    "note": f"로그인: {auth.get('authMethod')}" if auth.get("loggedIn") else "로그인 필요: 터미널에서 claude 실행 후 /login",
                    "tested": True})
    else:
        out.append({"id": "claude", "name": "Claude Code", "ready": False, "note": "설치 필요 (claude.com/claude-code)", "tested": True})
    codex = shutil.which("codex")
    if codex:
        ver = run([codex, "--version"], check=False).stdout.strip()
        st = run([codex, "login", "status"], check=False)
        out.append({"id": "codex", "name": "Codex", "version": ver, "ready": st.returncode == 0,
                    "note": (st.stdout or st.stderr).strip()[:80] or ("로그인됨" if st.returncode == 0 else "codex login 필요"),
                    "tested": False})
    else:
        out.append({"id": "codex", "name": "Codex", "ready": False, "note": "설치 필요 (npm i -g @openai/codex)", "tested": False})
    return out


def ai_scenario_prompt(goal, minutes, name=None, tags=None, start=None):
    """시나리오 만들기 모드: 문제 찾기가 아니라, 다음부터 AI 없이 매번 통과하는 시나리오 하나를 남긴다."""
    meta = [f"이름: {name}" if name else "이름: 직접 정한다 (화면-번호-내용, 예: login-03-empty-password. list_scenarios로 겹치지 않게)",
            f"태그: {', '.join(tags)}" if tags else "태그: 알맞게 (없어도 됨)",
            f"시작 공통 단계: {start} — launch 다음에 step 도구로 \"use: {start}\"를 밟는다 (save_scenario에는 start를 주지 않음, 이미 기록됨)"
            if start else "시작 공통 단계: 필요하면 list_common_steps에서 골라 launch 다음 step으로 \"use: <이름>\""]
    return f"""만들 시나리오: {goal}
{chr(10).join(meta)}

qakit MCP 도구로 이 흐름의 시나리오(.qa.yml)를 만든다. 문제 찾기가 목적이 아니라, 다음부터 AI 없이 매번 통과하는 시나리오를 남기는 것이 목적이다. qakit 도구 말고 다른 도구는 없다.
1. list_scenarios·list_common_steps로 있는 것을 보고, 비슷한 시나리오 하나를 read_scenario로 읽어 스타일을 맞춘다. 같은 흐름이 이미 있으면 새로 만들지 말고 그 이름을 보고한다.
2. launch로 시작하고 screen으로 화면을 읽으며 흐름을 밟는다. 조작 도구마다 why(왜 하는지 한 줄)를 준다.
3. 대상은 screen에 나온 #ID를 우선 쓴다. 라벨은 바뀌기 쉬우니 ID가 없을 때만. 화면이 바뀌는 tap에는 expect(다음 화면의 핵심 요소)를 붙이고, 마지막에 목표가 이뤄졌는지 expect로 확인한다.
4. 실패하거나 헤맨 단계가 섞였으면 launch부터 다시 깨끗하게 밟는다 (recorded_steps로 확인 — 저장되는 것은 마지막 launch 이후 통과한 단계).
5. save_scenario로 저장한다 — 새로 켠 앱에서 재생해 통과해야 남는다. 실패하면 원인(대신 이 대상? 제안 포함)을 보고 고쳐 launch부터 다시.
6. 앱 데이터를 지우거나 되돌릴 수 없는 일(삭제·탈퇴·결제·게시)은 하지 않는다. 그런 흐름이면 그 직전까지만 만들고 보고한다.
7. 시간은 약 {minutes}분이다.
8. 마지막 답변은 한국어 마크다운으로: 저장한 시나리오 이름·제목, 단계 요약, 확인(expect)한 것, 넣지 못한 것과 이유."""


def ai_prompt(goal, minutes, save):
    rule = ("확인한 정상 경로는 launch부터 다시 깨끗하게 밟은 뒤 save_scenario로 남긴다 (재생 통과해야 저장)."
            if save else "시나리오는 저장하지 않는다 (save_scenario 쓰지 않음). 남길 만한 경로는 보고서에 단계로 적는다.")
    return f"""목표: {goal}

qakit MCP 도구로 이 iOS 앱(시뮬레이터)을 직접 QA한다. qakit 도구 말고 다른 도구는 없다.
1. get_testing_guide를 먼저 읽고 그대로 따른다.
2. launch로 시작하고 screen으로 화면을 읽으며 진행한다. 조작 도구마다 why(왜 하는지 한 줄)를 준다.
3. 문제는 launch부터 같은 단계로 재현한 뒤 report_issue로 남긴다. 확실하지 않으면 보고서에 '확인 필요'로만.
4. {rule}
5. 시간은 약 {minutes}분이다. 목표 범위 밖은 하지 않는다.
6. 마지막 답변은 지침의 보고 형식으로, 한국어 마크다운."""


def ai_command(engine, ws, d, prompt, turns):
    """AI CLI 명령 (qakit 도구만 허용). → (명령, MCP 설정 파일)"""
    mcp = {"command": str(KIT_DIR / "bin" / "qakit"), "args": ["-w", str(ws.root), "mcp"], "env": {"QAKIT_AI_DIR": str(d)}}
    if engine == "claude":
        cfg = d / "mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {"qakit": mcp}}, ensure_ascii=False, indent=2), encoding="utf-8")
        return [shutil.which("claude") or "claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--strict-mcp-config", "--mcp-config", str(cfg), "--tools", "", "--allowedTools", "mcp__qakit",
                "--permission-mode", "dontAsk", "--max-turns", str(turns), "--no-session-persistence"]
    # codex (이 Mac에 없어 시험하지 못함): exec + JSON 이벤트, 읽기 전용 샌드박스, MCP는 -c로
    toml = lambda v: json.dumps(v, ensure_ascii=False)
    return [shutil.which("codex") or "codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
            "-c", f"mcp_servers.qakit.command={toml(mcp['command'])}", "-c", f"mcp_servers.qakit.args={toml(mcp['args'])}",
            "-c", f"mcp_servers.qakit.env={{QAKIT_AI_DIR={toml(str(d))}}}", prompt]


def ai_events(engine, obj):
    """에이전트 출력 한 줄(JSON) → 보여 줄 사건들 [{kind: info|text|tool|result|error, text}] + 결과 정보"""
    ev, res = [], None
    if engine == "claude":
        t = obj.get("type")
        if t == "system" and obj.get("subtype") == "init":
            st = {m.get("name"): m.get("status") for m in obj.get("mcp_servers") or []}
            n = sum(1 for x in obj.get("tools") or [] if str(x).startswith("mcp__qakit"))
            ev.append({"kind": "info" if st.get("qakit") == "connected" else "error",
                       "text": f"시작 · 모델 {obj.get('model')} · qakit {st.get('qakit', '없음')} (도구 {n}개)"})
        elif t == "assistant":
            for c in (obj.get("message") or {}).get("content") or []:
                if c.get("type") == "text" and c.get("text", "").strip():
                    ev.append({"kind": "text", "text": c["text"].strip()})
                elif c.get("type") == "tool_use":
                    inp = dict(c.get("input") or {})
                    why = inp.pop("why", None)
                    ev.append({"kind": "tool", "text": f"{str(c.get('name', '')).replace('mcp__qakit__', '')} "
                               f"{json.dumps(inp, ensure_ascii=False)[:160] if inp else ''}".strip(), "why": why})
        elif t == "result":
            res = {"text": obj.get("result") or "", "cost": obj.get("total_cost_usd"), "turns": obj.get("num_turns"),
                   "error": bool(obj.get("is_error")), "subtype": obj.get("subtype")}
    else:   # codex: 알려진 몇 가지 꼴만, 나머지는 건너뜀
        item = obj.get("item") or obj.get("msg") or {}
        typ = item.get("type") or obj.get("type")
        text = item.get("text") or item.get("message")
        if typ in ("agent_message", "assistant_message") and text:
            ev.append({"kind": "text", "text": str(text).strip()})
            res = {"text": str(text).strip(), "cost": None, "turns": None, "error": False, "subtype": None} \
                if obj.get("type") in ("item.completed",) else None
        elif typ in ("mcp_tool_call", "tool_call") and item.get("tool"):
            ev.append({"kind": "tool", "text": f"{item.get('tool')} {json.dumps(item.get('arguments') or {}, ensure_ascii=False)[:160]}"})
        elif obj.get("type") == "error" or typ == "error":
            ev.append({"kind": "error", "text": str(obj.get("message") or item)[:300]})
    return ev, res


AI_STEP_TOOLS = ("tap", "type_text", "swipe", "wait_for", "expect", "step")


def ai_session_info(ws, d, full=False):
    """results/ai/<시각>/ → 요약 (목록용) 또는 전체 (상세: 보고서·기록·문제·에이전트 사건·제안 단계)."""
    meta, rows, issues = {}, [], []
    with contextlib.suppress(OSError, ValueError):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    with contextlib.suppress(OSError):
        for line in (d / "log.jsonl").read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                rows.append(json.loads(line))
    with contextlib.suppress(OSError):
        for line in (d / "issues.jsonl").read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                issues.append(json.loads(line))
    # 제안 단계: 마지막으로 성공한 launch 이후 통과한 조작 (도구 결과 첫 줄 "단계: <글>")
    steps, from_launch, saved = [], False, []
    for r in rows:
        if not r.get("ok"):
            continue
        if r.get("tool") == "launch":
            steps, from_launch = [], True
        elif r.get("tool") in AI_STEP_TOOLS and str(r.get("summary", "")).startswith("단계: "):
            steps.append(r["summary"].split("\n")[0][len("단계: "):])
        elif r.get("tool") == "save_scenario":
            saved.append((r.get("args") or {}).get("name"))
    report = (d / "report.md").read_text(encoding="utf-8") if (d / "report.md").exists() else None
    started = meta.get("started") or (rows[0]["at"] if rows else None)
    ended = meta.get("ended") or (rows[-1]["at"] if rows else None)
    seconds = None
    with contextlib.suppress(TypeError, ValueError):
        seconds = round((datetime.datetime.fromisoformat(ended) - datetime.datetime.fromisoformat(started)).total_seconds())
    info_ = {"dir": results_rel(ws, d), "name": d.name, "goal": meta.get("goal"), "client": meta.get("client"), "mode": meta.get("mode") or "qa",
             "via": meta.get("via") or "MCP", "started": started, "ended": ended, "seconds": seconds,
             "cost": meta.get("cost"), "turns": meta.get("turns_used"), "code": meta.get("code"), "calls": len(rows),
             "failed": sum(1 for r in rows if not r.get("ok")), "issues": len(issues), "report": report is not None,
             "steps": len(steps), "saved": [x for x in saved if x]}
    if not full:
        return info_
    events = []
    engine = "codex" if "codex" in str(meta.get("client") or "").lower() else "claude"
    with contextlib.suppress(OSError):
        for line in (d / "agent.jsonl").read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                events += ai_events(engine, json.loads(line))[0]
    return dict(info_, report=report, rows=rows, issueList=issues, events=events, stepList=steps, fromLaunch=from_launch)


def ai_sessions(ws):
    root = ws.results_dir / "ai"
    if not root.is_dir():
        return []
    return [ai_session_info(ws, d) for d in sorted((x for x in root.iterdir() if x.is_dir()), reverse=True)]


def cmd_mcp(args):
    if args.action == "install":
        return mcp_install(find_workspace(args.workspace), args)
    out = sys.stdout
    sys.stdout = sys.stderr   # 프로토콜 외 출력(안내 문구 등)이 stdout에 섞이지 않게
    ws = find_workspace(args.workspace)
    session = McpSession(ws)
    tools = mcp_tools()

    def send(msg):
        out.write(json.dumps(msg, ensure_ascii=False) + "\n")
        out.flush()

    try:
        mcp_loop(session, tools, send)
    finally:
        if session.ring:
            session.ring.stop()


def mcp_loop(session, tools, send):
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:   # 알림 (notifications/initialized 등)
            continue
        try:
            if method == "initialize":
                want = params.get("protocolVersion")
                session.client = (params.get("clientInfo") or {}).get("name")
                result = {"protocolVersion": want if want in MCP_PROTOCOLS else MCP_PROTOCOLS[0],
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "qakit", "version": kit_version()},
                          "instructions": MCP_INSTRUCTIONS}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "tools/call":
                name, a = params.get("name"), dict(params.get("arguments") or {})
                why = a.pop("why", None)
                started = time.time()
                session.now(name, a)
                try:
                    content, is_error = session.call(name, a)
                except KeyError as e:
                    content, is_error = [{"type": "text", "text": f"인자가 빠짐: {e}"}], True
                finally:
                    session.now()
                summary = next((c["text"] for c in content if c["type"] == "text"), "(사진)")
                session.log(name, a, not is_error, time.time() - started, summary, why)
                result = {"content": content, "isError": is_error}
            else:
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"없는 메서드: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": mid, "result": result})
        except Exception as e:   # 도구 하나의 오류로 서버가 끝나지 않게
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}})


def mcp_install(ws, args):
    """AI 도구에 qakit MCP 서버를 등록한다. Claude Code: 작업공간 .mcp.json (이 폴더에서 연 세션). Codex: codex mcp add."""
    command = str(KIT_DIR / "bin" / "qakit")   # 지금 실행 중인 qakit (설치본이면 ~/ios-qa-kit/bin/qakit)
    margs = ["-w", str(ws.root), "mcp"]
    if not (args.claude or args.codex):
        fail("어디에 등록할지 고르세요", "qakit mcp install --claude  또는  --codex")
    if args.claude:
        p = ws.root / ".mcp.json"
        try:
            cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except ValueError:
            fail(f"{p} 형식이 잘못됐습니다", "고치거나 지운 뒤 다시")
        cfg.setdefault("mcpServers", {})["qakit"] = {"command": command, "args": margs}
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ok(f"Claude Code: {p}")
        info("이 폴더에서 claude를 열면 qakit 도구를 쓸지 묻습니다 (처음 한 번). 확인: /mcp")
        info(".mcp.json에는 이 Mac의 경로가 들어 있으니 git에 올리지 않는 편이 좋습니다")
    if args.codex:
        if shutil.which("codex"):
            r = run(["codex", "mcp", "add", "qakit", "--", command, *margs], check=False)
            if r.returncode == 0:
                ok("Codex: codex mcp add qakit")
                return
            warn("codex mcp add 실패 — 아래를 ~/.codex/config.toml에 직접 넣으세요")
        else:
            warn("codex가 없습니다 — 설치 뒤 아래를 ~/.codex/config.toml에 넣으세요")
        print(f'\n[mcp_servers.qakit]\ncommand = {json.dumps(command)}\nargs = {json.dumps(margs, ensure_ascii=False)}\n')


