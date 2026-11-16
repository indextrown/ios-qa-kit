# 비공개 API: 시뮬레이터 화면을 읽고, 손가락처럼 누르기

qakit은 시뮬레이터 화면을 실시간 영상으로 보여 주고(라이브 세션·AI 탭), 좌표로 손가락처럼 누르기(AI QA 직접 터치) 위해 Apple이 공개하지 않은 부품을 씁니다.
이 문서는 **무엇을, 왜, 어떻게** 부르는지와, Xcode가 바뀌어 깨졌을 때 **직접 조사하는 법**을 정리합니다.

[← README](../README.md) · 실시간 화면의 흐름만 짧게 보려면 [live-screen.md](live-screen.md)

> 확인한 환경: macOS 27.0.1 · Xcode 27.0 (27A266a) · iOS 27.0 시뮬레이터 (24A434) · CoreSimulator 1171.7 (2026-11-16)

## 한눈에

| 기능 | 도구 | 비공개 부품 | 핵심 호출 | 안 되면 |
|---|---|---|---|---|
| 실시간 화면 (라이브 세션·AI 탭) | `Tools/simscreen` | CoreSimulator | 화면 포트의 IOSurface + **프레임 콜백** | seed 폴링 → 스크린샷 방식 |
| AI 문제 보고 영상 | `simscreen --encode` | (화면 읽기는 위와 같음) 인코딩은 공개 AVFoundation | `AVAssetWriter` H.264 | 영상 없이 보고 |
| 녹화 버튼·실패 영상 | `simctl io recordVideo` | 공개 명령 (안쪽은 CoreSimulator `SimScreenCaptureService`) | — | — |
| 직접 터치 (좌표 탭·끌기·길게 누르기) | `Tools/simtouch` | SimulatorKit + IOKit SPI | `SimDeviceLegacyHIDClient` + Indigo HID 메시지 | XCUITest 탭 |
| 자동 ID (AutoID) | `AutoID/` dylib | 비공개 API는 아님 — **공식 지원 밖 방법** | `DYLD_INSERT_LIBRARIES` + 메서드 바꿔치기 | `autoid: embedded` |

- **비공개 API**: 헤더(공개 설명서)가 없는 함수·클래스. 이름으로 찾아 부른다. Xcode가 바뀌면 이름·형식이 바뀔 수 있다.
- 모두 **개발 도구 안에서만** 쓴다. 테스트하는 앱에는 들어가지 않는다 (AutoID는 QA 빌드를 시뮬레이터에서 켤 때만 주입).

## 왜 비공개 API인가

| 하고 싶은 것 | 공개 방법 | 한계 | qakit |
|---|---|---|---|
| 화면을 영상처럼 보기 | `simctl io screenshot` | 한 장 0.4~0.6초 → 초당 약 2장 | 화면 메모리를 바로 읽어 **초당 60장** |
| 화면 녹화 | `simctl io recordVideo` | 파일로만 저장, 실시간으로 못 봄 | 녹화는 이걸 그대로 쓰고, 실시간은 따로 |
| 좌표로 누르기·끌기 | XCUITest `coordinate(…).tap()` | 실행기를 거쳐 수백 ms, XCUITest가 앱을 붙잡고 있어야 함 | HID 신호를 바로 넣어 **한 번에 약 90ms** |

그래서 비공개 API를 쓰되, **언제나 공개 방법으로 돌아갈 길**을 둡니다 (아래 [위험과 대비](#위험과-대비)).

## 부품 위치 (Xcode 27)

| 부품 | 위치 | 쓰는 도구 |
|---|---|---|
| CoreSimulator | `/Library/Developer/PrivateFrameworks/CoreSimulator.framework` (Xcode가 설치. `simctl`도 이걸 씀) | simscreen, simtouch |
| SimulatorKit | `Xcode.app/Contents/SharedFrameworks/SimulatorKit.framework` (이전 Xcode: `Xcode.app/Contents/Developer/Library/PrivateFrameworks/`) | simtouch (두 곳 다 찾음) |
| IOKit의 HID 이벤트 함수 | `IOKit.framework` (공개 부품이지만 `IOHIDEvent…` 함수는 macOS SDK 헤더에 없음 = SPI) | simtouch |

## 헤더 없이 부르는 법 (공통)

헤더가 없으니 Objective-C 런타임에 **이름(문자열)** 으로 물어서 부릅니다.

```swift
dlopen("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/CoreSimulator", RTLD_NOW)   // 부품 열기
let cls = NSClassFromString("SimServiceContext")            // 클래스 이름으로
let sel = NSSelectorFromString("defaultDeviceSetWithError:") // 메서드 이름으로
obj.perform(NSSelectorFromString("io"))                     // 인자 없는 메서드
obj.value(forKey: "devices")                                // 속성
```

인자가 여러 개이거나 `NSError**`·블록·C 구조체가 있으면 `objc_msgSend`를 **정확한 C 함수 형식**으로 바꿔 부릅니다.

```swift
// -registerScreenCallbacksWithUUID:callbackQueue:frameCallback:surfacesChangedCallback:propertiesChangedCallback:
typealias Register = @convention(c) (AnyObject, Selector, NSUUID, DispatchQueue, AnyObject, AnyObject, AnyObject) -> Void
let msgSend = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "objc_msgSend")!   // -2 = RTLD_DEFAULT
let onFrame: @convention(block) () -> Void = { /* 새 장면 */ }                    // 블록은 @convention(block)
unsafeBitCast(msgSend, to: Register.self)(screen, sel, NSUUID(), queue, onFrame as AnyObject, onSurfaces as AnyObject, onProps as AnyObject)
```

- **형식이 하나라도 틀리면 바로 죽습니다.** arm64는 정수·객체와 실수(`Double`·`CGPoint`)를 다른 레지스터로 넘기므로 형식이 정확해야 합니다. 형식은 아래 [조사하는 법](#xcode가-바뀌면-조사하는-법)으로 확인합니다.
- `NSError**` 인자는 `UnsafeMutablePointer<NSError?>`로 넘깁니다 (`callWithError` 함수).

### 원격 객체 (ROCK)

시뮬레이터 기기는 내 프로세스가 아니라 **CoreSimulatorService**(백그라운드 서비스)에 있습니다. 내가 받는 객체는 그 서비스로 호출을 전달하는 대리 객체입니다.

```
내 프로세스                                 CoreSimulatorService
ROCKRemoteProxy-…-SimScreen-…  ── XPC ──▶  진짜 화면 객체
```

| 특징 | 결과 |
|---|---|
| 클래스 이름에 프로토콜 목록이 붙어 있다 (`ROCKRemoteProxy-<UUID>-SimScreen-SimDisplayIOSurfaceRenderable-…`) | 무슨 기능이 있는지 이름만 봐도 대강 안다 |
| 메서드가 클래스 메서드 목록에 없고 **프로토콜에만** 있다 | `class_copyMethodList` 대신 `class_copyProtocolList` + `protocol_copyMethodDescriptionList`로 본다. `responds(to:)`는 된다 |
| 호출은 서비스에 다녀오는 왕복 | 한 번에 수 ms (포트 목록 + 화면 메모리 찾기 6~10ms) → 자주 부르지 않는다 |
| **콜백은 메인 런루프로 들어온다** | 콜백을 받는 프로그램은 메인 스레드에서 `RunLoop.main.run()`을 돌려야 한다. 메인 스레드를 루프로 막아 두면 콜백이 **한 번도 오지 않는다** (실측) |

## 1. 기기와 입출력 포트 (CoreSimulator)

```text
SimServiceContext.sharedServiceContextForDeveloperDir:error:   (xcode-select -p)
  └ defaultDeviceSetWithError:
      └ devices → UDID가 같은 SimDevice
          └ io (SimDeviceIOClient)
              └ updateIOPorts → ioPorts → 포트마다 portIdentifier · descriptor
```

iPhone 17 시뮬레이터의 포트 (Xcode 27, `swift scripts/sim-probe.swift <udid>`로 출력):

| 포트 | 개수 | descriptor의 프로토콜 | 쓸모 |
|---|---|---|---|
| `com.apple.framebuffer.display` | 4 (**본 화면만 IOSurface 있음**, 나머지는 외부·CarPlay 화면 자리) | `SimScreen`, `SimDisplayIOSurfaceRenderable`, `SimDisplayRenderable`, `SimDisplayResizeableRenderable` | **실시간 화면** |
| `com.apple.framebuffer.server` | 1 | `SimScreenAdapter` | 화면 목록·연결·해제 이벤트, 외부 화면 만들기 |
| `com.apple.display.captureservice` | 1 | `SimScreenCaptureService` | 녹화·스크린샷 (`simctl io`의 본체) |
| `com.apple.CoreSimulator.HID.LegacyHID` | 1 | `SimLegacyHIDDescriptor` (`legacyHIDEventPort` — XPC 포트) | 터치·키 입력 통로 (simtouch는 SimulatorKit을 거쳐 씀) |
| `com.apple.SimStreamProcessor.default` | 3 | `SimStreamProcessorProgramInterface` | 시뮬레이터의 그래픽 처리 (안 씀) |
| `com.apple.accelerator.metal` · `…iosurface` | 각 1 | `SimAcceleratorMetalDevice` 등 | 시뮬레이터 GPU (안 씀) |
| `com.apple.CoreSimulator.Audio.HostRoute`, `com.apple.gputools.*` | | | 소리, GPU 도구 (안 씀) |

### 화면 관련 프로토콜 (런타임에서 읽은 형식)

`@?<v@?@"IOSurface"@"IOSurface">`는 "IOSurface 두 개를 받는 블록"이라는 뜻입니다 (확장 형식, [조사하는 법](#xcode가-바뀌면-조사하는-법) 5번).

| 프로토콜 | 메서드 | 형식 (요약) |
|---|---|---|
| **SimScreen** | `registerScreenCallbacksWithUUID:callbackQueue:frameCallback:surfacesChangedCallback:propertiesChangedCallback:` | `(NSUUID, dispatch_queue, void(^)(void), void(^)(IOSurface, IOSurface), void(^)(id<SimScreenProperties>))` |
| | `unregisterScreenCallbacksWithUUID:` | `(NSUUID)` |
| | `screenProperties` · `setPowerState:…` · `setCurrentMode:pixelSize:carPlayProperties:…` | |
| SimDisplayIOSurfaceRenderable | `framebufferSurface` · `maskedFramebufferSurface` | `→ IOSurface` (화면 메모리 / 모서리를 깎은 것) |
| | `registerCallbackWithUUID:ioSurfacesChangeCallback:` | `void(^)(IOSurface, IOSurface)` |
| SimDisplayRenderable | `registerCallbackWithUUID:damageRectanglesCallback:` | `void(^)(NSArray)` — 바뀐 영역 |
| | `displaySize` · `displayPitch` · `displaySizeInBytes` | |
| SimScreenAdapter | `enumerateScreensWithCompletionQueue:completionHandler:` | `void(^)(NSArray, NSError)` |
| | `registerScreenAdapterCallbacksWithUUID:callbackQueue:screenConnectedCallback:screenWillDisconnectCallback:` | `void(^)(id<SimScreen>)`, `void(^)(uint32 화면ID)` |
| SimScreenCaptureService | `startRecordingFromScreen:maskPolicy:assetWriterOutputSettings:outputFile:completionQueue:completionHandler:` | 파일로 녹화 |
| | `captureScreenshotFromScreen:maskPolicy:imageType:outputFile:completionQueue:completionHandler:` | 파일로 스크린샷 |

## 2. 화면 메모리를 읽어 영상으로 만들기 (simscreen)

시뮬레이터는 기기 화면을 Mac의 **공유 메모리(IOSurface)** 에 그립니다. qakit은 이 메모리를 복사하지 않고 그대로 읽어 영상으로 만듭니다.

```
① 화면 메모리 잡기     본 화면 포트의 framebufferSurface → IOSurface (1206×2622, BGRA — 기기 픽셀 그대로)
        │
② 새 장면 알림         SimScreen 프레임 콜백 (시뮬레이터가 한 장을 다 그리면 부름. 안 바뀌면 안 옴)
        │
③ 줄이고 JPEG          IOSurface를 복사 없이 CVPixelBuffer로 감쌈 → VTPixelTransfer(GPU)로 900px
        │               → VideoToolbox 하드웨어 JPEG (한 장 약 7ms, 약 200KB)
④ 보내기               stdout: [4바이트 길이][JPEG] 반복
        │
⑤ qakit ui 서버(Python) 최신 한 장을 보관 → /api/stream (MJPEG: multipart/x-mixed-replace)
        │
⑥ 브라우저 <img>        받는 대로 그림 = 영상
```

### ① 화면 메모리 잡기

- 포트 `com.apple.framebuffer.display` 중 `framebufferSurface`가 있는 것(여럿이면 가장 큰 것)이 본 화면입니다.
- **IOSurface**: 여러 프로세스가 함께 쓰는 그림 메모리. 시뮬레이터가 지금 그리고 있는 바로 그 메모리라서 읽을 때마다 최신 화면입니다.
- **seed**: IOSurface가 바뀔 때마다 오르는 번호. 같으면 화면이 그대로입니다.
- 원격 객체는 부를 때마다 새로 만들어지므로, 같은 화면인지는 객체가 아니라 **IOSurface ID**(`IOSurfaceGetID`)로 비교합니다. 기기를 재시작하면 ID가 바뀝니다.

### ② 새 장면 알림 — 프레임 콜백

| | 프레임 콜백 (지금) | seed 폴링 (예전, 대비용) |
|---|---|---|
| 방법 | 시뮬레이터가 새 장면을 다 그리면 불러 줌 | 1/60초마다 seed가 바뀌었나 확인 |
| 박자 | 시뮬레이터가 그리는 박자 그대로 | 내 박자 — 화면 박자와 어긋나 장면을 건너뜀 |
| 측정 (쉬지 않는 60Hz 애니메이션 10초) | **597장, 간격 16.6ms(중앙) · 18ms(90%) · 21ms(99%)** | 486~492장, 20.5ms · 23ms · 25ms |

- Simulator 앱도 같은 콜백을 씁니다: SimulatorKit의 `SimDeviceScreen.register(types:queue:handler:)`가 안에서 이 호출을 합니다 ([3. SimulatorKit](#3-simulatorkit-안을-보면)). qakit은 SimulatorKit 없이 CoreSimulator에 직접 등록합니다.
- 콜백은 화면 메모리가 바뀐 **직후**에 옵니다 (측정: 중앙 0.4ms). 가끔 바뀌기 전에(최대 4ms) 오므로, seed가 그대로면 1ms씩 최대 8ms 더 봅니다.
- 화면이 안 바뀌면 콜백이 오지 않습니다 (vsync처럼 계속 오지 않음). 새로 붙은 브라우저를 위해 2초마다 한 장은 그냥 보냅니다.
- 등록 직후 `surfacesChangedCallback`이 한 번 옵니다 (정상). 회전 등으로 메모리가 바뀌면 다시 옵니다 → 화면을 다시 잡습니다.
- `damageRectanglesCallback`(바뀐 영역)도 있지만, 줄여서 통째로 보내는 지금 방식에는 필요 없습니다.

구조 — 메인 스레드는 콜백만 받고, 인코딩은 따로:

```text
메인 스레드          RunLoop.main.run()  ← 콜백이 들어오는 곳
콜백 큐              frameCallback → "새 장면" 표시 + 인코딩 스레드 깨우기
인코딩 스레드        깨면: seed 확인 → (상한 60fps) → ③④ → 다시 기다림 (0.25초마다 한 번은 깨서 2초 알림·끊김 확인)
                     3초마다 화면 포트 확인 → IOSurface ID가 바뀌었으면(기기 재시작) 새 화면을 잡고 콜백 다시 등록
```

- 상한(60fps)은 장면을 **만들기 시작한 시각**으로 잽니다. 끝난 시각으로 재면 간격이 인코딩 시간만큼 늘어 40fps대로 떨어집니다 (실측 24ms 간격).
- 콜백 없이 화면이 바뀌는 일이 세 번 쌓이면(끊김) seed 폴링으로 내려갑니다. `SIMSCREEN_POLL=1`이면 처음부터 폴링.

### ③ 줄이고 JPEG — 하드웨어

| 방법 | 900px 한 장 | CPU (계속 바뀔 때) |
|---|---|---|
| **VideoToolbox** (지금): `CVPixelBufferCreateWithIOSurface`(복사 없이 감쌈) → `VTPixelTransferSession`(GPU 축소) → `VTCompressionSession`(`kCMVideoCodecType_JPEG`, 미디어 엔진) | 약 7ms | 약 12% |
| CoreGraphics + ImageIO (대비용, `SIMSCREEN_NO_HW=1`) | 약 24ms | 약 84% |

VideoToolbox·CoreGraphics는 **공개 API**입니다. 비공개는 ①②뿐입니다.

### ④⑤⑥ 보내기

- simscreen → Python 서버: stdout에 `[4바이트 big-endian 길이][JPEG]`를 이어 씁니다. 준비되면 stderr에 `ready 1206x2622 callback`(또는 `poll`).
- 서버는 최신 한 장만 들고 있다가 보는 브라우저 모두에게 `multipart/x-mixed-replace; boundary=qakitframe`로 보냅니다. 느린 브라우저는 장면을 건너뛰고 최신 것을 받습니다.
- WebKit(맥 앱 창·Safari)은 화면에서 빠진 `<img>`의 스트림을 끊지 않아 연결이 쌓입니다 → 웹 UI가 빠질 때 직접 끊고(`StreamImg`), 서버는 스트림을 최근 3개만 둡니다.
- 측정: 서버를 거쳐 15초에 881장(약 59fps). CPU(10초): Python 서버 0.18초(1.8%) · simscreen 1.33초(13%).

### 영상 파일 두 가지

| 영상 | 만드는 법 | 공개 여부 |
|---|---|---|
| **AI 문제 보고 영상** (`report_issue`) | AI 세션 동안 simscreen을 `--fps 10 --width 440`으로 띄워 마지막 30초 장면을 메모리에(`FrameRing`) → 보고할 때 `simscreen --encode out.mp4`에 `[8바이트 시각][4바이트 길이][JPEG]…`를 넣으면 `AVAssetWriter`로 H.264 mp4. 장면 시각을 그대로 써서 간격이 고르지 않아도 재생 속도가 맞고, 마지막 장면을 0.5초 더 보여 줌 | 화면 읽기는 비공개, 인코딩은 공개 |
| **녹화 버튼·시나리오 실패 영상** | `xcrun simctl io <udid> recordVideo --codec=h264 --force out.mp4` → 멈출 때 SIGINT | 공개 명령 (안쪽은 `SimScreenCaptureService.startRecordingFromScreen:…`) |

## 3. SimulatorKit 안을 보면

`SimulatorKit.framework`(1MB, Swift + Objective-C, arm64e)는 Simulator 앱의 화면·입력 부품입니다.

| 찾은 것 | 내용 |
|---|---|
| ObjC로 보이는 클래스 39개 | `SimDeviceScreen`, `SimDeviceScreenAdapter`, `SimDisplayRenderableView`, `SimDisplayView`, `SimDeviceLegacyHIDClient`, `SimHIDCaptureManager`, `SimDigitizerInputView`, `SimKeyboardInputController` … |
| `SimDeviceScreen` (Swift 전용 API) | `init(device:screenID:)`, `register(types:queue:handler:) -> Registration`, 이벤트 `ScreenEvent.frame / surfacesChanged / propertiesChanged / connected / disconnected`, 종류 `ScreenEventTypes.rendering / properties / lifecycle / all`, 속성 `unmaskedSurface` · `maskedSurface` · `pixelSize` · `scale` · `screen` |
| 안에서 부르는 것 | 바이너리 문자열에 `registerScreenCallbacksWithUUID:callbackQueue:frameCallback:…` · `registerScreenAdapterCallbacksWithUUID:…` → **CoreSimulator `SimScreen`·`SimScreenAdapter`를 감싼 것** |
| `SimDisplayRenderableView` | Simulator 창의 화면 뷰. 변수 `_screen` · `_screenEventToken` · `_frameCount` · `frameTimes` · `_fpsLabel` — 위 이벤트로 장면을 받아 그린다 |
| 입력 | `SimDeviceLegacyHIDClient` (Swift 클래스, 런타임 이름 `_TtC12SimulatorKit24SimDeviceLegacyHIDClient`), C 함수 `IndigoHIDMessageFor…` |

- Swift 전용 API는 모듈 정보가 없어 밖에서 부를 수 없습니다 (이름이 맹글링되고 ABI도 비공개). 그래서 **안쪽의 Objective-C 호출을 찾아 직접** 부릅니다.
- 화면은 SimulatorKit 없이 됩니다 → Xcode 27처럼 SimulatorKit 위치가 바뀌어도 실시간 화면은 영향이 없습니다 (tapflow #797은 이 변경으로 한때 깨짐).

## 4. 손가락처럼 누르기 (simtouch)

```text
SimDeviceLegacyHIDClient  alloc + initWithDevice:error:            (SimulatorKit, 기기의 HID 통로에 연결)
IOHIDEventCreateDigitizerEvent(…, x, y, …)                         (IOKit SPI: 손 전체)
IOHIDEventCreateDigitizerFingerEvent(…, x, y, …)                   (손가락 하나)
IOHIDEventAppendEvent(손, 손가락, 0)
IndigoHIDMessageForTrackpadEventFromHIDEventRef(손) → Indigo 메시지 (SimulatorKit C 함수)
메시지 0x6c(크기가 0x110 이상이면 0x10c도)에 UInt32 0x32   ← 경로 표시: 디지타이저로. 없으면 모든 터치가 무시됨
sendWithMessage:freeWhenDone:completionQueue:completion:          (보내기)
```

- 좌표는 화면 대비 0~1. 누름(contact 1, mask 0x07) → 이동 → 뗌(contact 0, mask 0x06).
- 디지타이저 함수가 없으면 `IndigoHIDMessageForMouseNSEvent`(마우스 방식)로.
- 연결 직후 첫 입력은 버려질 수 있어 0.25초 기다립니다.
- 상주(`TouchHelper`가 계속 띄워 둠)로 한 번에 약 90ms. 매번 새로 띄우면 부품 로딩 때문에 약 0.85초.
- **답이 `ok`여도 조용히 무시될 수 있습니다 — 부팅에 따라 다릅니다** (Xcode 27, 2026-11-16 조사):

  시뮬레이터 안에는 터치를 받는 곳이 둘 있습니다.

  | 받는 곳 | 누가 씀 | 기록에 남는 모습 |
  |---|---|---|
  | backboardd 안 **SimulatorHID** (옛 Indigo 경로) | simtouch | 내장 디지타이저 서비스 `eventSource: builtin; builtIn`이 생기고 터치 전달 ✅ |
  | **dtuhidd** (CoreDevice, Xcode 27의 새 경로) | Device Hub — 부팅 때 `mainTouchscreen(0x101)`·`touchscreen(0x104)`·`touchscreenGesture(0x501)` 서비스를 만들고 HID 보고서로 넣음 | `service mainTouchscreen(0x101), report type identifier 9` |

  simtouch의 메시지를 SimulatorHID가 직접 받으면 먹히고, dtuhidd로 넘기면 CoreDevice 트랙패드류 서비스(`eventSource: trackpad / externalAccessory`)에서 온 것이 되어 backboardd가 `ignoring digitizer event for display <main> from unsupported service`로 버립니다. **어느 쪽이 되는지가 부팅마다 달랐습니다:**

  | 기기 · 부팅 | simtouch |
  |---|---|
  | 시험용 기기 1차 부팅 (`simctl`, 만든 직후) — 실시간 화면 연결·Device Hub 표시·Device Hub 마우스 클릭 뒤에도 | ❌ |
  | 같은 기기 2차 부팅 (Device Hub Start) | ✅ 설정 → 일반 |
  | 같은 기기 3차 부팅 (`simctl boot`) | ✅ |
  | 공용 기기 11-15 20:41 부팅 / **11-16 00:49 부팅(그날 내내, AI 직접 터치 H3·H4)** / 23:19 부팅 | ❌ / ✅ / ❌ |

  그래서 원인은 "XCUITest가 켠 앱", "새 기기", "Device Hub에 안 띄움", "`simctl boot`"가 **아닙니다.** 부팅 때 SimulatorHID와 dtuhidd 중 어느 쪽이 디지타이저를 맡느냐가 갈리는 것으로 보입니다(무엇이 가르는지는 미확인). 다시 켜서 된 적이 여러 번 있습니다.

  확인한 메시지 형식 (`IndigoHIDMessageForMouseNSEvent`·`…TrackpadEventFromHIDEventRef` 역어셈블): 목적지(target)는 메시지 0x6c(두 번째 묶음 0x10c), 이벤트 종류는 NSEvent 값(누름 1·뗌 2·끌기 6), 가장자리 0~4. Device Hub의 입력 뷰 처리(`SimDeviceLegacyHIDClient.simDigitizerInputView(_:touchEvent:)`)도 같은 함수를 부르고, 목적지는 화면 뷰가 정한다. **모르는 목적지(예: 0x101)를 보내면 SimulatorHID가 assert로 죽어 backboardd가 다시 시작한다** — 공용 기기에서는 절대 시험하지 말 것.

  보는 법 (시뮬레이터 안 로그, zsh에선 `log`가 내장 명령이라 `/usr/bin/log` 또는 `simctl spawn … log`):

  ```bash
  xcrun simctl spawn <udid> log stream --level debug --predicate '(process == "backboardd" AND (category == "TouchEvents" OR category == "HID")) OR process == "dtuhidd"'
  ```

- **dtuhidd 새 경로로 직접 넣기 — 시도했으나 보류** (2026-11-17):

  | 단계 | 결과 |
  |---|---|
  | 연결 | ✅ `-[SimDevice lookup:error:]`("com.apple.coredevice.feature.remote.hid.digitizer") → mach 포트 → `xpc_endpoint_create_mach_port_4sim` → `xpc_connection_create_from_endpoint`. dtuhidd의 IndigoHIDServer가 상대로 받아들이고, **연결마다 따로** 가상 서비스(`mainTouchscreen(0x101)`·`touchscreen(0x104)`·`touchscreenGesture(0x501)`·`mainKeyboard(0x200)`·`mainScreenButtons(0x402)`)를 만든다 |
  | 메시지 타입 | CoreDeviceUtilities의 `IndigoDigitizerEvent(pointOne:pointTwo:eventType:edge:target:)` — 키 `pointOne`·`pointTwo`·`eventType`·`edge`·`target`, `DigitizerPoint(x:y:)`, 원시값은 모두 `UInt`: `DigitizerEventType` 0~2(start·position·end), `DigitizerEdge` 0~4(none…), `DigitizerTarget` 0~10(mainScreen, display1~10). Mercury(Swift XPC 메시징)가 `mangledTypeName`(`19CoreDeviceUtilities20IndigoDigitizerEventV`)으로 처리기를 고른다 |
  | 봉투 | ❌ `{mangledTypeName, value}`에 값을 XPC 사전·JSON·plist로, 타입 이름 3가지로 보내 봤으나 오류 기록도 처리 기록도 없이 버려짐. dtuhidd는 hardened가 아니지만 SIP 때문에 디버거로 붙을 수 없어 받는 쪽을 볼 수 없음 |
  | 본 화면 | ⚠️ 우리 연결의 터치스크린이 붙을 때 backboardd가 `*** already have a main display digitizer` — 본 화면 터치스크린은 먼저 붙은 Device Hub 몫이라, 형식을 맞혀도 Device Hub가 떠 있으면 본 화면에 안 들어갈 가능성이 큼 |

  그래서 보류. 대안 후보: 상주 실행기(XCUITest) 안에서 XCTest의 이벤트 합성(`XCSynthesizedEventRecord`, Maestro가 쓰는 방식)으로 좌표 탭·끌기 — 부팅과 상관없이 되고, `XCUICoordinate.tap()`보다 빠를 것으로 보임.
- 그래서 qakit은 **누른 뒤 화면이 바뀌었는지**로 판단합니다:
  - AI 직접 터치: 탭 뒤 1초 안에 화면이 안 바뀌면 알림, `expect`를 주면 그 자리에서 실패, `via: xcuitest`로 XCUITest 탭.
  - `qakit touch`: 누르기 전후 화면을 비교(JPEG 크기 차이 2% 이하 = 그대로)해 그대로면 알리고, 아는 원인(멈춘 실행기 → `qakit serve --stop`, 막힌 부팅 → 시뮬레이터를 껐다 켜거나 XCUITest 탭)을 안내합니다. 2% 기준은 화면 일부가 저절로 바뀌면(예: "최적화 중" 행이 새로 생김) "바뀜"으로 볼 수 있어, 실험할 때는 화면을 직접 봅니다.

## 5. 자동 ID (AutoID) — 비공개 API는 아니지만 공식 지원 밖

- `QAAutoID.dylib`을 앱 프로세스에 주입합니다: XCUITest는 `launchEnvironment["DYLD_INSERT_LIBRARIES"]`, `simctl launch`는 `SIMCTL_CHILD_DYLD_INSERT_LIBRARIES`.
- `Loader.m`의 `+load`가 `QAAutoID.start()`를 부르고, 공개 ObjC 런타임으로 `UIViewController.viewDidAppear(_:)` · `viewDidLayoutSubviews` · `UIView.didMoveToWindow`를 바꿔치기(`method_exchangeImplementations`)해 뷰가 나타날 때 `타입.프로퍼티` 경로로 `accessibilityIdentifier`를 붙입니다 (규칙: [동작 원리](how-it-works.md#자동으로-붙는-id-규칙)).
- 시뮬레이터에서만 주입합니다. 실기기는 dylib을 앱 안 `Frameworks/`에 넣고 앱과 같은 인증서로 서명합니다 ([실기기](device.md)).

## Xcode가 바뀌면: 조사하는 법

simscreen·simtouch가 실패하면(라이브 세션이 스크린샷 방식으로 바뀌거나, 직접 터치가 XCUITest로 돌아감) 이 순서로 봅니다. **실험은 따로 만든 시험용 시뮬레이터에서** 합니다 (같은 이름의 기기를 쓰는 다른 작업과 섞이지 않게).

> ⚠️ **Device Hub를 끄면(⌘Q) 켜져 있던 시뮬레이터가 모두 꺼집니다** (Xcode 27, 2026-11-16 실제로 겪음 — 다른 작업이 쓰던 기기까지). 다른 기기를 보려면 끄지 말고 Device Hub 왼쪽 목록에서 고르세요. Device Hub는 이미 떠 있으면 `-CurrentDeviceUDID` 실행 인자를 무시하고, 접근성 API에 창이 잡히지 않아(창 0개) 스크립트로 고르려면 마우스 클릭 이벤트(CGEvent)를 써야 합니다. 목록에서 고르기만 해서는 다른 기기가 꺼지지 않았습니다.

```bash
# 0) 시험용 기기 (끝나면 지움). 공용 기기와 이름이 겹치지 않게
UDID=$(xcrun simctl create qakit-probe com.apple.CoreSimulator.SimDeviceType.iPhone-17 | tail -1)
xcrun simctl boot $UDID && xcrun simctl bootstatus $UDID -b
#    화면 움직이기: 다크·라이트 전환, 또는 Mac에서 띄운 애니메이션 페이지를 Safari로 (시뮬레이터의 127.0.0.1 = Mac)
xcrun simctl ui $UDID appearance dark; xcrun simctl ui $UDID appearance light
xcrun simctl openurl $UDID http://127.0.0.1:8799/anim.html
xcrun simctl shutdown $UDID; xcrun simctl delete $UDID          # 끝나면

# 1) 부품 위치
find "$(xcode-select -p)/.." -maxdepth 3 -name SimulatorKit.framework
ls /Library/Developer/PrivateFrameworks/CoreSimulator.framework

# 2) 포트·프로토콜·블록 형식 (+ 프레임 콜백이 오는지)
swift scripts/sim-probe.swift $UDID
swift scripts/sim-probe.swift $UDID --frames 5

# 3) SimulatorKit의 Swift API
SK="$(xcode-select -p)/../SharedFrameworks/SimulatorKit.framework/SimulatorKit"
nm -g "$SK" | awk '{print $NF}' | xcrun swift-demangle --simplified | grep -E "SimDeviceScreen|ScreenEvent"

# 4) 그 Swift API가 안에서 부르는 Objective-C 메서드
strings -a "$SK" | grep -E "register.*Callbacks|unregister|framebufferSurface|IndigoHID"
```

5. **ObjC 클래스·메서드 목록**: 부품을 `dlopen`한 뒤 `objc_copyClassNamesForImage(경로)`로 클래스 이름을, `class_copyMethodList`·`class_copyIvarList`로 메서드·변수를 봅니다. 원격 객체는 `class_copyProtocolList` + `protocol_copyMethodDescriptionList`로 봅니다.
6. **블록 인자 형식**: `protocol_copyMethodDescriptionList`의 형식은 블록을 `@?`로만 보여 줍니다. 런타임 함수 `_protocol_getMethodTypeEncoding(프로토콜, 셀렉터, 필수, 인스턴스)`(`dlsym`)를 쓰면 `@?<v@?@"IOSurface"@"IOSurface">`처럼 블록 안 인자까지 나옵니다. `scripts/sim-probe.swift`가 이걸 씁니다.
7. **측정**: 콜백 수와 seed 변화 수를 같이 세고(`sim-probe --frames`), 받는 쪽에서 장면 간격(중앙·90%·99%)을 봅니다. 이 문서의 숫자는 이렇게 쟀습니다.

## 위험과 대비

| 깨질 수 있는 것 | 증상 | qakit이 하는 일 |
|---|---|---|
| CoreSimulator 클래스·메서드 이름 | simscreen이 시작하자마자 끝남 (0이 아닌 코드, stderr `simscreen: …`) | 라이브 세션이 **스크린샷 방식**(`simctl io screenshot`)으로 바뀌고 화면 아래에 이유. 30초 뒤 다시 시도 |
| 프레임 콜백 (없음·형식 바뀜·끊김) | 콜백 없이 화면만 바뀜 | 세 번 쌓이면 **seed 폴링**으로 (`SIMSCREEN_POLL=1`로 처음부터) |
| 하드웨어 JPEG | 결과가 JPEG가 아님 | CoreGraphics + ImageIO로 (`SIMSCREEN_NO_HW=1`) |
| SimulatorKit 위치·HID 함수·메시지 구조 | simtouch 시작 실패 | AI 직접 터치가 **XCUITest 탭**으로 |
| 터치가 조용히 무시됨 | 답은 `ok`인데 화면 변화 없음 | AI 직접 터치: 1초 안에 변화가 없으면 경고, `expect`로 실패 처리, `via: xcuitest`. `qakit touch`: 전후 화면 비교 후 원인 안내 |
| AutoID 주입 | ID가 안 붙음 | `autoid: embedded`(앱에 AutoID.swift를 넣는 방식) |

- CI(GitHub Actions, macOS)가 simscreen·simtouch가 **컴파일되는지** 확인합니다. 실제 동작(시뮬레이터)은 위 순서로 손으로 확인합니다.
- 이 도구들은 사용자의 Mac에서 처음 쓸 때 `xcrun swiftc`로 빌드되므로(소스가 바뀌면 다시), Xcode가 바뀌어도 그 Xcode의 SDK로 다시 컴파일됩니다.

## 관련 코드

| 파일 | 내용 |
|---|---|
| `Tools/simscreen/simscreen.swift` | 실시간 화면 (①~④), `--once`(한 장), `--encode`(mp4) |
| `Tools/simtouch/simtouch.swift` | 직접 터치 (stdin 한 줄 명령: `tap`·`press`·`swipe`·`down`·`move`·`up`) |
| `scripts/sim-probe.swift` | 포트·프로토콜·블록 형식 출력, 프레임 콜백 세기 |
| `lib/qakit/86_ui_server.py` | `/api/stream`(MJPEG), `/api/stream-status`, 녹화 |
| `lib/qakit/85_mcp_ai.py` | `FrameRing`(문제 보고 영상), 직접 터치 도구 |
| `lib/qakit/20_build.py` | `ensure_swift_tool`(도구 빌드), `TouchHelper`(simtouch 상주) |
| `AutoID/` | 자동 ID dylib |
