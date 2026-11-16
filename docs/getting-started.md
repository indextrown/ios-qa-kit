# 시작 가이드

처음 한 번, 약 10분. 설치부터 첫 테스트, 저장·복구까지 따라 합니다.

[← README](../README.md)

## 빠른 실행

**처음이라면** — 아래를 순서대로 붙여 넣으면 첫 테스트까지 갑니다. 각 줄의 자세한 설명은 [단계별 시작 가이드](#단계별-시작-가이드)에 있습니다.

```bash
# ① 설치 (컴퓨터당 한 번)
git clone -b main https://github.com/indextrown/qa-kit.git ~/qa-kit
~/qa-kit/bin/qakit install-skill

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
/qa-kit 로그인 화면에서 테스트 계정으로 로그인하면 홈 화면이 뜨는지 확인하는 테스트 만들어줘
```

## 준비물

| 항목 | 확인 명령 |
|---|---|
| macOS + Xcode (16 이상, 26.6에서 검증) | `xcodebuild -version` |
| iOS 시뮬레이터 | `xcrun simctl list devices available` |
| Python 3 (macOS 기본) | `python3 --version` |
| XcodeGen | `brew install xcodegen` |
| UIKit 또는 SwiftUI 앱 | — |

> [!NOTE]
> SwiftUI 화면은 QA 워크트리에서 빌드할 때 소스에 ID를 끼워 넣습니다. 자세한 건 [SwiftUI 화면의 ID](how-it-works.md#swiftui-화면의-id).

---

## 단계별 시작 가이드

처음 한 번, **약 10분**. 아래 순서대로 따라 하면 첫 테스트까지 돌아갑니다.

### 1단계 설치

```bash
git clone -b main https://github.com/indextrown/qa-kit.git ~/qa-kit
~/qa-kit/bin/qakit install-skill
```

`install-skill`은 아래 세 가지를 **심볼릭 링크**로 설치합니다.

| 무엇 | 설치 위치 | 호출 |
|---|---|---|
| `qakit` 명령 | `~/.local/bin/qakit` | PATH에 없으면 안내가 나옵니다 |
| Claude Code 스킬 | `~/.claude/skills/qa-kit` | `/qa-kit` |
| Codex 스킬 | `~/.agents/skills/qa-kit` | `$qa-kit` |

- 링크라서 레포를 고치면 **바로 반영**됩니다.
- 제거는 `qakit install-skill --uninstall`.

> [!TIP]
> **업데이트**
> - `qakit update` — 설치 폴더(`~/qa-kit`)를 원격 main으로 빨리 감기(fast-forward)합니다. 명령과 스킬이 함께 바뀝니다.
> - `qakit update --check` — 받지 않고 새 버전과 변경 목록만 봅니다.
> - `qakit --version` — 지금 버전을 봅니다.

> [!NOTE]
> **예전 이름 `ios-qa-kit`으로 설치했다면** — 레포와 스킬 이름이 `qa-kit`으로 바뀌었습니다 (안드로이드 지원 준비).
> `qakit update`(또는 `qakit install-skill`)를 한 번 실행하면 옛 스킬 링크(`~/.claude/skills/ios-qa-kit` 등)를 지우고 `qa-kit`으로 다시 연결합니다.
> 스킬은 이제 `/qa-kit`, `$qa-kit`으로 부릅니다. 설치 폴더(`~/ios-qa-kit`)는 그대로 써도 되고, 옛 GitHub 주소는 새 주소로 자동 연결됩니다.

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
- 워크트리는 **계속 유지**합니다. 자세한 건 [QA 워크트리 최신화](how-it-works.md#qa-워크트리-최신화).

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
/qa-kit 로그인 화면에서 테스트 계정으로 로그인하면 홈 화면이 뜨는지 확인하는 테스트 만들어줘
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

시나리오가 요소를 못 찾으면, 실패 순간 화면에서 **비슷하고 그 화면에 하나만 있는 요소**를 찾아 대신 쓸 대상을 제안합니다 (AI 없이, 비슷함 75% 이상). 이름은 맞는데 가려졌거나 화면 밖이면 이름 대신 스크롤·기다림을 안내합니다.

```text
   원인: 10초 안에 나타나지 않음: {"id":"home_serch_button","timeout":3}
   대신 이 대상? (실패 시점 화면에 하나만 있는 비슷한 요소):
     → home_search_button  (Button "SearchDark", 비슷함 97%)
   영상 (마지막 30초): results/2026-11-15/21-48-48_run_zz-typo/failure.mp4
```

시뮬레이터에서 `qakit run`이 실패하면 **실패 직전 30초 영상**(`failure.mp4`, 440×960)도 결과 폴더에 남습니다. 통과하면 버립니다 (실행 시간에 거의 영향 없음, 남길 때만 약 2초). `--video always`: 통과해도 `video.mp4`, `--video off`: 녹화 안 함. 실기기·`--bench` 중에는 녹화하지 않습니다. UI 실행 기록 상세에서 바로 재생됩니다.

- **체험해 보기** — `Pages/`에서 `QAID` 상수 하나를 없는 이름으로 바꿔 보세요. 실행 전에 **컴파일 에러**로 막히고 위치가 출력됩니다.
- **`NOTES.md`** — 새 작업공간에선 비어 있습니다. 로그인 후 공지·권한 팝업처럼 앱마다 다른 것은 AI가 실패를 통해 찾아 고치고 여기에 적습니다. 다음 세션의 AI는 이걸 먼저 읽습니다.
- **로그아웃 상태부터 확인** — `qakit test --reset <테스트>` (앱 재설치 + 키체인 초기화).

### 7단계 앱 변경 체험 (선택)

```bash
qakit --app ~/path/to/MyApp-other-branch test    # 다른 브랜치 폴더(git worktree)로 테스트 → 자동 재빌드
qakit test                                       # 원래 앱으로 돌아오면 다시 자동 재빌드
```

자세한 내용: [앱이 바뀌었을 때](how-it-works.md#앱이-바뀌었을-때)

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
- 보관소 말고 필요한 것: 원래 개발 폴더(앱 코드, 키가 든 xcconfig 같은 git에 없는 설정 파일), qa-kit 도구, `secrets.txt`.

> [!WARNING]
> 보관소(`~/.qakit/archive`)는 **이 컴퓨터에만** 있습니다. 컴퓨터가 바뀌어도 살리려면 `QA/`를 git에 커밋하거나 보관소를 따로 백업하세요.
