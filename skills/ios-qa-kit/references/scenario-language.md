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
| pinch | `pinch: { on: <대상>, scale: 2.5 }` | 1보다 크면 확대 |
| snapshot | `snapshot: { of: <대상>, as: 이름 }` | 스크린샷 저장·첨부 (changed 조건용) |
| expect | `expect: <조건>`, `timeout:`, `hold:`, `message:` | 판정. hold는 그 시간 동안 유지돼야 통과 |
| hide-keyboard | `hide-keyboard: true` | 키보드 내리기 |
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

`exists` · `missing` · `visible`(화면 안) · `hidden` · `selected` · `hittable`: <대상>
`right-of: [A, B]` (A가 B 가운데보다 오른쪽 — 커스텀 토글 판정 등) · `contains: { target, text }` · `equals: [a, b]`
`changed: { of: <대상>, since: 스냅샷 }` · `not:` · `all: [..]` · `any: [..]`

## 쓰는 기준

- 대부분의 시나리오는 이 파일로 쓴다 (AI가 만들고, 실행·복구는 파일만으로).
- 계산·복잡한 판정이 필요하면 Swift(`Runner/UITests/Flows`)로 쓴다.
- YAML 주의: 들여쓰기는 공백, `{}`·`[]` 안 글자에 `,`가 있으면 따옴표, 정규식은 작은따옴표 `'/(\d+)$'`.
