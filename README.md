# ios-qa-kit

**앱 코드를 한 줄도 고치지 않고** iOS 앱에 XCUITest를 붙이고, AI가 그 테스트를 쉽게 만들고 고칠 수 있게 해 주는 도구입니다.

- 시뮬레이터에서 앱을 실행할 때 작은 라이브러리를 끼워 넣어, 화면 요소마다 `LoginView.loginButton` 같은 **ID를 자동으로** 붙입니다 (Swift 프로퍼티 이름 기반).
- 앱 소스를 읽어 그 ID를 **Swift 상수(`QAID`)** 로 만들어 줍니다. 앱에서 이름이 바뀌면 테스트가 컴파일 에러로 바로 알려 줍니다.
- `qakit` 명령 하나로 빌드·설치·실행·실패 요약까지 합니다. 실패 요약은 텍스트라서 AI가 스크린샷 없이 읽고 고칠 수 있습니다.
- Claude Code / Codex용 **스킬**이 들어 있어서, "이 시나리오 테스트 만들어줘"라고 말하면 AI가 규칙대로 작성하고 통과할 때까지 고칩니다.

> computer use(스크린샷 보며 조작)로 QA하면 매번 토큰이 듭니다. 이 도구는 **AI가 한 번 테스트를 만들고, 이후 실행은 토큰 없이** 반복하게 하는 게 목적입니다.

---

## 동작 방식

```
 앱 (수정 없음)                       작업공간 (앱별 QA 폴더)
 ┌──────────────────┐   빌드·설치    ┌─────────────────────────────┐
 │ iOS 앱 프로젝트    │ ───────────▶ │ qakit.yml  (앱 경로·scheme)   │
 └──────────────────┘              │ secrets.txt (테스트 계정)      │
          │ 소스 읽기                │ NOTES.md   (앱 특이사항)       │
          ▼                         │ Runner/UITests/              │
   QAIDs.swift (ID 상수) ─────────▶ │   Pages/  화면별 Page Object   │
                                    │   Flows/  시나리오 테스트       │
 시뮬레이터에서 실행 시               └─────────────────────────────┘
 AutoID.dylib 주입 → 화면 요소에 ID 자동 부여 → XCUITest가 ID로 찾음
```

- **도구 레포 (`ios-qa-kit`)**: 어느 앱에나 쓰는 범용 코드만 있습니다.
- **작업공간 (`qa-workspaces/<앱>`)**: 앱 하나의 설정·계정·테스트. `qakit init`이 만들어 줍니다.

---

## 준비물

| 항목 | 확인 |
|---|---|
| macOS + Xcode (16 이상, 26.6에서 검증) | `xcodebuild -version` |
| iOS 시뮬레이터 | `xcrun simctl list devices available` |
| Python 3 (macOS 기본) | `python3 --version` |
| XcodeGen | `brew install xcodegen` |
| UIKit 앱 | SwiftUI 화면은 자동 ID가 붙지 않습니다 (아래 [한계](#한계) 참고) |

---

## 빠른 시작 (처음 한 번, 약 10분)

### 1. 설치

```bash
git clone <이 레포> ~/ios-qa-kit        # 원하는 위치
~/ios-qa-kit/bin/qakit install-skill
```

`install-skill`은 다음을 **심볼릭 링크**로 설치합니다 (레포를 고치면 바로 반영, 제거는 `--uninstall`).

- `qakit` 명령 → `~/.local/bin/qakit` (PATH에 없으면 안내가 나옵니다)
- Claude Code 스킬 → `~/.claude/skills/ios-qa-kit` (`/ios-qa-kit`)
- Codex 스킬 → `~/.agents/skills/ios-qa-kit` (`$ios-qa-kit`)

### 2. 앱에 작업공간 만들기

```bash
qakit init ~/path/to/MyApp            # .xcodeproj / .xcworkspace 또는 그 폴더
```

scheme, configuration, bundle ID를 자동으로 찾아 `~/path/to/qa-workspaces/myapp/`을 만듭니다 (`--dir`로 위치 지정 가능). 출력된 값이 맞는지 `qakit.yml`을 열어 확인하세요.

```yaml
app:
  project: ~/path/to/MyApp/MyApp.xcodeproj
  scheme: MyApp-Dev
  configuration: Debug
  bundleId: com.example.myapp.dev
simulator: iPhone 17
permissions: [location-always]     # 테스트 전에 미리 허용할 권한 (위치·사진 등)
```

### 3. 점검 → 빌드 → 첫 화면 보기

```bash
cd ~/path/to/qa-workspaces/myapp
qakit doctor        # ❌가 있으면 → 안내대로
qakit build-app     # 앱 빌드 + 시뮬레이터 설치 (처음엔 몇 분)
qakit dump-ui       # 첫 화면 구조 → results/ui-dump.txt
```

`results/ui-dump.txt` 맨 위에 **ID 커버리지**(누를 수 있는 요소 중 ID가 붙은 비율)가 나옵니다.

```
# interactive: 8, with auto/app ID: 8 (100%)
Button #LoginView.loginButton "로그인" @16,682 370x56
TextField #LoginView.emailField.textField @28,496 346x28
```

### 4. 로그인이 필요한 앱이면 계정 넣기

```bash
cp secrets.example.txt secrets.txt    # git에 올라가지 않습니다
```

```
EMAIL=qa@example.com
PASSWORD=...
```

키 이름은 자유입니다. `secrets.example.txt`에 적은 키는 `qakit doctor`가 빠졌는지 검사합니다.

### 5. 첫 테스트

**AI에게 맡기기 (권장)** — 작업공간 폴더에서 Claude Code / Codex를 열고:

```
/ios-qa-kit 로그인 화면에서 테스트 계정으로 로그인하면 홈 화면이 뜨는지 확인하는 테스트 만들어줘
```

AI는 스킬 규칙대로 ID 상수를 찾고, Page와 테스트를 만들고, `qakit test`가 통과할 때까지 고칩니다.

**직접 쓰기** — `Runner/UITests/Pages/LoginPage.swift`

```swift
import QAKit
import XCTest

final class LoginPage: BasePage {
    override var anchor: XCUIElement { el(QAID.LoginView.loginButton) }      // 이 화면의 대표 요소
    var email: XCUIElement { app.textFields[QAID.LoginView.emailField.textField] }
    var password: XCUIElement { app.secureTextFields[QAID.LoginView.passwordField.textField] }
}
```

`Runner/UITests/Flows/LoginTests.swift`

```swift
import QAKit
import XCTest

final class LoginTests: QATestCase {
    func test_login() throws {
        launchApp()
        let page = LoginPage(app).waitUntilDisplayed()
        try step("로그인 입력") {
            page.email.clearAndType(try QASecrets.require("EMAIL"))
            page.password.clearAndType(try QASecrets.require("PASSWORD"))
            page.anchor.tap()
        }
        XCTAssertTrue(HomePage(app).isDisplayed(timeout: 20), "로그인 후 홈 화면이 떠야 함")
    }
}
```

```bash
qakit test LoginTests
```

새 파일은 자동으로 프로젝트에 포함됩니다. 실패하면 원인·마지막 단계·실패 시점 화면 구조가 바로 출력됩니다.

---

## 자동으로 붙는 ID 규칙

ID는 **"누가 이 뷰를 프로퍼티로 갖고 있나"** 로 정해집니다.

| 대상 | ID | 예시 |
|---|---|---|
| VC의 뷰 프로퍼티 | `VC타입.프로퍼티` | `LoginViewController.rootView` |
| VC가 가진 커스텀 뷰의 자식 | `뷰타입.프로퍼티` | `LoginView.loginButton` |
| 커스텀 뷰 안의 커스텀 뷰 자식 | `상위ID.프로퍼티` | `LoginView.emailField.textField` |
| 앱 셀 | `셀타입` (여러 개면 라벨로 구분) | `OrderCell` |
| Collection/TableViewController의 목록 | `VC타입.collectionView` | `ListViewController.collectionView` |
| UIKit 기본 셀·섹션 헤더 | `목록ID.cell` / `.header` / `.footer` | `ListViewController.collectionView.header` |
| 탭바 버튼 | `Tab.탭첫화면VC타입` | `Tab.SettingsViewController` |
| 내비게이션 바 버튼 | 프로퍼티면 `VC.프로퍼티`, 아니면 `VC.nav.right.0` | `EditViewController.nav.right.0` |
| 검색창 입력칸 | `검색창ID.textField` | `ListView.searchBar.textField` |

- 앱이 직접 붙인 `accessibilityIdentifier`는 절대 덮어쓰지 않습니다.
- 테스트에서는 문자열 대신 `QAID` 상수를 씁니다: `QAID.LoginView.loginButton`. 하위 요소가 있는 컴포넌트는 `.id` (예: `QAID.LoginView.emailField.id`).
- 상수 파일(`Runner/UITests/Generated/QAIDs.swift`)은 큽니다. 필요한 화면만 찾으세요: `grep -n "enum LoginView " -A30 Runner/UITests/Generated/QAIDs.swift`

---

## 명령 요약

작업공간 폴더에서 실행합니다.

| 명령 | 하는 일 |
|---|---|
| `qakit init <앱>` | 작업공간 생성 (scheme·bundle ID 자동 탐지) |
| `qakit doctor` | 환경·설정·계정 키 점검 |
| `qakit build-app` | 앱 빌드 → 시뮬레이터 설치 → 권한 허용 |
| `qakit dump-ui [--attach] [--wait-id ID]` | 화면 구조를 텍스트로 (`--attach`: 지금 떠 있는 화면) |
| `qakit test [클래스[/테스트]] [--reset]` | 테스트 실행 (`--reset`: 앱 재설치+키체인 초기화 = 로그아웃 상태) |
| `qakit summarize` | 마지막 실패 요약 다시 보기 |
| `qakit sync` | 앱 변경 반영 (재빌드 + ID 재생성 + 테스트 코드 컴파일 확인) |
| `qakit gen-ids [--verify]` | ID 상수 생성 (`--verify`: 실제 화면 ID와 비교) |
| `qakit install-skill [--uninstall]` | 스킬·명령 설치/제거 |

전역 옵션: `--app <다른 앱 폴더>` (다른 브랜치 워크트리 검증), `--secrets <파일>` (다른 계정), `-w <작업공간>`.

상세: [skills/ios-qa-kit/references/cli.md](skills/ios-qa-kit/references/cli.md), QAKit API: [qakit-api.md](skills/ios-qa-kit/references/qakit-api.md)

---

## 앱이 바뀌었을 때

따로 할 일이 거의 없습니다. `qakit test`가 실행 전에 앱 상태(경로·브랜치·커밋·미커밋 변경)를 마지막 빌드와 비교하고, 바뀌었으면 **재빌드 → ID 재생성**을 먼저 합니다.

```
🔄 앱 변경 감지 (브랜치 develop → feature/new-login) → 동기화
   ID 변경: 추가 1, 삭제 1
     - LoginView.loginButton
     + LoginView.signInButton
❌ Runner/UITests/Pages/LoginPage.swift:5: 'QAID.LoginView' has no member 'loginButton'
```

- 삭제·추가 목록을 보고 Page의 상수만 바꾸면 됩니다 (AI에게 "`qakit sync` 결과대로 테스트 고쳐줘").
- 다른 브랜치 폴더(git worktree)를 검증: `qakit --app ~/path/MyApp-release test`
- 자동 동기화를 끄려면 `qakit.yml`에 `sync: warn` (알리기만) 또는 `off`.

---

## 원칙

- **대상 앱 레포를 수정하지 않습니다.** 빌드할 때도 `Package.resolved`를 고치지 않도록 고정하고, 빌드 전후로 앱 레포에 바뀐 파일이 있으면 경고합니다.
- **비밀값은 `secrets.txt`에만.** 테스트 출력·로그·실패 요약에서 비밀값은 `•••`로 가려집니다. (단, Xcode 결과 파일 `results/*.xcresult`에는 입력 기록이 남으니 공유하지 마세요. `results/`는 git에서 제외됩니다.)
- **되돌릴 수 없는 동작**(탈퇴·결제·삭제·실제 전송)은 사람이 승인한 경우에만 테스트에 넣고 `NOTES.md`에 기록합니다.
- 테스트끼리 상태를 공유하지 않습니다. 공통 진입(로그인 등)은 `Flows/*Steps.swift`에 한 번만 만들어 재사용합니다.

---

## 한계

| 경우 | 대신 |
|---|---|
| 지역 변수로 만든 뷰 (`let label = UILabel(); addSubview(label)`) | 화면 글자로 찾기: `text("확인")` |
| 외부 SDK가 내부에서 만든 뷰 (예: 지도 SDK의 버튼) | 화면 글자 또는 좌표 |
| 지도·차트·캔버스처럼 그려지는 영역 | 좌표로 조작, 결과는 그 위의 UI로 확인 |
| SwiftUI 화면 | 지원 안 함 (UIKit 전용) |
| 실기기 | 자동 ID 주입은 시뮬레이터 전용. 실기기는 `AutoID/AutoID.swift`를 앱 Debug 빌드에 넣고 `QAAutoID.start()` 호출 (`qakit.yml: autoid: embedded`) |

문제가 생기면: [troubleshooting.md](skills/ios-qa-kit/references/troubleshooting.md)

---

## 레포 구조

```
ios-qa-kit/
├── bin/qakit                 CLI (Python 3 표준 라이브러리만)
├── AutoID/                   자동 ID 라이브러리 (시뮬레이터 주입용 dylib)
├── Sources/QAKit/            테스트용 Swift 라이브러리 (BasePage, QATestCase, QAWait …)
├── Tools/gen-ids/            앱 소스 → QAID 상수 생성기
├── templates/workspace/      qakit init이 복사하는 작업공간 틀
├── skills/ios-qa-kit/        AI 스킬 (SKILL.md + references)
├── scripts/build-autoid.sh
└── docs/PLAN.md              설계·진행 기록
```

## 검증 현황

| 앱 | 결과 |
|---|---|
| 앱 A (UIKit + RxSwift + SnapKit, 로그인 있음) | 로그인 화면 ID 100%, 메인 92%. 로그인·재실행·메뉴·검색 테스트 5개 통과. 새 AI 세션이 스킬만 보고 시나리오 2개를 첫 실행에 통과 |
| 앱 B (UIKit, 리스트·탭바 위주) | 첫 화면 ID 100%. init → build → dump → 생성 ID 검증 → 기본 테스트 통과 |
