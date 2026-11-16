# ─────────────────────────────── 안드로이드: SDK·에뮬레이터 (A0) · 화면 파악 (A1) ───────────────────────────────
# Android Studio 없이 명령줄 도구(JDK 17 + cmdline-tools)만 쓴다.
# 화면 읽기는 adb + uiautomator dump. 결과는 iOS dump-ui와 같은 줄 형식이라 dump_elements·추천이 그대로 동작한다.

ANDROID_API = "35"
ANDROID_ABI = "arm64-v8a" if os.uname().machine == "arm64" else "x86_64"
ANDROID_IMAGE = f"system-images;android-{ANDROID_API};google_apis;{ANDROID_ABI}"
ANDROID_AVD = "qakit"
ANDROID_SDK_CANDIDATES = [
    Path.home() / "Library" / "Android" / "sdk",                 # Android Studio 기본 위치
    Path("/opt/homebrew/share/android-commandlinetools"),        # brew android-commandlinetools (Apple Silicon)
    Path("/usr/local/share/android-commandlinetools"),           # 같은 것 (Intel)
]
ANDROID_DUMP_REMOTE = "/data/local/tmp/qakit-dump.xml"


def android_sdk_root():
    """Android SDK 위치. 환경 변수 → Android Studio 기본 위치 → brew 위치 순. 없으면 None."""
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        v = os.environ.get(key)
        if v and Path(v).is_dir():
            return Path(v)
    for p in ANDROID_SDK_CANDIDATES:
        if p.is_dir():
            return p
    return None


def android_java_home():
    """JDK 17 이상 위치. JAVA_HOME → /usr/libexec/java_home → brew openjdk@17·openjdk 순. 없으면 None."""
    v = os.environ.get("JAVA_HOME")
    if v and (Path(v) / "bin" / "java").exists():
        return Path(v)
    r = run(["/usr/libexec/java_home", "-v", "17+"], check=False)
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip())
    for name in ("openjdk@17", "openjdk@21", "openjdk"):
        for prefix in ("/opt/homebrew/opt", "/usr/local/opt"):
            p = Path(prefix) / name
            if (p / "bin" / "java").exists():
                return p
    return None


def android_env():
    """sdkmanager·avdmanager·gradle이 쓸 환경 변수 (JAVA_HOME, ANDROID_HOME)."""
    env = dict(os.environ)
    jh, sdk = android_java_home(), android_sdk_root()
    if jh:
        env["JAVA_HOME"] = str(jh)
        env["PATH"] = f"{jh}/bin:" + env.get("PATH", "")
    if sdk:
        env["ANDROID_HOME"] = env["ANDROID_SDK_ROOT"] = str(sdk)
    return env


def android_tool(name):
    """SDK 안 도구 경로 (adb, emulator, sdkmanager, avdmanager). 없으면 None."""
    sdk = android_sdk_root()
    cands = []
    if sdk:
        cands += [sdk / "platform-tools" / name, sdk / "emulator" / name,
                  sdk / "cmdline-tools" / "latest" / "bin" / name, sdk / "cmdline-tools" / "bin" / name]
    for c in cands:
        if c.exists():
            return str(c)
    return shutil.which(name)


def require_tool(name):
    path = android_tool(name)
    if not path:
        fail(f"{name}을(를) 찾지 못했습니다 (Android SDK 미설치).", "qakit android setup")
    return path


# ─────────────────────────────── 기기 (에뮬레이터·USB) ───────────────────────────────

def adb_devices():
    """[(serial, state, 설명)] — state: device | offline | unauthorized."""
    adb = android_tool("adb")
    if not adb:
        return []
    r = run([adb, "devices", "-l"], check=False)
    rows = []
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        # 'List of devices attached'·'* daemon started' 같은 줄은 건너뛴다
        if len(parts) >= 2 and not line.startswith(("*", "List of")):
            desc = " ".join(p.split(":", 1)[1] for p in parts[2:] if p.startswith(("model:", "device:")))
            rows.append((parts[0], parts[1], desc))
    return rows


def android_avds():
    emu = android_tool("emulator")
    if not emu:
        return []
    r = run([emu, "-list-avds"], check=False, env=android_env())
    return [l.strip() for l in (r.stdout or "").splitlines() if l.strip() and not l.startswith("INFO")]


def emulator_avd_name(serial):
    """실행 중인 에뮬레이터의 AVD 이름 (실기기면 None)."""
    if not serial.startswith("emulator-"):
        return None
    r = run([android_tool("adb"), "-s", serial, "emu", "avd", "name"], check=False)
    lines = [l.strip() for l in (r.stdout or "").splitlines() if l.strip() and l.strip() != "OK"]
    return lines[0] if lines else None


def android_serial(avd=None, boot=True, headless=False):
    """쓸 기기 serial. ANDROID_SERIAL → 실행 중인 avd 에뮬레이터 → 연결된 기기 하나 → (boot면) avd를 띄움."""
    ready = [s for s, st, _ in adb_devices() if st == "device"]
    want = os.environ.get("ANDROID_SERIAL")
    if want:
        if want not in ready:
            fail(f"ANDROID_SERIAL={want} 기기가 연결돼 있지 않습니다.", "adb devices로 확인")
        return want
    if avd:
        for s in ready:
            if emulator_avd_name(s) == avd:
                return s
    elif len(ready) == 1:
        return ready[0]
    elif len(ready) > 1:
        fail("안드로이드 기기가 여러 대 연결돼 있습니다: " + ", ".join(ready), "ANDROID_SERIAL=<serial> 로 하나를 고르세요")
    if not boot:
        return None
    return android_boot(avd or ANDROID_AVD, headless=headless)


def android_boot(avd, headless=False, timeout=240):
    """에뮬레이터를 띄우고 부팅 완료까지 기다린다. serial을 돌려준다."""
    emu, adb = require_tool("emulator"), require_tool("adb")
    if avd not in android_avds():
        fail(f"AVD '{avd}'가 없습니다. 있는 AVD: {', '.join(android_avds()) or '(없음)'}", "qakit android setup")
    before = {s for s, _, _ in adb_devices()}
    log = Path.home() / ".qakit" / f"emulator-{avd}.log"
    log.parent.mkdir(exist_ok=True)
    cmd = [emu, "-avd", avd, "-no-snapshot-save", "-no-boot-anim"] + (["-no-window", "-no-audio"] if headless else [])
    info(f"에뮬레이터 '{avd}' 실행 중{' (화면 없이)' if headless else ''}…")
    with open(log, "ab") as f:
        subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         env=android_env(), start_new_session=True)   # qakit이 끝나도 에뮬레이터는 남긴다
    deadline = time.time() + timeout
    serial = None
    while time.time() < deadline:
        if not serial:
            new = [s for s, _, _ in adb_devices() if s not in before and s.startswith("emulator-")]
            serial = next((s for s in new if emulator_avd_name(s) == avd), None)
        if serial:
            r = run([adb, "-s", serial, "shell", "getprop", "sys.boot_completed"], check=False)
            if r.stdout.strip() == "1":
                ok(f"에뮬레이터 준비됨: {avd} ({serial})")
                return serial
        time.sleep(2)
    fail(f"에뮬레이터 '{avd}'가 {timeout}초 안에 부팅하지 않았습니다.", f"로그: {log}")


def adb(serial, *args, check=True, timeout=None):
    cmd = [require_tool("adb"), "-s", serial] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        fail("adb 응답 없음: " + " ".join(args))
    if check and r.returncode != 0:
        fail("adb 실패: " + " ".join(args), (r.stderr or r.stdout or "").strip()[-400:])
    return r


# ─────────────────────────────── A0: 설치 (qakit android setup) ───────────────────────────────

def cmd_android_setup(args):
    """JDK 17, cmdline-tools, platform-tools, emulator, 시스템 이미지, AVD를 설치한다 (Android Studio 불필요)."""
    brew = shutil.which("brew")
    if not android_java_home():
        if not brew:
            fail("JDK 17이 없습니다.", "Homebrew 설치 후 다시 실행하거나 JDK 17을 설치하고 JAVA_HOME을 지정하세요")
        info("JDK 17 설치: brew install openjdk@17")
        run([brew, "install", "openjdk@17"], capture=False)
    ok(f"JDK: {android_java_home()}")

    if not android_tool("sdkmanager"):
        if not brew:
            fail("Android cmdline-tools가 없습니다.", "https://developer.android.com/studio#command-line-tools-only")
        info("Android 명령줄 도구 설치: brew install --cask android-commandlinetools")
        run([brew, "install", "--cask", "android-commandlinetools"], capture=False)
    sdk = android_sdk_root()
    if not sdk:
        fail("Android SDK 폴더를 찾지 못했습니다.", "ANDROID_HOME을 지정하세요")
    ok(f"SDK: {sdk}")

    env = android_env()
    sdkm = require_tool("sdkmanager")
    image = args.image or ANDROID_IMAGE
    info("라이선스 동의 (sdkmanager --licenses)")
    subprocess.run([sdkm, "--licenses"], input="y\n" * 20, text=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pkgs = ["platform-tools", "emulator", image]
    info("SDK 패키지 설치 (처음이면 시스템 이미지 때문에 몇 분 걸립니다): " + ", ".join(pkgs))
    r = subprocess.run([sdkm, "--install"] + pkgs, env=env, text=True, capture_output=True)
    if r.returncode != 0:
        fail("sdkmanager 실패", (r.stderr or r.stdout or "")[-600:])
    ok("platform-tools · emulator · 시스템 이미지 설치됨")

    avd = args.avd or ANDROID_AVD
    if avd in android_avds():
        ok(f"AVD 있음: {avd}")
    else:
        avdm = require_tool("avdmanager")
        r = subprocess.run([avdm, "create", "avd", "-n", avd, "-k", image, "-d", args.device_profile],
                           input="no\n", text=True, env=env, capture_output=True)
        if r.returncode != 0:
            fail(f"AVD 생성 실패: {avd}", (r.stderr or r.stdout or "")[-600:])
        ok(f"AVD 만듦: {avd} ({args.device_profile}, {image})")
    print()
    ok("안드로이드 준비 완료. 다음: qakit android boot  →  qakit android screen")
    if not os.environ.get("ANDROID_HOME"):
        info(f"(선택) 셸 설정에 추가하면 adb를 바로 쓸 수 있습니다: export ANDROID_HOME={sdk}; "
             'export PATH="$ANDROID_HOME/platform-tools:$PATH"')


def android_doctor_lines():
    """[(정상 여부, 정상 문구, 문제 문구, 안내)] — qakit android doctor와 작업공간 doctor가 함께 쓴다."""
    jh, sdk = android_java_home(), android_sdk_root()
    rows = [
        (bool(jh), f"JDK: {jh}", "JDK 17 없음", "qakit android setup"),
        (bool(sdk), f"Android SDK: {sdk}", "Android SDK 없음", "qakit android setup"),
        (bool(android_tool("adb")), "adb 설치됨", "adb 없음 (platform-tools)", "qakit android setup"),
        (bool(android_tool("emulator")), "emulator 설치됨", "emulator 없음", "qakit android setup"),
    ]
    avds = android_avds()
    rows.append((bool(avds), f"AVD: {', '.join(avds)}", "AVD 없음", "qakit android setup"))
    devs = adb_devices()
    ready = [f"{s}{' ' + d if d else ''}" for s, st, d in devs if st == "device"]
    bad = [f"{s}({st})" for s, st, _ in devs if st != "device"]
    rows.append((not bad, f"연결된 기기: {', '.join(ready) or '(없음 — qakit android boot)'}",
                 f"응답 없는 기기: {', '.join(bad)}", "unauthorized면 기기에서 USB 디버깅 허용"))
    return rows


def cmd_android_doctor(args):
    problems = 0
    for good, okmsg, badmsg, hint in android_doctor_lines():
        if good:
            ok(okmsg)
        else:
            problems += 1
            print(f"❌ {badmsg}\n   → {hint}")
    print()
    if problems:
        fail(f"문제 {problems}개")
    ok("모두 정상")


def cmd_android_boot(args):
    serial = android_serial(args.avd or ANDROID_AVD, boot=False)
    if serial and (not args.avd or emulator_avd_name(serial) == args.avd):
        ok(f"이미 실행 중: {serial}")
        return
    android_boot(args.avd or ANDROID_AVD, headless=args.headless)


# ─────────────────────────────── A1: 지금 화면 파악 ───────────────────────────────

def android_foreground(serial):
    """지금 앞에 있는 화면: {"package", "activity"} (activity는 짧은 클래스 이름)."""
    r = adb(serial, "shell", "dumpsys", "activity", "activities", check=False)
    m = re.search(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)[:=].*?\{[^}]*?\s([\w.]+)/([\w.$]+)",
                  r.stdout or "")
    if not m:
        r = adb(serial, "shell", "dumpsys", "window", check=False)
        m = re.search(r"mCurrentFocus=.*?\s([\w.]+)/([\w.$]+)\}", r.stdout or "")
    if not m:
        return {"package": None, "activity": None, "activityFull": None}
    pkg, act = m.group(1), m.group(2)
    full = pkg + act if act.startswith(".") else act
    return {"package": pkg, "activity": full.rsplit(".", 1)[-1], "activityFull": full}


# 화면 파악에 의미 없는 라이브러리·내부 프래그먼트
FRAGMENT_NOISE = re.compile(r"^(SupportRequestManagerFragment|RequestManagerFragment|ReportFragment|"
                            r"LifecycleFragment|HolderFragment|ViewModelStoreFragment)$")


def android_fragments(serial, package):
    """package의 맨 위 Activity에 붙은 Fragment (바깥부터 안쪽, 보이는 것 위주): ["HomeFragment", ...]."""
    r = adb(serial, "shell", "dumpsys", "activity", "top", check=False)
    text = r.stdout or ""
    # 'ACTIVITY <pkg>/...' 블록 중 마지막(맨 위) 것
    blocks = re.split(r"\n\s*ACTIVITY ", text)
    mine = [b for b in blocks if b.startswith(package + "/")] if package else []
    if not mine:
        return []
    names = []
    for m in re.finditer(r"^(\s*)#\d+: (\w+)\{[0-9a-f]+\}?[^\n]*", mine[-1], re.M):
        name = m.group(2)
        if FRAGMENT_NOISE.match(name) or name in names:
            continue
        names.append(name)
    return names


ANDROID_TYPE = [   # (클래스 이름 끝, 덤프 타입) — 위에서부터 먼저 맞는 것
    ("EditText", "TextField"), ("AutoCompleteTextView", "TextField"),
    ("Switch", "Switch"), ("SwitchCompat", "Switch"), ("SwitchMaterial", "Switch"), ("ToggleButton", "Switch"),
    ("CheckBox", "Switch"), ("RadioButton", "Switch"),
    ("ImageButton", "Button"), ("Button", "Button"), ("FloatingActionButton", "Button"), ("Chip", "Button"),
    ("ImageView", "Image"), ("TextView", "StaticText"),
    ("RecyclerView", "CollectionView"), ("GridView", "CollectionView"), ("ViewPager", "CollectionView"),
    ("ListView", "Table"), ("ScrollView", "ScrollView"), ("NestedScrollView", "ScrollView"),
    ("WebView", "WebView"), ("TabLayout", "TabBar"), ("BottomNavigationView", "TabBar"), ("NavigationBarView", "TabBar"),
]
INTERACTIVE_TYPES = {"Button", "TextField", "SecureTextField", "Switch", "Cell"}


def android_type(node):
    cls = node.get("class", "").rsplit(".", 1)[-1]
    t = next((v for k, v in ANDROID_TYPE if cls.endswith(k)), "Other")
    if t == "TextField" and node.get("password") == "true":
        t = "SecureTextField"
    if t in ("Other", "StaticText", "Image") and node.get("clickable") == "true":
        # 글자가 둘 이상인 클릭 영역은 목록 행(Cell), 아이콘 하나·글자 하나면 버튼 (Compose는 클래스가 View뿐)
        labeled = sum(1 for n in node.iter("node") if node_has_label(n))
        t = "Cell" if t == "Other" and labeled >= 2 else "Button"
    return t


def node_has_label(node):
    return bool(node.get("text") or node.get("content-desc"))


def android_short_id(rid, package):
    """resource-id → 덤프 ID. 앱 id(com.app:id/loginButton)는 loginButton,
    Compose testTag(testTagsAsResourceId)는 그대로, 프레임워크 id(android:id/button1)는 android.button1."""
    if not rid:
        return ""
    if ":id/" in rid:
        pkg, name = rid.split(":id/", 1)
        return name if pkg != "android" else "android." + name
    return rid


def parse_bounds(b):
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", b or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0, 0)


def android_density(serial):
    r = adb(serial, "shell", "wm", "density", check=False)
    vals = re.findall(r"density: (\d+)", r.stdout or "")
    return int(vals[-1]) / 160 if vals else 1.0    # Override가 있으면 마지막 값


def android_ui_xml(serial, retries=3):
    """uiautomator dump XML. 화면이 계속 움직이면 실패하므로 몇 번 다시 시도한다."""
    last = ""
    for i in range(retries):
        r = adb(serial, "shell", "uiautomator", "dump", "--compressed", ANDROID_DUMP_REMOTE, check=False, timeout=30)
        last = (r.stdout + r.stderr).strip()
        if "dumped to" in last:
            x = adb(serial, "exec-out", "cat", ANDROID_DUMP_REMOTE, check=False)
            if x.stdout.lstrip().startswith("<?xml"):
                return x.stdout
        time.sleep(1 + i)
    fail("화면 덤프 실패 (uiautomator dump)", last[-300:] +
         "\n   애니메이션이 계속되는 화면이면 멈춘 뒤 다시, 다른 UiAutomator 세션(Appium 등)이 있으면 종료")


def first_text(node):
    for n in node.iter("node"):
        t = n.get("text") or n.get("content-desc")
        if t:
            return t.replace("\n", " ")
    return ""


def android_dump_lines(xml, target, density):
    """uiautomator XML → (덤프 줄들, 통계). iOS dump-ui와 같은 꼴: `타입 #ID "라벨" ... @x,y wxh` (dp)."""
    root = ET.fromstring(xml)
    lines, stats = [], {"interactive": 0, "withId": 0, "missing": []}

    def coord(v):
        return str(int(round(v / density)))   # iOS 덤프처럼 정수 (공용 파서가 정수만 읽는다)

    def visit(node, depth, window=False):
        if node.tag != "node":
            for c in node:
                visit(c, depth, window=True)
            return
        pkg = node.get("package") or ""
        if window and target and pkg and pkg != target:
            lines.append(f"# (다른 앱 창: {pkg})")   # 앱 위에 뜬 시스템 권한 대화상자 등
        typ = android_type(node)
        rid = android_short_id(node.get("resource-id", ""), target)
        text, desc = node.get("text") or "", node.get("content-desc") or ""
        label = (text or desc).replace("\n", " ")
        if not label and typ == "Button" and node.get("clickable") == "true":
            label = first_text(node)   # Compose 아이콘 버튼: 이름이 안쪽 아이콘의 설명에 있다 ("Navigate up")
        meaningful = bool(rid or label or typ != "Other" or node.get("scrollable") == "true")
        if meaningful:
            parts = [typ] + (["#" + rid] if rid else []) + ([f'"{label}"'] if label else [])
            hint = node.get("hint") or ""
            if typ in ("TextField", "SecureTextField") and hint and hint != label:
                parts.append(f'value="{hint}"')   # iOS 덤프처럼 빈 입력칸의 안내 문구는 value
            if node.get("enabled") == "false":
                parts.append("(disabled)")
            if node.get("checked") == "true" or node.get("selected") == "true":
                parts.append("(selected)")
            x1, y1, x2, y2 = parse_bounds(node.get("bounds"))
            parts.append(f"@{coord(x1)},{coord(y1)} {coord(max(0, x2 - x1))}x{coord(max(0, y2 - y1))}")  # 화면 끝에 걸린 칸은 음수가 나온다
            lines.append("  " * depth + " ".join(parts))
            if typ in INTERACTIVE_TYPES:
                stats["interactive"] += 1
                if rid:
                    stats["withId"] += 1
                else:
                    name = label or first_text(node)   # 목록 행은 보통 라벨이 자식 글자에 있다
                    stats["missing"].append(f'{typ} "{name}"' if name else typ)
        for c in node:
            visit(c, depth + 1 if meaningful else depth)   # 이름 없는 레이아웃 칸은 접어서 깊이를 늘리지 않는다

    visit(root, 0)
    return lines, stats


def android_dump_text(serial, package=None):
    """지금 화면 → iOS dump-ui와 같은 형식의 텍스트, 메타 정보 dict."""
    fg = android_foreground(serial)
    target = package or fg["package"]
    density = android_density(serial)
    lines, st = android_dump_lines(android_ui_xml(serial), target, density)
    frags = android_fragments(serial, target)
    total, with_id = st["interactive"], st["withId"]
    ratio = round(with_id * 100 / total) if total else 100
    header = [
        "# qakit dump-ui",
        f"# package: {target}",
        f"# activity: {fg['activityFull'] or '-'}" + ("" if fg["package"] == target else f" (앞 화면: {fg['package']})"),
        f"# fragments: {' > '.join(frags) or '-'}",
        f"# interactive: {total}, with ID: {with_id} ({ratio}%)",
        f"# coords: dp (density {density:g})",
    ]
    if st["missing"]:
        header.append("# missing ID: " + ", ".join(st["missing"][:20]))
    meta = {"package": target, "activity": fg["activity"], "activityFull": fg["activityFull"], "fragments": frags,
            "interactive": total, "withId": with_id, "density": density}
    return "\n".join(header + lines) + "\n", meta


def cmd_android_screen(args):
    """지금 화면이 어느 Activity·Fragment인지 (덤프 없이 빠르게)."""
    serial = android_serial(args.avd, boot=False)
    if not serial:
        fail("연결된 안드로이드 기기가 없습니다.", "qakit android boot")
    fg = android_foreground(serial)
    if not fg["package"]:
        fail("앞에 있는 화면을 알 수 없습니다 (잠금 화면이거나 부팅 중)")
    frags = android_fragments(serial, fg["package"])
    if args.json:
        print(json.dumps({"serial": serial, **fg, "fragments": frags}, ensure_ascii=False))
        return
    info(f"기기: {serial}")
    info(f"앱: {fg['package']}")
    info(f"Activity: {fg['activityFull']}")
    info(f"Fragment: {' > '.join(frags) or '-'}")


def cmd_android_dump(args):
    """작업공간 없이 지금 화면 덤프 (앞에 있는 앱 기준). 작업공간이 있으면 qakit dump-ui가 같은 일을 한다."""
    serial = android_serial(args.avd, boot=False)
    if not serial:
        fail("연결된 안드로이드 기기가 없습니다.", "qakit android boot")
    if args.settle:
        time.sleep(args.settle)
    text, meta = android_dump_text(serial, args.package)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        ok(f"저장: {args.out}")
    if args.json:
        print(json.dumps({"serial": serial, **meta, "elements": dump_elements(text)}, ensure_ascii=False))
    elif not args.out or args.print:
        print(text, end="")


def android_launch(serial, package, fresh=True):
    """앱을 (fresh면 종료 후) 첫 화면으로 띄우고, 화면이 뜰 때까지 기다린다 (am start -W)."""
    r = adb(serial, "shell", "cmd", "package", "resolve-activity", "--brief",
            "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", package, check=False)
    comp = (r.stdout or "").strip().splitlines()[-1:] or [""]
    if "/" not in comp[0]:
        fail(f"{package}가 기기에 없거나 실행할 화면이 없습니다.", "qakit build-app")
    if fresh:
        adb(serial, "shell", "am", "force-stop", package, check=False)
    # 다른 앱 화면(브라우저 로그인 등)이 이 앱 작업 위에 남아 있으면 force-stop으로 안 닫힌다 → 작업째 비우고 시작
    r = adb(serial, "shell", "am", "start", "-W", "--activity-clear-task", "-n", comp[0], check=False, timeout=60)
    if "Error" in (r.stdout + r.stderr):
        fail(f"앱 실행 실패: {comp[0]}", (r.stdout + r.stderr).strip()[-300:])


def android_dump_ui_ws(ws, args):
    """작업공간(platform: android)의 qakit dump-ui. --attach가 아니면 앱을 새로 띄운 뒤 덤프한다."""
    serial = android_serial(ws.emulator, headless=False)
    if not args.attach:
        if not ws.package:
            fail("qakit.yml에 app.packageName이 없습니다.")
        android_launch(serial, ws.package)
    if not args.wait_id:
        time.sleep(args.settle)
        text, _ = android_dump_text(serial, ws.package)
        return masker(ws.secrets())(text)
    deadline = time.time() + 20
    while True:
        text, _ = android_dump_text(serial, ws.package)
        if re.search(rf"#{re.escape(args.wait_id)}(\s|$)", text, re.M):
            return masker(ws.secrets())(text)
        if time.time() > deadline:
            fail(f"{args.wait_id}가 20초 안에 나타나지 않았습니다.")
        time.sleep(1)


def android_doctor_ws(ws, check, problem_count):
    """작업공간(platform: android)의 qakit doctor."""
    for good, okmsg, badmsg, hint in android_doctor_lines():
        check(good, okmsg, badmsg, hint)
    gradle_root = ws.app_dir
    check(gradle_root and gradle_root.is_dir() and any((gradle_root / n).exists() for n in
          ("settings.gradle", "settings.gradle.kts")),
          f"Gradle 프로젝트: {gradle_root}", f"Gradle 프로젝트 아님: {gradle_root}",
          "qakit.yml의 app.project에 settings.gradle(.kts)가 있는 폴더를 적으세요")
    check(bool(ws.package), f"packageName: {ws.package}", "app.packageName 비어 있음")
    check(ws.emulator in android_avds(), f"에뮬레이터(AVD): {ws.emulator}", f"AVD '{ws.emulator}' 없음",
          "qakit android setup --avd " + ws.emulator)
    serial = android_serial(ws.emulator, boot=False) if ws.emulator in android_avds() else None
    if serial and ws.package:
        r = adb(serial, "shell", "pm", "path", ws.package, check=False)
        check(r.stdout.startswith("package:"), "대상 앱 설치됨", "대상 앱이 기기에 없음", "qakit build-app")
    print()
    if problem_count():
        fail(f"문제 {problem_count()}개", "위 → 안내대로 고친 뒤 다시 qakit doctor")
    ok("모두 정상")


# ─────────────────────────────── A3: 상주 실행기 (AndroidRunner, UiAutomator2) ───────────────────────────────
# iOS 상주 실행기와 같은 HTTP 명령(/ping /step /dump /run /launch /reset /stop). 기기 안 127.0.0.1:7912에 열고
# adb forward로 붙는다. 그래서 serve_request·run_via_serve·qakit do는 그대로 쓴다.

ANDROID_RUNNER_DIR = KIT_DIR / "AndroidRunner"
ANDROID_RUNNER_BUILD = KIT_DIR / ".build" / "android-runner"
ANDROID_RUNNER_DEVICE_PORT = 7912
ANDROID_RUNNER_TEST = "com.qakit.runner.test/androidx.test.runner.AndroidJUnitRunner"


def android_runner_hash():
    """실행기 소스 해시 (빌드·설치·상주 실행기 재시작 판단)."""
    h = hashlib.sha1()
    for f in sorted(ANDROID_RUNNER_DIR.rglob("*")):
        rel = f.relative_to(ANDROID_RUNNER_DIR)
        if f.is_file() and not ({"build", ".gradle"} & set(rel.parts)):
            h.update(str(rel).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def ensure_android_runner_built():
    """실행기 APK 두 개(빈 앱 + instrumentation)를 소스가 바뀌었을 때만 빌드한다. → (app_apk, test_apk)"""
    app_apk, test_apk = ANDROID_RUNNER_BUILD / "runner.apk", ANDROID_RUNNER_BUILD / "runner-test.apk"
    stamp = ANDROID_RUNNER_BUILD / "hash"
    h = android_runner_hash()
    if app_apk.exists() and test_apk.exists() and stamp.exists() and stamp.read_text() == h:
        return app_apk, test_apk
    if not android_java_home() or not android_sdk_root():
        fail("안드로이드 실행기를 빌드할 JDK·SDK가 없습니다.", "qakit android setup")
    info("안드로이드 실행기 빌드 중 (처음에는 Gradle을 받느라 몇 분 걸립니다)…")
    r = subprocess.run(["./gradlew", "-q", "--console=plain", ":runner:assembleDebug", ":runner:assembleDebugAndroidTest"],
                       cwd=ANDROID_RUNNER_DIR, env=android_env(), capture_output=True, text=True)
    if r.returncode != 0:
        fail("안드로이드 실행기 빌드 실패", ((r.stdout or "") + (r.stderr or ""))[-1500:])
    out = ANDROID_RUNNER_DIR / "runner" / "build" / "outputs" / "apk"
    ANDROID_RUNNER_BUILD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / "debug" / "runner-debug.apk", app_apk)
    shutil.copyfile(out / "androidTest" / "debug" / "runner-debug-androidTest.apk", test_apk)
    stamp.write_text(h)
    ok("안드로이드 실행기 빌드됨")
    return app_apk, test_apk


def ensure_android_runner_installed(serial):
    app_apk, test_apk = ensure_android_runner_built()
    h = android_runner_hash()
    stamp = SERVE_DIR / f"{serial}.android-runner"
    installed = adb(serial, "shell", "pm", "list", "instrumentation", check=False).stdout
    if stamp.exists() and stamp.read_text() == h and "com.qakit.runner.test" in installed:
        return
    info("기기에 실행기 설치 중…")
    for apk in (app_apk, test_apk):
        r = adb(serial, "install", "-r", "-t", str(apk), check=False, timeout=180)
        if "Success" not in (r.stdout or ""):
            fail(f"실행기 설치 실패: {apk.name}", (r.stdout + r.stderr).strip()[-400:])
    SERVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp.write_text(h)


def android_app_installed(serial, package):
    return adb(serial, "shell", "pm", "path", package, check=False).stdout.startswith("package:")


def android_serve_start(ws, serial, idle=1800, launch=True):
    """안드로이드 상주 실행기를 띄우고 /ping이 될 때까지 기다린다. iOS serve_start와 같은 상태 파일을 쓴다."""
    SERVE_DIR.mkdir(parents=True, exist_ok=True)
    if not ws.package:
        fail("qakit.yml에 app.packageName이 없습니다.")
    if not android_app_installed(serial, ws.package):
        fail(f"기기({serial})에 {ws.package}가 설치되어 있지 않습니다.", "qakit build-app")
    ensure_android_runner_installed(serial)
    token = hashlib.sha1(os.urandom(32)).hexdigest()
    r = adb(serial, "forward", "tcp:0", f"tcp:{ANDROID_RUNNER_DEVICE_PORT}")
    port = int(r.stdout.strip())
    log = SERVE_DIR / f"{serial}.log"
    cmd = [require_tool("adb"), "-s", serial, "shell", "am", "instrument", "-w",
           "-e", "port", str(ANDROID_RUNNER_DEVICE_PORT), "-e", "token", token, "-e", "package", ws.package,
           "-e", "idle", str(int(idle)), "-e", "launch", "1" if launch else "0",
           "-e", "class", "com.qakit.runner.ServeTest", ANDROID_RUNNER_TEST]
    info("상주 실행기 시작 중 (안드로이드)…")
    started_at = time.time()
    with open(log, "w") as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    probe = {"port": port, "token": token}
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            if serve_request(probe, "/ping", timeout=5).get("ok"):
                break
        except (ServeTimeout, ConnectionError):
            pass
        if proc.poll() is not None:
            kept = SERVE_DIR / f"{serial}.failed.log"
            shutil.copyfile(log, kept)
            tail = "\n   ".join(log.read_text(errors="replace").strip().splitlines()[-12:])
            fail("상주 실행기가 시작되지 않았습니다. 다시 실행하면 새로 띄웁니다.", f"{tail}\n   전체 로그: {kept}")
        time.sleep(0.5)
    else:
        os.killpg(proc.pid, 15)
        fail("상주 실행기가 120초 안에 준비되지 않았습니다.", f"로그: {log}")
    serve_request(probe, "/config", {"secrets": ws.secrets()}, timeout=10)   # 비밀값은 명령줄 대신 요청 본문으로
    st = {"udid": serial, "platform": "android", "pid": proc.pid, "port": port, "token": token,
          "workspace": str(ws.root), "bundleId": ws.package, "runnerHash": android_runner_hash(),
          "attachOnly": not launch, "started": datetime.datetime.now().isoformat(timespec="seconds"), "log": str(log)}
    serve_state_file(serial).write_text(json.dumps(st, ensure_ascii=False, indent=2))
    ok(f"상주 실행기 준비됨 (포트 {port}, {time.time() - started_at:.0f}초)")
    return st


def android_format_dump(xml, package, density, activity=None, fragments=None):
    """실행기가 보낸 uiautomator 형식 XML → qakit 덤프 텍스트 (android_dump_text와 같은 머리말)."""
    lines, st = android_dump_lines(xml, package, density or 1.0)
    total, with_id = st["interactive"], st["withId"]
    header = ["# qakit dump-ui", f"# package: {package}"]
    if activity:
        header.append(f"# activity: {activity}")
    if fragments is not None:
        header.append(f"# fragments: {' > '.join(fragments) or '-'}")
    header += [f"# interactive: {total}, with ID: {with_id} ({round(with_id * 100 / total) if total else 100}%)",
               f"# coords: dp (density {density or 1:g})"]
    if st["missing"]:
        header.append("# missing ID: " + ", ".join(st["missing"][:20]))
    return "\n".join(header + lines) + "\n"


def android_convert_response(res):
    """실행기 응답의 XML(화면 구조, dump: 단계 파일)을 덤프 텍스트로 바꾼다. iOS 응답은 그대로."""
    if not isinstance(res, dict) or "density" not in res:
        return res
    if res.get("xml"):
        res["dump"] = android_format_dump(res.pop("xml"), res.get("package"), res.get("density"))
    for k, v in list((res.get("files") or {}).items()):
        if isinstance(v, str) and v.startswith("@xml "):
            res["files"][k] = android_format_dump(v[5:], res.get("package"), res.get("density"))
    return res


def android_seen_ids(ws):
    """안드로이드는 앱 소스에서 ID를 뽑지 않는다 → 저장된 화면 덤프에서 본 ID (coverage용)."""
    ids = set()
    files = [ws.results_dir / "ui-dump.txt"] + sorted((ws.results_dir / "dumps").glob("*.txt"))
    for f in files:
        try:
            ids |= {e["id"] for e in ui_parse_dump(f.read_text(encoding="utf-8"))["elements"] if e["id"]}
        except OSError:
            pass
    return ids
