# ios-qa-kit

**앱 코드를 한 줄도 고치지 않고** iOS 앱에 XCUITest를 붙이고, AI가 테스트를 만들고 고치게 하는 도구입니다.

> [!TIP]
> **한 줄 요약** — AI가 시나리오를 한 번 테스트로 만들어 두면, 이후에는 `qakit test` 한 줄로 **토큰 없이** 계속 돌립니다.
> computer use(스크린샷 보며 조작)처럼 매번 AI 비용이 들지 않습니다.

---

## 왜 ios-qa-kit인가

XCUITest는 Apple이 주는 **UI 테스트 엔진**입니다. 엔진은 좋지만, 실제 앱에 붙여 계속 쓰려면 준비할 게 많습니다. ios-qa-kit이 그 준비를 대신합니다.

**같은 테스트("로그인하면 홈 화면이 뜬다")를 만들 때**

```text
XCUITest만   앱 코드에 ID 추가 → 앱에 UI 테스트 타깃 추가 → 테스트 코드 작성
             → xcodebuild로 실행 → 실패하면 .xcresult를 열어 원인 찾기 → 고치고 다시 빌드

ios-qa-kit   "/ios-qa-kit 로그인하면 홈이 뜨는지 확인해줘" (AI가 작성 → 실행 → 통과할 때까지 수정)
             → 다음부터는 qakit run 한 줄
```

### 1. 앱 코드를 고치지 않아도 됩니다

XCUITest로 버튼을 안정적으로 찾으려면 앱 코드에 ID를 붙여야 합니다.

```swift
// XCUITest만 쓸 때: 앱 코드(LoginView.swift)에 직접 추가
loginButton.accessibilityIdentifier = "loginButton"
```

ios-qa-kit은 **프로퍼티 이름을 그대로 ID로** 붙입니다. 앱에는 아무것도 추가하지 않습니다.

```swift
// 앱 코드는 그대로
let loginButton = UIButton()
// → 테스트에서 QAID.LoginView.loginButton 으로 찾음
```

### 2. 앱이 바뀌면 깨진 곳을 바로 알려 줍니다

앱에서 `loginButton`을 `signInButton`으로 바꾸면, 테스트를 돌리기 전에 위치까지 알려 줍니다.

```text
🔄 앱 변경 감지 → 재빌드
   - LoginView.loginButton
   + LoginView.signInButton
❌ Pages/LoginPage.swift:5: 'QAID.LoginView' has no member 'loginButton'
```

### 3. 실패 원인을 텍스트로 바로 읽습니다

`.xcresult`를 열지 않아도 됩니다. 사람도 AI도 이것만 보고 고칩니다.

```text
❌ LoginTests/test_login()
   원인: 로그인 후 홈 화면이 뜨지 않음. 화면 안내: 팝업: 이미 다른 기기에서 로그인 중입니다…
   마지막 단계: 로그인 입력
```

### 4. 한 번 만들면 AI 없이 계속 돌립니다

- computer use(스크린샷 보며 조작)는 **돌릴 때마다** AI 비용이 듭니다.
- ios-qa-kit은 AI가 **처음 한 번** 만들어 두면 이후는 `qakit run` 한 줄이고 **토큰 0**입니다.
- 시나리오 파일은 [컴파일 없이](#시나리오-파일에-컴파일이-필요-없는-이유) 바로 돌고, 값만 바꿔 다시 실행할 수 있습니다.

  ```bash
  qakit run search-favorite --var item=라떼
  ```

<details>
<summary>XCUITest만 쓸 때와 항목별 비교</summary>

| XCUITest만 쓰면 | ios-qa-kit을 쓰면 |
|---|---|
| **요소에 ID를 붙이려면 앱 코드를 고쳐야 합니다.** 화면마다 `accessibilityIdentifier`를 넣어야 하고, 없으면 글자·순서로 찾아 쉽게 깨집니다 | 시뮬레이터에서 실행할 때 **프로퍼티 이름으로 ID가 자동으로** 붙습니다 (`LoginView.loginButton`). 앱 코드는 한 줄도 고치지 않습니다 |
| ID를 문자열로 써서, 앱에서 이름이 바뀌면 **실행해 봐야** 깨진 걸 압니다 | ID를 Swift 상수(`QAID`)로 만들어 줍니다. 이름이 바뀌면 **컴파일 에러**로 바로 위치를 알려 줍니다 |
| UI 테스트 타깃을 **앱 프로젝트 안에** 만들어야 해서 앱 레포에 QA 코드가 섞입니다 | 테스트용 Xcode 프로젝트가 **작업공간에 따로** 있습니다. 앱 레포는 읽기만 합니다 |
| 실행·결과 확인이 `xcodebuild` 옵션과 `.xcresult` 분석이라 손이 많이 갑니다 | `qakit test` 한 줄로 빌드·설치·실행. 실패하면 **원인·마지막 단계·그 순간 화면 구조를 텍스트로** 요약합니다 |
| 앱 브랜치가 바뀌면 다시 빌드하고 깨진 곳을 직접 찾아야 합니다 | 실행 전에 앱 변경을 감지해 **재빌드 → ID 재생성**을 먼저 하고, 바뀐 ID 목록을 보여 줍니다 |
| 시나리오마다 Swift 코드를 짜고 컴파일해야 합니다 | **시나리오 파일(`.qa.yml`)** 로 쓸 수 있습니다. [컴파일이 필요 없고](#시나리오-파일에-컴파일이-필요-없는-이유), `--var`로 값(검색어 등)을 바꿔 실행합니다 |

</details>

### 그대로인 것

- 테스트 엔진은 XCUITest입니다. Swift로 직접 XCUITest를 써도 되고, 시나리오 파일과 같은 작업공간에서 함께 씁니다.
- 자동 ID는 시뮬레이터와 실기기(`--device`) 모두 됩니다. 실기기는 qakit이 AutoID를 앱 안에 넣고 다시 서명해서 설치합니다.

### AI가 브랜치에서 accessibilityIdentifier를 붙이면 되지 않나?

한 번은 됩니다. 문제는 **계속 유지하는 비용**입니다.

| | 브랜치에서 `accessibilityIdentifier` 직접 추가 | AutoID (ios-qa-kit) |
|---|---|---|
| 처음 작업 | 화면마다 수백~수천 곳 수정 | 0줄 |
| develop이 바뀔 때 | 브랜치를 계속 맞춰야 하고, 같은 파일을 고친 커밋마다 충돌 | 영향 없음. 어떤 커밋이든 그대로 빌드 |
| 새 화면이 생기면 | 그때마다 다시 붙여야 함 (빠뜨리면 테스트가 못 찾음) | 자동으로 붙음 |
| 예전 커밋·다른 브랜치 검증 | 그 브랜치에도 같은 작업 | `qakit --app <폴더>`로 바로 |
| 이름 규칙 | 사람마다, 작업마다 달라질 수 있음 | 항상 `타입.프로퍼티` (예: `LoginView.loginButton`). 바뀌면 실행 전에 알려 줌 |
| 앱 레포 | 테스트용 코드가 섞이고 리뷰 부담 | 그대로 |

**팀이 테스트용 ID를 앱에 정식으로 넣기로 합의했다면** 그게 가장 튼튼합니다. 앱이 직접 붙인 ID가 있으면 ios-qa-kit은 그걸 그대로 씁니다 (AutoID는 앱의 ID를 덮어쓰지 않음). AutoID는 그 합의와 유지 없이 바로 시작하게 해 주는 부분입니다.

그리고 ID는 일부일 뿐입니다. ID를 앱에 직접 붙여도 아래는 따로 필요합니다.

- 시나리오 파일(`.qa.yml`)을 컴파일 없이 돌리는 실행기
- 실패 원인·마지막 단계·그 순간 화면 구조 요약
- `--bench` 성능 측정 (CPU·메모리·함수별 CPU, 한글 요약)
- `--device` 실기기 서명·설치·실행
- QA 워크트리를 develop에 맞춰 최신화

ios-qa-kit의 필요성은 "ID 붙이기"보다 **QA를 누구나 같은 명령으로 반복할 수 있게 만드는 것**에 있습니다.

### 시나리오 파일에 컴파일이 필요 없는 이유

**테스트 코드는 미리 한 번만 컴파일해 두고, 시나리오(`.qa.yml`)는 그 코드가 실행할 때 읽는 데이터로 넘깁니다.** 그래서 시나리오를 고쳐도 다시 빌드하지 않습니다. 게임 엔진은 그대로 두고 맵 파일만 바꾸는 것과 같습니다.

**① 미리 컴파일해 둔 것: 범용 실행기**

도구 안에 앱과 상관없는 XCUITest 테스트가 하나 있습니다 (`ScenarioTests.test_run` + `QAScenarioRunner`).
`qakit run`을 처음 할 때 `xcodebuild build-for-testing`으로 한 번 빌드해 두고(`.xctestrun`), 이후로는 **도구가 바뀌었을 때만** 다시 빌드합니다 (소스 해시로 판단). 앱이 여러 개여도 이 실행기 하나를 같이 씁니다.

**② 실행할 때: yml → JSON → 실행기에 전달**

```text
scenarios/login.qa.yml
   │  qakit이 읽어서: use: 로 쓴 공통 단계를 펼치고, --var 값을 넣고, ID가 앱에 있는지 검사
   ▼
.qakit/scenarios/login.json
   │  환경변수로 경로를 넘김 (실기기는 Mac 파일을 못 읽어서 내용째 base64로)
   ▼
xcodebuild test-without-building   ← 빌드 없이 미리 만든 실행기만 실행
   ▼
QAScenarioRunner가 JSON을 한 단계씩 읽어 XCUITest 동작으로
```

**③ 실행기 안: 단계 이름 → XCUITest 호출**

```yaml
# 시나리오 (데이터)
- tap: LoginView.loginButton
- type: { into: LoginView.emailField, text: "{secret:EMAIL}" }
- expect: { visible: HomeView.title }
  timeout: 10
```

```swift
// 실행기 (미리 컴파일된 코드) — 단계마다 키를 보고 같은 동작을 부른다
if let target = step["tap"] {            // "LoginView.loginButton"
    resolve(target).tap()                //   → app.descendants(…)["LoginView.loginButton"].tap()
} else if let spec = step["type"] {
    resolve(spec["into"]).typeText(text(spec["text"]))
} else if let condition = step["expect"] {
    try waitUntil(condition, timeout: step["timeout"])
} …
```

대상(ID·라벨)과 값(`{변수}`, `{secret:…}`)은 컴파일할 때가 아니라 **실행할 때** 문자열로 찾고 채웁니다. 그래서 시나리오 내용이 바뀌어도 실행기 코드는 그대로입니다.

| | Swift 테스트 | 시나리오 파일 |
|---|---|---|
| 무엇을 빌드하나 | 테스트를 고칠 때마다 그 테스트 코드 | 도구의 **범용 실행기 하나** |
| 언제 빌드하나 | 고칠 때마다 | **도구가 바뀌었을 때 한 번만** |
| 앱마다 | 앱별 테스트 프로젝트 | 모든 앱이 같은 실행기를 씀 |
| 시나리오를 고친 뒤 | 다시 빌드 → 실행 | **바로 실행** |

- 컴파일 에러가 해 주던 확인은 `qakit check`가 대신합니다. 형식과 ID가 앱에 실제로 있는지를 실행 없이 검사합니다 (`qakit run`도 실행 전에 먼저 검사).
- 실행기가 모르는 동작이 필요하면 도구에 단계를 하나 추가합니다 (예: `pinch-to`). 그때만 실행기를 다시 빌드합니다.

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
| 값을 바꿔 실행 (매개변수) | `qakit run <시나리오> --var ship="선박명"` |
| 마지막 실패 다시 보기 | `qakit summarize` |
| 성능 측정 (시나리오 후 30분) | `qakit run <시나리오> --bench 30m` |
| Release 빌드로 | `qakit run <시나리오> --build release` |
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

0. [왜 ios-qa-kit인가](#왜-ios-qa-kit인가) · [AI가 ID를 직접 붙이면 되지 않나?](#ai가-브랜치에서-accessibilityidentifier를-붙이면-되지-않나) · [시나리오 파일에 컴파일이 필요 없는 이유](#시나리오-파일에-컴파일이-필요-없는-이유)
1. [빠른 실행](#빠른-실행)
2. [준비물](#준비물)
3. [단계별 시작 가이드](#단계별-시작-가이드)
   - [1단계 설치](#1단계-설치) · [2단계 QA 워크트리](#2단계-qa-워크트리-만들기) · [3단계 점검·빌드](#3단계-점검과-빌드-첫-화면-보기) · [4단계 계정](#4단계-로그인-계정-넣기)
   - [5단계 첫 테스트](#5단계-첫-테스트-만들기) · [6단계 실패 고치기](#6단계-실패-읽고-고치기) · [7단계 앱 변경 체험](#7단계-앱-변경-체험-선택) · [8단계 정리](#8단계-정리)
   - [처음 쓸 때 알아 둘 것](#처음-쓸-때-알아-둘-것)
4. [시나리오 파일로 QA (Swift 없이)](#시나리오-파일로-qa-swift-없이)
   - [실기기에서 실행 (`--device`)](#실기기에서-실행---device)
5. [저장과 복구 (AI 없이)](#저장과-복구-ai-없이)

**이해하기**

6. [동작 원리](#동작-원리)
   - [세 곳의 역할](#세-곳의-역할) · [기존 프로젝트를 가져오는 방법](#기존-프로젝트를-가져오는-방법) · [테스트가 만들어지는 과정](#테스트가-만들어지는-과정) · [누가 무엇을 만드나](#누가-무엇을-만드나)
7. [자동으로 붙는 ID 규칙](#자동으로-붙는-id-규칙)
   - [UIKit 화면의 ID](#uikit-화면의-id) · [SwiftUI 화면의 ID](#swiftui-화면의-id)
8. [UI 요소를 찾는 우선순위](#ui-요소를-찾는-우선순위)
   - [화면에 보이는 것은 어떻게 읽나](#화면에-보이는-것은-어떻게-읽나) · [AI가 요소를 알아내는 순서](#ai가-요소를-알아내는-순서) · [찾은 뒤 상태 판정하기](#찾은-뒤-상태-판정하기)
9. [앱이 바뀌었을 때](#앱이-바뀌었을-때)
   - [QA 워크트리 최신화](#qa-워크트리-최신화)

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
- 워크트리는 **계속 유지**합니다. 자세한 건 [QA 워크트리 최신화](#qa-워크트리-최신화).

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
   스크린샷: results/2026-11-04/101530-test-logintests/result-attachments/….png
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

- 전체 문법: [scenario-language.md](skills/ios-qa-kit/references/scenario-language.md)
- 언어로 표현이 안 되는 계산·판정만 Swift(`QA/Runner/UITests/Flows`)로 씁니다. **두 방식은 같은 작업공간에서 함께** 씁니다.

<sub>[↑ 목차](#목차)</sub>

---

### 실기기에서 실행 (`--device`)

같은 Wi-Fi(또는 케이블)로 연결된 iPhone·iPad에서 시나리오와 성능 측정을 그대로 돌립니다. 명령 뒤에 `--device`만 붙이면 됩니다.

```bash
qakit run <시나리오> --device                          # 기기 목록이 뜨고 ↑↓ · Enter로 고름 (= --device select)
qakit run <시나리오> --device "내 iPhone"              # 이름으로 바로
qakit run <시나리오> --device last                     # 지난번에 고른 기기
qakit run <시나리오> --device last --bench 5m          # 실기기 성능 측정 (Time Profiler)
qakit build-app --device last                          # 기기에 앱만 빌드·설치
```

```text
실행할 기기를 고르세요  (↑↓ 이동 · Enter 선택 · Esc 취소)

  ❯ 내 iPhone      iPhone 15          iOS 26.6   케이블 연결됨   ← 지난번
    팀 iPad        iPad Air (4th…)    iOS 26.5   같은 네트워크 (실행할 때 연결)
    시뮬레이터     iPhone 17          (qakit.yml의 simulator)
    옛 iPhone      iPhone 13          iOS 27.0   연결 안 됨        ← 흐리게, 고를 수 없음
```

**처음 한 번 (기기마다)**

1. 기기에서 **개발자 모드**를 켠다: 설정 › 개인정보 보호 및 보안 › 개발자 모드
2. 케이블로 연결해 Xcode에서 페어링하고 "네트워크로 연결"을 켠다. 그다음부터는 같은 Wi-Fi에서 무선으로 된다.
3. 실행하는 동안 기기 잠금을 풀어 둔다.

**qakit이 대신 하는 일**

| 단계 | 시뮬레이터 | 실기기 |
|---|---|---|
| 앱 빌드 | 서명 없이 | 앱의 개발자 팀으로 자동 서명 (`-allowProvisioningUpdates`) |
| 자동 ID (AutoID) | dylib을 환경변수로 주입 | dylib을 앱 안 `Frameworks/`에 넣고 앱과 같은 인증서로 다시 서명한 뒤 주입 |
| 설치 | `simctl install` | `devicectl device install app` |
| 시나리오 전달 | 파일 경로 | 기기 안 실행기는 Mac 파일을 못 읽어서 내용째(base64) 전달 |
| `pref` 조건 (앱 설정 값) | Mac에서 설정 파일을 직접 읽음 | AutoID가 앱 설정 값을 보이지 않는 요소(`QAKit.prefs`)에 담아 두고 테스트가 읽음 |
| 덤프 (`dump:`·`dump-ui`) | 결과 폴더에 바로 저장 | 테스트 첨부로 받아 결과 폴더로 꺼냄 |
| `--bench` | `ps`(CPU·메모리) + `sample`(함수) | **Time Profiler** 하나로 CPU %와 함수 목록. `bench.trace`는 Instruments로 바로 열림. 메모리는 같이 녹화하는 Activity Monitor에서 |

**성능 측정(`--bench`)은 어디서 무엇이 되나**

| | 시뮬레이터 | 실기기 |
|---|---|---|
| Time Profiler 기록 (`bench.trace`) | ❌ — 명령어(`xctrace`)로 시뮬레이터 앱에 붙으면 녹화가 시작되지 않고 멈춘다 | ✅ |
| 함수별 CPU (요약의 상위 함수) | ✅ `sample`로 대신 기록 (`bench-sample.txt`) | ✅ Time Profiler에서 |
| 호출 트리 텍스트 | ✅ `bench-sample.txt` (sample 원본) | ✅ `bench-calltree.txt` (Time Profiler 샘플로 만든 한글 트리, 0.5% 이상만) |
| CPU % (1초 단위) | ✅ `ps` | ✅ Time Profiler 샘플로 계산 |
| 메모리 (1초 단위) | ✅ `ps` | ✅ Activity Monitor (Time Profiler와 같이 녹화, Xcode 메모리 게이지와 같은 physical footprint) |

- **Time Profiler는 실기기에서만 된다.** 시뮬레이터 앱을 Time Profiler로 보려면 Instruments 앱에서 직접 녹화한다.
- **실기기 측정(`--bench`)은 케이블로 연결해서 한다.** 무선에서는 Time Profiler가 앱에 붙지 못하고(`Cannot find process`), 대신 하는 기기 전체 녹화도 테스트와 같이 돌면 몇 초 만에 끊긴다(`Device disconnected`). 시나리오 실행만은 무선으로 된다. 무선으로 측정을 시작하면 qakit이 미리 알리고, 녹화가 짧게 끊기면 요약에 적는다.
- 권한(위치 등)은 미리 허용할 수 없다. 처음 한 번 기기에서 허용하거나 시나리오가 팝업을 누르게 한다.
- `--reset`은 앱 재설치만 한다. 키체인은 지울 수 없어 저장된 로그인 정보가 남을 수 있다.
- 서명 팀은 앱 빌드 설정의 `DEVELOPMENT_TEAM`을 쓴다. 다르게 하려면 `qakit.yml`에 `device: { team: <팀 ID> }`.
- 실기기 실행은 `qakit run`(시나리오)·`dump-ui`·`build-app`에서 된다. `qakit test`(Swift 테스트)는 아직 시뮬레이터만.

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
6. 로그·덤프·실패 요약은 작업공간의 `results/<날짜>/<시-분-초>_<종류>_<이름>/`(예: `14-15-16_run_interpolation-setup`, 측정은 `14-20-03_bench-1m_…`)에 실행마다 폴더로 남습니다 (`results/latest`가 마지막 실행).

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

**어떻게 붙이나** — 앱 코드에는 손대지 않습니다. 시뮬레이터에서 끼워 넣은 `AutoID.dylib`가 UIKit 메서드에 **익스텐션으로 훅을 걸고**, 화면이 뜰 때 **`Mirror`로 저장 프로퍼티 이름을 읽어** ID로 붙입니다.

```swift
// ① dylib가 로드되면 시작 (Loader.m의 +load → QAAutoID.start)
//    UIKit 메서드를 익스텐션 메서드와 맞바꾼다 (method swizzling)
swizzle(UIViewController.self, #selector(viewDidAppear(_:)), #selector(qa_viewDidAppear(_:)))
swizzle(UIView.self,           #selector(didMoveToWindow),   #selector(qa_didMoveToWindow))

// ② 화면이 뜨면 원래 동작을 먼저 하고, ID 붙이기를 덧붙인다
extension UIViewController {
    @objc func qa_viewDidAppear(_ animated: Bool) {
        qa_viewDidAppear(animated)                 // 맞바꿨으므로 = 원래 viewDidAppear
        QAAutoID.handle(viewController: self)
    }
}
extension UIView {
    @objc func qa_didMoveToWindow() {
        qa_didMoveToWindow()                       // = 원래 didMoveToWindow
        if window != nil { QAAutoID.handle(view: self) }
    }
}

// ③ 저장 프로퍼티를 Mirror로 훑어 "타입.프로퍼티" ID를 붙인다 (하위 커스텀 뷰는 재귀)
for child in Mirror(reflecting: loginView).children {       // LoginView의 저장 프로퍼티들
    guard let name = child.label, let view = child.value as? UIView else { continue }
    if view.accessibilityIdentifier?.isEmpty ?? true {       // 앱이 붙인 ID는 덮어쓰지 않음
        view.accessibilityIdentifier = "LoginView.\(name)"   // → "LoginView.loginButton"
    }
}
```

<sub>간추린 코드입니다. 실제 구현(부모 클래스 프로퍼티, `[UIView]` 배열, 셀·탭바·검색창 처리 등): [AutoID/AutoID.swift](AutoID/AutoID.swift)</sub>

**규칙**

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

### 화면에 보이는 것은 어떻게 읽나

픽셀(스크린샷)을 읽는 게 아닙니다. XCUITest는 iOS가 VoiceOver용으로 만드는 **접근성 트리**를 읽습니다. 화면의 요소 하나하나가 트리의 노드이고, 노드마다 아래 값이 있습니다.

| 노드의 값 | 어디서 오나 | 순위 |
|---|---|---|
| `identifier` | `accessibilityIdentifier` (앱이 붙였거나 AutoID가 자동으로 붙인 ID) | 1~3 |
| `label` | `UILabel.text`, 버튼 제목, 텍스트필드 placeholder·값, `accessibilityLabel`처럼 **화면에 보이는 글자** | 3, 4 |
| `elementType` | UIKit 클래스에서 정해지는 종류 (`Button`, `StaticText`, `Cell`, `TextField` …) | 5 |
| `frame` | 화면 위 위치·크기 (pt) | 6 |
| `isSelected`, `value`, `isHittable` 등 | 선택 상태, 스위치·슬라이더 값, 누를 수 있는지 | 판정용 |

테스트는 이 값으로 **조건을 걸어** 요소를 찾습니다.

```swift
app.descendants(matching: .any).matching(identifier: "LoginView.loginButton")   // 1. identifier로
app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "확인"))  // 4. label로 = text("확인")
app.cells.matching(identifier: "ItemCell")                                       // 3. ID + 그 안 label로 한 개 고르기
    .containing(NSPredicate(format: "identifier == %@ AND label == %@", "ItemCell.titleLabel", "검색"))
app.cells.element(boundBy: 0)                                                     // 5. 종류 + 순서로
app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()            // 6. 화면 비율 좌표로
```

`qakit dump-ui`는 같은 트리를 `app.snapshot()`으로 한 번에 떠서 한 줄씩 텍스트로 보여 줍니다. 그래서 덤프에 나온 값이 곧 테스트에서 쓸 수 있는 값입니다.

```text
Button #LoginView.loginButton "로그인" @16,682 370x56
└─종류  └─identifier          └─label  └─frame (x,y 너비x높이)
```

> [!NOTE]
> - 지도·차트처럼 **그려지는 영역**은 안쪽이 노드 하나라 글자·요소가 트리에 없습니다 → 좌표(6순위)를 씁니다.
> - `isHidden` 뷰나 팝업에 가려진 뷰는 트리에서 빠집니다. 덤프에 안 보이면 테스트도 찾을 수 없습니다.
> - 글자는 언어에 따라 바뀌므로 `qakit.yml`의 `language`·`locale`로 고정합니다.

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

### QA 워크트리 최신화

QA 워크트리(`qa/workspace`)는 **한 번 만들면 계속 유지**합니다. 개발 브랜치(`develop`)가 앞서 나가면 그 커밋을 **QA 워크트리 쪽으로 가져와** 최신 앱으로 테스트합니다.

```text
develop       ──●──●──●──●──●
                 \         \  가져오기 (merge)
qa/workspace      ●──●──●───●   ← QA 결과물은 여기 그대로
```

| 하는 것 (기본) | 하지 않는 것 |
|---|---|
| `qakit test`·`qakit run` 전에 `develop`(원격이 앞서면 `origin/develop`)보다 뒤처졌는지 확인 → 뒤처졌으면 가져오기 → 바뀐 앱으로 재빌드 | QA 브랜치를 `develop` 등 다른 브랜치로 **병합하지 않습니다** (사용자가 명시적으로 요청할 때만) |
| 앱 소스에 미커밋 변경이 있거나 충돌이 나면 **가져오지 않고 알려 줌** (충돌은 자동으로 되돌림) | **push하지 않습니다** |

```bash
qakit worktree-update --check      # 뒤처졌는지만 확인 (doctor도 알려 줌)
qakit worktree-update              # 지금 가져오기
qakit worktree-update --from release/1.2.0   # 다른 브랜치를 따라가기
```

```yaml
# qakit.yml
worktree:
  base: develop      # 따라갈 브랜치
  update: auto       # auto: test/run 전에 자동 / warn: 알리기만 / off
```

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
| `qakit worktree-update [--check] [--from 브랜치]` | QA 워크트리를 따라갈 브랜치(기본 `develop`)의 최신 커밋으로 (merge, push 안 함. test/run 전에 자동) |

**실행·결과**

| 명령 | 하는 일 |
|---|---|
| `qakit test [클래스[/테스트]] [--reset]` | Swift 테스트 실행 (`--reset`: 앱 재설치+키체인 초기화 = 로그아웃 상태) |
| `qakit run <시나리오> [--reset] [--var 키=값]` | 시나리오 파일 실행 (`--var`: `vars` 기본값 대신 이번 실행에 쓸 값. 여러 번 가능) |
| `qakit run <시나리오> --bench <시간> [--no-profile]` | 시나리오가 끝난 화면 그대로 그 시간 동안 CPU·메모리(1초 단위) + 함수별 CPU(`sample`) 기록. Time Profiler는 실기기(`--device`)에서만. 시간은 단위 필수: `30s`·`5m`·`1h`·`1h30m` (`30초`·`5분`·`1시간`도 됨, 최소 5초). 1분 이하는 전체를, 더 길면 3분마다 20초씩 함수를 찍는다. 권한 불필요. `--no-profile`: CPU·메모리만 |
| `qakit run <시나리오> --device [select\|last\|이름]` | 실기기에서 실행. 값을 빼면 방향키 목록에서 고름. `--bench`와 같이 쓰면 Time Profiler로 측정 ([실기기에서 실행](#실기기에서-실행---device)) |
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
| `--build debug\|release` | 빌드 종류 (기본 debug = `qakit.yml`의 `app.configuration`, release = `app.release.configuration` 기본 `Release`) |

상세: [cli.md](skills/ios-qa-kit/references/cli.md) · QAKit API: [qakit-api.md](skills/ios-qa-kit/references/qakit-api.md)

<sub>[↑ 목차](#목차)</sub>

---

## 원칙

| 원칙 | 내용 |
|---|---|
| 🔒 **대상 앱 레포를 수정하지 않습니다** | 빌드할 때도 `Package.resolved`를 고치지 않도록 고정하고, 빌드 전후로 앱 레포에 바뀐 파일이 있으면 경고합니다 |
| 🔑 **비밀값은 `secrets.txt`에만** | 테스트 출력·로그·실패 요약에서 비밀값은 `•••`로 가려집니다 |
| ⚠️ **되돌릴 수 없는 동작은 승인 후에만** | 탈퇴·결제·삭제·실제 전송은 사람이 승인한 경우에만 테스트에 넣고 `NOTES.md`에 기록합니다 |
| 🌿 **QA 워크트리는 유지하고 병합하지 않습니다** | 다른 브랜치가 앞서면 그 커밋을 QA 워크트리로 가져올 뿐, QA 브랜치를 다른 브랜치로 병합하거나 push하지 않습니다 (사용자가 명시적으로 요청할 때만) |
| 🧩 **테스트끼리 상태를 공유하지 않습니다** | 공통 진입(로그인 등)은 `Flows/*Steps.swift`에 한 번만 만들어 재사용합니다 |

> [!CAUTION]
> Xcode 결과 파일 `results/…/result.xcresult`에는 **입력 기록이 남으니 공유하지 마세요.** (`results/`는 git에서 제외됩니다.)

<sub>[↑ 목차](#목차)</sub>

---

## 한계

| 경우 | 대신 |
|---|---|
| 지역 변수로 만든 뷰 (`let label = UILabel(); addSubview(label)`) | 화면 글자로 찾기: `text("확인")` |
| 외부 SDK가 내부에서 만든 뷰 (예: 지도 SDK의 버튼) | 화면 글자 또는 좌표 |
| 지도·차트·캔버스처럼 그려지는 영역 | 좌표로 조작, 결과는 그 위의 UI로 확인 |
| SwiftUI 화면 | `qakit init --worktree`로 만든 QA 워크트리에서만 ID가 붙음 (개발 폴더 소스는 안 건드림). 시스템 기본 뒤로가기·동적 라벨 버튼은 라벨·순서 번호로 |
| 실기기 | `--device`로 시나리오·`--bench`는 된다 ([실기기에서 실행](#실기기에서-실행---device)). Swift 테스트(`qakit test`)와 권한 미리 허용은 아직 시뮬레이터만 |

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
