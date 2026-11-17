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


def android_java_home(timeout=None):
    """JDK 17 이상 위치. JAVA_HOME → /usr/libexec/java_home → brew openjdk@17·openjdk 순. 없으면 None.
    timeout: java_home이 그 안에 답하지 않으면 subprocess.TimeoutExpired (qakit doctor)"""
    v = os.environ.get("JAVA_HOME")
    if v and (Path(v) / "bin" / "java").exists():
        return Path(v)
    r = run(["/usr/libexec/java_home", "-v", "17+"], check=False, timeout=timeout)
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip())
    for name in ("openjdk@17", "openjdk@21", "openjdk"):
        for prefix in ("/opt/homebrew/opt", "/usr/local/opt"):
            p = Path(prefix) / name
            if (p / "bin" / "java").exists():
                return p
    return None


def android_env(timeout=None):
    """sdkmanager·avdmanager·gradle이 쓸 환경 변수 (JAVA_HOME, ANDROID_HOME). timeout: java_home을 기다리는 최대 초"""
    env = dict(os.environ)
    jh, sdk = android_java_home(timeout), android_sdk_root()
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

def adb_devices(timeout=None):
    """[(serial, state, 설명)] — state: device | offline | unauthorized.
    timeout초 안에 답이 없으면 subprocess.TimeoutExpired (adb 서버가 멈추면 끝나지 않는다 — qakit doctor)"""
    adb = android_tool("adb")
    if not adb:
        return []
    r = run([adb, "devices", "-l"], check=False, timeout=timeout)
    rows = []
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        # 'List of devices attached'·'* daemon started' 같은 줄은 건너뛴다
        if len(parts) >= 2 and not line.startswith(("*", "List of")):
            desc = " ".join(p.split(":", 1)[1] for p in parts[2:] if p.startswith(("model:", "device:")))
            rows.append((parts[0], parts[1], desc))
    return rows


def android_avds(timeout=None):
    emu = android_tool("emulator")
    if not emu:
        return []
    r = run([emu, "-list-avds"], check=False, env=android_env(timeout), timeout=timeout)
    return [l.strip() for l in (r.stdout or "").splitlines() if l.strip() and not l.startswith("INFO")]


def emulator_avd_name(serial, timeout=None):
    """실행 중인 에뮬레이터의 AVD 이름 (실기기면 None)."""
    if not serial.startswith("emulator-"):
        return None
    r = run([android_tool("adb"), "-s", serial, "emu", "avd", "name"], check=False, timeout=timeout)
    lines = [l.strip() for l in (r.stdout or "").splitlines() if l.strip() and l.strip() != "OK"]
    return lines[0] if lines else None


def android_serial(avd=None, boot=True, headless=False, timeout=None):
    """쓸 기기 serial. ANDROID_SERIAL → 실행 중인 avd 에뮬레이터 → 연결된 기기 하나 → (boot면) avd를 띄움.
    timeout: adb 명령 하나를 기다리는 최대 초 (넘기면 subprocess.TimeoutExpired — qakit doctor)"""
    ready = [s for s, st, _ in adb_devices(timeout) if st == "device"]
    want = os.environ.get("ANDROID_SERIAL")
    if want:
        if want not in ready:
            fail(f"ANDROID_SERIAL={want} 기기가 연결돼 있지 않습니다.", "adb devices로 확인")
        return want
    if avd:
        for s in ready:
            if emulator_avd_name(s, timeout) == avd:
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
        if android_avd_tuned(avd) is False:
            android_avd_enable_gpu(avd)
            ok(f"AVD 설정을 맞췄습니다 ({avd}: GPU 가속·하드웨어 키보드) — 실행 중인 에뮬레이터는 다시 켜야 반영됩니다 "
               "(adb emu kill → qakit android boot)")
    else:
        avdm = require_tool("avdmanager")
        r = subprocess.run([avdm, "create", "avd", "-n", avd, "-k", image, "-d", args.device_profile],
                           input="no\n", text=True, env=env, capture_output=True)
        if r.returncode != 0:
            fail(f"AVD 생성 실패: {avd}", (r.stderr or r.stdout or "")[-600:])
        android_avd_enable_gpu(avd)   # 기본값(auto)은 화면 캡처가 느려 라이브 화면이 1fps 안팎이 될 수 있다
        ok(f"AVD 만듦: {avd} ({args.device_profile}, {image}, GPU 가속)")
    print()
    ok("안드로이드 준비 완료. 다음: qakit android boot  →  qakit android screen")
    if not os.environ.get("ANDROID_HOME"):
        info(f"(선택) 셸 설정에 추가하면 adb를 바로 쓸 수 있습니다: export ANDROID_HOME={sdk}; "
             'export PATH="$ANDROID_HOME/platform-tools:$PATH"')


def android_avd_config(avd):
    return Path(os.environ.get("ANDROID_AVD_HOME") or Path.home() / ".android" / "avd") / f"{avd}.avd" / "config.ini"


AVD_TUNING = {
    "hw.gpu.enabled": "yes", "hw.gpu.mode": "host",   # 꺼져 있으면 화면 캡처 한 장 2.5초 → 라이브 화면 1fps
    "hw.keyboard": "yes",   # 하드웨어 키보드가 있으면 소프트 키보드를 숨길 수 있다 (실행기가 show_ime_with_hard_keyboard=0)
}


def android_avd_tuned(avd):
    """qakit용 AVD 설정(GPU 가속·하드웨어 키보드)이 다 맞나. 설정 파일이 없으면 None."""
    try:
        cfg = dict(l.split("=", 1) for l in android_avd_config(avd).read_text().splitlines() if "=" in l)
    except OSError:
        return None
    return all(cfg.get(k) == v for k, v in AVD_TUNING.items())


def android_avd_enable_gpu(avd):
    """AVD 설정을 qakit에 맞춘다 (GPU 가속, 하드웨어 키보드). 에뮬레이터를 다시 켜야 반영된다."""
    f = android_avd_config(avd)
    lines = [l for l in f.read_text().splitlines() if l.split("=", 1)[0] not in AVD_TUNING]
    f.write_text("\n".join(lines + [f"{k}={v}" for k, v in AVD_TUNING.items()]) + "\n")


def android_doctor_lines(timeout=None):
    """→ ([(정상 여부, 정상 문구, 문제 문구, 안내)], AVD 목록, 기기 목록) — qakit android doctor와 작업공간 doctor가 함께 쓴다.
    바깥 명령(java_home·emulator -list-avds·adb devices)은 동시에 돌리고 각각 timeout초까지만 기다린다 — 넘기면 그 줄은
    "확인 못 함"이고 목록은 None (adb 서버가 멈추면 adb devices가 끝나지 않는다)."""
    import concurrent.futures

    def java():
        try:
            return android_java_home(timeout)
        except OSError:   # java_home이 없는 시스템
            return None

    def slow(what, cmd, hint="잠시 뒤 다시 점검"):
        return (False, "", f"{what} 확인 못 함 — {timeout}초 안에 답이 없음 ({cmd})",
                f"{hint} — 계속 느리면 --timeout {(timeout or 0) * 3}")

    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        java_f = pool.submit(limited, java)
        avds_f = pool.submit(limited, android_avds, timeout)
        devs_f = pool.submit(limited, adb_devices, timeout)
    (jh, java_slow), (avds, avds_slow), (devs, devs_slow) = java_f.result(), avds_f.result(), devs_f.result()
    sdk = android_sdk_root()
    rows = [
        slow("JDK", "/usr/libexec/java_home") if java_slow else (bool(jh), f"JDK: {jh}", "JDK 17 없음", "qakit android setup"),
        (bool(sdk), f"Android SDK: {sdk}", "Android SDK 없음", "qakit android setup"),
        (bool(android_tool("adb")), "adb 설치됨", "adb 없음 (platform-tools)", "qakit android setup"),
        (bool(android_tool("emulator")), "emulator 설치됨", "emulator 없음", "qakit android setup"),
    ]
    if avds_slow:
        rows.append(slow("AVD", "emulator -list-avds"))
    else:
        rows.append((bool(avds), f"AVD: {', '.join(avds)}", "AVD 없음", "qakit android setup"))
        off = [a for a in avds if android_avd_tuned(a) is False]
        rows.append((not off, "AVD 설정 (GPU 가속·하드웨어 키보드)",
                     f"AVD 설정이 qakit용이 아님: {', '.join(off)} (GPU 가속이 꺼지면 라이브 화면 1fps 안팎, 하드웨어 키보드가 없으면 "
                     "소프트 키보드가 버튼을 가림)", "qakit android setup --avd <이름> 으로 맞춘 뒤 에뮬레이터 다시 켜기"))
    if devs_slow:
        rows.append(slow("연결된 기기", "adb devices", "adb 서버가 멈췄으면 adb kill-server 뒤 다시 점검"))
    else:
        ready = [f"{s}{' ' + d if d else ''}" for s, st, d in devs if st == "device"]
        bad = [f"{s}({st})" for s, st, _ in devs if st != "device"]
        rows.append((not bad, f"연결된 기기: {', '.join(ready) or '(없음 — qakit android boot)'}",
                     f"응답 없는 기기: {', '.join(bad)}", "unauthorized면 기기에서 USB 디버깅 허용"))
    return rows, avds, devs


def cmd_android_doctor(args):
    problems = 0
    rows, _, _ = android_doctor_lines(getattr(args, "timeout", DOCTOR_TIMEOUT))
    for good, okmsg, badmsg, hint in rows:
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
    else:
        serial = android_boot(args.avd or ANDROID_AVD, headless=args.headless)
    if args.orientation:
        android_set_orientation(serial, args.orientation)
        w, h = android_display_size(serial)
        ok(f"화면 방향: {args.orientation} ({w}x{h})")


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


def android_dump_lines(xml, target, density, screen=None):
    """uiautomator XML → (덤프 줄들, 통계). iOS dump-ui와 같은 꼴: `타입 #ID "라벨" ... @x,y wxh` (dp).
    screen=(가로, 세로 픽셀)을 주면 맨 위에 iOS처럼 `Application` 줄을 둔다 — qakit ui가 화면 크기·방향을 여기서 읽는다."""
    root = ET.fromstring(xml)
    lines, stats = [], {"interactive": 0, "withId": 0, "missing": []}
    base = 0
    if screen:
        lines.append(f'Application "{target}" @0,0 {round(screen[0] / density)}x{round(screen[1] / density)}')
        base = 1

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

    visit(root, base)
    return lines, stats


def android_dump_text(serial, package=None):
    """지금 화면 → iOS dump-ui와 같은 형식의 텍스트, 메타 정보 dict."""
    fg = android_foreground(serial)
    target = package or fg["package"]
    density = android_density(serial)
    lines, st = android_dump_lines(android_ui_xml(serial), target, density, android_display_size(serial))
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


def android_doctor_ws(ws, check, problem_count, timeout=None):
    """작업공간(platform: android)의 qakit doctor. timeout: 바깥 명령(adb·emulator) 하나를 기다리는 최대 초."""
    rows, avds, devs = android_doctor_lines(timeout)
    for good, okmsg, badmsg, hint in rows:
        check(good, okmsg, badmsg, hint)
    gradle_root = ws.app_dir
    check(gradle_root and gradle_root.is_dir() and any((gradle_root / n).exists() for n in
          ("settings.gradle", "settings.gradle.kts")),
          f"Gradle 프로젝트: {gradle_root}", f"Gradle 프로젝트 아님: {gradle_root}",
          "qakit.yml의 app.project에 settings.gradle(.kts)가 있는 폴더를 적으세요")
    check(bool(ws.package), f"packageName: {ws.package}", "app.packageName 비어 있음")
    if avds is not None:   # None이면 위에서 "AVD 확인 못 함"을 이미 알렸다
        check(ws.emulator in avds, f"에뮬레이터(AVD): {ws.emulator}", f"AVD '{ws.emulator}' 없음",
              "qakit android setup --avd " + ws.emulator)
    serial = None
    if avds is not None and ws.emulator in avds and devs is not None:   # adb가 멈췄으면 다시 기다리지 않는다
        try:
            serial = android_serial(ws.emulator, boot=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            check(False, "", f"실행 중인 에뮬레이터 확인 못 함 — {timeout}초 안에 답이 없음 (adb emu avd name)",
                  f"잠시 뒤 다시 qakit doctor — 계속 느리면 --timeout {(timeout or 0) * 3}")
    if serial and ws.package:
        try:
            r = subprocess.run([android_tool("adb"), "-s", serial, "shell", "pm", "path", ws.package],
                               capture_output=True, text=True, timeout=timeout)
            check(r.stdout.startswith("package:"), "대상 앱 설치됨", "대상 앱이 기기에 없음", "qakit build-app")
        except subprocess.TimeoutExpired:
            check(False, "", f"대상 앱 설치 확인 못 함 — {timeout}초 안에 답이 없음 (adb shell pm path)",
                  f"잠시 뒤 다시 qakit doctor — 계속 느리면 --timeout {(timeout or 0) * 3}")
    print()
    if problem_count():
        fail(f"문제 {problem_count()}개", "위 → 안내대로 고친 뒤 다시 qakit doctor")
    ok("모두 정상")


# ─────────────────────────────── A3: 상주 실행기 (AndroidRunner, UiAutomator2) ───────────────────────────────
# iOS 상주 실행기와 같은 HTTP 명령(/ping /step /dump /run /launch /reset /stop). 기기 안 127.0.0.1:7912에 열고
# adb forward로 붙는다. 그래서 serve_request·run_via_serve·qakit do는 그대로 쓴다.

ANDROID_RUNNER_DIR = KIT_DIR / "AndroidRunner"
ANDROID_RUNNER_BUILD = BUILD_DIR / "android-runner"
ANDROID_RUNNER_DEVICE_PORT = 7912
ANDROID_FRAME_DEVICE_PORT = 7913   # 라이브 화면 (FrameServer)
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
    gradle_dir = writable_src("AndroidRunner") / "AndroidRunner"   # Gradle은 프로젝트 안에 build·.gradle을 쓴다
    r = subprocess.run(["./gradlew", "-q", "--console=plain", ":runner:assembleDebug", ":runner:assembleDebugAndroidTest"],
                       cwd=gradle_dir, env=android_env(), capture_output=True, text=True)
    if r.returncode != 0:
        fail("안드로이드 실행기 빌드 실패", ((r.stdout or "") + (r.stderr or ""))[-1500:])
    out = gradle_dir / "runner" / "build" / "outputs" / "apk"
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
    android_runner_kill(serial)
    if ws.orientation:   # qakit.yml orientation: — 앱을 켜기 전에 방향을 맞춘다
        android_set_orientation(serial, ws.orientation)
    android_soft_keyboard(serial, show=ws.keyboard == "show")
    token = hashlib.sha1(os.urandom(32)).hexdigest()
    r = adb(serial, "forward", "tcp:0", f"tcp:{ANDROID_RUNNER_DEVICE_PORT}")
    port = int(r.stdout.strip())
    frame_port = int(adb(serial, "forward", "tcp:0", f"tcp:{ANDROID_FRAME_DEVICE_PORT}").stdout.strip())   # 라이브 화면
    log = SERVE_DIR / f"{serial}.log"
    cmd = [require_tool("adb"), "-s", serial, "shell", "am", "instrument", "-w",
           "-e", "port", str(ANDROID_RUNNER_DEVICE_PORT), "-e", "token", token, "-e", "package", ws.package,
           "-e", "idle", str(int(idle)), "-e", "launch", "1" if launch else "0",
           "-e", "framePort", str(ANDROID_FRAME_DEVICE_PORT), "-e", "frameSize", str(live_frame_size("android")),
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
    st = {"udid": serial, "platform": "android", "pid": proc.pid, "port": port, "framePort": frame_port, "token": token,
          "workspace": str(ws.root), "bundleId": ws.package, "runnerHash": android_runner_hash(),
          "attachOnly": not launch, "started": datetime.datetime.now().isoformat(timespec="seconds"), "log": str(log)}
    serve_state_file(serial).write_text(json.dumps(st, ensure_ascii=False, indent=2))
    ok(f"상주 실행기 준비됨 (포트 {port}, {time.time() - started_at:.0f}초)")
    return st


def android_format_dump(xml, package, density, activity=None, fragments=None, screen=None):
    """실행기가 보낸 uiautomator 형식 XML → qakit 덤프 텍스트 (android_dump_text와 같은 머리말)."""
    lines, st = android_dump_lines(xml, package, density or 1.0, screen)
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
    screen = (res["screenW"], res["screenH"]) if res.get("screenW") and res.get("screenH") else None
    if res.get("xml"):
        res["dump"] = android_format_dump(res.pop("xml"), res.get("package"), res.get("density"), screen=screen)
    for k, v in list((res.get("files") or {}).items()):
        if isinstance(v, str) and v.startswith("@xml "):
            res["files"][k] = android_format_dump(v[5:], res.get("package"), res.get("density"), screen=screen)
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


# qakit.yml permissions: (iOS simctl privacy 이름과 같은 말) → 안드로이드 권한. android.permission.X를 그대로 써도 된다
ANDROID_PERMISSIONS = {
    "location": ["ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"],
    "location-always": ["ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "ACCESS_BACKGROUND_LOCATION"],
    "notifications": ["POST_NOTIFICATIONS"],
    "nearby": ["BLUETOOTH_SCAN", "BLUETOOTH_CONNECT", "NEARBY_WIFI_DEVICES"],   # 근처 기기 (블루투스·Wi-Fi)
    "camera": ["CAMERA"],
    "microphone": ["RECORD_AUDIO"],
    "photos": ["READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO"],
    "contacts": ["READ_CONTACTS"],
    "calendar": ["READ_CALENDAR", "WRITE_CALENDAR"],
}


def android_grant_permissions(ws, serial):
    """qakit.yml permissions:를 미리 허용한다 (앱 설치·pm clear 뒤 권한 대화상자가 시나리오를 막지 않게)."""
    granted = []
    for name in ws.permissions:
        name = str(name)
        if name == "background":   # 배터리 최적화 예외 → "항상 백그라운드에서 실행할까요?" 대화상자가 뜨지 않는다
            adb(serial, "shell", "dumpsys", "deviceidle", "whitelist", "+" + ws.package, check=False)
            granted.append("배터리 최적화 예외")
            continue
        perms = ANDROID_PERMISSIONS.get(name) or ([name.split(".")[-1]] if "." in name else None)
        if not perms:
            warn(f"알 수 없는 권한 이름: {name} (location·notifications·camera… 또는 android.permission.X)")
            continue
        for perm in perms:
            r = adb(serial, "shell", "pm", "grant", ws.package, "android.permission." + perm, check=False)
            if r.returncode == 0:
                granted.append(perm)
    if granted:
        ok("권한 미리 허용: " + ", ".join(dict.fromkeys(granted)))



# ─────────────────────────────── A6: 라이브 세션 (qakit ui) ───────────────────────────────

def android_live_runner(ws, serial):
    """라이브 화면용 상주 실행기. 이미 떠 있으면 그대로, 없으면 앱을 다시 켜지 않고(launch=False) 띄운다."""
    st = serve_load(serial)
    if st and st.get("workspace") == str(ws.root) and st.get("runnerHash") == android_runner_hash() \
            and serve_same_app(ws, st) and st.get("framePort") and serve_alive(st):
        return st
    # 다른 실행(qakit run·do·build-app)이 실행기를 띄우거나 쓰는 중이면 건드리지 않는다 — 여기서 다시 띄우면 그 실행의
    # 실행기를 죽이고 서로 번갈아 "Process crashed"가 난다 (qakit ui를 열어 둔 채 qakit run, 2026-11-16)
    busy = device_busy(serial)
    if busy:
        raise RuntimeError(f"다른 실행이 기기를 쓰는 중 — 끝나면 화면이 다시 나옵니다 ({busy})")
    with sim_lock(ws, "qakit ui 라이브 화면"):
        serve_stop(serial, quiet=True)
        return android_serve_start(ws, serial, launch=False)


def cmd_android_frames(args):
    """(qakit ui 내부용) 실행기 화면 서버에서 받은 JPEG 프레임을 그대로 표준 출력으로 — simscreen과 같은 형식."""
    import socket
    try:
        sock = socket.create_connection(("127.0.0.1", args.port), timeout=10)
    except OSError as e:
        print(f"androidframes: 화면 서버에 연결하지 못함: {e}", file=sys.stderr)
        sys.exit(1)
    sock.settimeout(15)
    out = sys.stdout.buffer
    try:
        while True:
            data = sock.recv(1 << 16)
            if not data:
                print("androidframes: 화면 서버가 연결을 끊음 (실행기 종료?)", file=sys.stderr)
                sys.exit(1)
            out.write(data)
            out.flush()
    except (socket.timeout, BrokenPipeError, KeyboardInterrupt):
        pass


DISPLAY_SIZE = {}


def android_display_size(serial):
    """지금 화면 크기(픽셀, 회전 반영) — 2초 동안 기억한다."""
    hit = DISPLAY_SIZE.get(serial)
    if hit and time.time() - hit[0] < 2:
        return hit[1]
    out = adb(serial, "shell", "dumpsys", "window", "displays", check=False).stdout
    m = re.search(r"\bcur=(\d+)x(\d+)", out)
    if not m:
        m = re.search(r"(\d+)x(\d+)", adb(serial, "shell", "wm", "size", check=False).stdout)
    size = (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)
    DISPLAY_SIZE[serial] = (time.time(), size)
    return size


def android_touch(serial, kind, pts, secs):
    """라이브 세션 직접 터치. 좌표는 화면 대비 0~1. kind: tap · press(길게) · swipe(끌기)."""
    w, h = android_display_size(serial)
    px = [int(round(v * (w if i % 2 == 0 else h))) for i, v in enumerate(pts)]
    ms = str(max(1, int(secs * 1000)))
    if kind == "tap":
        cmd = ["input", "tap", str(px[0]), str(px[1])]
    elif kind == "press":
        cmd = ["input", "swipe", str(px[0]), str(px[1]), str(px[0]), str(px[1]), ms]
    else:
        cmd = ["input", "swipe", *map(str, px[:4]), ms]
    r = adb(serial, "shell", *cmd, check=False, timeout=secs + 10)
    good = r.returncode == 0 and not (r.stderr or "").strip()
    return good, ("ok" if good else (r.stderr or r.stdout).strip()[-200:])


ANDROID_REC_REMOTE = "/sdcard/qakit-rec.mp4"


def android_record_start(serial):
    """화면 녹화 시작 (adb screenrecord, 최대 3분 — 안드로이드 제한). → Popen"""
    adb(serial, "shell", "rm", "-f", ANDROID_REC_REMOTE, check=False)
    return subprocess.Popen([require_tool("adb"), "-s", serial, "shell", "screenrecord", "--time-limit", "180",
                             ANDROID_REC_REMOTE], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def android_record_stop(serial, proc, out):
    """녹화를 끝내고 파일을 가져온다. screenrecord는 SIGINT를 받아야 파일을 마무리한다."""
    adb(serial, "shell", "pkill", "-INT", "screenrecord", check=False)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    time.sleep(0.5)
    adb(serial, "pull", ANDROID_REC_REMOTE, str(out), check=False, timeout=120)
    adb(serial, "shell", "rm", "-f", ANDROID_REC_REMOTE, check=False)


# ─────────────────────────────── 화면 방향 ───────────────────────────────

def android_set_orientation(serial, orientation):
    """화면 방향 고정: landscape(가로) · portrait(세로) · auto(기기 회전 따름).
    자동 회전을 끄고 user_rotation을 정한다. 기기의 기본 방향(휴대폰=세로, 태블릿=가로)에 따라 값이 다르다."""
    orientation = (orientation or "").lower()
    if orientation in ("", "auto"):
        adb(serial, "shell", "settings", "put", "system", "accelerometer_rotation", "1", check=False)
        return
    if orientation not in ("landscape", "portrait"):
        fail(f"화면 방향은 landscape·portrait·auto 중 하나: {orientation}")
    m = re.search(r"Physical size: (\d+)x(\d+)", adb(serial, "shell", "wm", "size", check=False).stdout)
    natural_landscape = bool(m) and int(m.group(1)) > int(m.group(2))
    want_landscape = orientation == "landscape"
    rotation = "0" if natural_landscape == want_landscape else "1"
    adb(serial, "shell", "settings", "put", "system", "accelerometer_rotation", "0", check=False)
    adb(serial, "shell", "settings", "put", "system", "user_rotation", rotation, check=False)
    DISPLAY_SIZE.pop(serial, None)
    deadline = time.time() + 5   # 회전이 끝날 때까지 (화면 크기 가로·세로가 바뀜)
    while time.time() < deadline:
        w, h = android_display_size(serial)
        if (w > h) == want_landscape:
            break
        DISPLAY_SIZE.pop(serial, None)
        time.sleep(0.3)


def cmd_android_rotate(args):
    serial = android_serial(args.avd, boot=False)
    if not serial:
        fail("연결된 안드로이드 기기가 없습니다.", "qakit android boot")
    android_set_orientation(serial, args.orientation)
    w, h = android_display_size(serial)
    ok(f"화면 방향: {args.orientation} ({w}x{h})")


# 에뮬레이터의 화면 키보드 앱. 꺼 두면 입력칸에 포커스가 가도 키보드가 뜨지 않는다 (음성 입력만 남아 화면에 안 보임)
SOFT_KEYBOARDS = ("com.google.android.inputmethod.latin", "com.android.inputmethod.latin")


def android_soft_keyboard(serial, show):
    """에뮬레이터 화면 키보드 켜기/끄기 (qakit.yml keyboard: show | hide(기본)).
    qakit은 글자를 키보드 없이 넣는다(SET_TEXT). 떠 있는 키보드는 버튼을 가리고, 쓸기가 키보드에 닿으면
    글라이드 입력으로 글자가 들어간다 (태블릿에서 확인, 2026-11-16). show_ime_with_hard_keyboard=0은 이 이미지에서 듣지 않았다.
    실기기는 건드리지 않는다. 끈 뒤에도 Mac 키보드로 에뮬레이터 창에 입력할 수 있다 (AVD hw.keyboard=yes)."""
    if not serial.startswith("emulator-"):
        return
    installed = adb(serial, "shell", "pm", "list", "packages", check=False).stdout
    disabled = adb(serial, "shell", "pm", "list", "packages", "-d", check=False).stdout
    for pkg in SOFT_KEYBOARDS:
        if f"package:{pkg}" not in installed.split():
            continue
        is_off = f"package:{pkg}" in disabled
        if show and is_off:
            adb(serial, "shell", "pm", "enable", pkg, check=False)
            info(f"화면 키보드 켬 ({pkg})")
        elif not show and not is_off:
            adb(serial, "shell", "pm", "disable-user", "--user", "0", pkg, check=False)
            info("화면 키보드 끔 — 시험 중 버튼을 가리지 않게 (qakit.yml keyboard: show 로 켬, Mac 키보드 입력은 됨)")



# ─────────────────────────────── A4: 앱 빌드·설치 (qakit build-app) ───────────────────────────────

def android_gradle_task(ws):
    """:app:assembleDebug 꼴. module은 app 또는 feature:home처럼 Gradle 경로, variant는 debug·prodDebug 등."""
    module = ws.module.strip(":")
    return f":{module}:assemble{ws.variant[:1].upper()}{ws.variant[1:]}"


def android_find_apk(ws):
    """빌드 결과에서 variant의 APK와 applicationId. Gradle이 쓰는 output-metadata.json을 읽는다 (flavor 폴더도)."""
    out = ws.app_dir / Path(*ws.module.strip(":").split(":")) / "build" / "outputs" / "apk"
    best = None
    for meta in out.rglob("output-metadata.json"):
        try:
            data = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        if data.get("variantName") != ws.variant:
            continue
        for el in data.get("elements") or []:
            apk = meta.parent / el.get("outputFile", "")
            if apk.exists() and (best is None or apk.stat().st_mtime > best[0].stat().st_mtime):
                best = (apk, data.get("applicationId"))
    return best or (None, None)


def android_build_app(ws):
    """Gradle로 앱을 빌드하고 에뮬레이터(또는 연결된 기기)에 설치한 뒤 권한을 미리 허용한다."""
    ws.results_dir.mkdir(exist_ok=True)
    gradle_root = ws.app_dir
    gradlew = gradle_root / "gradlew" if gradle_root else None
    if not gradlew or not gradlew.exists():
        fail(f"Gradle 프로젝트가 아닙니다 (gradlew 없음): {gradle_root}", "qakit.yml app.project에 settings.gradle(.kts)가 있는 폴더")
    if not android_java_home():
        fail("JDK가 없습니다.", "qakit android setup")
    serial = ensure_booted(ws)
    task = android_gradle_task(ws)
    info(f"앱 빌드 중: {task} — 처음엔 라이브러리를 받느라 몇 분 걸립니다")
    log_path = ws.results_dir / "build-app.log"
    state = app_state(ws)
    before = git(gradle_root, "status", "--porcelain", "--", *app_pathspec(ws))
    started = time.time()
    with open(log_path, "w", encoding="utf-8") as log:
        r = subprocess.run(["./gradlew", "--console=plain", task], cwd=gradle_root, env=android_env(),
                           stdout=log, stderr=subprocess.STDOUT, text=True)
    text = log_path.read_text(encoding="utf-8", errors="replace")
    after = git(gradle_root, "status", "--porcelain", "--", *app_pathspec(ws))
    if before is not None and after != before:
        changed = sorted(set((after or "").splitlines()) - set((before or "").splitlines()))
        warn("빌드 중 앱 레포 파일이 바뀌었습니다: " + ", ".join(c[3:] for c in changed))
    if r.returncode != 0:
        lines = text.splitlines()
        # Kotlin 컴파일 오류(e: …)와 Gradle 실패 이유(What went wrong 아래)를 먼저
        errors = [l for l in lines if l.startswith("e: ") or "error:" in l]
        i = next((n for n, l in enumerate(lines) if "What went wrong" in l), None)
        why = lines[i + 1:i + 4] if i is not None else []
        fail("앱 빌드 실패", "\n   ".join(dict.fromkeys([*errors[:12], *why])) or f"로그: {log_path}")
    ok(f"빌드 완료 ({time.time() - started:.0f}초)")

    apk, app_id = android_find_apk(ws)
    if not apk:
        fail(f"빌드 결과에서 {ws.variant} APK를 찾지 못했습니다.", "qakit.yml app.module·app.variant 확인")
    if app_id and ws.package and app_id != ws.package:
        fail(f"빌드한 앱({app_id})이 qakit.yml packageName({ws.package})과 다릅니다.",
             "debug 빌드는 applicationIdSuffix(.debug 등)가 붙을 수 있습니다 — app.packageName을 맞추세요")
    serve_stop(serial, quiet=True)   # 설치하면 앱이 꺼진다 → 실행기도 새로 띄운다
    info(f"설치 중: {apk.name} ({apk.stat().st_size // (1 << 20)}MB) → {serial}")
    r = adb(serial, "install", "-r", "-t", str(apk), check=False, timeout=900)
    if "Success" not in (r.stdout or ""):
        msg = (r.stdout + r.stderr).strip()
        hint = None
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in msg:
            hint = f"다른 키로 서명된 같은 앱이 있습니다 → adb -s {serial} uninstall {ws.package} 뒤 다시 (앱 데이터가 지워짐)"
        fail("설치 실패", (msg[-400:] + (f"\n   → {hint}" if hint else "")))
    ok(f"설치: {apk.name} → {serial}")
    android_grant_permissions(ws, serial)
    state.update(installedOn=serial, apk=str(apk))
    save_state(ws, ws.state_name, state)



def live_frame_size(platform):
    """라이브 화면 크기: 안드로이드는 긴 변, iOS(simscreen)는 가로 폭 (px). QAKIT_LIVE_SIZE로 바꿈.
    레티나 화면에서 기기 그림이 흐리지 않을 만큼 (화면에 그리는 폭 약 660pt × 2)."""
    with contextlib.suppress(ValueError):
        v = int(os.environ.get("QAKIT_LIVE_SIZE", "0"))
        if 320 <= v <= 3000:
            return v
    return 1280 if platform == "android" else 900


def android_runner_kill(serial):
    """기기에 남은 실행기를 끝낸다. 호스트 쪽 adb만 끝나고 기기 안 실행기가 살아 있으면(상태 파일이 지워진 뒤 등)
    새 am instrument가 그 프로세스와 부딪쳐 "Process crashed"로 실패한다 (build-app 직후 첫 실행에서 확인, 2026-11-16)."""
    adb(serial, "shell", "am", "force-stop", "com.qakit.runner", check=False)
    deadline = time.time() + 5
    while time.time() < deadline and adb(serial, "shell", "pidof", "com.qakit.runner", check=False).stdout.strip():
        time.sleep(0.2)


# ─────────────────────────────── A5: 로그·크래시·네트워크 ───────────────────────────────
# 앱 로그는 uid로 거른다 (pid는 재실행·크래시 뒤 바뀜). 크래시는 crash 버퍼, ANR은 system 버퍼(ActivityManager).
# 네트워크는 앱이 OkHttp HttpLoggingInterceptor로 남긴 줄을 읽는다 — 보통 debug 빌드에만 있다.

LOGCAT_RE = re.compile(r"^(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEFA])\s+(.*?)\s*: ?(.*)$")
LOG_LEVELS = "VDIWEFA"
HTTP_TAGS = ("okhttp.OkHttpClient", "OkHttp", "OkHttpClient")
HTTP_REQ_RE = re.compile(r"^--> (GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS) (\S+)")
HTTP_RES_RE = re.compile(r"^<-- (\d{3})\b.*?(https?://\S+).*?\((\d+)ms")
HTTP_FAIL_RE = re.compile(r"^<-- HTTP FAILED: (.*)")
_REDACT = [   # 결과 폴더에 남기기 전에 인증 값 가리기 (secrets.txt 값은 masker가 따로 가린다)
    (re.compile(r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|[\w-]*token)\s*:\s*\S.*"), r"\1: •••"),
    (re.compile(r'(?i)("[\w-]*(?:token|password|passwd|secret|cookie)[\w-]*"\s*:\s*)"[^"]*"'), r'\1"•••"'),
    (re.compile(r"(?i)\b((?:access|refresh|id)_?token=)[^&\s]+"), r"\1•••"),
]


def log_redact(line):
    for rx, rep in _REDACT:
        line = rx.sub(rep, line)
    return line


def android_app_uid(serial, pkg):
    out = adb(serial, "shell", "pm", "list", "packages", "-U", pkg, check=False, timeout=20).stdout
    for line in out.splitlines():
        m = re.match(r"package:(\S+) uid:(\d+)", line.strip())
        if m and m.group(1) == pkg:
            return m.group(2)
    return None


def android_device_time(serial):
    """기기 시각 (logcat -T에 넣을 epoch 초.밀리초). 호스트 시계와 어긋나도 되게 기기에서 읽는다."""
    t = adb(serial, "shell", "date", "+%s.%3N", check=False, timeout=10).stdout.strip()
    return t if re.fullmatch(r"\d+\.\d{3}", t) else None


def parse_since(text, serial):
    """'90s'·'10m'·'2h' → 기기 기준 그 시각 (epoch 문자열). 숫자만 쓰면 분."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([smh]?)", (text or "").strip())
    if not m:
        fail(f"--since 형식: 30s, 10m, 2h (받은 값: {text})")
    sec = float(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "": 60}[m.group(2)]
    now = android_device_time(serial)
    return f"{float(now) - sec:.3f}" if now else None


def android_logcat(serial, pkg, since=None, tail=None):
    """→ (앱 로그 줄, crash 버퍼 줄, system 버퍼 줄). since: 기기 epoch 문자열, tail: 앱 로그 마지막 N줄.
    logcat -t는 거르기 전 전체 줄 수라서 쓰지 않고 다 받아 자른다 (앱 로그 1.7MB ≈ 0.1초)."""
    win = ["-T", since] if since else []
    base = ["shell", "logcat", "-d", "-v", "threadtime", *win]
    uid = android_app_uid(serial, pkg)
    app = adb(serial, *base, f"--uid={uid}", check=False, timeout=60).stdout.splitlines() if uid else []
    app = [l for l in app if not l.startswith("--------- beginning of")]
    if tail:
        app = app[-tail:]
    crash = adb(serial, *base, "-b", "crash", check=False, timeout=30).stdout.splitlines()
    system = adb(serial, *base, "-b", "system", check=False, timeout=30).stdout.splitlines()
    return app, crash, system


def _owns(text, pkg):
    """크래시·ANR 글이 이 앱 것인지 (com.app이 com.app.debug에 걸리지 않게)."""
    p = re.escape(pkg)
    return bool(re.search(rf"(?:Process: {p},|>>> {p} <<<|Cmdline: {p}(?:\s|$)|ANR in {p}(?:\s|$|\())", text))


def android_log_report(app, crash, system, pkg):
    """로그 줄 → {crashes: [[줄]], anrs: [[줄]], errors: [(횟수, 줄)], http: {...}}."""
    parsed = [(l, LOGCAT_RE.match(l)) for l in app]
    # 크래시: FATAL EXCEPTION(자바)·*** *** ***(네이티브)에서 시작해 같은 pid 줄을 모은다
    crashes, cur, cur_pid = [], None, None
    for line in crash:
        m = LOGCAT_RE.match(line)
        msg, pid = (m.group(6), m.group(2)) if m else (line, None)
        if "FATAL EXCEPTION" in msg or msg.startswith("*** *** ***"):
            cur, cur_pid = [line], pid
            crashes.append(cur)
        elif cur is not None and pid == cur_pid:
            cur.append(line)
    crashes = [c for c in crashes if _owns("\n".join(c), pkg)]
    # ANR: ActivityManager의 "ANR in <앱>"과 바로 뒤 같은 스레드의 설명 줄
    anrs = []
    for i, line in enumerate(system):
        if _owns(line, pkg) and "ANR in" in line:
            m = LOGCAT_RE.match(line)
            block = [line]
            for nxt in system[i + 1:i + 12]:
                n = LOGCAT_RE.match(nxt)
                if not (m and n and n.group(3) == m.group(3)):
                    break
                block.append(nxt)
            anrs.append(block)
    # 오류: E/F 줄, 숫자를 지운 문장이 같으면 한 번만 (횟수)
    errors = {}
    for line, m in parsed:
        if m and m.group(4) in "EF" and m.group(5) not in HTTP_TAGS:
            key = (m.group(5), re.sub(r"\d+", "#", m.group(6))[:160])
            n, first = errors.get(key, (0, line))
            errors[key] = (n + 1, first)
    # 네트워크 (OkHttp 로그)
    reqs, failed, last_req = 0, [], {}
    for line, m in parsed:
        if not m or m.group(5) not in HTTP_TAGS:
            continue
        msg, tid = m.group(6), m.group(3)
        if (q := HTTP_REQ_RE.match(msg)):
            reqs += 1
            last_req[tid] = f"{q.group(1)} {q.group(2)}"
        elif (r := HTTP_RES_RE.match(msg)):
            if int(r.group(1)) >= 400:
                failed.append(f"{m.group(1)}  {r.group(1)}  {r.group(2)} ({r.group(3)}ms)")
        elif (f := HTTP_FAIL_RE.match(msg)):
            failed.append(f"{m.group(1)}  실패  {last_req.get(tid, '?')} — {f.group(1)[:160]}")
    return {"crashes": crashes, "anrs": anrs, "lines": len(app),
            "errors": sorted(errors.values(), key=lambda e: -e[0]),
            "http": {"requests": reqs, "failed": failed, "logged": reqs > 0}}


def android_mapping_file(ws):
    """난독화(R8) 빌드의 mapping.txt (크래시 스택 복원용). 없으면 None."""
    base = ws.app_dir / Path(*ws.module.strip(":").split(":")) / "build" / "outputs" / "mapping"
    for cand in [base / ws.variant / "mapping.txt", *sorted(base.glob(f"*/{ws.variant}/mapping.txt"))]:
        if cand.is_file():
            return cand
    return None


def android_retrace(mapping, lines):
    """R8 retrace로 난독화된 스택을 원래 이름으로. 실패하면 원래 줄."""
    tool = android_tool("retrace")
    if not (tool and mapping):
        return lines
    try:
        r = subprocess.run([tool, str(mapping)], input="\n".join(lines) + "\n", capture_output=True, text=True,
                           timeout=120, env=android_env())
    except (OSError, subprocess.TimeoutExpired):
        return lines
    out = [l for l in r.stdout.rstrip("\n").splitlines() if not l.startswith("Waiting for stack-trace input")]
    return out if r.returncode == 0 and out else lines


def _log_msg(line):
    m = LOGCAT_RE.match(line)
    return m.group(6) if m else line


def android_report_lines(rep, indent="   ", max_errors=8, mapping=None):
    """보고서 → 요약에 넣을 줄 (없으면 빈 목록)."""
    out = []
    for c in rep["crashes"][-2:]:
        body = android_retrace(mapping, c) if mapping else c
        msgs = [_log_msg(l) for l in body]
        out.append(f"{indent}💥 앱 크래시 ({len(rep['crashes'])}번)" + (" — mapping으로 복원" if mapping and body != c else ""))
        out += [f"{indent}   {m}" for m in msgs[:25]] + ([f"{indent}   …({len(msgs) - 25}줄 더)"] if len(msgs) > 25 else [])
    for a in rep["anrs"][-1:]:
        out.append(f"{indent}⏳ ANR (응답 없음, {len(rep['anrs'])}번)")
        out += [f"{indent}   {_log_msg(l)}" for l in a[:8]]
    if rep["http"]["failed"]:
        out.append(f"{indent}🌐 실패한 요청 {len(rep['http']['failed'])}개 / 전체 {rep['http']['requests']}개")
        out += [f"{indent}   {log_redact(x)}" for x in rep["http"]["failed"][-8:]]
    if rep["errors"] and max_errors:
        out.append(f"{indent}앱 오류 로그 (E) {sum(n for n, _ in rep['errors'])}줄 — 많은 순")
        for n, line in rep["errors"][:max_errors]:
            m = LOGCAT_RE.match(line)
            text = f"{m.group(5)}: {m.group(6)}" if m else line
            out.append(f"{indent}   {('×' + str(n)).ljust(5)} {log_redact(text)[:200]}")
    return out


def android_collect_run_logs(ws, serial, since, rd, mask):
    """run 하나의 로그를 결과 폴더에 (logcat.txt, crash.txt) → 보고서 (실패하면 None)."""
    if not since:
        return None
    try:
        app, crash, system = android_logcat(serial, ws.package, since=since)
    except SystemExit:
        return None
    rep = android_log_report(app, crash, system, ws.package)
    rep["mapping"] = android_mapping_file(ws) if ws.variant != "debug" else None
    text = "\n".join(log_redact(l) for l in app)
    (rd / "logcat.txt").write_text(mask(text) + "\n", encoding="utf-8")
    if rep["crashes"] or rep["anrs"]:
        blocks = [android_retrace(rep["mapping"], c) for c in rep["crashes"]] + rep["anrs"]
        (rd / "crash.txt").write_text(mask("\n\n".join("\n".join(b) for b in blocks)) + "\n", encoding="utf-8")
    return rep


def _logs_target(args):
    """(serial, 패키지, 작업공간 또는 None)"""
    ws = None
    explicit = getattr(args, "workspace", None)
    if explicit or any((d / "qakit.yml").exists() for d in [Path.cwd(), *Path.cwd().parents]):
        ws = find_workspace(explicit)
    if ws and ws.platform != "android":
        ws = None
    serial = android_serial(args.avd or (ws.emulator if ws else None), boot=False)
    if not serial:
        fail("연결된 안드로이드 기기가 없습니다.", "qakit android boot")
    pkg = args.package or (ws.package if ws else None) or android_foreground(serial)["package"]
    if not pkg:
        fail("어느 앱의 로그인지 모릅니다.", "--package <앱 패키지> 또는 작업공간 폴더에서 실행")
    return serial, pkg, ws


def cmd_android_logs(args):
    """앱 로그 보기: 기본은 최근 줄, --crash 크래시·ANR만, --net 네트워크만, -f 실시간."""
    serial, pkg, ws = _logs_target(args)
    mask = masker(ws.secrets()) if ws else (lambda s: s)
    min_level = LOG_LEVELS.index(args.level) if args.level else 0
    grep = re.compile(args.grep, re.I) if args.grep else None

    def keep(line):
        m = LOGCAT_RE.match(line)
        if m and LOG_LEVELS.index(m.group(4)) < min_level:
            return False
        if args.net and not (m and m.group(5) in HTTP_TAGS):
            return False
        return not grep or bool(grep.search(line))

    if args.follow:
        uid = android_app_uid(serial, pkg)
        if not uid:
            fail(f"{pkg}가 설치돼 있지 않습니다.")
        info(f"{pkg} 로그 (uid {uid}, 끝내려면 Ctrl-C)")
        proc = subprocess.Popen([require_tool("adb"), "-s", serial, "logcat", "-v", "threadtime", "-T", "1", f"--uid={uid}"],
                                stdout=subprocess.PIPE, text=True, errors="replace")
        try:
            for line in proc.stdout:
                if keep(line.rstrip("\n")):
                    print(mask(log_redact(line.rstrip("\n"))), flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            proc.kill()
        return
    since = parse_since(args.since, serial) if args.since else None
    app, crash, system = android_logcat(serial, pkg, since=since)
    rep = android_log_report(app, crash, system, pkg)
    mapping = android_mapping_file(ws) if ws and ws.variant != "debug" else None
    if args.json:
        print(json.dumps({"serial": serial, "package": pkg, "lines": rep["lines"],
                          "crashes": [android_retrace(mapping, c) for c in rep["crashes"]], "anrs": rep["anrs"],
                          "errors": [{"count": n, "line": log_redact(l)} for n, l in rep["errors"]],
                          "http": rep["http"]}, ensure_ascii=False, indent=1))
        return
    if args.crash:
        lines = android_report_lines({**rep, "errors": [], "http": {**rep["http"], "failed": []}}, indent="", mapping=mapping)
        print(mask("\n".join(lines)) if lines else "크래시·ANR 없음" + (f" (최근 {args.since})" if args.since else ""))
        return
    if not app:
        warn(f"{pkg} 로그가 없습니다" + ("" if android_app_uid(serial, pkg) else " (설치돼 있지 않음)")
             + (" — 작업공간 기본은 debug 빌드입니다. release 앱이면 --build release" if ws and ws.variant == "debug" else ""))
    shown = [l for l in app if keep(l)]
    if not since:
        shown = shown[-args.lines:]
    for l in shown:
        print(mask(log_redact(l)))
    if args.net and not rep["http"]["logged"]:
        warn("OkHttp 로그가 없습니다 — 보통 debug 빌드만 HttpLoggingInterceptor를 켭니다 (--build release면 안 보임)")
    summary = android_report_lines(rep, indent="", max_errors=0 if args.net else 5, mapping=mapping)
    if summary and not args.grep:
        print("\n── 요약")
        print(mask("\n".join(summary)))


class AndroidTouch:
    """AI 직접 터치용 (TouchHelper와 같은 꼴: tap(x, y)·send("tap|press|swipe …")). 좌표는 0~1."""

    def __init__(self, serial):
        self.serial = serial

    def tap(self, x, y):
        return android_touch(self.serial, "tap", [x, y], 0.06)

    def send(self, cmd, timeout=None):
        p = cmd.split()
        try:
            if p[0] == "tap":
                return android_touch(self.serial, "tap", [float(p[1]), float(p[2])], 0.06)
            if p[0] == "press":
                return android_touch(self.serial, "press", [float(p[1]), float(p[2])], float(p[3]))
            if p[0] == "swipe":
                return android_touch(self.serial, "swipe", [float(v) for v in p[1:5]], float(p[5]))
        except (IndexError, ValueError):
            pass
        return False, f"모르는 터치 명령: {cmd}"


def android_shot_jpeg(serial, width=440):
    """작은 JPEG 한 장 (screencap PNG → sips로 줄여 JPEG). 실패하면 None."""
    r = subprocess.run([require_tool("adb"), "-s", serial, "exec-out", "screencap", "-p"], capture_output=True, timeout=30)
    if r.returncode != 0 or not r.stdout.startswith(b"\x89PNG"):
        return None
    src = Path(tempfile.mkstemp(suffix=".png")[1])
    dst = src.with_suffix(".jpg")
    try:
        src.write_bytes(r.stdout)
        ok_ = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70", "--resampleWidth", str(width),
                              str(src), "--out", str(dst)], capture_output=True).returncode == 0
        return dst.read_bytes() if ok_ and dst.exists() else None
    finally:
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)

