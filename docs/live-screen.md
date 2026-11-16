# 실시간 화면: 시뮬레이터 화면 메모리를 바로 읽기

`qakit ui` 라이브 세션은 시뮬레이터 화면을 **사진(스크린샷)** 이 아니라 **실시간 영상**으로 보여 줍니다.
이 문서는 그 원리와 qakit의 구현(`Tools/simscreen/simscreen.swift`), tapflow와의 차이를 정리합니다.

## 한 줄 요약

시뮬레이터는 앱 화면을 Mac의 **공유 메모리(IOSurface)** 에 그립니다. qakit은 Xcode의 비공개 부품(CoreSimulator)으로 그 메모리를 찾아 붙잡고, **화면이 바뀔 때마다** 작게 줄인 JPEG로 바꿔 브라우저에 보냅니다.

```
시뮬레이터 (앱이 화면을 그림)
   │  그리는 곳: IOSurface  ← 포트 이름 com.apple.framebuffer.display
   ▼
simscreen (Swift 도구)     바뀌었나? (seed) → 900px로 줄여 하드웨어 JPEG
   │  stdout: [길이 4바이트][JPEG] …
   ▼
qakit ui 서버 (Python)     최신 한 장을 보관 → 보고 있는 브라우저 모두에게
   │  /api/stream  (MJPEG: multipart/x-mixed-replace)
   ▼
브라우저 <img>             받는 대로 바로 그림 = 영상처럼 보임
```

## 왜 스크린샷으로는 안 되나

| | 스크린샷 (`xcrun simctl io <udid> screenshot`) | 화면 메모리 직접 읽기 |
|---|---|---|
| 한 장 걸리는 시간 | 0.4~0.6초 (매번 프로세스 실행·PNG/JPEG 저장) | 수십 ms (메모리를 읽어 줄이기만) |
| 한 장 크기 | 약 650KB (원본 해상도) | 약 150KB (600px 폭) |
| 초당 장수 | 약 2장 | 화면이 움직일 때 약 20장 |
| 안 바뀐 화면 | 그래도 매번 찍음 | 안 보냄 (seed로 판단) |

## 단어 정리

| 단어 | 뜻 |
|---|---|
| **IOSurface** | macOS에서 여러 프로세스가 함께 쓰는 그림 메모리. 시뮬레이터는 기기 화면을 여기에 그린다. 다른 프로세스도 같은 메모리를 열어 읽을 수 있다 |
| **framebuffer** | "화면 한 장 분량의 픽셀이 들어 있는 메모리". 시뮬레이터 기기의 화면 출력 포트 이름이 `com.apple.framebuffer.display` |
| **CoreSimulator** | `/Library/Developer/PrivateFrameworks/CoreSimulator.framework`. `simctl`이 내부에서 쓰는 부품. 기기 목록·부팅·입출력 포트를 다룬다. **헤더가 공개되지 않은 비공개 API** |
| **SimulatorKit** | Xcode 안의 또 다른 비공개 부품 (Xcode 27: `Xcode.app/Contents/SharedFrameworks/`). 화면 콜백·터치 주입 같은 기능이 있다. tapflow가 사용. qakit은 쓰지 않는다 |
| **seed** | IOSurface가 바뀔 때마다 올라가는 번호. 같으면 화면이 그대로라는 뜻 |
| **MJPEG** | JPEG를 이어 붙여 보내는 가장 단순한 영상. `<img>` 태그가 디코더 없이 그대로 보여 준다 |

## qakit 구현 (`Tools/simscreen/simscreen.swift`)

비공개 API라 헤더가 없으므로 Objective-C 런타임으로 **이름(문자열)** 으로 불러 씁니다 (`NSClassFromString`, `NSSelectorFromString`, `perform`, `value(forKey:)`).

### 1. 기기 찾기

```text
dlopen(CoreSimulator.framework)
SimServiceContext.sharedServiceContextForDeveloperDir:error:   (xcode-select -p 경로)
  └ defaultDeviceSetWithError:                                  기기 모음
      └ devices → UDID가 같은 SimDevice                          (qakit.yml의 시뮬레이터)
```

### 2. 화면 메모리 잡기

```text
SimDevice.io                         기기의 입출력
  └ updateIOPorts / ioPorts          포트 목록 (화면·오디오·키보드 …)
      └ portIdentifier == "com.apple.framebuffer.display"
          └ descriptor.framebufferSurface  → IOSurface (가장 큰 것 = 본 화면)
```

이 IOSurface는 시뮬레이터가 지금 그리고 있는 **바로 그 메모리**입니다. 복사본이 아니므로, 읽을 때마다 최신 화면이 들어 있습니다.

### 3. 바뀔 때만 보내기

```text
반복 (최대 60fps):
  seed가 지난번과 다르면 (또는 2초 지났으면 — 새로 붙은 브라우저용)
    IOSurface → VTPixelTransfer(GPU)로 900px 폭으로 줄임 → VideoToolbox 하드웨어 JPEG(품질 0.7)
    (하드웨어가 안 되면 CGImage → 줄임 → ImageIO JPEG. SIMSCREEN_NO_HW=1이면 이쪽만)
    stdout에 [4바이트 길이][JPEG]
  3초마다 포트를 다시 확인 (회전·기기 재시작으로 화면 메모리가 바뀔 수 있음)
```

- 픽셀 형식: BGRA (`premultipliedFirst | byteOrder32Little`).
- 확인용: `simscreen <udid> --once out.jpg` → 한 장 저장하고 끝.
- 준비되면 stderr에 `ready 1206x2622`, 실패하면 `simscreen: <이유>`와 0이 아닌 종료 코드.

### 4. qakit ui 서버

| 할 일 | 방법 |
|---|---|
| 빌드 | 처음 쓸 때 `xcrun swiftc -O`로 `Tools/simscreen/.build/simscreen` (소스 해시가 바뀌었을 때만, 몇 초) |
| 띄우기 | 브라우저가 `/api/stream`을 처음 열 때 하나만. 여러 브라우저가 같은 도구를 나눠 봄 |
| 보내기 | 읽은 최신 한 장을 `multipart/x-mixed-replace; boundary=qakitframe`로 각 브라우저에 |
| 끄기 | 보는 브라우저가 없으면 30초 뒤, `qakit ui` 종료 시 |
| 상태 | `/api/stream-status` → 실행 중인지, 최근 초당 장수, 멈춘 이유 |
| 실패 | 빌드 실패·비공개 API 바뀜·시뮬레이터 꺼짐 → 라이브 세션이 **스크린샷 방식으로 자동 전환**하고 이유 표시. 30초 동안은 다시 시도하지 않음 |

## tapflow와 비교

| | tapflow | qakit |
|---|---|---|
| 화면 메모리 | SimulatorKit의 화면 콜백 등록 (`registerScreenCallbacksWithUUID:…frameCallback:…`) — 새 프레임마다 호출됨 | CoreSimulator 포트에서 IOSurface를 잡고 seed를 주기적으로 확인 (콜백 없음, 코드가 짧음) |
| 인코딩 | H.264 (VideoToolbox 하드웨어) 기본, 안 되는 브라우저는 JPEG | 하드웨어 JPEG (VideoToolbox) → MJPEG — 로컬(127.0.0.1)이라 대역폭 걱정이 적고 디코더가 필요 없음 |
| 전송 | relay 서버를 거쳐 WebSocket (원격 팀 공유) | 같은 Mac의 HTTP (`<img>` 하나) |
| 터치 | SimulatorKit의 HID 신호 주입 — 좌표로 진짜 손가락처럼 | XCUITest가 **ID·라벨로** (시나리오에 이름으로 기록되는 게 핵심이라 좌표 터치는 안 씀) |
| Xcode 27 대응 | SimulatorKit 위치 변경으로 한때 화면·터치가 안 됨 (tapflow #797) | SimulatorKit을 안 써서 그 변경과 무관. CoreSimulator 위치는 그대로 |

방법(어떤 포트·속성을 쓰는지)만 참고했고, 코드는 직접 작성했습니다.

## 측정 (Xcode 27, iPhone 17 시뮬레이터)

| 항목 | 결과 |
|---|---|
| 화면 메모리 | 1206×2622, 색·노치 정상 |
| 화면이 움직일 때 | 시뮬레이터가 그리는 만큼 (상한 60, 계속 바뀌면 약 50장) |
| 한 장 만들기 (900px) | 하드웨어 JPEG 약 7ms · CoreGraphics+ImageIO 약 24ms (2026-11 이전 방식) |
| 한 장 크기 | 약 200KB (900×1956) |
| 도구 CPU (계속 바뀔 때 50장/초) | 하드웨어 약 12% · CoreGraphics 약 84% — 이전 방식은 CPU를 시뮬레이터·브라우저와 다퉈 버벅였다. 멈춰 있으면 거의 0 |
| 멈춰 있을 때 | 2초에 한 장 |

## 한계와 위험

- **비공개 API**: Apple이 문서화하지 않았으므로 Xcode 업데이트에서 이름·위치가 바뀔 수 있습니다. 그때는 스크린샷 방식으로 돌아가며, 이 문서의 이름들을 새 Xcode에서 다시 확인해야 합니다 (`nm -gU`, `class-dump`, 런타임 `responds(to:)`).
- **시뮬레이터만**: 실기기 화면은 이 방법으로 읽을 수 없습니다.
- **보기만**: 이 경로는 화면을 읽기만 합니다. 앱 조작은 계속 XCUITest(상주 실행기)가 합니다.

## 직접 확인하기

```bash
udid=$(xcrun simctl list devices booted | grep -oE '[0-9A-F-]{36}' | head -1)
xcrun swiftc -O Tools/simscreen/simscreen.swift -o /tmp/simscreen
/tmp/simscreen "$udid" --once /tmp/screen.jpg && open /tmp/screen.jpg
```
