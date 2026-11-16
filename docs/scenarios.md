# 시나리오 파일 · 상주 실행기 · CI

Swift 없이 `.qa.yml`로 QA하는 법, `qakit serve`·`qakit do`, GitHub Actions에서 돌리는 법입니다. 전체 문법은 [scenario-language.md](../skills/qa-kit/references/scenario-language.md).

[← README](../README.md)

## 시나리오 파일로 QA (Swift 없이)

AI가 Swift 대신 **시나리오 파일**(`QA/scenarios/<이름>.qa.yml`)을 쓰면, 도구 안의 범용 실행기가 그 파일을 읽어 그대로 실행합니다.
→ 앱마다 QA용 Xcode 프로젝트를 만들거나 컴파일하지 않습니다.

```yaml
name: 검색한 상품을 즐겨찾기에 넣고 지도 모드로 보기
reset: true                               # 앱 초기화부터
vars: { item: 커피 }
steps:
  - use: login                            # steps/login.qa.yml (공통 단계)
  - tap: HomeView.menuButton
  - tap: { cell: MenuCell, has: { id: MenuCell.titleLabel, label: 검색 } }
  - input: { tap: SearchView.searchField, alert: "{item}", confirm: 완료 }
  - read: { from: { id: ResultCell.infoLabel }, pattern: '/(\d+)$', as: code }
  - unless: { exists: { id: ResultCell.favoriteBadge } }           # 이미 즐겨찾기면 누르지 않음
    then: [ tap: { id: ResultCell.nameLabel, contains: "{item}" } ]
  - expect: { selected: { segment: SettingView.modeControl, label: 지도 } }
    hold: 5
  - pinch: { on: HomeView.mapView, scale: 2.5 }
```

```bash
qakit check search-favorite      # 형식 + 적힌 ID가 앱에 있는지 (실행 없이, Swift의 컴파일 에러 역할)
qakit run search-favorite        # 실행 (reset: true면 앱 초기화부터)
qakit run search-favorite --var item=라떼   # vars 값을 바꿔서 실행 (매개변수)
```

**표현할 수 있는 것**

| 종류 | 문법 |
|---|---|
| 분기 | `if` / `unless` |
| 값 읽기 | `read` |
| 여러 후보 대기 | `wait-any` |
| 위치 비교 | `right-of` |
| 화면 변화 | `changed` |
| 화면에 안 나오는 앱 상태 (예: 지도 줌) | 앱 설정(UserDefaults) 값으로 판정 `pref`, `read-pref` |
| 목표 값까지 반복 (예: "줌 15가 될 때까지 핀치") | `repeat` + `watch` |

- 전체 문법: [scenario-language.md](../skills/qa-kit/references/scenario-language.md)
- 언어로 표현이 안 되는 계산·판정만 Swift(`QA/Runner/UITests/Flows`)로 씁니다. **두 방식은 같은 작업공간에서 함께** 씁니다.

## 빠르게 돌리고 눌러 보기 (`qakit serve` · `qakit do`)

`qakit run`은 시나리오마다 `xcodebuild`로 실행기(XCUITest)를 새로 띄웁니다. 컴파일은 없지만 실행기 설치·연결을 매번 다시 합니다.
**상주 실행기**는 실행기를 시뮬레이터에 한 번 띄워 두고 명령만 주고받습니다 (Maestro·Appium과 같은 구조).

| 방식 | 실행기 | 한 번 실행 비용 |
|---|---|---|
| `qakit run` (기본) | 매번 새로 | 준비 + 앱 실행 + 단계 |
| `qakit run` (상주 실행기가 떠 있을 때) | 계속 떠 있음 | 앱 실행 + 단계 (시범 앱 기준 시나리오당 약 8초, 23% 빠름) |
| `qakit do '<단계>'` | 계속 떠 있음 | 단계 하나 (1~2초, 실행기를 처음 띄울 때만 1분 안팎) |

```bash
qakit serve                                  # 띄우기 (안 해도 qakit do / run --serve가 알아서 띄움)
qakit do launch                              # 앱 새로 실행
qakit do 'use: login'                        # 공통 단계 그대로
qakit do 'tap: HomeView.menuButton'          # 시나리오 단계 하나 (문법이 .qa.yml과 같다)
qakit do dump                                # 지금 화면 구조 → results/ui-dump.txt
qakit run home-search                        # 떠 있으면 자동으로 상주 실행기로 실행
qakit run home-search --no-serve             # 지금처럼 xcodebuild로
qakit serve --stop                           # 멈추기 (30분 동안 명령이 없으면 스스로 끝남)
```

**어디에 쓰나**

- **화면 탐색** — AI는 시나리오를 쓰기 전에 `qakit do`로 한 단계씩 눌러 보고 `qakit do dump`로 화면을 읽습니다. 탐색용 시나리오를 만들어 20~40초씩 돌리는 일을 반복하지 않습니다. 통과한 단계는 그대로 `.qa.yml`에 옮깁니다.
- **고치며 반복 실행** — 시나리오를 여러 번 고쳐 돌릴 때 `qakit run --serve`. 결과 폴더·실패 요약(원인·마지막 단계·실패 시점 화면 구조·스크린샷)·실행 기록은 기본 방식과 같습니다.

**알아 둘 것**

- `qakit do`는 앱 상태와 변수를 다음 명령으로 이어 갑니다. 처음부터는 `qakit do launch`. `qakit run`은 지금처럼 앱을 새로 실행해 처음부터 돕니다.
- 명령이 제한 시간(`qakit do` 120초, `qakit run` 600초, `--timeout`)을 넘기면 실행기를 멈추고 실패로 알립니다. 다음 명령이 다시 띄웁니다.
- `qakit test`·`dump-ui`는 시작 전에 상주 실행기를 멈춥니다. `--bench`는 늘 기본 방식으로 돕니다.
- **실기기**: `--device`를 붙이면 됩니다 (`qakit do 'tap: …' --device i`, `qakit run <시나리오> --device i --serve`). USB든 Wi-Fi든 됩니다. USB면 Mac이 usbmuxd(Xcode가 쓰는 USB 포트 전달)로 기기 안 `127.0.0.1`의 실행기에 붙고, Wi-Fi면 실행기를 CoreDevice 터널(페어링된 Mac만 쓰는 통로)의 기기 쪽 주소에만 열어 그 주소로 붙습니다 — 같은 Wi-Fi의 다른 기기에서는 보이지 않습니다. 시범 앱 기준 시나리오당 USB 약 4초(38%), Wi-Fi 약 6초(46%) 빠릅니다.
- 실행기는 `127.0.0.1`에만 열리고 요청마다 무작위 토큰을 확인합니다. 상태 파일: `~/.qakit/serve/<시뮬레이터 udid>.json`.
- 상주 실행기로 돈 `run`은 xcresult 대신 결과 폴더에 `summary.txt`·`failure-dump.txt`·`failure.png`를 남깁니다. `qakit summarize`는 어느 쪽이든 마지막 실행의 요약을 보여 줍니다.

## CI에서 돌리기 (GitHub Actions)

시나리오를 **PR마다 GitHub 서버(macOS·시뮬레이터)가 자동으로** 돌리게 합니다. 예시: [`templates/ci/qa.yml`](../templates/ci/qa.yml) — 앱 저장소의 `.github/workflows/qa.yml`로 복사해 고쳐 씁니다.

```
PR → macOS 러너: qakit 설치 → 앱 빌드 → qakit run --tag smoke --junit
   → PR 체크 ✅/❌, 결과(실패 요약·스크린샷·실패 영상·JUnit)를 내려받기로 첨부
매일 밤 → 전체 시나리오 · Actions 탭 "Run workflow" → 태그를 골라서
```

| 준비 (저장소 Settings) | 내용 |
|---|---|
| Secret `QA_SECRETS` | 작업공간 `secrets.txt` 내용 그대로 (로그인 계정 등) |
| Variable `QA_SIMULATOR` | 러너에 있는 시뮬레이터 이름 (예: `iPhone 16`). 비우면 `qakit.yml` 값 |
| Variable `QA_REPO` · Secret `QA_REPO_TOKEN` | QA 작업공간이 앱 저장소 안 `QA/`가 아니라 **따로 된 저장소**일 때만 |

- 러너에서는 QA 워크트리 자동 최신화를 끄고(`update: off`, 이미 이번 커밋을 받았으므로) 시뮬레이터 이름을 바꿉니다.
- macOS 러너는 Linux보다 분당 비용이 약 10배 → PR엔 `smoke`, 전체는 하루 한 번.
- 로그인이 필요한 화면은 러너에서도 로그인해야 합니다. 아이디·비밀번호는 secrets로 되지만, **애플·소셜 로그인처럼 사람이 확인하는 로그인은 자동으로 못 합니다** → 로그인 없는 화면만 돌리거나, `precheck`가 "로그인 상태가 아님"으로 멈춥니다(종료 코드 2).
- 종료 코드: 0 통과 · 1 앱 판정 실패 · 2 환경·설정 문제.
