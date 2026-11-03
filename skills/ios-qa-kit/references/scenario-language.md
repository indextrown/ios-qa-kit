# qakit 시나리오 언어 (.qa.yml)

Swift 테스트를 쓰지 않고 파일만으로 QA를 실행한다. `qakit run <이름>`이 도구의 범용 실행기로 돌린다 (앱별 Xcode 프로젝트·컴파일 없음).
실행 전에 `qakit check`가 파일 형식과 **ID가 앱에 있는지** 검사한다 (Swift의 컴파일 에러 역할).

```yaml
name: 시나리오 이름
reset: true                       # 실행 전 앱 재설치 + 키체인 초기화 (= qakit run --reset)
vars: { item: 커피 }               # {item}으로 사용. 비밀값은 {secret:KEY} (secrets.txt)
steps:
  - use: login                    # steps/login.qa.yml을 펼침 (with: { 변수: 값 }로 넘김 가능)
  - tap: HomeView.menuButton
```

## 단계

| 단계 | 형식 | 설명 |
|---|---|---|
| tap | `tap: <대상>` | 나타날 때까지(10초) 기다렸다 탭. `timeout:` 가능 |
| input | `input: { tap?: <대상>, alert: 글자, confirm: 완료 }` | 시스템 입력 알림(UIAlertController)에 입력 후 버튼 |
| type | `type: { into: <대상>, text: 글자 }` | 입력칸 지우고 입력 |
| wait | `wait: <대상>` / `wait: { for: <대상>, timeout: 초 }` | 나타날 때까지 |
| wait-any | `wait-any: { candidates: { 키: <대상> }, as: 변수, timeout: 초 }` | 먼저 나타난 키를 변수에 |
| if / unless | `if: <조건>` + `then: [단계]` + `else: [단계]`, `timeout:` | 조건 분기 (timeout 동안 조건을 기다림) |
| read | `read: { from: <대상>, pattern: '정규식', as: 변수 }` | 라벨에서 값 추출 (첫 그룹) |
| scroll-to | `scroll-to: { target: <대상>, in: <대상>, max: 8, dir: up, required: false }` | 화면에 보일 때까지 스크롤 |
| swipe | `swipe: { on: <대상>, dir: up }` | |
| pinch | `pinch: { on: <대상>, scale: 2.5, velocity?, settle?: 0.5 }` | 1보다 크면 확대, 작으면 축소. 속도 부호 자동, 기본 속도 `max(4, scale 또는 1/scale)` (동작 1초 안팎). settle: 끝난 뒤 쉬는 초 |
| snapshot | `snapshot: { of: <대상>, as: 이름 }` | 스크린샷 저장·첨부 (changed 조건용) |
| expect | `expect: <조건>`, `timeout:`, `hold:`, `message:` | 판정. hold는 그 시간 동안 유지돼야 통과 |
| repeat | `repeat: { until: <조건>, max: 5, wait: 3, watch?: 설정키, steps: [단계] }` | **처음 실행 전에 조건을 먼저 본다** — 이미 맞으면 한 번도 실행하지 않는다("반복 0번"). 맞을 때까지 최대 max번 반복, 끝까지 안 맞으면 실패 (`required: false`면 통과). `wait`: 매 반복 뒤 조건을 기다리는 최대 초. **`watch`**: 매 반복 뒤 그 앱 설정 값이 바뀌고 1초간 멈출 때까지 최대 `wait`초 기다렸다 판정 — 관성 확대·늦은 저장으로 목표를 넘치는 것을 막는다. 값이 안 바뀌면(한계 도달 등) `wait`초를 다 쓴다 |
| read-pref | `read-pref: { key: 키, as: 변수 }` | 앱 설정(UserDefaults) 값을 변수로 (기록·비교용) |
| hide-keyboard | `hide-keyboard: true` | 키보드 내리기 |
| dump | `dump: 이름`, `settle?: 초` | 지금 화면 구조를 `results/dumps/이름.txt`에 저장. 앱을 다시 켜면 못 가는 화면을 볼 때 (`dump-ui`는 첫 화면만) |
| note / relaunch / fail | `note: 글자` / `relaunch: true` / `fail: 글자` | |

## 대상

| 형식 | 의미 |
|---|---|
| `"ID"` | 자동 ID로 찾기 (`QAIDs.swift`의 값) |
| `{ id, label, contains, type, in: <대상>, index }` | 조합. contains는 대소문자 무시 포함. type: button/cell/text/textField/secureTextField/switch/image/segment/other |
| `{ cell: 셀ID, has: { id?, label?, contains? } }` | 안에 조건에 맞는 요소가 있는 셀 |
| `{ segment: 세그먼트ID, label: 항목 }` | UISegmentedControl 항목 |
| `{ alert-button: 버튼 }` / `{ alert-field: true }` | 시스템 알림 버튼 / 입력칸 |

## 조건

| 조건 | 참이 되는 경우 |
|---|---|
| `exists` / `missing` | 접근성 구조에 있다 / 없다 (화면 밖이어도 "있다") |
| `visible` | 있고, 프레임이 화면 안에 있다 |
| `hidden` | 없거나, 화면 밖에 있다 → **하단 시트·드로어를 닫았는지**는 이걸로 판정 (닫혀도 화면 밖에 남아 exists는 참) |
| `selected` / `hittable` | 있고 선택됨 / 있고 누를 수 있음 |
| `pref: { key, gte\|lte\|gt\|lt\|eq\|ne\|exists }` | 앱 설정(UserDefaults) 값 비교. **화면에 안 나오는 앱 상태**(지도 줌, 모드 등)를 판정할 때. 디스크 반영이 늦을 수 있어 `timeout:`/`wait:`와 함께 쓴다 |

`right-of: [A, B]` (A가 B 가운데보다 오른쪽 — 커스텀 토글 판정 등) · `contains: { target, text }` · `equals: [a, b]`
`changed: { of: <대상>, since: 스냅샷 }` · `not:` · `all: [..]` · `any: [..]`

## 앱 설정값(pref)으로 판정하기

화면에 노출되지 않는 상태도 앱이 UserDefaults에 저장한다면 읽을 수 있다 (시뮬레이터 안 앱 데이터의 `Library/Preferences/<bundleId>.plist`, qakit이 경로를 넘겨 줌).
어떤 키가 있는지는 앱 소스(UserDefaults 키)나 `plutil -p <경로>`로 확인한다.
**앱은 설정을 디스크에 늦게 쓴다 (5초 넘게 걸린 적 있음).** `expect`의 pref 판정은 `timeout: 10~15`, 반복에는 `watch`를 쓴다.

- **시작 값이 오래된 값일 수 있다**: 앱이 직전 변경을 아직 디스크에 안 썼을 수 있다. 화면 조작 직후 시작한다면 `expect: { pref: … }`에 `timeout`을 두거나, 첫 `repeat`가 한 번 더 도는 것을 감안한다.
- **확대와 축소의 효과가 다르다** (지도 앱 측정): 확대는 핀치 한 번에 대략 `log2(scale) × 0.9` 단계(scale 2.5 ≈ +1.1, 10 ≈ +3.2)지만, **축소는 훨씬 작다** (scale 0.25 ≈ −0.7). 축소 반복은 `max`를 넉넉히(8 이상).

```yaml
# 예: 지도를 줌 20 근처까지 확대
- repeat:
    until: { pref: { key: zoom, gte: 17 } }
    watch: zoom          # 핀치 뒤 zoom 값이 갱신될 때까지 기다렸다 판정 (넘침 방지)
    wait: 5
    max: 6
    steps: [ pinch: { on: HomeView.mapView, scale: 10 } ]
- repeat:
    until: { pref: { key: zoom, gte: 19.5 } }
    watch: zoom
    wait: 5
    max: 6
    steps: [ pinch: { on: HomeView.mapView, scale: 2 } ]
```

```yaml
# 예: 지금 줌이 크든 작든 12 근처(11.5~12.5)로 — 큰 핀치로 범위 가까이, 작은 핀치로 양쪽에서 맞춘다
- repeat: { until: { pref: { key: zoom, lte: 13.5 } }, watch: zoom, wait: 8, max: 8, steps: [ pinch: { on: HomeView.mapView, scale: 0.25 } ] }
- repeat: { until: { pref: { key: zoom, gte: 10.5 } }, watch: zoom, wait: 8, max: 6, steps: [ pinch: { on: HomeView.mapView, scale: 4 } ] }
- repeat: { until: { pref: { key: zoom, lte: 12.5 } }, watch: zoom, wait: 8, max: 6, steps: [ pinch: { on: HomeView.mapView, scale: 0.7 } ] }
- repeat: { until: { pref: { key: zoom, gte: 11.5 } }, watch: zoom, wait: 8, max: 6, steps: [ pinch: { on: HomeView.mapView, scale: 1.5 } ] }
- expect: { all: [ { pref: { key: zoom, gte: 11.5 } }, { pref: { key: zoom, lte: 12.5 } } ] }
  timeout: 15
```

## 기본 대기 시간

| 단계 | 기본 | 비고 |
|---|---|---|
| `tap`, `wait`, `read` | 10초 | 대상이 나타날 때까지 |
| `wait-any` | 30초 | |
| `input` 알림 | 5초 | |
| `expect`, `if`, `unless` | **0초 (바로 판정)** | 화면 전환 직후라면 `timeout:`을 꼭 적는다 (예: 닫기 뒤 `hidden`은 `timeout: 5`) |

## 변수

- `vars`와 `read ... as:`, `wait-any ... as:`의 값은 **글자만** 된다. 대상(맵)을 변수에 넣어 재사용할 수는 없다 → 같은 대상은 그대로 다시 쓴다.
- 비밀값은 `{secret:KEY}`로만 쓰고, `note`에 넣지 않는다.

## 쓰는 기준

- **`name:`과 그 아래 맨 위 주석 1~2줄이 QA 폴더 README의 설명이 된다** (qakit이 자동으로 목록을 만든다). 무엇을 확인하는지 짧게 쓰고, 자세한 메모는 한 줄 띄워 그 아래에 쓴다.
- 만들기 전에 `scenarios/`, `steps/`, `Runner/UITests/Flows/`에 **같은 시나리오·단계가 이미 있는지** 본다.
- NOTES.md나 Swift Page에 적힌 헬퍼(예: `openMenu()`)는 Swift용이다. 시나리오 파일에서는 그 Page 소스(`Runner/UITests/Pages`)에 적힌 ID를 그대로 쓴다.

- 대부분의 시나리오는 이 파일로 쓴다 (AI가 만들고, 실행·복구는 파일만으로).
- 계산·복잡한 판정이 필요하면 Swift(`Runner/UITests/Flows`)로 쓴다.
- YAML 주의: 들여쓰기는 공백, `{}`·`[]` 안 글자에 `,`가 있으면 따옴표, 정규식은 작은따옴표 `'/(\d+)$'`.
