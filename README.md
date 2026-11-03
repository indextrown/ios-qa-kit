# ios-qa-kit

**앱 코드를 한 줄도 고치지 않고** iOS 앱에 XCUITest를 붙이고, AI가 테스트를 만들고 고치게 하는 도구입니다.

> [!TIP]
> **한 줄 요약** — AI가 시나리오를 한 번 테스트로 만들어 두면, 이후에는 `qakit test` 한 줄로 **토큰 없이** 계속 돌립니다.
> computer use(스크린샷 보며 조작)처럼 매번 AI 비용이 들지 않습니다.

---

## 빠른 실행

**처음이라면** — 아래를 순서대로 붙여 넣으면 첫 테스트까지 갑니다. 각 줄의 자세한 설명은 [단계별 시작 가이드](#단계별-시작-가이드)에 있습니다.

```bash
# ① 설치 (컴퓨터당 한 번)
git clone -b main https://github.com/indextrown/ios-qa-kit.git ~/ios-qa-kit
~/ios-qa-kit/bin/qakit install-skill

# ② 앱에 QA 작업공간 만들기 (앱당 한 번)
qakit init ~/path/to/MyApp --worktree
cd ~/path/to/MyApp-qa/QA

# ③ 점검 → 앱 빌드·설치 → 첫 화면 확인
qakit doctor
qakit build-app
qakit dump-ui                 # → results/ui-dump.txt

# ④ 로그인이 필요한 앱이면 계정 넣기
cp secrets.example.txt secrets.txt
```

```text
# ⑤ 작업공간 폴더에서 Claude Code / Codex를 열고 요청
/ios-qa-kit 로그인 화면에서 테스트 계정으로 로그인하면 홈 화면이 뜨는지 확인하는 테스트 만들어줘
```

**이미 설정했다면** — 작업공간 폴더에서:

| 하고 싶은 것 | 명령 |
|---|---|
| 전체 테스트 실행 (토큰 0) | `qakit test` |
| 테스트 하나만 | `qakit test LoginTests` |
| 시나리오 파일 실행 | `qakit run <시나리오>` |
| 마지막 실패 다시 보기 | `qakit summarize` |
| 도구 최신화 | `qakit update` |

---

## 한눈에 보기

| 무엇을 | 어떻게 |
|---|---|
| **화면 요소 찾기** | 시뮬레이터에서 실행할 때 라이브러리를 끼워 넣어 `LoginView.loginButton` 같은 **ID를 자동으로** 붙입니다 (Swift 프로퍼티 이름 기반) |
| **앱 변경에 강하게** | 앱 소스에서 ID를 **Swift 상수(`QAID`)** 로 만들어, 이름이 바뀌면 컴파일 에러로 바로 알려 줍니다 |
| **실행·실패 분석** | `qakit` 명령 하나로 빌드·설치·실행·실패 요약까지. 요약은 텍스트라 AI가 스크린샷 없이 고칩니다 |
| **AI 작업** | Claude Code / Codex **스킬**: "이 시나리오 테스트 만들어줘" → 작성하고 통과할 때까지 수정 |

---

## 목차

**시작하기**

1. [빠른 실행](#빠른-실행)
2. [준비물](#준비물)
3. [단계별 시작 가이드](#단계별-시작-가이드)
   - [1단계 설치](#1단계-설치) · [2단계 QA 워크트리](#2단계-qa-워크트리-만들기) · [3단계 점검·빌드](#3단계-점검과-빌드-첫-화면-보기) · [4단계 계정](#4단계-로그인-계정-넣기)
   - [5단계 첫 테스트](#5단계-첫-테스트-만들기) · [6단계 실패 고치기](#6단계-실패-읽고-고치기) · [7단계 앱 변경 체험](#7단계-앱-변경-체험-선택) · [8단계 정리](#8단계-정리)
   - [처음 쓸 때 알아 둘 것](#처음-쓸-때-알아-둘-것)
4. [시나리오 파일로 QA (Swift 없이)](#시나리오-파일로-qa-swift-없이)
5. [저장과 복구 (AI 없이)](#저장과-복구-ai-없이)

**이해하기**

6. [동작 원리](#동작-원리)
   - [세 곳의 역할](#세-곳의-역할) · [기존 프로젝트를 가져오는 방법](#기존-프로젝트를-가져오는-방법) · [테스트가 만들어지는 과정](#테스트가-만들어지는-과정) · [누가 무엇을 만드나](#누가-무엇을-만드나)
7. [자동으로 붙는 ID 규칙](#자동으로-붙는-id-규칙)
   - [UIKit 화면의 ID](#uikit-화면의-id) · [SwiftUI 화면의 ID](#swiftui-화면의-id)
8. [UI 요소를 찾는 우선순위](#ui-요소를-찾는-우선순위)
   - [AI가 요소를 알아내는 순서](#ai가-요소를-알아내는-순서) · [찾은 뒤 상태 판정하기](#찾은-뒤-상태-판정하기)
9. [앱이 바뀌었을 때](#앱이-바뀌었을-때)

**참고**

10. [명령 요약](#명령-요약)
11. [원칙](#원칙)
12. [한계](#한계)
13. [레포 구조](#레포-구조)
14. [기여하기](#기여하기)
15. [검증 현황](#검증-현황)

---

## 준비물

| 항목 | 확인 명령 |
|---|---|
| macOS + Xcode (16 이상, 26.6에서 검증) | `xcodebuild -version` |
| iOS 시뮬레이터 | `xcrun simctl list devices available` |
| Python 3 (macOS 기본) | `python3 --version` |
| XcodeGen | `brew install xcodegen` |
| UIKit 또는 SwiftUI 앱 | — |

> [!NOTE]
> SwiftUI 화면은 QA 워크트리에서 빌드할 때 소스에 ID를 끼워 넣습니다. 자세한 건 [SwiftUI 화면의 ID](#swiftui-화면의-id).

<sub>[↑ 목차](#목차)</sub>

---

## 단계별 시작 가이드

처음 한 번, **약 10분**. 아래 순서대로 따라 하면 첫 테스트까지 돌아갑니다.

### 1단계 설치

```bash
git clone -b main https://github.com/indextrown/ios-qa-kit.git ~/ios-qa-kit
~/ios-qa-kit/bin/qakit install-skill
```

`install-skill`은 아래 세 가지를 **심볼릭 링크**로 설치합니다.

| 무엇 | 설치 위치 | 호출 |
|---|---|---|
| `qakit` 명령 | `~/.local/bin/qakit` | PATH에 없으면 안내가 나옵니다 |
| Claude Code 스킬 | `~/.claude/skills/ios-qa-kit` | `/ios-qa-kit` |
| Codex 스킬 | `~/.agents/skills/ios-qa-kit` | `$ios-qa-kit` |

- 링크라서 레포를 고치면 **바로 반영**됩니다.
- 제거는 `qakit install-skill --uninstall`.

> [!TIP]
> **업데이트**
> - `qakit update` — 설치 폴더(`~/ios-qa-kit`)를 원격 main으로 빨리 감기(fast-forward)합니다. 명령과 스킬이 함께 바뀝니다.
> - `qakit update --check` — 받지 않고 새 버전과 변경 목록만 봅니다.
> - `qakit --version` — 지금 버전을 봅니다.

### 2단계 QA 워크트리 만들기

권장 방식입니다.

```bash
qakit init ~/path/to/MyApp --worktree
cd ~/path/to/MyApp-qa/QA
```

이 명령이 하는 일:

- **QA 전용 git 워크트리**를 만듭니다.
  - 이름 `MyApp-qa`, 브랜치 `qa/workspace` (`develop`에서 생성)
  - 그 안 `QA/` 폴더가 작업공간입니다.
  - 원래 개발 폴더와 섞이지 않고, 이름이 `-qa`라 다른 워크트리와 헷갈리지 않습니다.
- **git에 없는 작은 로컬 설정 파일**(키가 든 xcconfig 등)을 원래 폴더에서 워크트리로 복사합니다. 없으면 빌드가 실패하기 때문입니다.
- `QA/`를 이 PC의 git 무시 목록(`.git/info/exclude`)에 넣습니다.
  - 팀이 커밋하기로 하면 그대로 커밋하면 됩니다. `QA/.gitignore`가 생성물·비밀값을 이미 제외합니다.
- scheme·configuration·bundle ID를 자동으로 찾아 `qakit.yml`에 적습니다.

**`qakit.yml`을 확인하고 필요한 권한을 넣으세요.**

```yaml
app:
  project: ../MyApp.xcodeproj        # 워크트리의 앱 (상대 경로)
  scheme: MyApp-Dev
  bundleId: com.example.myapp.dev
permissions: [location-always]       # 테스트 전에 미리 허용할 권한
```

> [!NOTE]
> 워크트리를 쓰지 않으려면
> - `qakit init <앱>` → 앱 옆 `qa-workspaces/<이름>`
> - `qakit init <앱> --in-project` → 앱 폴더 안 `QA/`

### 3단계 점검과 빌드, 첫 화면 보기

```bash
# 작업공간 폴더에서 (2단계에서 cd 한 곳, 또는 qa-workspaces/myapp)
qakit doctor        # ❌가 있으면 → 안내대로
qakit build-app     # 앱 빌드 + 시뮬레이터 설치 (처음엔 몇 분)
qakit dump-ui       # 첫 화면 구조 → results/ui-dump.txt
```

`results/ui-dump.txt` 맨 위에 **ID 커버리지**(누를 수 있는 요소 중 ID가 붙은 비율)가 나옵니다.

```text
# interactive: 8, with auto/app ID: 8 (100%)
Button #LoginView.loginButton "로그인" @16,682 370x56
TextField #LoginView.emailField.textField @28,496 346x28
```

`dump-ui` 사용 팁:

| 상황 | 방법 |
|---|---|
| 기본 동작 | 앱을 새로 띄워 **처음 보이는 화면**을 덤프합니다. 로그인돼 있으면 로그인 화면이 아니라 홈 화면(또는 그 위 팝업)이 잡힙니다 |
| 특정 요소가 뜰 때까지 기다리기 | `qakit dump-ui --wait-id <ID>` (30초 안에 안 뜨면 실패) |
| 테스트로 원하는 화면까지 간 뒤 보기 | `qakit dump-ui --attach` |

> [!WARNING]
> 화면 위에 팝업이 떠 있으면 **아래 화면 요소가 덤프에서 사라집니다.**
> 커버리지가 이상하게 낮으면 덤프 맨 아래쪽(최상단 요소)을 보세요.

### 4단계 로그인 계정 넣기

로그인이 필요한 앱만 해당합니다.

```bash
cp secrets.example.txt secrets.txt    # git에 올라가지 않습니다
```

```text
EMAIL=qa@example.com
PASSWORD=...
```

- 키 이름은 자유입니다.
- `secrets.example.txt`에 적은 키는 `qakit doctor`가 빠졌는지 검사합니다.

### 5단계 첫 테스트 만들기

#### 방법 A. AI에게 맡기기 (권장)

작업공간 폴더에서 Claude Code / Codex를 열고:

```text
/ios-qa-kit 로그인 화면에서 테스트 계정으로 로그인하면 홈 화면이 뜨는지 확인하는 테스트 만들어줘
```

AI는 스킬 규칙대로 **ID 상수 찾기 → Page·테스트 작성 → `qakit test` 통과할 때까지 수정**합니다.

#### 방법 B. 직접 쓰기

<details>
<summary>Page와 테스트 코드 예시 보기</summary>

`Runner/UITests/Pages/LoginPage.swift`

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

</details>

```bash
qakit test LoginTests
```

- 새 파일은 **자동으로 프로젝트에 포함**됩니다.
- 실패하면 원인·마지막 단계·실패 시점 화면 구조가 바로 출력됩니다.

### 6단계 실패 읽고 고치기

```bash
qakit test                 # 전체 실행
qakit summarize            # 마지막 실패 요약 다시 보기
```

실패 요약은 이렇게 나옵니다. **AI도 이것만 읽고 고칩니다.**

```text
❌ LoginTests/test_login()
   원인: 로그인 후 홈 화면이 뜨지 않음. 화면 안내: 팝업: 이미 다른 기기에서 로그인 중입니다…
   마지막 단계:
     - 로그인 입력
   실패 시점 화면 구조 (ID/라벨 있는 요소):
     Button, identifier: 'AlertView.confirmButton', label: '로그인'
   스크린샷: results/test-…-attachments/….png
```

- **체험해 보기** — `Pages/`에서 `QAID` 상수 하나를 없는 이름으로 바꿔 보세요. 실행 전에 **컴파일 에러**로 막히고 위치가 출력됩니다.
- **`NOTES.md`** — 새 작업공간에선 비어 있습니다. 로그인 후 공지·권한 팝업처럼 앱마다 다른 것은 AI가 실패를 통해 찾아 고치고 여기에 적습니다. 다음 세션의 AI는 이걸 먼저 읽습니다.
- **로그아웃 상태부터 확인** — `qakit test --reset <테스트>` (앱 재설치 + 키체인 초기화).

### 7단계 앱 변경 체험 (선택)

```bash
qakit --app ~/path/to/MyApp-other-branch test    # 다른 브랜치 폴더(git worktree)로 테스트 → 자동 재빌드
qakit test                                       # 원래 앱으로 돌아오면 다시 자동 재빌드
```

자세한 내용: [앱이 바뀌었을 때](#앱이-바뀌었을-때)

### 8단계 정리

```bash
rm -rf ~/path/to/qa-workspaces/myapp-practice
```

시뮬레이터에 설치된 앱은 그대로 둬도 됩니다. 다른 작업공간에서 다음 `qakit test`를 하면 그 작업공간 기준으로 다시 맞춥니다.

### 처음 쓸 때 알아 둘 것

| 상황 | 알아 둘 것 |
|---|---|
| **qakit을 동시에 두 개 실행** | 한 시뮬레이터에서 두 실행이 같은 앱을 조작하면 입력이 섞입니다 (예: 이메일이 두 번 입력됨). qakit이 **시뮬레이터마다 잠금**을 걸어, 다른 실행이 있으면 누가 돌리는지 알려 주고 끝날 때까지 기다립니다 |
| **새 작업공간의 첫 `build-app`** | 작업공간마다 빌드 폴더가 따로라서 처음엔 몇 분 걸립니다. 이후는 바뀐 부분만 |
| **로그인 테스트가 다른 기기를 로그아웃시킴** | 동시 로그인 기기 수 제한이 있는 앱이면 테스트 로그인이 다른 기기 세션을 끊을 수 있습니다. QA 전용 계정을 쓰고, 이런 동작은 사람이 승인한 뒤 `NOTES.md`에 기록합니다 |
| **권한 팝업(위치·사진 등)이 테스트를 막음** | `qakit.yml`의 `permissions`에 넣고 `qakit build-app`을 다시 실행 |
| **내가 쓰는 qakit 버전** | `qakit --version` (버전과 도구 폴더의 브랜치) |

<sub>[↑ 목차](#목차)</sub>

---

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

- 전체 문법: [scenario-language.md](skills/ios-qa-kit/references/scenario-language.md)
- 언어로 표현이 안 되는 계산·판정만 Swift(`QA/Runner/UITests/Flows`)로 씁니다. **두 방식은 같은 작업공간에서 함께** 씁니다.

<sub>[↑ 목차](#목차)</sub>

---

## 저장과 복구 (AI 없이)

**AI는 QA를 만들 때만** 씁니다. 만들어진 결과물을 저장해 두면, 작업공간을 지워도 **AI 없이 그대로 복구**됩니다.

```bash
qakit save -m "즐겨찾기 시나리오 추가"    # qa.lock.json(파일 목록·해시) + 보관소 ~/.qakit/archive/<이름>/
rm -rf QA                                     # 지워도
qakit restore --from myapp --to QA           # 보관소에서 복사 → ID 재생성 → 앱 빌드·설치 → 해시 확인
qakit run search-favorite                     # 바로 실행
qakit history                                 # 실행 기록: 언제·어느 앱 커밋에서·무엇이 통과/실패
```

**저장 대상**

| 저장되는 결과물 (save·restore 대상) | 저장 안 함 (restore가 다시 만듦) |
|---|---|
| `scenarios/`, `steps/`, `Runner/UITests/Pages·Flows`, `README.md`, `NOTES.md`, `qakit.yml`, `history.jsonl`, `qa.lock.json` | `QAIDs.swift`, Runner 프로젝트, `.build/`, `results/` |
| | `secrets.txt` (보안상 제외 → 복구 후 다시 넣기) |

- `QA/`를 **git에 커밋하는 팀**은 보관소 없이 커밋된 파일만으로 같은 복구가 됩니다 (`qakit restore`).
- `qa.lock.json`에 저장 시점의 도구 버전·앱 브랜치/커밋·파일 해시가 남아, 복구한 파일이 저장 때와 같은지 확인합니다.

> [!NOTE]
> **QA 폴더의 `README.md`는 qakit이 자동으로 만듭니다.**
> - 내용: 시나리오·공통 단계·Swift 테스트 목록, 각각 무엇을 확인하는지(시나리오 `name:`·맨 위 주석, Swift `///`), 앱 초기화 여부, 마지막 실행 결과
> - 갱신 시점: `run`·`test`·`check`·`save`·`restore` 때 자동 (`qakit readme`로 수동 갱신)
> - 자동 부분 밖에 직접 쓴 글은 보존됩니다.

### QA 워크트리까지 통째로 지워졌을 때

워크트리 폴더(`MyApp-qa/`)가 빌드 결과까지 모두 사라져도 **보관소만 있으면 복구**됩니다. `qa/workspace` 브랜치는 남아 있다고 가정합니다 (없으면 `develop`에서 새로 만듭니다).

```bash
qakit init ~/path/to/MyApp --worktree                                  # 워크트리 다시 만들기 + git에 없는 키 설정 파일 복사
qakit restore --from myapp --to ~/path/to/MyApp-qa/QA --force          # 보관소 내용으로 덮어쓰기 → ID 재생성 → 앱 빌드·설치
cp <계정 파일> ~/path/to/MyApp-qa/QA/secrets.txt                       # 계정은 보관소에 없음
cd ~/path/to/MyApp-qa/QA && qakit run <시나리오>
```

- 결과물(시나리오·공통 단계·Swift·NOTES·설정·실행 기록)은 지우기 전과 **완전히 같게** 돌아옵니다. 앱을 처음부터 빌드하는 몇 분이 대부분입니다.
- 보관소 말고 필요한 것: 원래 개발 폴더(앱 코드, 키가 든 xcconfig 같은 git에 없는 설정 파일), ios-qa-kit 도구, `secrets.txt`.

> [!WARNING]
> 보관소(`~/.qakit/archive`)는 **이 컴퓨터에만** 있습니다. 컴퓨터가 바뀌어도 살리려면 `QA/`를 git에 커밋하거나 보관소를 따로 백업하세요.

<sub>[↑ 목차](#목차)</sub>

---

## 동작 원리

### 세 곳의 역할

| 곳 | 예시 위치 | 들어 있는 것 | 누가 바꾸나 |
|---|---|---|---|
| **앱 프로젝트** (기존 그대로) | `~/work/MyApp` | 앱 소스. **복사하지 않고 경로만 참조**합니다 | 아무도 (qakit은 읽기만) |
| **도구** (이 레포) | `~/ios-qa-kit` | qakit CLI, 자동 ID 라이브러리, QAKit, 스킬, 템플릿 | 도구 개발자 ([docs/gitflow.md](docs/gitflow.md)) |
| **작업공간** (앱별 QA 폴더) | `~/work/qa-workspaces/myapp` | 설정·계정·테스트·빌드 결과. git으로 관리하지 않는 일회용 | 사람(설정·계정) + AI(테스트) + qakit(자동 생성) |

```mermaid
flowchart LR
    subgraph APP["앱 프로젝트 (수정 없음)"]
        SRC["MyApp.xcodeproj<br/>Sources/*.swift"]
    end
    subgraph WS["작업공간 qa-workspaces/myapp"]
        CFG["qakit.yml<br/>앱 경로·scheme·bundleId"]
        SEC["secrets.txt<br/>테스트 계정 (사람)"]
        NOTES["NOTES.md<br/>앱 특이사항 (AI 기록)"]
        IDS["Generated/QAIDs.swift<br/>ID 상수 (자동)"]
        TESTS["Pages/ · Flows/<br/>Page·시나리오 테스트 (AI)"]
        BUILD[".build/<br/>앱·테스트 빌드 결과 (자동)"]
        RES["results/<br/>로그·덤프·실패 요약 (자동)"]
    end
    SIM["iOS 시뮬레이터<br/>실행할 때 AutoID 주입 → 화면 요소에 ID 자동 부여"]

    CFG -- "① 경로 참조" --> SRC
    SRC -- "② 빌드 (xcodebuild)" --> BUILD
    SRC -- "③ 소스 읽기 (gen-ids)" --> IDS
    BUILD -- "④ 설치" --> SIM
    IDS -- "상수로 사용" --> TESTS
    TESTS -- "⑤ qakit test: ID로 찾아 조작" --> SIM
    SIM -- "⑥ 결과" --> RES
```

<details>
<summary>그림이 안 보이는 환경(터미널 등)이면 펼치기</summary>

1. `qakit.yml`에 적힌 경로로 앱 프로젝트를 **참조만** 합니다 (복사·수정 없음).
2. 앱을 빌드하고, 결과는 작업공간의 `.build/`에 저장합니다.
3. 앱 소스를 읽어 ID 상수 `Generated/QAIDs.swift`를 만듭니다.
4. 빌드한 앱을 시뮬레이터에 설치합니다. 실행할 때 AutoID를 끼워 넣어 화면 요소에 ID를 자동으로 붙입니다.
5. AI가 만든 Page·테스트가 ID 상수로 요소를 찾아 조작합니다 (`qakit test`).
6. 로그·덤프·실패 요약은 작업공간의 `results/`에 남습니다.

</details>

<details>
<summary>자동 ID가 붙는 원리 (dylib 주입 + Mirror)</summary>

시뮬레이터에서 앱을 실행할 때 `DYLD_INSERT_LIBRARIES`로 `AutoID.dylib`를 끼워 넣습니다. 이 라이브러리는 화면이 뜰 때 ViewController·커스텀 뷰의 **저장 프로퍼티 이름**을 읽어(Swift `Mirror`) 그 뷰에 `accessibilityIdentifier`를 붙입니다. 앱 바이너리와 소스는 그대로이고, 시뮬레이터에서 qakit으로 실행할 때만 동작합니다. 규칙은 [자동으로 붙는 ID 규칙](#자동으로-붙는-id-규칙).

</details>

### 기존 프로젝트를 가져오는 방법

**앱 프로젝트는 복사하거나 고치지 않습니다.** `qakit init`이 앱 경로를 `qakit.yml`에 적어 두고, 이후 모든 명령은 그 경로를 읽기만 합니다.

| 단계 | 명령 | 앱 프로젝트에 하는 일 | 결과가 저장되는 곳 |
|---|---|---|---|
| 연결 | `qakit init ~/work/MyApp` | `xcodebuild -list`로 scheme·bundle ID 읽기 | 작업공간 생성, `qakit.yml`에 경로 기록 |
| 빌드 | `qakit build-app` | `xcodebuild build` (패키지 버전 고정, 빌드 전후 git 상태 비교 → 바뀌면 경고) | `작업공간/.build/app/` → 시뮬레이터에 설치 |
| ID 상수 | `qakit gen-ids` (`sync`·`test`가 자동 실행) | `*.swift` 읽기 (Pods·Tests 제외) | `작업공간/Runner/UITests/Generated/QAIDs.swift` |
| 실행 | `qakit test` | 없음 (설치된 앱을 실행, 자동 ID 라이브러리를 끼워 넣음) | `작업공간/results/` |
| 앱 변경 감지 | `qakit test` 시작 시 | `git` 브랜치·커밋·미커밋 변경 읽기 | `작업공간/.qakit/` (마지막 빌드 상태) |

- **다른 브랜치를 검증**하려면 앱을 옮기지 말고 그 브랜치 폴더(git worktree)를 가리킵니다: `qakit --app ~/work/MyApp-release test`. 빌드 결과는 경로별로 따로 저장됩니다.
- 같은 앱에 **작업공간을 여러 개** 만들어도 됩니다 (예: 연습용, 기능별). 작업공간을 지워도 앱에는 아무 영향이 없습니다.

### 테스트가 만들어지는 과정

| # | 누가 | 하는 일 | 만들어지는 것 |
|---|---|---|---|
| 1 | 👤 사람 | `qakit init <앱>` → `qakit.yml` 확인(권한 등) → `secrets.txt`에 계정 | 작업공간, 기본 테스트(`SmokeTests`) |
| 2 | ⚙️ qakit | `build-app`: 앱 빌드·설치·권한 허용 / `dump-ui`: 첫 화면 구조 | `.build/`, `results/ui-dump.txt` |
| 3 | 👤 사람 | AI에게 시나리오를 한 문장으로 요청: `/ios-qa-kit 로그인 후 홈이 뜨는지 확인해줘` | — |
| 4 | 🤖 AI | `NOTES.md`·기존 공통 단계 읽기 → `QAIDs.swift`에서 화면 ID grep → 필요하면 앱 소스·덤프 확인 | — (읽기만) |
| 5 | 🤖 AI | 화면마다 Page, 시나리오 테스트, 여러 테스트가 쓸 공통 단계 작성 | `Pages/LoginPage.swift`, `Flows/LoginTests.swift`, `Flows/AuthSteps.swift` |
| 6 | 🤖 ↔ ⚙️ | `qakit test` → 실패하면 텍스트 요약(원인·마지막 단계·그 순간 화면 구조)을 읽고 수정 → 통과할 때까지 (같은 원인 3번이면 멈추고 사람에게 보고) | 통과하는 테스트 |
| 7 | 🤖 AI | 새로 알게 된 것(뜨는 팝업, 상태 판별 기준, ID 없는 영역, 사람의 결정)을 기록 | `NOTES.md` |
| 8 | 👤 사람 | 다음 시나리오 요청. AI는 이미 있는 공통 단계(예: `ensureLoggedIn()`)를 재사용 | 시나리오가 쌓일수록 빨라짐 |

> [!TIP]
> 이후에는 사람·AI 없이 `qakit test`만 반복하면 됩니다 (**토큰 0**).
> 앱이 바뀌면 `qakit test`가 먼저 재빌드·ID 재생성을 하고, 깨진 테스트는 다시 AI에게 "`qakit sync` 결과대로 고쳐줘"라고 맡깁니다.

### 누가 무엇을 만드나

| 파일 | 만드는 쪽 | 설명 |
|---|---|---|
| `qakit.yml` | qakit 초안 → 사람 확인 | 앱 경로, scheme, bundle ID, 시뮬레이터, 미리 허용할 권한 |
| `secrets.txt` | **사람만** | 테스트 계정. AI는 값을 열어 보지 않고 `QASecrets`로만 씁니다 |
| `Pages/*Page.swift` | AI | 화면 하나 = Page 하나. 화면 대표 요소(anchor)와 요소·동작. ID는 여기에만 |
| `Flows/*Tests.swift` | AI | 시나리오 테스트. Page만 사용 |
| `Flows/*Steps.swift` | AI | 여러 테스트가 쓰는 공통 단계 (로그인, 메뉴 열기 …) |
| `NOTES.md` | AI (사람도 가능) | 앱 특이사항. 다음 세션의 AI가 먼저 읽습니다 |
| `Generated/QAIDs.swift` | qakit (자동) | 앱 소스에서 만든 ID 상수. 직접 고치지 않습니다 |
| `Runner/project.yml`, `Host/`, `QAKit/` | qakit (템플릿) | 테스트 실행용 Xcode 프로젝트 틀. 손대지 않습니다 |
| `.build/`, `results/`, `.qakit/` | qakit (자동) | 빌드 결과, 로그·덤프·실패 요약, 마지막 빌드 상태 |

시나리오가 몇 개 쌓인 작업공간 예:

```text
qa-workspaces/myapp/
├── qakit.yml  secrets.txt  NOTES.md  AGENTS.md  CLAUDE.md
├── Runner/UITests/
│   ├── Pages/        LoginPage  HomePage  MenuPage  SearchPage       ← AI
│   ├── Flows/        AuthSteps  MenuSteps                            ← AI (공통 단계)
│   │                 LoginTests  MenuTests  SearchTests  SmokeTests  ← AI (시나리오)
│   ├── Generated/    QAIDs.swift                                     ← 자동
│   └── QAKit/        QAKitDumpTests.swift                            ← 템플릿
├── .build/  results/  .qakit/                                        ← 자동
```

`AGENTS.md`·`CLAUDE.md`는 작업공간을 연 AI가 스킬 규칙을 따르게 하는 안내입니다 (스킬이 설치돼 있지 않은 AI도 읽음).

<sub>[↑ 목차](#목차)</sub>

---

## 자동으로 붙는 ID 규칙

ID는 **"누가 이 뷰를 프로퍼티로 갖고 있나"** 로 정해집니다.

### UIKit 화면의 ID

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

- 앱이 직접 붙인 `accessibilityIdentifier`는 **절대 덮어쓰지 않습니다.**
- 테스트에서는 문자열 대신 **`QAID` 상수**를 씁니다: `QAID.LoginView.loginButton`
  - 하위 요소가 있는 컴포넌트는 `.id` (예: `QAID.LoginView.emailField.id`)
- 상수 파일(`Runner/UITests/Generated/QAIDs.swift`)은 큽니다. 필요한 화면만 찾으세요:

  ```bash
  grep -n "enum LoginView " -A30 Runner/UITests/Generated/QAIDs.swift
  ```

### SwiftUI 화면의 ID

SwiftUI는 실행 중에 읽을 프로퍼티 이름이 없습니다. 그래서:

1. **QA 워크트리에서 `qakit build-app`을 할 때** 소스에 `.accessibilityIdentifier(…)`를 끼워 넣고
2. 빌드한 뒤
3. **바로 되돌립니다.**

> [!IMPORTANT]
> - 워크트리 소스는 빌드하는 동안만 바뀌고 레포 이력에는 남지 않습니다.
> - **개발 폴더에는 절대 쓰지 않습니다.**
> - 설정: `qakit.yml`의 `swiftui: auto | insert | off` (기본 `auto` = `import SwiftUI`가 있으면 삽입)

| 대상 | ID | 예시 |
|---|---|---|
| 바인딩이 있는 컨트롤 (TextField, Toggle, Picker …) | `뷰타입.바인딩경로` | `TextField(text: $email)` → `LoginView.email` |
| 라벨이 글자인 컨트롤 (Button, NavigationLink …) | `뷰타입.종류.라벨` | `Button("로그인")` → `LoginView.Button.로그인` |
| 라벨을 소스에서 알 수 없는 컨트롤 | `뷰타입.종류.N` (등장 순서) | `Button(item.title)` → `ListView.Button.0` (상수는 `QAID.ListView.Button._0`) |
| 컨트롤 하나만 감싼 커스텀 뷰의 호출부 | `뷰타입.커스텀뷰.인자` | `IconButton(icon: .close)` → `HeaderView.IconButton.close` |
| ForEach/List 행 | `뷰타입.row` (여러 행이 같은 ID, 라벨·index로 구분) | `ItemListView.row` |

- **이름 규칙** — 같은 ID가 한 뷰에 둘 이상이면 `_2`, `_3`. 라벨은 공백·구두점이 `_`로 바뀌고 20자에서 잘립니다.
- **붙이지 않는 곳** — 앱이 직접 붙인 `accessibilityIdentifier`가 있는 요소. Text·Image·VStack 같은 컨테이너 (컨테이너 ID는 자식 ID를 덮어씁니다).
- **확인 방법** — 삽입될 목록은 `qakit swiftui-ids --list`. 삽입된 소스를 직접 보려면 `--insert` 뒤 `git diff`, 끝나면 `--restore`.
- **Tuist처럼 프로젝트를 생성하는 앱** — 워크트리에서 먼저 생성한 뒤 `qakit init`을 합니다. `ids.sources`로 빌드되는 모듈 폴더만 지정하세요 (보관용 복사본 폴더가 있으면 같은 타입 이름이 섞입니다).

<sub>[↑ 목차](#목차)</sub>

---

## UI 요소를 찾는 우선순위

테스트는 **기본적으로 키(ID)로 찾고**, ID가 없을 때만 화면에 보이는 것(글자 → 좌표)으로 내려갑니다.
위에 있을수록 앱 문구·레이아웃이 바뀌어도 잘 깨지지 않습니다. AI도 스킬 규칙으로 이 순서를 따릅니다.

| 순위 | 무엇으로 | 코드 예 | 쓰는 경우 | 약점 |
|---|---|---|---|---|
| 1 | **자동 ID 상수** (프로퍼티 이름) | `el(QAID.LoginView.loginButton)` | 대부분. 앱 코드에 프로퍼티로 있는 뷰 | 앱에서 프로퍼티 이름을 바꾸면 깨짐 → `qakit sync`가 컴파일 에러로 바로 알려 줌 |
| 2 | **위치 규칙 ID** | `app.buttons["Tab.SettingsViewController"]`<br>`QAID.X.collectionView + ".header"` | 탭바·기본 셀·헤더·바 버튼·검색창 (UIKit이 만드는 요소) | 상수가 없어 문자열로 씀 |
| 3 | **ID + 화면 글자** | `cell(QAID.ItemCell.id, labelID: QAID.ItemCell.titleLabel, label: "검색")` | 같은 ID가 여러 개 (목록 셀, 반복 컴포넌트) | 글자가 바뀌면 깨짐 |
| 4 | **화면 글자** (라벨) | `text("확인")`, `app.buttons["로그인"]` | ID가 없는 요소: 지역 변수로 만든 뷰, 외부 SDK 버튼, 시스템 알림 | 문구·언어가 바뀌면 깨짐 (그래서 `qakit.yml`의 `language`로 언어를 고정) |
| 5 | **타입 + 순서** | `app.cells.element(boundBy: 0)` | "첫 번째 항목"처럼 순서 자체가 시나리오일 때 | 데이터 순서가 바뀌면 깨짐 |
| 6 | **좌표** | `app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()` | 지도·차트·캔버스처럼 그려지는 영역 (안에 요소가 없음) | 화면 크기·레이아웃에 민감. 결과 확인은 그 위의 UI로 |

> [!NOTE]
> **스크린샷은 찾는 수단이 아닙니다.** 덤프로도 판단이 안 될 때 사람이나 AI가 상황을 이해하는 용도로만 봅니다 (실패 요약에 경로가 나옵니다). 테스트 코드는 항상 위 1~6으로 씁니다.

### AI가 요소를 알아내는 순서

싼 것부터 씁니다.

| 순서 | 방법 | 비용 |
|---|---|---|
| 1 | `QAIDs.swift`에서 화면 enum만 grep → 순위 1 상수 확보 | 매우 적음 |
| 2 | 앱 소스에서 버튼 → 액션 → 화면 전환 확인 (push / 시트 / 탭, 토글 여부, 위험한 버튼 위치) | 적음 |
| 3 | `qakit dump-ui` 텍스트 덤프 → 실제 ID·글자·좌표·커버리지 (순위 2~6이 필요한 화면) | 적음 (스크린샷보다 훨씬 작음) |
| 4 | 실패 요약 속 스크린샷 | 큼 (덤프로 판단이 안 될 때만) |

### 찾은 뒤 상태 판정하기

찾는 것과 판정은 다릅니다. 상황에 맞는 판정을 씁니다.

| 알고 싶은 것 | 쓰는 것 | 주의 |
|---|---|---|
| 화면이 떴나 | `page.isDisplayed(timeout:)` (anchor 존재) | — |
| 정말 화면 안에 보이나 | `isVisibleOnScreen` | 하단 시트·드로어는 닫혀도 화면 밖에 남아 `exists`가 true |
| 닫혔나 | `page.waitUntilGone()` | 사라짐 또는 화면 밖 |
| 선택됐나 (탭·세그먼트) | `element.isSelected` | — |
| 선택 표시가 있나 (배지 등) | 그 표시 요소가 **있는지** | 숨긴(`isHidden`) 뷰는 접근성 구조에서 빠지므로 "없음 = 숨김" |
| 여러 후보 중 먼저 뜬 것 | `QAWait.forAny([...])` | 로그인 화면 vs 홈 화면처럼 분기할 때 |

<sub>[↑ 목차](#목차)</sub>

---

## 앱이 바뀌었을 때

**따로 할 일이 거의 없습니다.** `qakit test`가 실행 전에 앱 상태(경로·브랜치·커밋·미커밋 변경)를 마지막 빌드와 비교하고, 바뀌었으면 **재빌드 → ID 재생성**을 먼저 합니다.

```text
🔄 앱 변경 감지 (브랜치 develop → feature/new-login) → 동기화
   ID 변경: 추가 1, 삭제 1
     - LoginView.loginButton
     + LoginView.signInButton
❌ Runner/UITests/Pages/LoginPage.swift:5: 'QAID.LoginView' has no member 'loginButton'
```

| 하고 싶은 것 | 방법 |
|---|---|
| 깨진 테스트 고치기 | 삭제·추가 목록을 보고 Page의 상수만 바꾸면 됩니다 (AI에게 "`qakit sync` 결과대로 테스트 고쳐줘") |
| 다른 브랜치 폴더(git worktree) 검증 | `qakit --app ~/path/MyApp-release test` |
| 자동 동기화 끄기 | `qakit.yml`에 `sync: warn` (알리기만) 또는 `off` |

<sub>[↑ 목차](#목차)</sub>

---

## 명령 요약

작업공간 폴더에서 실행합니다.

**설정**

| 명령 | 하는 일 |
|---|---|
| `qakit install-skill [--uninstall]` | 스킬·명령 설치/제거 |
| `qakit update [--check]` | 도구를 최신 버전으로 받기 (`--check`: 확인만) |
| `qakit init <앱>` | 작업공간 생성 (scheme·bundle ID 자동 탐지) |
| `qakit init <앱> --worktree` | QA 전용 워크트리(`<앱>-qa`) + 그 안 `QA/` 작업공간 |
| `qakit doctor` | 환경·설정·계정 키 점검 |

**빌드·화면 보기**

| 명령 | 하는 일 |
|---|---|
| `qakit build-app` | 앱 빌드 → 시뮬레이터 설치 → 권한 허용 |
| `qakit dump-ui [--attach] [--wait-id ID]` | 화면 구조를 텍스트로 (`--attach`: 지금 떠 있는 화면) |
| `qakit gen-ids [--verify]` | ID 상수 생성 (`--verify`: 실제 화면 ID와 비교) |
| `qakit swiftui-ids --list` | SwiftUI 화면에 붙을 ID 목록 (`--insert`/`--restore`: 손으로 삽입·되돌리기) |
| `qakit sync` | 앱 변경 반영 (재빌드 + ID 재생성 + 테스트 코드 컴파일 확인) |

**실행·결과**

| 명령 | 하는 일 |
|---|---|
| `qakit test [클래스[/테스트]] [--reset]` | Swift 테스트 실행 (`--reset`: 앱 재설치+키체인 초기화 = 로그아웃 상태) |
| `qakit run <시나리오> [--reset]` | 시나리오 파일 실행 |
| `qakit check` | 시나리오 형식·ID 정적 검사 |
| `qakit summarize` | 마지막 실패 요약 다시 보기 |
| `qakit history [-n 20]` | 실행 기록 |

**저장·문서**

| 명령 | 하는 일 |
|---|---|
| `qakit save -m "…"` | 결과물 저장 |
| `qakit restore [--from 이름 --to QA]` | AI 없이 복구 |
| `qakit readme` | QA 폴더 README.md의 QA 목록 갱신 (run·test·check·save 때 자동) |

**전역 옵션**

| 옵션 | 용도 |
|---|---|
| `--app <다른 앱 폴더>` | 다른 브랜치 워크트리 검증 |
| `--secrets <파일>` | 다른 계정 |
| `-w <작업공간>` | 작업공간 지정 |

상세: [cli.md](skills/ios-qa-kit/references/cli.md) · QAKit API: [qakit-api.md](skills/ios-qa-kit/references/qakit-api.md)

<sub>[↑ 목차](#목차)</sub>

---

## 원칙

| 원칙 | 내용 |
|---|---|
| 🔒 **대상 앱 레포를 수정하지 않습니다** | 빌드할 때도 `Package.resolved`를 고치지 않도록 고정하고, 빌드 전후로 앱 레포에 바뀐 파일이 있으면 경고합니다 |
| 🔑 **비밀값은 `secrets.txt`에만** | 테스트 출력·로그·실패 요약에서 비밀값은 `•••`로 가려집니다 |
| ⚠️ **되돌릴 수 없는 동작은 승인 후에만** | 탈퇴·결제·삭제·실제 전송은 사람이 승인한 경우에만 테스트에 넣고 `NOTES.md`에 기록합니다 |
| 🧩 **테스트끼리 상태를 공유하지 않습니다** | 공통 진입(로그인 등)은 `Flows/*Steps.swift`에 한 번만 만들어 재사용합니다 |

> [!CAUTION]
> Xcode 결과 파일 `results/*.xcresult`에는 **입력 기록이 남으니 공유하지 마세요.** (`results/`는 git에서 제외됩니다.)

<sub>[↑ 목차](#목차)</sub>

---

## 한계

| 경우 | 대신 |
|---|---|
| 지역 변수로 만든 뷰 (`let label = UILabel(); addSubview(label)`) | 화면 글자로 찾기: `text("확인")` |
| 외부 SDK가 내부에서 만든 뷰 (예: 지도 SDK의 버튼) | 화면 글자 또는 좌표 |
| 지도·차트·캔버스처럼 그려지는 영역 | 좌표로 조작, 결과는 그 위의 UI로 확인 |
| SwiftUI 화면 | `qakit init --worktree`로 만든 QA 워크트리에서만 ID가 붙음 (개발 폴더 소스는 안 건드림). 시스템 기본 뒤로가기·동적 라벨 버튼은 라벨·순서 번호로 |
| 실기기 | 자동 ID 주입은 시뮬레이터 전용. 실기기는 `AutoID/AutoID.swift`를 앱 Debug 빌드에 넣고 `QAAutoID.start()` 호출 (`qakit.yml: autoid: embedded`) |

문제가 생기면: [troubleshooting.md](skills/ios-qa-kit/references/troubleshooting.md)

<sub>[↑ 목차](#목차)</sub>

---

## 레포 구조

<details>
<summary>폴더 구성 보기</summary>

```text
ios-qa-kit/
├── bin/qakit                 CLI (Python 3 표준 라이브러리만)
├── AutoID/                   자동 ID 라이브러리 (시뮬레이터 주입용 dylib)
├── Sources/QAKit/            테스트용 Swift 라이브러리 (BasePage, QATestCase, QAWait …)
├── Tools/gen-ids/            앱 소스 → QAID 상수 생성기
├── templates/workspace/      qakit init이 복사하는 작업공간 틀
├── skills/ios-qa-kit/        AI 스킬 (SKILL.md + references)
├── scripts/build-autoid.sh
└── docs/
    ├── PLAN.md               설계·진행 기록
    └── gitflow.md            브랜치 규칙·기여 순서 (Git Flow)
```

</details>

---

## 기여하기

이 저장소는 **Git Flow**를 씁니다.

- 사용자는 `main`을 설치합니다.
- 개발은 `develop`에서 `feature/…` 브랜치 → PR로 합칩니다.
- CI가 없으니 PR 전에 [머지 전 확인](docs/gitflow.md#머지-전-확인)을 직접 돌립니다.

자세한 순서: [docs/gitflow.md](docs/gitflow.md)

---

## 검증 현황

<details>
<summary>검증한 앱과 결과 보기</summary>

| 앱 | 결과 |
|---|---|
| **앱 A** (UIKit + RxSwift + SnapKit, 로그인 있음) | 로그인 화면 ID 100%, 메인 92%. Swift 테스트 6개 통과. 시나리오 파일(초기화 → 로그인 → 검색 → 선대 등록·선택 → 설정 → 지도 확대, 71단계) 통과. QA 폴더 삭제 → AI 없이 복구 → 재실행 통과. 새 AI 세션이 스킬만 보고 Swift·시나리오 파일 테스트를 작성해 통과 |
| **앱 B** (UIKit, 리스트·탭바 위주) | 첫 화면 ID 100%. init → build → dump → 생성 ID 검증 → 테스트 2개 통과 |
| **앱 C** (SwiftUI + TCA, Tuist 모듈, 로그인 있음) | QA 워크트리에서 build-app이 SwiftUI ID 139개를 삽입·빌드·복원 (워크트리 깨끗). 로그인 화면 ID 100%, 온보딩 67%. `gen-ids --verify` 불일치 0. ID로 쓴 시나리오(온보딩 건너뛰기 → 로그인 화면) 통과 |

</details>

<sub>[↑ 목차](#목차)</sub>
