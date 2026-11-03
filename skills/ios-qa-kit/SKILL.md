---
name: ios-qa-kit
description: iOS 앱의 QA 시나리오를 XCUITest로 만들고, 돌리고, 고친다. 앱 코드를 수정하지 않고 시뮬레이터에서 자동으로 붙는 accessibilityIdentifier(타입.프로퍼티 경로)와 qakit CLI를 쓴다. 사용자가 "이 화면 테스트 만들어줘", "QA 시나리오 자동화", "UI 테스트 돌려줘", "XCUITest 작성", "로그인부터 ○○까지 확인하는 테스트", "테스트 깨진 거 고쳐줘", "앱 바뀌었는데 테스트 최신화"처럼 요청하거나, 폴더에 qakit.yml이 있거나, 스킬을 직접 호출할 때(Codex `$ios-qa-kit`, Claude Code `/ios-qa-kit`) 사용한다. 스크린샷을 보며 앱을 직접 조작하는 computer use QA 대신 이 스킬로 재실행 가능한 테스트를 남긴다. 앱 기능 개발이나 단위 테스트에는 쓰지 않는다.
---

# ios-qa-kit: AI가 XCUITest를 만들고 돌리는 방법

목표는 **한 번 만들면 토큰 없이 계속 돌릴 수 있는 테스트**를 남기는 것이다. 화면은 스크린샷이 아니라 텍스트(ID 상수, 화면 덤프)로 파악한다.

- CLI: `qakit` (PATH에 없으면 `<skill-dir>/../../bin/qakit`). 모든 명령은 작업공간 폴더(`qakit.yml`이 있는 곳)에서 실행한다.
- API·명령 상세: [references/qakit-api.md](references/qakit-api.md), [references/cli.md](references/cli.md)
- **시나리오 언어(.qa.yml)**: [references/scenario-language.md](references/scenario-language.md)
- 문제 해결: [references/troubleshooting.md](references/troubleshooting.md)

## 절대 규칙

1. **대상 앱 레포를 수정하지 않는다.** 테스트·Page·노트는 작업공간에만 쓴다. ID가 없으면 앱에 ID를 추가하지 말고 라벨이나 좌표로 찾는다.
2. **도구 레포(ios-qa-kit)에 앱 전용 코드를 넣지 않는다.** 범용 기능이 필요하면 사용자에게 제안한다.
3. **되돌릴 수 없는 동작은 사용자 승인 없이 테스트에 넣지 않는다.** 회원탈퇴, 결제, 데이터 삭제, 실제 메시지·신고 전송, 다른 사용자에게 보이는 변경 등. 승인받으면 `NOTES.md`에 날짜와 함께 기록한다.
4. **비밀값은 `QASecrets`로만 읽고** 출력·로그·note·테스트 이름에 넣지 않는다. secrets.txt를 직접 열어 값을 읽지 않는다 (키 확인은 `qakit doctor`).
5. **`sleep` 금지.** `waitForExistence`, `QAWait.forAny`, `BasePage.waitUntilDisplayed`를 쓴다.
6. **ID는 문자열로 쓰지 않고 `QAID` 상수로 쓴다.** 상수가 없는 요소만 라벨(`text("…")`)로 찾는다.

## 1. 시작

```bash
cd <작업공간>          # qakit.yml 위치. 모르면: find ~ -maxdepth 4 -name qakit.yml
qakit doctor           # ❌가 있으면 → 안내대로 해결
```

작업공간이 없으면 `qakit init <앱 프로젝트 경로>` → 결과 안내를 따른다 (qakit.yml 확인, secrets.txt는 사용자가 작성).

**반드시 먼저 읽는다:** `qakit.yml`, `NOTES.md` (앱 특이사항: 진입 흐름, 상태 판별 기준, 자주 뜨는 팝업, ID 없는 영역), 그리고 `Runner/UITests/Flows/`의 기존 공통 단계(예: 로그인). **이미 있는 단계를 다시 만들지 않는다.**

## 2. 화면 파악 (싼 것부터)

1. **ID 상수 검색** — `Runner/UITests/Generated/QAIDs.swift`는 크다. 통째로 읽지 말고 화면 enum만 찾는다.
   ```bash
   grep -n "enum .*ViewController " Runner/UITests/Generated/QAIDs.swift      # 화면(VC) 목록
   grep -n "enum SearchView " -A40 Runner/UITests/Generated/QAIDs.swift       # 한 화면의 ID
   ```
   VC 이름을 모르면 앱 소스에서 키워드로 찾는다: `grep -rl "검색" <앱>/ --include='*.swift' | head` (zsh에서는 글롭을 따옴표로 감싼다)
2. **앱 소스 읽기** — 화면 전환 구조를 확인한다. ID 상수만으로는 알 수 없다.
   - 버튼 → 액션: VC의 `bind`/`rx.tap`/`addTarget` → ViewModel → Coordinator/Router 순으로 따라간다.
   - 확인할 것: **push / modal / 같은 화면 안 교체(시트·탭)** 중 무엇인지, 뒤로·닫기가 **어디로** 돌아가는지.
   - **상수가 있다고 화면에 보이는 것은 아니다.** 공통 컴포넌트의 버튼(예: back/close 둘 다 선언)은 화면마다 일부만 붙는다. 실제로 보이는지는 소스의 `isHidden`/`addSubview` 또는 덤프로 확인한다.
3. **화면 덤프** — 실제 구조·라벨·좌표가 필요할 때. **화면 enum에 ID가 몇 개 없으면**(목록·탭바처럼 UIKit 기본 컴포넌트 위주 화면) 위치 규칙 ID와 라벨을 봐야 하므로 덤프를 먼저 한다.
   - 첫 화면: `qakit dump-ui --wait-id <QAID 문자열>`
   - 깊은 화면: 그 화면까지 가는 테스트를 먼저 돌린 뒤 `qakit dump-ui --attach` (앱이 떠 있는 화면 그대로 덤프)
   - 결과: `results/ui-dump.txt` (`#ID "라벨" @x,y WxH`). 맨 위에 ID 커버리지와 ID 없는 요소 목록이 있다.
4. 스크린샷은 덤프로 판단이 안 될 때만 본다 (실패 요약에 경로가 있다).

## 3. 작성

**먼저 시나리오 파일(`scenarios/<이름>.qa.yml`)로 쓸 수 있는지 본다** — 컴파일·프로젝트 없이 실행되고, 저장·복구가 파일만으로 된다.
여러 시나리오가 쓰는 단계는 `steps/<이름>.qa.yml`로 빼고 `- use: <이름>`으로 부른다 (기존 steps를 먼저 확인).
`qakit check <이름>` → `qakit run <이름>` 순서로 돌린다. 문법: [references/scenario-language.md](references/scenario-language.md).
조건·계산이 언어로 표현이 안 될 때만 아래 Swift 방식으로 쓴다.

파일 위치와 역할:

| 위치 | 내용 |
|---|---|
| `Runner/UITests/Pages/<화면>Page.swift` | 화면 하나 = `BasePage` 하나. `anchor`(화면 대표 요소)와 요소·동작. 셀렉터는 여기에만 |
| `Runner/UITests/Flows/<시나리오>Tests.swift` | `QATestCase` 상속 테스트. Page만 사용 |
| `Runner/UITests/Flows/*Steps.swift` | 여러 테스트가 쓰는 공통 단계 (`extension QATestCase`) |
| `Runner/UITests/Generated/` | 자동 생성. 수정 금지 |

```swift
// 아래 이름(ItemListView 등)은 설명용 가상 이름이다. 실제 이름은 QAIDs.swift에서 grep으로 찾는다.
final class ItemListPage: BasePage {
    // 일반 요소: 상수 그대로
    override var anchor: XCUIElement { el(QAID.ItemListView.titleLabel) }
    // 복합 컴포넌트(하위 enum이 있는 것): .id
    var searchBox: XCUIElement { el(QAID.ItemListView.searchBox.id) }
    // 입력칸: 실제 TextField 타입 쿼리 + 컴포넌트 안쪽 상수
    var searchField: XCUIElement { app.textFields[QAID.ItemListView.searchBox.textField] }
    // 셀: 셀 타입 .id, 같은 셀이 여러 개면 셀 안 라벨로
    func item(_ title: String) -> XCUIElement {
        cell(QAID.ItemCell.id, labelID: QAID.ItemCell.titleLabel, label: title)
    }
}

final class ItemListFlowTests: QATestCase {
    func test_openList_showsItems() throws {
        launchApp()
        try ensureLoggedIn()                       // 기존 공통 단계 재사용 (Flows/*Steps.swift)
        let page = ItemListPage(app)
        try step("목록 열기") {
            HomePage(app).openListButton.waitAndTap()   // 셀렉터는 Page에만, 테스트는 Page를 통해
            guard page.isDisplayed(timeout: 10) else {
                XCTFail("목록 화면이 10초 안에 뜨지 않음")
                throw QAError.timeout("item list")   // step 안에서 중단할 때
            }
        }
        XCTAssertTrue(page.item("첫 항목").exists, "'첫 항목'이 보여야 함")
        note("항목 \(app.cells.matching(identifier: QAID.ItemCell.id).count)개")
    }
}
```

**QAID 사용 규칙** — `QAIDs.swift` 구조 그대로다:
- `static let x = "…"` → `QAID.Screen.x` (문자열 상수)
- `enum x { static let id … }` (하위 요소가 있는 복합 컴포넌트, 셀) → 그 요소 자체는 `QAID.Screen.x.id`, 안쪽은 `QAID.Screen.x.child`
- 이름을 추측하지 말고 grep 결과에 있는 이름만 쓴다. 없는 이름은 컴파일 에러로 바로 드러난다.

원칙:
- 테스트 하나는 독립적으로 돌아야 한다 (다른 테스트가 만든 상태에 기대지 않는다). 시작은 `launchApp()` + 공통 진입 단계.
- 단계는 `step("…")`로 감싼다 → 실패 요약에 "어디까지 갔는지"로 나온다. 판단 결과는 `note()`로 남긴다.
- 실패 메시지는 사람이 읽고 바로 이해하게 쓴다: `XCTAssertTrue(x, "검색 결과가 1건 이상이어야 함")`.
- ID 이름 규칙 (자동 부여):

  | 대상 | ID | QAID 상수 |
  |---|---|---|
  | VC의 뷰 프로퍼티 | `VC타입.프로퍼티` | 있음 |
  | VC가 가진 뷰의 자식 / 그 안쪽 | `뷰타입.프로퍼티` / `상위ID.프로퍼티` | 있음 |
  | 앱 셀 자체 | `셀타입` (여러 개 → 라벨로 `cell(…)`) | 있음 (`.id`) |
  | Collection/TableViewController의 목록 | `VC타입.collectionView` / `.tableView` | 있음 |
  | UIKit 기본 셀·섹션 헤더 | `<목록 ID>.cell` / `.header` / `.footer` | 없음 → 문자열 `QAID.X.collectionView + ".cell"` |
  | 탭바 버튼 | `Tab.<탭 첫 화면 VC타입>` | 없음 → `"Tab.SettingsViewController"` |
  | 바 버튼 | 프로퍼티면 `VC.프로퍼티`, 아니면 `VC.nav.left.0` / `VC.nav.right.0` / `VC.toolbar.0` | 프로퍼티만 |
  | 검색창 입력칸 | `<검색창 ID>.textField` | 없음 |
  | 지역 변수로 만든 뷰, 외부 SDK가 만든 뷰 | 없음 → 라벨 | — |
- 입력칸은 컴포넌트 안쪽의 실제 TextField ID를 쓴다 (예: `…emailTextField.textField.textField`). 덤프에서 `TextField`/`SecureTextField` 타입을 확인한다.
- 그림으로 그리는 영역(지도, 차트, 캔버스)은 내부 요소가 없다 → 좌표(`app.coordinate(withNormalizedOffset:)`)로 조작하고, 결과는 그 위의 UI로 확인한다.
- 팝업이 떠 있으면 아래 화면 요소가 접근성 구조에서 사라질 수 있다 → 팝업을 먼저 처리하고 NOTES에 적는다.
- **"닫혔다" 판정**: 하단 시트·드로어처럼 닫혀도 화면 밖에 남는 화면은 `exists`가 계속 true다 → `page.waitUntilGone()` / `page.isVisibleOnScreen`을 쓴다. 판정에 쓴 근거를 note로 남긴다.
- **같은 ID가 여러 개인 시스템 셀·섹션 헤더**(덤프에서 헤더도 `Cell` 타입으로 나온다)는 ID와 라벨을 함께 건다:
  `app.cells.matching(NSPredicate(format: "identifier == %@ AND label == %@", QAID.X.collectionView + ".header", "제목")).firstMatch`
  (`cell(_:labelID:label:)`은 셀 *안의 라벨*에 ID가 있는 앱 셀용이다)
- **탭바**: 탭 버튼은 `app.buttons["Tab.<탭 첫 화면 VC>"]`. 선택 상태는 `isSelected`로 판정한다. 탭바 자체는 Page로 만들지 말고 탭 버튼 묶음 헬퍼(일반 struct)로 두고, 각 탭 화면을 Page로 만든다.
- **탭 전환 판정**: 이전 탭 화면은 보통 접근성 구조에서 빠진다 → 새 탭 Page `isDisplayed` + 이전 탭 Page `isVisibleOnScreen == false` + 탭 버튼 `isSelected`.
- `isVisibleOnScreen`은 Page에서는 속성(`page.isVisibleOnScreen`), 요소에서는 함수(`element.isVisibleOnScreen(in: app)`)다.
- `Pages/`, `Flows/`에 새 Swift 파일을 만들면 `qakit test`가 프로젝트에 자동으로 포함한다 (Xcode 프로젝트를 직접 고치지 않는다).

## 4. 실행 → 고치기 루프

```bash
qakit test SearchFlowTests                    # 클래스
qakit test SearchFlowTests/test_search_showsResults
qakit test --reset FreshLoginTests            # 앱 재설치+키체인 초기화 후 (로그아웃 상태가 필요할 때)
```

- 앱 소스가 바뀌었으면 `qakit test`가 먼저 알아서 재빌드·ID 재생성한다.
- 실패하면 출력된 요약(원인 / 마지막 단계 / 실패 시점 화면 구조)을 읽고 고친다. 더 필요하면 `qakit summarize`.
- 컴파일 에러는 테스트 실행 전에 원인만 출력된다 → 그대로 고친다.
- **같은 원인으로 3번 고쳐도 안 되면 멈추고** 사용자에게 상황(시도한 것, 화면 구조 근거)을 보고한다. 앱 버그로 보이면 테스트를 앱에 맞추지 말고 버그로 보고한다.
- 테스트가 지나치게 느리면(시나리오당 60초 이상) 기다림 시간·불필요한 재실행을 줄인다.

## 5. 마무리

- `qakit save -m "무엇을 만들었나"` — 결과물 목록·해시(qa.lock.json)와 보관소 복사. 이후 복구는 AI 없이 `qakit restore`.

- 새로 알게 된 것을 `NOTES.md`에 적는다: 진입 흐름, 상태 판별 anchor, 새 팝업과 처리법, ID 없는 영역, 사용자 결정.
- 사용자에게 보고: 만든/고친 테스트, 통과 여부(`qakit test` 출력 근거), 실행 횟수, 남은 문제.
- 커밋은 사용자가 요청할 때만.

## 앱이 바뀌었을 때

`qakit sync` → 출력의 순서대로 처리한다.
1. **ID 변경 목록** (`- 삭제`, `+ 추가`): 삭제된 ID를 쓰던 Page를 새 ID로 바꾼다. 이름만 바뀐 경우가 많다 (`- X.submitButton` / `+ X.confirmButton`).
2. **컴파일 실패 위치**: 위 변경 때문이면 Page를 고친다.
3. 그다음 `qakit test`로 동작(흐름·팝업) 변경을 확인하고 4번 루프로 고친다.
4. 다른 브랜치 폴더(워크트리)를 검증할 때: `qakit --app <앱 폴더> test …`. 끝나면 원래 앱 기준으로 `qakit sync`.
