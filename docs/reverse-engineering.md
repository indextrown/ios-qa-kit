# 비공개 API 조사 방법: 역어셈블 · 런타임 · 로그 · XPC

[비공개 API](private-apis.md)에 적은 내용을 **어떻게 알아냈는지**, 다음에 Xcode가 바뀌었을 때 같은 방법으로 다시 조사할 수 있게 정리합니다.
실제로 쓴 명령과 그 결과(Xcode 27.0, macOS 27.0.1, iOS 27.0 시뮬레이터, 2026-11-16~17)를 함께 적습니다.

[← 비공개 API](private-apis.md) · [← README](../README.md)

## 지킬 것

| 규칙 | 이유 (실제로 겪은 일) |
|---|---|
| **실험은 새로 만든 시험용 시뮬레이터에서만** (`simctl create qakit-probe …`, 끝나면 `simctl delete`) | 공용 기기를 다른 작업(다른 세션의 시나리오)이 쓰고 있다. 이름은 공용 기기와 겹치지 않게 |
| **Device Hub를 끄지 말 것** | 끄면 켜져 있던 시뮬레이터가 모두 꺼진다 (공용 기기까지 꺼져 다시 켬). 기기를 바꾸려면 목록에서 고른다 |
| **모르는 값을 공용 기기에 보내지 말 것** | 목적지 0x101 메시지 한 번에 기기 안 backboardd가 죽었다 (시험용 기기였음) |
| **원인을 단정하기 전에 대조 실험** — 같은 조건을 여러 부팅·여러 기기로 | "XCUITest가 켠 앱", "새 기기", "Device Hub에 안 띄움"을 차례로 원인으로 적었다가 모두 틀렸다. 실제는 부팅마다 갈리는 문제였다 |
| **판정은 화면을 보고** | JPEG 크기 2% 비교는 화면 일부가 저절로 바뀌면("최적화 중" 행) 속는다. 설정 앱이 아직 다 안 그려진 상태(5KB)와 비교하면 무효 |
| **사용자가 다른 앱을 쓰는 중이면 좌표 클릭을 보내지 않는다** | 대상 앱이 앞으로 안 오면 클릭이 엉뚱한 창(예: Safari)에 들어간다 |

## 한눈에: 무엇을 알고 싶을 때 무엇을 쓰나

| 알고 싶은 것 | 도구 | 예 |
|---|---|---|
| 부품이 어디 있나, 무엇에 의존하나 | `find`, `otool -L`, 실행 중이면 `vmmap <pid>` | Device Hub는 `DeviceKit` + `SimulatorDeviceKitPlugin`으로 SimulatorKit을 불러온다 |
| ObjC 클래스·메서드·변수 | `scripts/objc-dump.swift` (`objc_copyClassNamesForImage`) | `SimDeviceLegacyHIDClient`의 `initWithDevice:sessionResetQueue:error:sessionResetHandler:` |
| Swift API (ObjC에 안 보이는 것) | `nm` + `xcrun swift-demangle` (`scripts/macho-tools.py symbols`) | `SimDeviceScreen.register(types:queue:handler:)`, `IndigoDigitizerEvent.init(pointOne:pointTwo:eventType:edge:target:)` |
| Swift 구조체 필드·CodingKeys | `__swift5_reflstr` 구역 (`macho-tools.py fields`), `strings` | dtuhidd의 `pointOne pointTwo eventType edge target` |
| 함수 안에서 무엇을 부르나·어떤 값을 넘기나 | 역어셈블 (`macho-tools.py calls/disasm`, lldb) | Device Hub 터치 처리 → `IndigoHIDMessageForMouseNSEvent` |
| 원격 객체(ROCK)의 메서드·블록 형식 | `_protocol_getMethodTypeEncoding` (`scripts/sim-probe.swift`) | `@?<v@?@"IOSurface"@"IOSurface">` |
| 시뮬레이터 안에서 실제로 무슨 일이 일어나나 | 시뮬레이터 안 로그 (`simctl spawn … log stream`) | backboardd `ignoring digitizer event … from unsupported service` |
| 왜 죽었나 | 충돌 보고서 `~/Library/Logs/DiagnosticReports/*.ips` | `-[SimHIDVirtualServiceManager serviceForIndigoHIDData:]` assert |
| 시뮬레이터 안 프로세스의 실제 파일 | `ps` (기기별 `launchd_sim`의 자식) + `lsof -p <pid>` | dtuhidd = `CoreSimulator.framework/…/Platforms/iphoneos/usr/libexec/dtuhidd` |
| 시뮬레이터 안 XPC 서비스에 말 걸기 | `-[SimDevice lookup:error:]` + `xpc_endpoint_create_mach_port_4sim` | dtuhidd `…remote.hid.digitizer`에 연결 |
| 디버거로 붙을 수 있나 | `codesign -dv` (hardened runtime 여부), `csrutil status` | dtuhidd는 hardened가 아니지만 Apple 서명이라 SIP가 붙기를 막음 |

## 1. 부품 찾기

```bash
# Xcode 안 비공개 부품
find "$(xcode-select -p)/.." -maxdepth 3 -name "*.framework" | grep -i -E "simul|devicekit"
ls /Library/Developer/PrivateFrameworks/            # CoreSimulator·CoreDevice·CoreDeviceUtilities …

# 무엇에 기대나 (바이너리 이름은 버전 폴더 안 실제 파일로)
otool -L "$(xcode-select -p)/../SharedFrameworks/SimulatorKit.framework/Versions/A/SimulatorKit"

# 실행 중인 앱이 실제로 불러온 부품 (Device Hub처럼 플러그인으로 나중에 불러오는 것까지)
vmmap $(pgrep -f "DeviceHub.app/Contents/MacOS/DeviceHub") | grep -E "SimulatorKit|CoreSimulator|DeviceKit" | awk '{print $NF}' | sort -u
```

시뮬레이터 안 프로세스도 Mac의 프로세스입니다. 기기마다 `launchd_sim`이 있고 그 자식이 기기 안 프로세스입니다.

```bash
LS=$(ps -ax -o pid,command | grep "[l]aunchd_sim" | grep <UDID> | awk '{print $1}')
ps -ax -o pid,ppid,command | awk -v p=$LS '$2==p'                 # 그 기기의 프로세스
lsof -p <pid> | awk '$4=="txt"{print $NF}' | head -3              # 실제 실행 파일 (ps는 /usr/libexec/dtuhidd처럼 기기 안 경로만 보여 줌)
```

## 2. Objective-C 런타임으로 보기

```bash
swift scripts/objc-dump.swift <바이너리>                    # 클래스 목록
swift scripts/objc-dump.swift <바이너리> 'LegacyHIDClient'  # 메서드(+/-), 형식 문자열, 변수
```

- 형식 문자열 읽기: `@` 객체, `@?` 블록, `^@` `NSError**`, `B` Bool, `I`/`Q` 정수, `d` Double, `{CGPoint=dd}` 구조체. 예: `initWithDevice:sessionResetQueue:error:sessionResetHandler:  @48@0:8@16@24^@32@?40`.
- Swift 클래스는 런타임 이름이 맹글링돼 있다: `_TtC12SimulatorKit24SimDeviceLegacyHIDClient` (`NSClassFromString`에 이 이름을 쓴다).
- Swift 클래스의 메서드는 `@objc`인 것만 보인다. 나머지는 3번으로.

## 3. Swift 심볼 풀기

```bash
nm <바이너리> | awk '{print $NF}' | xcrun swift-demangle --simplified | grep SimDeviceScreen
python3 scripts/macho-tools.py symbols <바이너리> 'IndigoDigitizerEvent'     # 주소까지
```

읽는 요령:

| 보이는 것 | 뜻 |
|---|---|
| `enum case for DigitizerTarget.mainScreen(_:)` | 열거형의 경우 (이름 순으로 나오니 선언 순서는 따로 확인) |
| `X.y.getter` · `property descriptor for X.y` | 속성 |
| `X.init(a:b:)` | 생성자와 인자 이름 |
| `dispatch thunk of …` · `method descriptor for …` | 바깥에 열린 메서드 (실제 구현은 이름이 지워져 있을 수 있음) |
| `…CodingKeys33_<해시>LLO` | 직접 선언한 Codable 키 → 키 문자열은 `strings`로 (아래) |
| `_$s10CoreDevice15DigitizerTargetO8rawValueSuvg` | `Su` = UInt 원시값 |

바이너리 안 문자열로 Swift 안쪽이 부르는 ObjC 메서드를 찾을 수 있습니다. SimulatorKit의 `SimDeviceScreen`이 CoreSimulator의 `registerScreenCallbacksWithUUID:…frameCallback:…`를 부른다는 것을 이렇게 알았습니다.

```bash
strings -a <바이너리> | grep -E "register.*Callbacks|IndigoHID"
strings -a <CoreDeviceUtilities> | grep -n -A6 "^pointOne$"      # CodingKeys 문자열은 보통 한데 모여 있다
```

## 4. Swift 필드 이름 (리플렉션)

Swift 구조체·클래스의 속성 이름은 `__TEXT,__swift5_reflstr` 구역에 남습니다. 메시지 구조를 짐작할 때 씁니다.

```bash
python3 scripts/macho-tools.py fields <바이너리>
```

`otool -s __TEXT __swift5_reflstr`로 바로 보면 4바이트씩 뒤집혀 나오므로, 구역 위치(`otool -l`)를 찾아 파일에서 그대로 읽어야 합니다(스크립트가 그렇게 함).

## 5. 역어셈블

Swift 함수는 `otool -tV` 출력에 이름표가 없어서 **주소로** 찾습니다.

```bash
python3 scripts/macho-tools.py calls  <바이너리> 'LegacyHIDClient\.simDigitizerInputView\(_:touchEvent'   # 부르는 것만
python3 scripts/macho-tools.py disasm <바이너리> 0x189c0 120                                              # 전체
# 같은 일을 lldb로 (프로세스에 붙지 않고 파일만 연다)
lldb --batch -o "target create --arch arm64e <바이너리>" -o "disassemble -s 0x189c0 -c 80"
```

arm64 읽는 요령:

| 보이는 것 | 뜻 |
|---|---|
| 인자 `x0`~`x7`, 실수 인자 `d0`~`d7` | C 호출 규약. 정수와 실수는 따로 센다 — `IndigoHIDMessageForMouseNSEvent(점1, 점2, 목적지, 종류, 가장자리, 크기)`의 크기(CGSize)는 `d0`·`d1` |
| Swift: `x20` = self, `x8` = 간접 반환 주소 | 구조체를 돌려주는 함수는 `x8`이 가리키는 곳에 쓴다 |
| `bl _심볼` / `; symbol stub for: _x` | 이름 있는 호출 (가져온 함수면 stub) |
| `blraa x9, x17` | 프로토콜 증인 테이블·vtable을 통한 간접 호출 (무엇인지는 앞에서 어떤 표를 읽는지로 추적) |
| `ldr x0, [x20, #0x28]` + `ret` | 속성 getter → 그 필드의 위치 (TouchEvent: 0x00 touch1, 0x10 touch2, 0x20 손가락 수, 0x21 phase, 0x28 type, 0x30 edge) |
| `cmp x0, #N` + `csel` + `strb` | 열거형 `init(rawValue:)` → 원시값 0~N-1 (N이 nil 표시) |
| `str w19, [x21, #0x6c]` | 메시지 구조체의 어느 위치에 무엇을 쓰나 (Indigo 메시지의 목적지 = 0x6c, 두 번째 묶음 0x10c) |
| `mov w8, #0x33` 분기 | 상수 (SimDeviceScreen.buttonTarget: 내장 화면 0x33) |

이 방법으로 알아낸 것:
- Device Hub의 터치 처리(`SimDeviceLegacyHIDClient.simDigitizerInputView(_:touchEvent:)`)는 `IndigoHIDMessageForMouseNSEvent`를 부르고, 목적지는 화면 뷰(디지타이저 호스트)에서 받아 온다.
- `IndigoHIDMessageForMouseNSEvent`는 NSEvent 종류(누름 1·뗌 2·끌기 6)와 가장자리 0~4를 받고, 목적지를 0x6c에 쓴다 → simtouch와 형식이 같다는 것을 확인.

## 6. 원격 객체의 메서드와 블록 형식

CoreSimulator가 돌려주는 기기·포트 객체는 다른 프로세스로 호출을 넘기는 대리 객체(ROCK)라 메서드가 클래스가 아니라 **프로토콜에만** 보입니다. 블록 인자 형식은 런타임 함수 `_protocol_getMethodTypeEncoding`(확장 형식)으로 봅니다.

```bash
swift scripts/sim-probe.swift <UDID>              # 포트 · 프로토콜 · 블록 형식
swift scripts/sim-probe.swift <UDID> --frames 5   # 프레임 콜백이 오는지
```

콜백은 **메인 런루프가 돌아야** 들어옵니다. 메인 스레드를 루프로 막은 시험 프로그램에서는 콜백이 0번이었습니다.

## 7. 시뮬레이터 안 로그

가장 많이 쓴 방법입니다. 시뮬레이터 안 프로세스의 로그는 기기마다 따로 쌓입니다.

```bash
# 실시간 (터치가 어디까지 가는지)
xcrun simctl spawn <UDID> log stream --style compact --level debug \
  --predicate '(process == "backboardd" AND (category == "TouchEvents" OR category == "HID")) OR process == "dtuhidd"'
# 지난 기록 (부팅마다 무엇이 만들어졌나 — 기기 로그는 재부팅을 넘어 남는다)
xcrun simctl spawn <UDID> log show --last 30h --style compact --predicate 'process == "dtuhidd" AND eventMessage CONTAINS "mainTouchscreen"'
```

- **zsh에는 `log`라는 내장 명령이 있다.** Mac 쪽 로그는 `/usr/bin/log`로 불러야 한다 (그냥 `log show`는 조용히 아무것도 안 나옴).
- 터치 문제에서 본 기록: `new contact` · `Digitizer token … down` (전달됨), `ignoring digitizer event for display <main> from unsupported service` (버려짐), `service mainTouchscreen(0x101), report type identifier 9` (Device Hub 경로), `*** already have a main display digitizer` (본 화면 소유권).
- 비교할 때는 같은 술어로 두 경우를 각각 실시간으로 받는다. 지난 기록은 재부팅·재시작으로 pid가 섞여 헷갈린다.

## 8. 충돌 보고서

```bash
ls -t ~/Library/Logs/DiagnosticReports/ | grep -E "backboardd|dtuhidd" | head
python3 - <<'EOF' ~/Library/Logs/DiagnosticReports/<파일>.ips
import json, sys
d = json.loads(open(sys.argv[1]).read().partition('\n')[2])
th = d["threads"][d.get("faultingThread", 0)]; imgs = d["usedImages"]
for f in th["frames"][:14]:
    print(imgs[f["imageIndex"]].get("name"), f.get("symbol"))
EOF
```

목적지 0x101로 보낸 메시지가 backboardd 안 `SimulatorHID`의 `serviceForIndigoHIDData:` assert로 죽은 것을 보고 "simtouch 메시지는 backboardd의 옛 경로로 간다"는 것을 알았습니다.

## 9. 시뮬레이터 안 XPC 서비스에 직접 말 걸기

```swift
// 1) 기기 안 서비스 이름 → mach 포트
typealias Lookup = @convention(c) (AnyObject, Selector, NSString, UnsafeMutablePointer<NSError?>) -> UInt32
let sel = NSSelectorFromString("lookup:error:")
let port = unsafeBitCast(device.method(for: sel), to: Lookup.self)(device, sel, "com.apple.coredevice.feature.remote.hid.digitizer", &err)
// 2) 포트 → endpoint (시뮬레이터용 비공개 libxpc 함수) → 연결
typealias MkEndpoint = @convention(c) (UInt32) -> xpc_endpoint_t?
let mk = unsafeBitCast(dlsym(UnsafeMutableRawPointer(bitPattern: -2), "xpc_endpoint_create_mach_port_4sim")!, to: MkEndpoint.self)
let conn = xpc_connection_create_from_endpoint(mk(port)!)
```

- 어떤 이름을 듣는지는 그 프로세스의 시작 로그에 나온다: `activating connection: mach=true listener=true … name=com.apple.coredevice.feature.remote.hid.digitizer`.
- libxpc가 내보내는 함수는 `dyld_info -exports /usr/lib/system/libxpc.dylib | grep endpoint`로 찾았다.
- 상대가 Mercury(Swift XPC 메시징, 타입 이름으로 처리기를 고름)를 쓰면, 형식이 틀린 메시지는 오류 없이 버려진다. 이번에는 봉투 형식을 맞추지 못했다 ([비공개 API](private-apis.md) "dtuhidd 새 경로").

## 10. 디버거

```bash
codesign -dv --verbose=4 <바이너리> 2>&1 | grep flags     # 0x10000(runtime)이면 hardened
csrutil status
```

dtuhidd는 hardened가 아니지만 Apple 서명이라 SIP가 켜진 Mac에서는 `lldb -p`가 거부됩니다(`Not allowed to attach to process`). 이럴 때는 로그(7)·충돌 보고서(8)·정적 분석(3~5)으로 대신합니다. 파일만 여는 lldb 역어셈블은 언제나 됩니다.

## 11. 화면이 필요한 대조 실험 (Device Hub)

- Device Hub 창은 접근성 API에 잡히지 않는다(창 0개). 목록을 고르려면 마우스 클릭 이벤트(CGEvent)를 쓴다 — 먼저 `osascript -e 'tell application id "com.apple.dt.Devices" to activate'`로 앞으로 가져오고, 화면을 찍어 좌표를 확인한 뒤 누른다.
- 화면 좌표는 포인트 단위 (이 Mac: 1680×1050pt). 스크린샷을 줄였다면 비율을 곱한다.
- 이미 떠 있는 Device Hub는 `-CurrentDeviceUDID` 실행 인자를 무시한다. **끄고 다시 켜면 시뮬레이터가 모두 꺼진다.**
- 기기가 꺼지면 목록 순서가 바뀐다 → 누르기 전에 매번 화면으로 확인.

## 12. 판정

```bash
Tools/simscreen/.build/simscreen <UDID> --width 300 --once before.jpg   # 화면 한 장 (실시간 화면 도구)
```

- 앱을 켠 뒤에는 **크기가 두 번 연속 같아질 때까지** 기다린다 (설정 앱 첫 실행은 6초 넘게 빈 화면).
- 크기 비교는 빠른 거름망일 뿐이다. 바뀌었다고 나오면 사진을 직접 본다.

## 사례: 이번에 이 방법으로 알아낸 것

| 질문 | 쓴 방법 | 답 |
|---|---|---|
| Simulator 앱은 새 장면을 어떻게 아나 | 3 (`SimDeviceScreen` 심볼), 3 (`strings`로 안쪽 호출), 6 | CoreSimulator `SimScreen`의 프레임 콜백 → simscreen에 직접 적용 (49→60fps) |
| Device Hub 터치는 왜 먹히고 simtouch는 안 먹히나 | 1 (`vmmap`), 5 (터치 처리 역어셈블), 7 (기기 안 로그), 8 (충돌 보고서) | 받는 곳이 둘(SimulatorHID·dtuhidd), 부팅마다 갈림 |
| dtuhidd에 직접 넣을 수 있나 | 1 (`lsof`), 4 (필드 이름), 3 (CoreDeviceUtilities 타입), 9 (XPC 연결), 10 | 연결은 됨, Mercury 형식·본 화면 소유권에서 막힘 |
