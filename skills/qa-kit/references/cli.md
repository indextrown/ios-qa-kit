# qakit CLI

작업공간(`qakit.yml`) 폴더에서 실행. 전역 옵션은 명령 앞에 쓴다: `qakit --app <경로> test`.

| 명령 | 하는 일 |
|---|---|
| `qakit init <앱 프로젝트> [--name] [--dir] [--scheme] [--force]` | 작업공간 생성. scheme·configuration·bundleId 자동 탐지 |
| `qakit update [--check]` | 도구를 최신 버전으로 받기 (설치 폴더를 git fast-forward). `--check`: 새 버전이 있는지만 |
| `qakit doctor` | 환경·설정·secrets 키 점검 |
| `qakit build-app` | 앱 빌드 → 시뮬레이터 설치 → 권한 허용 |
| `qakit worktree-update [--check] [--from 브랜치]` | QA 워크트리를 따라갈 브랜치(`worktree.base`, 기본 develop. 원격이 앞서면 origin/…)의 새 커밋으로 merge. push·다른 브랜치로 병합은 하지 않음. 미커밋 변경·충돌이면 가져오지 않고 알림. `test`·`run` 전에 자동(`worktree.update: auto`) |
| `qakit sync [--rebuild] [--skip-build]` | 앱 변경 반영: 재빌드·설치 + ID 재생성(추가/삭제 보고) + 테스트 코드 컴파일 확인 |
| `qakit gen-ids [--verify]` | ID 상수 생성 (SwiftUI ID 포함). `--verify`: 저장된 덤프와 비교 |
| `qakit swiftui-ids --list \| --insert \| --restore` | SwiftUI ID 삽입 도구. `--list`: 삽입될 ID 목록. `--insert`: 워크트리 소스에 삽입한 채 둠(diff 확인용). `--restore`: 되돌림. `build-app`은 자동으로 삽입→빌드→복원 |
| `qakit dump-ui [--attach] [--wait-id ID] [--settle 초] [--print]` | 화면 구조 → `results/ui-dump.txt` |
| `qakit serve [--stop\|--status] [--idle 초] [--no-launch] [--device 이름]` | 상주 실행기. 실기기는 `--device`. 포트는 qakit이 정해 넘긴다. USB면 Mac이 usbmuxd로 기기 안 `127.0.0.1:<포트>`에 붙고, Wi-Fi면 실행기를 CoreDevice 터널의 기기 쪽 주소(`devicectl`의 `tunnelIPAddress`, 예: `fdxx::1`)에만 열어 그 주소로 붙는다 (같은 Wi-Fi의 다른 기기에서는 안 보임). 실행기(XCUITest)를 백그라운드로 띄워 두고 명령만 주고받는다. 상태 파일 `~/.qakit/serve/<udid>.json`. `--status`: 떠 있는지, `--stop`: 멈춤, `--idle`: 명령이 없으면 스스로 끝내는 시간(기본 1800초), `--no-launch`: 시작할 때 앱을 띄우지 않음. 떠 있으면 `qakit run`이 자동으로 이쪽으로 돈다. `test`·`dump-ui`는 시작 전에 상주 실행기를 멈춘다 |
| `qakit do '<단계>' [--timeout 초]` | 시나리오 단계 하나를 바로 실행 (1~2초, 없으면 상주 실행기를 띄움 1분 안팎. 그때는 "실행기 시작 포함 전체 N초"도 출력). 단계 문법은 `.qa.yml`과 같다 (`use:`는 펼쳐 실행). 한 번에 단계 하나. 앱 상태·변수는 다음 `qakit do`로 이어진다. 실패하면 ❌ 원인 + `results/do-fail-dump.txt`, 종료 코드 1, 실행기는 유지. `--timeout`(기본 120초)을 넘기면 실행기를 멈춘다(다음 명령 때 다시 띄움) |
| `qakit do steps` / `qakit do save <이름> [--force] [--title 제목] [--tag 태그 …] [--start 공통단계]` | **`qakit do`로 통과한 단계는 기록된다** (`.qakit/do-steps.jsonl`, 실패한 단계는 빠짐, `qakit do launch`부터 새로 시작). `steps`: 기록 보기. `save`: 그 단계로 `scenarios/<이름>.qa.yml` 초안을 쓰고 형식·ID를 바로 검사 (있으면 `--force` 없이 덮어쓰지 않음). **탭 바로 다음 `wait`는 탭의 `expect`로 합쳐 저장**한다 |
| `qakit coverage [--unused] [--json]` | 앱 ID(자동 ID) 중 시나리오가 쓰는 것을 화면(ID 맨 앞 타입)별로. `use:`·`start:`·조건 안까지 셈. 앱이 직접 붙인 ID(snake_case)는 전체 수를 몰라 따로. 다음에 무엇을 시나리오로 만들지 고를 때 |
| `qakit mcp` · `qakit mcp install --claude\|--codex` | AI가 앱을 직접 QA하는 MCP 서버 (stdio). 도구: `get_testing_guide`·`launch`·`screen`·`screenshot`·`tap`(+`expect`)·`type_text`·`swipe`·`wait_for`·`expect`·`step`·`recorded_steps`·`list_scenarios`·`list_common_steps`·`read_scenario`·`find_ids`·`run_scenario`·`save_scenario`(재생 통과해야 저장)·`report_issue`(재현한 것만, `results/ai/<시각>/`). install: Claude Code는 작업공간 `.mcp.json`, Codex는 `codex mcp add`. 조작 도구는 선택 인자 `why`(이유 한 줄) — `qakit ui` 라이브 세션 "AI 활동"에 보임. `qakit ui`의 **AI QA** 메뉴에서 목표만 적고 시작할 수도 있다 (로그인된 `claude -p`/`codex exec`를 qakit 도구만 허용해 실행, 결과 `results/ai/<시각>/report.md`). 지난 세션은 AI QA·실행 기록에서 보고, AI가 통과한 단계로 시나리오 초안 → 재생 → 저장 |
| `qakit ui [--port N] [--no-open]` | 로컬 웹 UI (`127.0.0.1`, 실행마다 토큰): 실행 기록·실패 상세(요약·스크린샷·화면 구조·단계별 시간·로그), **시나리오 선택 목록에서 골라 실행**(태그로 한꺼번에 선택, 앱 재사용·멈춤 방식·사전 확인, 실시간 로그·멈춤), 시나리오별 최근 결과와 불안정 표시, **시뮬레이터 라이브 화면**(실시간: 화면 메모리를 바로 읽어 영상, 안 되면 스크린샷), **라이브 조작**(화면 위 요소를 눌러 ID·라벨 단계로 탭·기다림·확인·쓸기, `qakit do`로 실행·기록. 실행기가 누르는 자리로 커서가 움직임(라이브 조작·`qakit do`·시나리오 실행, 시뮬레이터), '누르면 탭'을 켜면 화면을 누르는 즉시 탭 — 둘 다 켜고 끌 수 있음. 만들어 둔 시나리오를 골라 실행하고 라이브 화면으로 진행을 봄), **시나리오로 저장**(초안 → 앱을 새로 켜고 재생 → 통과해야 `scenarios/`로), **편집**(시나리오·공통 단계 YAML 편집기, 고칠 때마다 검사, 태그, ID 찾기, 밖에서 바뀌면 덮어쓰지 않음). Ctrl+C로 끝냄 (UI에서 시작한 실행도 멈춤) |
| `qakit show [--no-launch]` | 시뮬레이터 화면을 띄우고(Xcode 27+ Device Hub, 이전 Simulator) 대상 앱 실행. 로그인처럼 사람이 직접 만질 때. 테스트가 도는 동안에는 만지지 않는다 |
| `qakit do dump [--settle 초]` / `launch` / `reset` / `ping` | `dump`: 지금 화면 구조 출력 + `results/ui-dump.txt`. `launch`: 앱 다시 실행 + 변수 비움. `reset`: 변수만 비움(앱 그대로). `ping`: 응답 시간·앱 상태 |
| `qakit test [필터...] [--reset]` | 테스트 실행. 필터 예: `LoginFlowTests`, `LoginFlowTests/test_x`. `--reset`: 앱 재설치+키체인 초기화 |
| `qakit check [시나리오...]` | 시나리오 형식·ID 정적 검사 (실행 없이). 탭 다음 `wait`처럼 탭의 `expect`로 합칠 수 있는 곳이 있으면 💡로 알려 줌 |
| `qakit run <시나리오> <시나리오> …` / `qakit run 'home-*'` | 여러 개를 차례로. 패턴은 `scenarios/`의 이름에 맞춰 펼친다 (zsh에서는 따옴표 필수). 준비(워크트리 최신화·앱 변경 확인·ID 검사)와 README 갱신은 한 번만, 판정·결과 폴더는 시나리오마다. 하나가 실패해도 나머지를 돌리고 끝에 요약(실패하면 종료 코드 1, 다시 돌릴 명령 안내). **연속한 두 시나리오가 같은 원인·같은 단계에서 실패하면 환경 문제(로그아웃·서버 점검 등)로 보고 멈춘다** (`--keep-going`: 끝까지, `--fail-fast`: 첫 실패에서 멈춤). `--reuse-app`과 같이 쓰면 앱도 이어서 쓴다. `--bench`는 하나만 |
| `qakit run … [--precheck \| --no-precheck]` | `qakit.yml`에 `precheck: <공통 단계>`가 있으면 **여러 개를 돌리기 전에** 그 단계를 한 번(앱을 새로 켜고) 돌려 환경을 확인한다. 실패하면 시나리오를 하나도 돌리지 않고 종료 코드 2, 단계 파일의 `message:`를 보여 줌 (예: "로그인 상태가 아님"). 하나만 돌릴 때는 `--precheck`로 |
| `qakit run --tag <태그> [--exclude-tag <태그>]` | 시나리오 맨 위 `tags:`로 고른다 (이름·패턴과 함께 쓰면 그 안에서 고름) |
| `qakit run … --junit <파일>` | JUnit XML 보고서 (CI용). 앱 판정 실패는 `failure`, 환경·설정 실패는 `error`, 돌리지 않은 것은 `skipped` |
| `qakit run … --video fail\|always\|off` | 시뮬레이터 화면 녹화. 기본 `fail`: 실패하면 마지막 30초를 결과 폴더 `failure.mp4`(440×960)로, 통과하면 버림. `always`: 통과해도 `video.mp4`. 실기기·`--bench`는 녹화 안 함. 간헐 실패(불안정)는 영상으로 탭 순간 화면을 확인 |
| `qakit run <시나리오> --reuse-app` | 앱이 이미 시작 화면(시나리오의 `start:` 조건)이면 다시 켜지 않는다 (= `launch: reuse`). `start:`가 없거나 화면이 다르면 다시 켠다. `--reset`이면 무시. 자세히는 scenario-language.md "앱 재실행 생략" |
| `qakit run <시나리오> [--serve\|--no-serve] [--timeout 초]` | 이 작업공간용 상주 실행기가 떠 있으면 자동으로 그쪽으로 돈다 (xcodebuild 준비 생략, 시나리오당 약 8초 빠름). `--serve`: 없으면 띄워서. `--no-serve`: 떠 있어도 xcodebuild로 (상주 실행기는 멈춤). `--timeout`: 상주 실행기로 돌 때 제한 시간(기본 600초). `--reset`이면 실행기를 새로 띄운다. `--bench`는 늘 xcodebuild. 실기기도 상주 실행기로 (시나리오의 `dump:` 단계 파일은 응답으로 받아 같은 곳에 쓴다). 결과 폴더·`latest`·실행 기록(`"via": "serve"`)·실패 요약은 같고, xcresult 대신 `failure.png`·`failure-dump.txt`를 남긴다 |
| `qakit run <시나리오> [--reset] [--var 키=값 ...] [--bench 시간 [--no-profile]] [--no-check]` | 시나리오 파일 실행. `--var`: `vars` 기본값을 이번 실행 값으로 덮어씀 (예: `--var ship="ULTRA FOREST"`). `--bench <시간>`: 시나리오가 끝난 화면 그대로 그 시간 동안 (단위 필수: `30s`·`5m`·`1h`·`1h30m`, `30초`·`5분`·`1시간`도 됨. 단위가 없으면 오류, 최소 5초) CPU·메모리(1초 단위, `ps`) + 함수별 CPU(macOS `sample`, 10ms 간격. 1분 이하는 전체, 더 길면 3분마다 20초씩. 권한 불필요) → 실행 폴더의 `bench-*`. 요약에 직접 CPU를 쓴 함수·앱 코드 기준 상위 10개. `--no-profile`: CPU·메모리만 |
| `qakit run <시나리오> --device [select\|last\|<이름>]` | 실기기에서 실행 (`build-app`·`dump-ui`도 됨). 값을 빼면 방향키 목록(터미널에서만, AI는 이름으로 지정). 앱·실행기를 앱의 개발자 팀으로 서명, AutoID를 앱 `Frameworks/`에 넣고 다시 서명해 `devicectl`로 설치. 시나리오는 base64로 전달, `pref`는 AutoID의 숨은 요소 `QAKit.prefs`로 읽고, 덤프는 첨부(이름에 경로를 16진수로)로 받아 결과 폴더로 꺼낸다. `--bench`는 Time Profiler + Activity Monitor로 CPU %·메모리·함수 목록(`bench.trace`, `bench-cpu.csv`). Time Profiler는 실기기에서만 — 시뮬레이터는 `sample`. 권한 미리 허용 불가, `--reset`은 재설치만(키체인 유지), `qakit test`는 시뮬레이터만 |
| `qakit save -m "…"` | 결과물 목록·해시(`qa.lock.json`) + 보관소 `~/.qakit/archive/<이름>/` 복사. git 커밋은 하지 않음 |
| `qakit restore [--from 이름 --to QA]` | 보관소에서 AI 없이 복구 |
| `qakit summarize [xcresult \| 실행 폴더]` | 실패 요약 (기본: 마지막 실행). 상주 실행기로 돈 `run`은 그 실행 폴더의 `summary.txt` |

**`qakit run` 종료 코드**: `0` 모두 통과 · `1` 앱 판정 실패가 하나라도 있음 (환경 실패와 섞여도 1) · `2` 실행 환경·설정 문제만 (실행기가 안 뜸·연결 끊김·시간 초과, 앱 미설치, 시나리오·태그 없음, ID 검사 실패, 옵션 오류). CI에서 1은 앱 회귀, 2는 인프라로 나눠 다룬다.

환경 변수 `QAKIT_TIMING=1`: 명령이 끝날 때 qakit 단계별 걸린 시간과, 상주 실행기로 돈 `run`이면 실행기 안 시간(앱 실행·단계·끼어드는 화면 확인)과 오래 걸린 단계 5개를 출력한다 (느릴 때 어디인지 보기). 실행기 안 단계별 시간은 늘 결과 폴더 `output.log`의 `timing:` 아래에 남는다.

| 전역 옵션 | 설명 |
|---|---|
| `-w <작업공간>` | 다른 폴더에서 실행할 때 |
| `--app <앱 폴더>` | 다른 브랜치 워크트리 등 앱 경로 일시 변경 |
| `--secrets <파일>` | 다른 계정 파일 |
| `--build debug\|release` | 빌드 종류 (기본 debug = `app.configuration`, release = `app.release.configuration` 기본 `Release`, bundle ID는 자동). 명령 뒤에 써도 됨. 앱의 Release가 실서비스 서버를 쓰면 시나리오도 실서비스에 접속한다 |

## 안드로이드 (미리 보기)

`qakit.yml`에 `platform: android`면 `run`·`do`·`serve`·`dump-ui`·`doctor`가 안드로이드로 동작한다. 시나리오 문법은 iOS와 같다 (설계: 도구 레포 `docs/PLAN.md` "안드로이드 지원 설계").
- 상주 실행기(UiAutomator2)로만 돈다: 첫 실행 때 실행기를 빌드(Gradle, 몇 분)·설치하고 띄운다. `--no-serve`·`--bench`·실패 영상은 아직 없음.
- 앱은 미리 기기에 설치해 둔다 (`build-app` 아직). `--reset`·`reset: true`는 `pm clear`.
- ID 정적 검사(`check`의 앱에 없는 ID)는 하지 않는다. coverage는 저장된 덤프(`results/ui-dump.txt`, `results/dumps/`)에서 본 ID 기준.
- 글자 입력은 한글도 된다. 칸을 누르지 않고 바로 넣으므로(접근성 SET_TEXT) 대개 키보드가 뜨지 않는다 → `hide-keyboard`는 꼭 필요할 때만. `hide-keyboard`는 키보드가 실제로 떠 있을 때만 뒤로 가기를 보내는데, 앱에 따라 그 뒤로 가기에 화면·앱이 닫힐 수 있다 (시범 앱 로그인 화면에서 확인).
- qakit.yml `orientation: landscape|portrait|auto` — 실행기를 띄울 때 화면 방향 고정. `keyboard: hide`(기본)|`show` — 에뮬레이터 화면 키보드 앱(Gboard)을 꺼 두어 버튼을 가리지 않게 한다 (실기기는 그대로, Mac 키보드 입력은 됨). 키보드에 가려진 요소는 hittable이 아니고, 탭·쓸기는 키보드 영역을 피한다.
- `pref`·`read-pref`는 SharedPreferences(debuggable 빌드).
- `permissions:`(qakit.yml)는 reset(`pm clear`) 뒤 미리 허용한다: `location`, `location-always`, `notifications`, `nearby`(블루투스·Wi-Fi 근처 기기), `camera`, `microphone`, `photos`, `contacts`, `calendar`, `background`(배터리 최적화 예외 — "항상 백그라운드에서 실행" 대화상자), 또는 `android.permission.X`.
- Compose `contentDescription`은 ID가 아니라 라벨이다: `{ label: currentLocationButton }`. 팝업이 떠 있으면 대상은 위 창(팝업)에서 먼저 찾는다.
- `input:`(입력 알림)은 맨 위 대화상자의 첫 입력칸, `alert-button`은 버튼 글자(대소문자 무시).

| 명령 | 설명 |
|---|---|
| `qakit android setup [--avd 이름] [--image 시스템이미지] [--device-profile pixel_tablet]` | JDK 17(brew openjdk@17)·cmdline-tools·platform-tools·emulator·시스템 이미지·AVD(기본 `qakit`, pixel_7) 설치. Android Studio 불필요. 이미 있으면 건너뜀. AVD는 GPU 가속·하드웨어 키보드를 켠다 (기존 AVD도 맞춤, 에뮬레이터 재시작 필요). 태블릿: `--avd qakit-tablet --device-profile pixel_tablet` (2560x1600) |
| `qakit android doctor` | JDK·SDK·adb·emulator·AVD·연결된 기기 점검 |
| `qakit android boot [--avd 이름] [--headless] [--landscape \| --orientation landscape\|portrait\|auto]` | 에뮬레이터 실행 후 부팅 완료까지 대기 (이미 떠 있으면 그대로). `--landscape`: 부팅 뒤 가로로 고정. 로그 `~/.qakit/emulator-<AVD>.log` |
| `qakit android rotate landscape\|portrait\|auto [--avd 이름]` | 실행 중인 에뮬레이터 화면 방향 바꾸기 (자동 회전 끄고 고정, auto는 다시 켬). 휴대폰·태블릿의 기본 방향 차이를 알아서 맞춘다 |
| `qakit android screen [--json]` | 지금 앞의 앱 패키지·Activity·Fragment(바깥 → 안쪽). 덤프보다 빠름 |
| `qakit android dump [--package P] [--settle 초] [-o 파일 [--print]] [--json]` | 지금 화면 구조. 형식은 iOS `dump-ui`와 같다 (`타입 #ID "라벨" value="…" (disabled) @x,y wxh`, 좌표 dp). 머리말에 package·activity·fragments·ID 없는 요소 |

- ID: XML 뷰 `com.app:id/loginButton` → `#loginButton`, 프레임워크 `android:id/button1` → `#android.button1`, Compose testTag(testTagsAsResourceId)는 그대로. Compose 화면은 대개 ID가 없어 글자(`"Navigate up"`)로 찾는다.
- 기기가 여러 대면 `ANDROID_SERIAL=<serial>` 또는 `--avd`.
- 작업공간 `qakit.yml`에 `platform: android`, `app.project`(Gradle 루트), `app.packageName`, `emulator`(AVD 이름)를 적으면 `qakit doctor`·`qakit dump-ui [--attach] [--wait-id ID] [--settle 초]`가 안드로이드로 동작한다 (`--attach`가 아니면 앱을 종료 후 첫 화면부터 띄움).

## qakit.yml

```yaml
name: my-app
app:
  project: ~/path/App.xcodeproj
  scheme: App-Dev
  configuration: Debug
  bundleId: com.example.app.dev
simulator: iPhone 17
language: ko
locale: ko_KR
permissions: [location-always]   # simctl privacy 이름
secrets: ./secrets.txt
# precheck: precheck            # 여러 개 실행 전 steps/precheck.qa.yml로 환경 확인 (로그인 상태 등)
autoid: inject                   # inject(시뮬레이터 주입) | embedded
sync: auto                       # auto | warn | off
  # release:                      # --build release 때 (생략 시 configuration: Release, bundleId 자동)
  #   configuration: Release
worktree:                        # QA 워크트리(init --worktree)일 때
  base: develop                  # 따라갈 브랜치. release/* 처럼 쓰면 버전이 가장 높은 브랜치(예: release/0.6.0)
  update: auto                   # auto(test/run 전 자동으로 가져옴) | warn | off
# ids:
#   sources: [~/path/App/Sources]
```

## 결과 파일 (results/, git 제외)

실행 한 번이 폴더 하나다: `results/<날짜>/<시-분-초>_<종류>[_<이름>][_<실기기>]/`. 종류는 `run`·`test`·`dump`, 성능 측정이면 `bench-<시간>` (예: `results/2026-11-04/14-15-16_run_interpolation-setup/`, `14-20-03_bench-1m_interpolation-setup_iphone-15/`)

| 파일 (실행 폴더 안) | 내용 |
|---|---|
| `output.log` | 테스트 출력 (비밀값 가림) |
| `result.xcresult` | Xcode 결과 (상주 실행기로 돈 `run`은 없음) |
| `summary.txt` | 상주 실행기로 돈 `run`의 요약 (`qakit summarize`가 보여 줌) |
| `failure.png`, `failure-dump.txt` | 상주 실행기로 돈 `run`이 실패했을 때: 실패 시점 스크린샷·화면 구조 (`output.log`에는 메모·지나간 단계) |
| `result-attachments/` | 실패 시점 화면 구조·스크린샷 (`qakit summarize` 때) |
| `build.log` | Swift 테스트 Runner 빌드 로그 (`qakit test`) |
| `bench-summary.txt`, `bench-cpu.csv`, `bench-sample.txt` (긴 측정은 `bench-sample-01.txt`…) | `--bench` 성능 측정 요약·1초 단위 CPU/메모리·함수 호출 트리 원본 (시뮬레이터) |
| `bench.trace`, `bench-calltree.txt` | 실기기 `--bench`: Time Profiler 기록(Instruments로 열기)·그 샘플로 만든 호출 트리 텍스트 |

| 파일 (results/ 바로 아래) | 내용 |
|---|---|
| `latest` → 마지막 실행 폴더, `latest.xcresult` → 그 결과 | 바로가기 (`qakit summarize`가 씀). 마지막 실행이 상주 실행기로 돈 `run`이면 `latest.xcresult`는 없다 |
| `ui-dump.txt`, `dumps/` | 화면 덤프 (마지막 덤프 / 모아 둔 덤프·시나리오 `dump:`). `qakit do dump`도 `ui-dump.txt`에 쓴다 |
| `do-fail-dump.txt` | 마지막으로 실패한 `qakit do` 단계의 실패 시점 화면 구조 |
| `build-app.log` | 앱 빌드 로그 |


### qakit.yml `device` (선택)

```yaml
device:
  team: ABCDE12345   # 실기기 서명 팀. 없으면 앱 빌드 설정의 DEVELOPMENT_TEAM
```
