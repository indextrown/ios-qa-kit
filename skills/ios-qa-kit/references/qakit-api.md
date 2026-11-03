# QAKit API

테스트 코드에서 `import QAKit`. 모든 타입은 `@MainActor`.

## QATestCase (테스트 기본 클래스)

| 멤버 | 설명 |
|---|---|
| `app: XCUIApplication!` | 테스트 중인 앱 |
| `launchApp(arguments:environment:)` | 앱 새로 실행 (데이터 유지). 자동 ID 주입·언어 고정 포함 |
| `step("이름") { … }` | 단계 기록 (throws 가능). 실패 요약의 "마지막 단계" |
| `note("텍스트")` | 결과에 메모. 콘솔에 `[qakit-note]`로도 출력 |
| 자동 | `continueAfterFailure = false`, 시스템 권한 팝업 자동 허용, 실패 시 화면 구조·스크린샷 첨부 |

## BasePage

```swift
final class XPage: BasePage {
    override var anchor: XCUIElement { el(QAID.XView.titleLabel) }   // 필수
}
```

| 멤버 | 설명 |
|---|---|
| `el(_ id: String)` | ID로 요소 (타입 무관, 첫 번째) |
| `text(_ label: String)` | 라벨로 요소 (ID 없을 때) |
| `isDisplayed(timeout:)` | anchor 존재 여부 (timeout 0이면 즉시) |
| `isVisibleOnScreen` | anchor가 존재하고 화면 안에 있는지 (시트·드로어 판정) |
| `waitUntilGone(timeout:)` | 사라지거나 화면 밖으로 나갈 때까지 대기 → Bool |
| `cell(_ cellID:, labelID:, label:)` | 같은 셀 여러 개 중 셀 안 라벨로 하나 |
| `waitUntilDisplayed(timeout:)` | 안 뜨면 실패 |
| `app` | XCUIApplication |

타입이 중요한 요소는 쿼리를 직접 쓴다: `app.textFields[QAID…]`, `app.secureTextFields[…]`, `app.cells.matching(identifier: QAID.Cell.id).element(boundBy: 0)`.

## 대기·입력

| API | 설명 |
|---|---|
| `QAWait.forAny(["a": el1, "b": el2], timeout:)` | 먼저 나타난 키 (없으면 nil). 분기 판단용 |
| `QAWait.forDisappear(el, timeout:)` | 사라질 때까지 (exists 기준) |
| `QAWait.forOffscreen(el, in: app, timeout:)` | 사라지거나 화면 밖으로 나갈 때까지 |
| `el.isVisibleOnScreen(in: app)` | 존재 + 화면 안 (exists는 화면 밖 요소도 true) |
| `el.waitAndTap(timeout:)` | 기다렸다 탭, 없으면 실패 |
| `el.clearAndType(text, timeout:)` | 지우고 입력 |
| `el.waitForExistence(timeout:)` | XCTest 기본 |

## 비밀값·설정

| API | 설명 |
|---|---|
| `try QASecrets.require("KEY")` | 필수 비밀값. 없으면 키·파일 안내와 함께 실패 |
| `QASecrets.value("KEY")` | 선택 비밀값 |
| `QAConfig.value("NAME")` | CLI가 넘긴 값 (예: `--reset` → `QAConfig.value("RESET") == "1"`) |

## 오류

| API | 설명 |
|---|---|
| `QAError.timeout("무엇")` | 기다리던 것이 안 나타나 step을 중단할 때 `XCTFail(...)` 후 `throw` |
| `QAError.missingSecret(key)` | `QASecrets.require`가 던짐 |

`step`은 throws를 전달한다: `try step("…") { … throw QAError.timeout("…") }`. 테스트 함수는 `throws`로 선언한다.

## 팝업·덤프

| API | 설명 |
|---|---|
| `QAInterruptions.dismissSystemAlerts()` | 지금 뜬 시스템 팝업 닫기 |
| `try QADump.run(app: app)` | 테스트 안에서 현재 화면 덤프 → `results/ui-dump.txt` |

## XCUITest 기본기

- 스크롤: `el.swipeUp()`, 보일 때까지: `while !el.isHittable { scroll.swipeUp() }` (횟수 제한 둘 것)
- 좌표 탭: `app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()`
- 길게 누르기: `el.press(forDuration: 1.0)`
- 키보드 내리기: `app.keyboards.buttons["Return"]` 또는 빈 곳 탭
- 앱 재실행: `app.terminate(); launchApp()`
