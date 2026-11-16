# qa-kit 설계와 진행 기록

> 어느 iOS 앱에나 붙일 수 있는 AI용 XCUITest 도구. 앱 코드를 고치지 않고 붙이고, AI는 QA를 **만들 때만** 쓴다.
> 이 문서는 특정 앱의 정보를 담지 않는다. 앱별 기록은 각 앱의 QA 폴더(`NOTES.md`)에 둔다.

## 원칙

| 구분 | 위치 | 내용 |
|---|---|---|
| 도구 | 이 저장소 | 범용 코드만. 특정 앱 이름·화면·ID 금지 |
| QA 작업공간 | 앱 레포의 QA 워크트리 안 `QA/` (권장) 또는 별도 폴더 | 앱별 설정, 시나리오, Swift 테스트, 노트 |
| 대상 앱 | 앱 레포 | 수정하지 않음 (경로만 참조) |

## 구성

| 부분 | 역할 |
|---|---|
| AutoID (dylib) | 시뮬레이터에서 앱 실행 시 주입. Swift `Mirror`로 저장 프로퍼티 이름을 읽어 `accessibilityIdentifier` 부여 |
| gen-ids | 앱 소스를 읽어 같은 규칙으로 ID 상수(`QAIDs.swift`) 생성, 실행 중 ID와 교차 검증 |
| QAKit | Swift 테스트용 라이브러리 (BasePage, QATestCase, QAWait, QASecrets, QADump) |
| 시나리오 실행기 | `.qa.yml` 시나리오를 읽어 실행하는 범용 XCUITest. 앱별 Xcode 프로젝트 없음 |
| qakit CLI | init(워크트리), doctor, build-app, sync, gen-ids, dump-ui, test, run, check, save, restore, history, readme |
| 스킬 | Claude Code·Codex가 QA를 만들 때 따르는 규칙과 문서 |

## ID 규칙 (AutoID)

| 대상 | 형식 |
|---|---|
| VC의 뷰 프로퍼티 | `VC타입.프로퍼티` |
| VC가 가진 커스텀 뷰의 자식 / 그 안쪽 | `뷰타입.프로퍼티` / `상위ID.프로퍼티` |
| 앱 셀 | `셀타입` |
| Collection/TableViewController 목록 | `VC타입.collectionView` / `.tableView` |
| UIKit 기본 셀·헤더 | `목록ID.cell` / `.header` / `.footer` |
| 탭바 버튼 | `Tab.탭첫화면VC타입` |
| 바 버튼 | `VC.프로퍼티` 또는 `VC.nav.left|right.N`, `VC.toolbar.N` |
| 검색창 입력칸 | `검색창ID.textField` |

앱이 직접 붙인 ID는 덮어쓰지 않는다. VC가 직접 가진 뷰는 항상 VC 쪽 이름을 받는다 (선언 순서와 무관).

## SwiftUI 지원 설계 (다음 단계)

> 상태: S1(PoC)·S2(도구)·S3(CLI 통합) 완료(2026-11-03, SwiftUI 시범 앱). 남은 것은 S4 문서·둘째 앱 검증. 조사 결과를 바탕으로 방식 ②(QA 빌드 직전 소스 삽입)로 결정.

### 왜 UIKit 방식이 안 되나

AutoID는 실행 중에 `Mirror`로 **프로퍼티 이름**을 읽는다. SwiftUI는 `var body`가 매번 만드는 이름 없는 값이고 화면 요소는 SwiftUI 내부의 비공개 객체(`SwiftUI.AccessibilityNode`)가 만든다. 실행 중에 읽을 이름이 없고, Apple DTS도 "SwiftUI 뷰는 UIView와 1:1로 대응하지 않으며 identifier로 찾는 방법은 없다"고 답했다.

### 검토한 방식

| 방식 | 결과 |
|---|---|
| ① 런타임 swizzle | 시뮬레이터 iOS 27 공유 캐시에 `SwiftUI.AccessibilityNode`가 있어 가능은 하나, 비공개·해시 심볼이라 OS마다 깨질 수 있고 결국 라벨 기반. 탈락 |
| ② QA 빌드 직전 소스 삽입 | 공개 API만 사용. QA 워크트리에만 적용하므로 "앱 코드를 고치지 않는다" 원칙과 맞음. **채택** |
| Swift 매크로 | body 매크로(SE-0415)는 아직 실험 플래그 필요. attached 매크로는 기존 `body`를 못 고침. 앱에 패키지 의존성도 넣어야 함. 탈락 |
| 기성 도구 | SwiftUI 소스에 ID를 자동 삽입하는 공개 도구 없음. lint(BrowserStack), 상수 생성(tandha, num42 매크로), AI 편집(Xcode 26 어시스턴트, 스킬)뿐. 업계 답은 "소스에 명시" |
| 보조: 화면 스코프 | `_UIHostingView`는 UIView라 AutoID가 공개 API로 `rootView` 타입 이름을 붙일 수 있음. 자식은 글자로 찾되 화면 안에서만. 혼합 앱용 보조 수단으로 보류 |

### 동작 흐름

```text
qakit build-app
  1. 전제 확인   앱 폴더가 QA 워크트리인지(qa/workspace), 대상 .swift가 git에서 깨끗한지
  2. 삽입        swiftui-ids insert <sources> → .accessibilityIdentifier(...) 끼워 넣고 manifest 기록
  3. 빌드        xcodebuild (기존 그대로)
  4. 복원        항상(finally, SIGINT 포함) git checkout -- <삽입한 파일>, manifest 삭제
```

- 워크트리 소스는 **빌드하는 동안만** 바뀐다. 평소엔 `develop`과 같아서 `sync`의 merge가 깨지지 않고, 레포 이력에 아무것도 남지 않는다.
- QA 워크트리가 아니면(`--in-project`, `qa-workspaces/`) 삽입을 거부한다. 개발 폴더는 절대 건드리지 않는다.
- 복원에 실패하면(강제 종료 등) manifest가 남는다. `qakit doctor`가 이를 찾아 `qakit swiftui-ids --restore`를 안내한다.
- `autoid: embedded`(실기기)에서도 같은 흐름. 소스 단계라 주입 방식과 무관하다.
- 삽입 대상은 `ids.sources`(기본: 앱 폴더). 레포 밖 패키지·외부 SDK는 UIKit과 같은 한계로 제외.

### 구성 요소

| 부분 | 역할 |
|---|---|
| `Tools/swiftui-ids` | SwiftSyntax(604) 기반 Swift 패키지. `list`(ID만 계산, `--json`), `insert`(소스 수정 + manifest에 원본 보관), `restore`(manifest로 복원). 첫 빌드는 SwiftSyntax 컴파일로 약 3분, `Tools/swiftui-ids/.build/release/swiftui-ids` |
| gen-ids | SwiftUI ID는 Python으로 다시 구현하지 않고 `swiftui-ids list`를 호출해 합친다. **삽입과 상수 생성이 같은 코드**라 규칙 불일치 버그가 원천 차단된다 |
| qakit CLI | `build-app` 훅(워크트리 확인 → insert → 빌드 → finally restore), `doctor` 검사(워크트리·manifest 잔존), `swiftui-ids --list\|--insert\|--restore`. `gen-ids`가 `list --json`을 트리에 합쳐 `QAID` 상수로 만들고(순서 번호는 `_0`), `check`·`gen-ids --verify`는 그대로 동작 |
| `qakit.yml` | `swiftui: auto \| insert \| off` (기본 auto: `import SwiftUI`가 있는 파일이 있으면 삽입). `ids.sources`로 빌드되는 모듈 폴더만 지정 |
| 스킬 | SwiftUI ID 규칙과 함정(아래) 추가 |

### ID 규칙 (SwiftUI)

접두사는 `body`를 가진 **View 타입 이름**. 중첩 타입은 `바깥.안쪽`. `@ViewBuilder` 함수·계산 프로퍼티·extension의 코드도 같은 타입 접두사를 받는다.

| 대상 | 형식 | 예 |
|---|---|---|
| 바인딩이 있는 컨트롤 (TextField, SecureField, TextEditor, Toggle, Picker, Slider, Stepper, DatePicker) | `뷰타입.바인딩경로` | `TextField(text: $email)` → `LoginView.email`, `$vm.email` → `LoginView.vm.email` |
| 라벨이 문자열 리터럴인 컨트롤 (Button, NavigationLink, Link, Menu) | `뷰타입.종류.라벨` | `Button("로그인")` → `LoginView.Button.로그인` |
| 라벨이 클로저인 Button | 안의 첫 `Text("…")`/`Label("…")`/`Image(systemName:)` 리터럴 | `Button { } label: { Image(systemName: "xmark") }` → `LoginView.Button.xmark` |
| 라벨을 정적으로 알 수 없음 (보간 문자열, 변수) | `뷰타입.종류.N` (body 안 등장 순서) | `Button(item.title)` → `ListView.Button.0` |
| 같은 ID가 한 타입 안에 둘 이상 | 두 번째부터 `_2`, `_3` | `LoginView.Button.확인_2` |
| 컨트롤 하나짜리 커스텀 뷰의 호출부 | `뷰타입.커스텀뷰타입.인자리터럴` (enum `.close`, 문자열) / 없으면 `.N` | `IconButton(icon: .close)` → `HeaderView.IconButton.close`. 바깥 ID가 안쪽 ID를 덮는다(S1 확인). 도구가 커스텀 뷰 body를 분석해 말단 컨트롤이 정확히 하나일 때만 붙인다 |
| 컨트롤 둘 이상인 커스텀 뷰의 호출부 | 붙이지 않음 | 붙이면 안의 ID가 전부 덮인다(S1 확인). 안쪽 body가 자기 타입 접두사로 받음 |
| ForEach/List 행 | 행 콘텐츠에 `.accessibilityElement(children: .contain)` + `뷰타입.row` | 행은 여러 개가 같은 ID. 테스트는 index·라벨로 고름 (UIKit 셀과 동일). `.contain` 동작은 S1에서 확인, List 셀 구조는 미확인 |
| Text, Image, 컨테이너(VStack 등) | 붙이지 않음 | 글자로 찾기. 컨테이너에 ID를 붙이면 자손 요소 ID를 전부 덮는다(S1 확인) |

라벨 문자열은 공백·구두점을 `_`로 바꾸고 20자에서 자른다. 그래야 ID 문자열과 `QAID` Swift 상수 이름이 같아진다(Swift 식별자는 한글 허용).

앱이 이미 `.accessibilityIdentifier`를 붙인 식, `.accessibilityHidden(true)`인 식은 건드리지 않는다 (UIKit과 같은 원칙).

### 조사로 확인한 함정 (규칙에 반영)

- **컨테이너 ID는 자식 ID를 덮어쓴다.** VStack에 붙이면 안의 요소가 전부 그 ID가 된다. Apple 엔지니어의 해법은 `.accessibilityElement(children: .contain)`을 먼저 붙이는 것. → 말단 컨트롤에만 붙이고, 행만 `.contain`으로 감싼다.
- **List 행 안 HStack에 붙이면 셀이 아니라 안의 Text에 붙는다.** → 행 규칙.
- **Button은 자식을 합치고 XCUITest는 Button의 accessibilityElement 설정을 무시한다.** → Button 안 Text가 아니라 Button 자체에 붙인다.
- **수식어 순서가 결과를 바꾼다** (introspect 같은 수식어 뒤에 두면 사라진 사례). → 호출식 바로 뒤, 다른 수식어 앞에 삽입.
- **ID는 앱 전체에서 유일하고 정적이어야 한다** (Apple 권고). → 콘텐츠로 ID를 만들지 않는다. 동적 라벨은 순서 번호.
- **SwiftUI TextField의 ID는 안의 UITextField에 전달되지 않는다.** XCUITest 접근성 트리에는 보이므로 테스트에는 문제없음. AutoID의 UIKit 규칙과 섞이지 않게만 주의.

### S1 결과 (2026-11-03, SwiftUI 시범 앱의 온보딩·로그인 화면)

QA 워크트리 소스에 손으로 `.accessibilityIdentifier`를 넣고 두 번 빌드해 `dump`로 확인했다. 베이스라인 커버리지 0% → 67%(온보딩), 75%(로그인).

| 실험 | 결과 |
|---|---|
| 리터럴 라벨 Button (`Text("건너뛰기", bundle:)`) | ✅ `OnboardingView.Button.건너뛰기` |
| 커스텀 뷰 안 Button, 동적 라벨 → 순서 번호 | ✅ `NextButton.Button.0`, 같은 커스텀 뷰 3개면 전부 같은 ID (`LoginButton.Button.0`) |
| Button 안 Text에도 ID | Text가 Button의 자식 요소로 **자기 ID를 유지**. Button이 자식 ID를 지우지 않음 |
| 커스텀 뷰 호출부 ID (안쪽 ID와 함께) | ✅ 바깥이 이김. `.disabled()` 앞이든 뒤든 같음 |
| 컨테이너(VStack) ID, `.contain` 없이 | ❌ 직계 자손 요소(Button, CollectionView)의 ID를 전부 덮음. 단, Button 안의 Text(요소의 자식)는 유지 |
| 컨테이너 ID + `.accessibilityElement(children: .contain)` | ✅ 컨테이너가 `Other #id`로 나오고 자식 ID 유지 |
| TabView(.page) | XCUITest에는 CollectionView/Cell로 보임. ID 없는 Cell이 커버리지를 깎음 |
| NavigationStack 기본 뒤로가기 | Button 라벨 "backButton", ID 없음. 규칙 필요 (미결) |

도구에서 같이 발견한 것:
- `qakit build-app`의 `-sdk iphonesimulator`가 Tuist/SPM 매크로 플러그인(macOS 실행 파일)까지 시뮬레이터용으로 빌드해 "produced malformed response"로 실패 → `-sdk` 제거 (`-destination`이 SDK를 정함). 수정함.
- 워크트리의 `.git/info/exclude`는 `--git-dir`이 아니라 `--git-common-dir` 아래 것을 읽는다 → 수정함.
- 세션 중간 화면(다시 켜면 못 가는 화면)을 보려고 시나리오 `dump: 이름` 단계 추가 → `results/dumps/이름.txt`.
- Tuist 프로젝트는 워크트리에 `tuist generate`를 먼저 해야 `init`이 workspace를 찾는다. `init`의 로컬 파일 복사가 `*.xcodeproj`·`Derived/`·`.githooks`까지 가져온다 → 제외 목록 보강 필요 (S3).
- 1MB 넘는 gitignore 폴더(RN 프레임워크 263MB)는 복사되지 않아 손으로 복사했다 → `qakit.yml`에 복사 목록을 적는 방안 (S3).

### S2 결과 (2026-11-03)

`Tools/swiftui-ids`를 만들어 시범 앱(Tuist·TCA, SwiftUI 위주)의 `Projects/`(보관용 복사본 제외, 92개 파일)에 돌렸다. ID 139개를 40개 파일에 삽입한 소스가 **컴파일 에러 없이 빌드**됐고, 온보딩·로그인 화면 덤프에 나온 앱 ID 7개가 **모두 `list` 결과와 일치**했다 (로그인 화면 커버리지 100%). `restore` 뒤 `git status` 깨끗.

구현하면서 규칙에 더한 것:
- **모듈 키**: 같은 타입 이름이 다른 모듈에 있을 수 있다 (같은 화면 이름이 V1·V2 모듈에 각각). 경로의 `Sources` 바로 위까지를 모듈 키로 삼아 (모듈, 타입)별로 번호·중복을 매긴다. ID 문자열에는 모듈이 들어가지 않으므로 두 모듈이 같은 ID를 낼 수 있다 → 상수 생성 때 중복 제거 필요 (S3).
- **컨트롤 하나짜리 판정**에 "컨트롤 밖에 Text/Image/Label이 없다"를 추가. 버튼 하나와 설명 글자가 있는 화면 뷰(점검 안내 화면)를 래퍼로 오인해 호출부 ID가 글자에도 붙는 것을 막는다.
- **행 규칙 제한**: 행 콘텐츠에 XCUITest가 보는 것(컨트롤·글자·그림·커스텀 뷰)이 있을 때만, 그리고 콘텐츠가 호출식일 때만 붙인다. 점(Capsule)만 있는 ForEach, `if`/`switch`로 시작하는 행은 제외 (if 식 뒤에는 수식어를 못 붙인다).
- 라벨 추출은 `Text("x", bundle:, comment:)`, `String(localized: "x", …)`, `LocalizedStringKey`, `Label`, `Image(systemName:)`까지.
- `#Preview`, `PreviewProvider`, `*Tests`·`*Demo` 폴더는 건너뛴다.
- S1 미결이던 "backButton"은 앱의 커스텀 뒤로가기 뷰여서 `<그 뷰>.Button.0`으로 잡혔다. 시스템 기본 뒤로가기는 여전히 미결.

### S3 결과 (2026-11-03)

- `qakit build-app`: 삽입 → 빌드 → `finally` 복원. 시범 앱에서 139개 삽입 빌드 뒤 manifest 삭제·`git status` 깨끗 확인. `sync`·`restore`·`test`의 자동 재빌드도 같은 함수를 지나므로 함께 적용된다.
- 삽입 전 확인: QA 워크트리(`--git-dir` ≠ `--git-common-dir`)가 아니면 실패, manifest가 남아 있으면 실패, 워크트리의 추적 Swift 파일에 미커밋 변경이 있으면 실패.
- `gen-ids`: `swiftui-ids list --json`을 UIKit 트리에 합친다. 시범 앱 `Projects/` 기준 ID 150개(SwiftUI 139). `gen-ids --verify` 덤프 6개 불일치 0. `QAIDs.swift`는 `swiftc -parse` 통과. 시나리오를 `tap: OnboardingView.Button.건너뛰기` 같은 ID로 고쳐 `check`·`run` 통과.
- 도구 빌드 여부는 소스 해시 스탬프로 판단한다 (수정 시각은 checkout·복사로 흔들려 두 번 빌드했다).
- `init`의 로컬 파일 복사에서 `*.xcodeproj`·`*.xcworkspace`·`Derived`·`.githooks`·`.tuist`·`.codex`·`.obsidian`을 제외했다.
- 문서: README(준비물·한계·"SwiftUI 화면의 ID" 절), cli.md, troubleshooting.md, SKILL.md(SwiftUI 화면 찾는 법), 템플릿 `qakit.yml`.
- 남은 것(S4): 둘째 앱(혼합 UIKit+SwiftUI) 검증, 1MB 넘는 gitignore 폴더 복사 목록(`qakit.yml`), 시스템 기본 뒤로가기 규칙.

### 단계

| 단계 | 내용 | 완료 조건 |
|---|---|---|
| S1. PoC | 손으로 삽입 → `dump` (시범 앱) | ✅ 커버리지 0→67~75%. 컨테이너 덮어쓰기·`.contain`·Button 자식 동작 확인, 호출부 규칙 확정 |
| S2. 도구 | `Tools/swiftui-ids` (list/insert/restore), 위 규칙 전부 | ✅ 시범 앱 139개 삽입 빌드 성공, 덤프 ID 7/7 일치, 복원 뒤 git 깨끗 |
| S3. CLI | build-app 훅, 복원 보장, doctor, gen-ids 통합, `qakit.yml` 항목 | ✅ 시범 앱: 훅 빌드 뒤 git 깨끗, `gen-ids --verify` 불일치 0, ID 시나리오 `check`·`run` 통과 |
| S4. 문서·검증 | 스킬 규칙, README 한계 갱신, 혼합(UIKit+SwiftUI) 앱 한 개 더 | 새 AI 세션이 스킬만 보고 SwiftUI 화면 테스트를 첫 실행에 통과 |

S1~S3은 SwiftUI 시범 앱의 QA 워크트리에서 마쳤다. 다음은 S4: 혼합(UIKit+SwiftUI) 앱 하나 더, 새 AI 세션이 스킬만 보고 SwiftUI 화면 테스트를 첫 실행에 통과하는지.

### 미결

- ~~커스텀 뷰 호출부 이름~~ → S1에서 확정 (컨트롤 하나일 때만 호출부에 붙임, ID 규칙 표 참고).
- NavigationStack 기본 뒤로가기(라벨 "backButton")·toolbar 항목: 소스에 없는 요소라 삽입으로 못 붙인다. UIKit의 `VC.nav.left.N`처럼 라벨 기반 규칙을 테스트 쪽에 둘지 검토.
- 커스텀 뷰가 **레포 밖 패키지**에 있으면 body를 못 보므로 호출부에 붙이지 않는다 (외부 SDK 한계와 동일).
- `if`/`switch` 양쪽에 같은 라벨 Button이 있으면 `_2`가 붙는다. 한 번에 하나만 보이므로 논리적으로는 같은 버튼. 자주 걸리면 분기별 번호를 없애는 규칙 검토.
- 행 ID의 `.contain`이 List 셀 구조(XCUITest `cells`)와 어떻게 맞물리는지는 S1에서 확인.

## 상주 실행기 설계 (다음 단계)

> 상태: R1(PoC)·R2(CLI)·R3(run 통합) 완료 (2026-11-06). R4(문서)·R5(실기기 USB·Wi-Fi) 완료 (2026-11-07). 시뮬레이터 먼저, 실기기는 나중.

### 왜 필요한가

지금 `qakit run`은 시나리오마다 `xcodebuild test-without-building`을 새로 띄운다. 실행기는 미리 빌드해 두므로 컴파일은 없지만, 매번 실행기 설치·실행, 테스트 세션 연결, 앱 실행을 처음부터 한다.

| 문제 | 시범 앱(SwiftUI) 홈 QA에서 본 것 |
|---|---|
| 느림 | 시나리오 하나 20~40초 중 실제 단계는 몇 초. 나머지가 준비 시간 |
| 탐색이 느림 | 화면 하나 보려고 탐색 시나리오를 쓰고 → 돌리고 → 덤프를 읽는 일을 여러 번 반복 |
| 가끔 멈춤 | `xcodebuild`가 결과 없이 멈춤 (원인 미확인, 다시 돌리면 통과). 감시 스크립트로 150초 뒤 끊고 재시도해 넘겼다 |

### 무엇을 바꾸나

실행기(XCUITest)를 한 번 띄워 두고 명령만 주고받는다. Maestro·Appium(WebDriverAgent)과 같은 구조다. iOS에서 다른 앱을 조작할 수 있는 건 XCTest 프로세스뿐이라 실행기 자체는 그대로 필요하다.

| 방식 | 컴파일 | 실행기 프로세스 | 한 번 실행 비용 |
|---|---|---|---|
| 일반 XCUITest | 고칠 때마다 | 매번 새로 | 빌드 + 준비 + 동작 |
| 지금 시나리오 | 처음 한 번 | 매번 새로 | 준비 + 동작 |
| 상주 실행기 | 처음 한 번 | 계속 떠 있음 | 동작만 |

### 동작

```text
qakit serve                     한 번. 백그라운드로 xcodebuild … -only-testing ScenarioTests/test_serve
  실행기: 끝나지 않는 테스트 test_serve
    ├─ 127.0.0.1:<포트>에 작은 HTTP 서버 (Network.framework)
    ├─ 준비되면 포트·토큰을 상태 파일에 쓴다 → qakit이 읽음
    └─ 메인 스레드에서 명령 큐를 돌며 하나씩 실행 (XCUITest API는 메인 스레드)

qakit do 'tap: home_search_button'   → POST /step   → 1초 안에 결과
qakit do dump                        → POST /dump   → 화면 구조 텍스트
qakit run home-02                    → POST /run    → 시나리오 전체 (서버가 있으면 자동으로 이 길)
qakit serve --stop                   → POST /stop   → 테스트가 끝나고 xcodebuild 종료
```

- 시뮬레이터 프로세스는 Mac과 같은 네트워크를 쓰므로 Mac에서 `127.0.0.1:<포트>`로 바로 붙는다 (R1에서 확인).
- 상태 파일: `~/.qakit/serve/<udid>.json` (pid, 포트, 토큰, 작업공간, 실행기 해시, 시작 시각).

### 명령 (HTTP, JSON)

| 경로 | 하는 일 | 앱 재실행 |
|---|---|---|
| `GET /ping` | 살아 있는지, 실행기 해시, 앱 상태 | — |
| `POST /step` | 시나리오 단계 하나 (`tap`, `wait`, `expect`, `swipe` …, 지금 문법 그대로) | 안 함 |
| `POST /run` | 시나리오 JSON 전체 (`qakit run`이 지금 만드는 것 그대로) | 함 (`launch: false`가 아니면) |
| `POST /dump` | 지금 화면 구조 (`QADump`) | 안 함 |
| `POST /launch` | 앱 다시 실행 (AutoID 주입 환경 포함) | 함 |
| `POST /stop` | 서버 종료 | — |

응답은 `{ ok, message, notes[], durationMs, dump?, screenshot? }`. 실패하면 `ok: false`와 원인, 그 시점 화면 구조를 같이 돌려준다 (지금 실패 요약과 같은 내용).

### 핵심 제약: 실패해도 죽지 않아야 한다

지금 실행기는 실패하면 `XCTFail`을 부르고 `continueAfterFailure = false`라서 그 자리에서 테스트가 끝난다. 상주 실행기에서는 명령 하나가 실패해도 서버가 살아 있어야 한다.

- `QAScenarioRunner`에 실패 처리 방식을 둔다: 지금처럼 기록(`XCTFail`) / 오류로만 던짐. 서버 모드는 오류로만 던지고 응답에 담는다.
- XCUITest 자체가 내는 실패(예: 화면 밖 요소 스와이프)는 서버용 테스트 케이스에서 `record(_ issue:)`를 가로채 현재 명령의 오류로 바꾸고 테스트에는 남기지 않는다. 서버 모드는 `continueAfterFailure = true`.
- `runStep`을 바깥(서버)에서 부를 수 있게 연다. 시나리오 변수(`vars`)와 스냅샷은 `/run`마다 새로, `/step`끼리는 이어진다 (`qakit do --reset-vars`로 비움).

### 결과·기록

- `/run` 결과는 지금처럼 `results/`에 실행 폴더를 만들고 요약을 쓴다. xcresult는 없으므로 실패 시점 화면 구조와 스크린샷(`app.screenshot()`)을 응답으로 받아 Mac에서 파일로 저장한다.
- 실행 기록(`qakit history`), QA README 자동 갱신, 시나리오 잠금은 지금과 같게 유지한다.

### 수명과 안전장치

| 상황 | 처리 |
|---|---|
| 명령이 멈춤 (앱이 조용해지지 않음 등) | Mac 쪽 요청 제한 시간(기본 120초, `--timeout`). 넘으면 서버를 죽이고 다시 띄운 뒤 실패로 보고. 지금처럼 10분 넘게 기다리지 않는다 |
| 서버가 죽음 (시뮬레이터 재부팅, 실행기 종료) | `ping` 실패 → 상태 파일 정리 → 다음 명령 때 자동으로 다시 띄움 |
| 실행기 코드가 바뀜 (`qakit update`) | 상태 파일의 실행기 해시가 다르면 다시 띄움 |
| `build-app`으로 앱 재설치 | 앱만 꺼진다. 서버는 그대로, 다음 명령이 앱을 다시 실행 |
| 오래 안 씀 | 30분 동안 명령이 없으면 스스로 종료 (`--idle`) |
| 다른 실행과 충돌 | 서버가 떠 있으면 `run`·`dump-ui`는 서버로 보낸다. `--no-serve`로 지금 방식을 강제하면 서버를 먼저 멈춘다. 명령 하나하나는 지금처럼 시뮬레이터 잠금을 잡는다 |
| 다른 앱이 화면을 가로챔 | 명령 전에 대상 앱이 앞에 있는지 확인하고, 아니면 바로 실패로 알린다 (다른 앱이 떠 있어 10분 멈췄던 경우) |
| 보안 | 127.0.0.1에만 열고, 상태 파일의 무작위 토큰을 요청마다 확인 |

### 실기기

기기 안 실행기는 Mac의 `127.0.0.1`이 아니다. USB 포트 전달(usbmux) 또는 무선 터널이 필요하고, 측정(`--bench`)과 함께 쓸 때 연결이 끊긴 적이 있다. 시뮬레이터에서 안정화한 뒤 R5에서 따로 본다. 그전까지 실기기는 지금 방식.

### 스킬·AI 작업 방식

- 탐색: 시나리오를 쓰기 전에 `qakit do`로 한 단계씩 눌러 보고 덤프를 읽는다. 탐색용 시나리오 파일을 만들지 않는다.
- 작성: 확인한 단계를 그대로 `.qa.yml`에 옮긴다 (`qakit do`의 입력이 곧 시나리오 단계 문법).
- 시나리오의 독립성은 그대로: `/run`은 시작할 때 앱을 다시 실행한다.

### R1 결과 (2026-11-06, 시범 앱 홈 화면, iPhone 17 시뮬레이터)

구현: `Sources/QAKit/Serve/QAServer.swift`(Network.framework, 127.0.0.1, 토큰, 요청 큐), `ScenarioTests.test_serve`(메인 스레드 루프), `QAScenarioRunner.recordsFailures`·`runStep(json:)`, `QAError.failed`. 띄우기는 qakit 내부 함수(`run_scenario_runner(ws, "test_serve", …)`)를 부르는 임시 스크립트로 했다.

| 확인 | 결과 |
|---|---|
| Mac → 시뮬레이터 안 리스너 `127.0.0.1` | ✅ 붙는다. 역방향 구조 필요 없음 |
| 서버 뜨는 시간 (xcodebuild ~ 상태 파일) | 35초 (앱 실행 포함) |
| `/ping` | 첫 요청 2.2초, 이후 0.01~0.1초 |
| `/step` 탭 | 첫 탭 2.7초, 이후 0.2~1초 (지금 방식은 같은 동작에 20~40초) |
| 실패한 단계 | 서버 유지. `ok: false` + 원인 + 실패 시점 화면 구조 |
| XCUITest 자체 실패 (화면 밖 스와이프) | `record(_:)`에서 가로채 응답으로. 테스트 실패로 남지 않음 |
| 실패 뒤 다음 단계 | 정상 |
| 토큰 없이 요청 | 401 |
| `/launch` (앱 다시 실행) | 14.9초. 앱 실행이 원래 무겁다 → `/run`도 시작마다 이만큼 든다 |
| `/stop` | 테스트 ✅ 통과로 끝나고 xcodebuild 종료 |

배운 것:
- 시나리오 한 번의 비용 대부분은 xcodebuild 준비(약 20초)와 앱 실행(약 15초)이다. 상주 실행기는 앞의 것을 없앤다. R3의 "시나리오 하나 10초 안" 목표는 앱 재실행 비용 때문에 어렵다 → 목표를 "준비 시간 제거(시나리오당 약 20초 단축)"로 바꾸고, 같은 앱 상태에서 이어 가도 되는 시나리오는 `launch: false`로 묶는 방안을 R3에서 본다.
- 10분 넘게 도는 동안 XCTest가 테스트를 끊는지는 아직 확인 안 함 (66초 실행만 확인).

### R2 결과 (2026-11-06, 시범 앱 온보딩·로그인 화면, 로그아웃 상태 시뮬레이터)

`qakit serve [--stop|--status|--idle|--no-launch]`, `qakit do '<단계>'|dump|launch|reset|ping [--timeout]`. 상태 파일 `~/.qakit/serve/<udid>.json`(pid, 포트, 토큰, 작업공간, 실행기 소스 해시). 실행기에 `/reset`과 "대상 앱이 맨 앞에 없으면 바로 실패"를 더했다.

| 확인 | 결과 |
|---|---|
| 서버 없이 `qakit do ping` | 자동으로 띄움. 실행기 빌드 포함 첫 명령 40초, 빌드 없으면 20초 |
| `qakit do 'tap: …'` / `wait` | 명령 전체 0.8~2.2초 (CLI 시작·잠금 포함) |
| `qakit do dump` | 화면 구조 출력 + `results/ui-dump.txt` |
| 실패한 단계 | ❌ 원인 + `results/do-fail-dump.txt`, 종료 코드 1, 서버 유지 |
| 서버 프로세스 강제 종료 | 다음 `qakit do`가 "응답 없음"으로 알아채고 다시 띄움 |
| 요청 제한 시간 초과 (`--timeout 5`) | 6초 만에 실행기를 바로 끝내고 알림. 남는 프로세스 없음 |
| 서버가 떠 있는데 `qakit run` | 시작 전에 상주 실행기를 멈추고 평소대로 실행, 통과 |
| `use:` 공통 단계 | 펼쳐서 실행. 없는 단계 파일은 오류 메시지로 |

다듬은 것: 제한 시간 초과 때 바쁜 서버에 `/stop`을 보내고 기다리느라 정리가 23초 걸렸다 → 기다리지 않고 바로 끝낸다(`force`).

### R3 결과 (2026-11-06, 시범 앱 홈 시나리오 11개, 로그인된 시뮬레이터)

실행기에 `/run`(시나리오 전체, 새 실행기 인스턴스, 끝난 뒤 `qakit do`가 그 변수로 이어 감)을 더했다. 메모는 `QATestCase.noteSink`로, 지나간 단계는 `QAScenarioRunner.trail`로 모아 응답에 담는다. 실패하면 화면 구조와 스크린샷(base64)도 담는다 (`QADump.run(save: false)`로 `results/ui-dump.txt`를 덮지 않는다).
`qakit run`은 이 작업공간용 상주 실행기가 떠 있으면 자동으로 그쪽으로 간다. `--serve`(없으면 띄움), `--no-serve`(xcodebuild 강제), `--timeout`(기본 600초). `--reset`이면 앱 데이터 경로가 바뀌므로 실행기를 새로 띄운다. `--bench`·실기기는 지금 방식.
결과 폴더(`output.log`, 실패 시 `failure.png`·`failure-dump.txt`), `results/latest`, `history.jsonl`(`"via": "serve"`), 실패 요약 형식은 xcodebuild 경로와 같게 남긴다.

| 확인 | 결과 |
|---|---|
| 홈 시나리오 11개 | 모두 통과 (재시도 없음) |
| 같은 시나리오 3회씩 (명령 전체) | xcodebuild 34.9·35.5·32.5초 (평균 34.3) / 상주 실행기 27.3·25.7·26.6초 (평균 26.5) → **약 8초(23%) 단축** |
| 실패 시나리오 | 원인·마지막 단계·실패 시점 화면 구조·스크린샷, 종료 코드 1, 기록 `Failed` |

배운 것:
- R1에서 "xcodebuild 준비 약 20초"로 본 것은 과대 추정이었다. 실제 차이는 약 8초다. 시나리오 시간의 대부분은 앱 재실행과 단계 자체(화면 로딩 대기)다.
- 명령 전체와 실행기 안 시간 사이에 약 6~7초가 남는다 (앱 변경 확인·ID 검사·기록·README 갱신 등 qakit 쪽 일). 두 경로가 함께 쓰는 비용이라 따로 줄일 수 있다 → 아래 "qakit 쪽 준비 시간".
- 다른 날·다른 도구로 잰 시간과 비교하면 틀린다. 같은 조건에서 번갈아 여러 번 잰다.

### R4 결과 (2026-11-07, 시범 앱 찜 탭, 로그인된 시뮬레이터)

문서: README "빠르게 돌리고 눌러 보기" 절, SKILL.md(탐색은 `qakit do`), cli.md, troubleshooting.md. 함께 고친 것: 상주 실행기로 돈 `run`도 `qakit summarize`로 다시 보기(`summary.txt`), 첫 `qakit do`에 실행기 시작 포함 전체 시간 표시.

새 AI 세션(이 대화 맥락 없음, `qakit do`를 알려 주지 않음)에게 "찜 탭 테스트 만들어줘"만 줬다.

| 확인 | 결과 |
|---|---|
| 탐색 방법 | SKILL §2-3을 따라 `qakit do` 8번 + `qakit do dump`. 탐색용 시나리오 파일 없음 |
| 탐색 중 실패 | 2번 (라벨 짐작, SwiftUI 세그먼트의 `selected`) → `do-fail-dump.txt`·`qakit do`로 바로 고침 |
| 시나리오 | `qakit check` → `qakit run --serve` 첫 실행 통과 (20.4초), 시나리오 수정 0번 |
| 마무리 | NOTES·README 실행 명령·`qakit save`·`qakit serve --stop` |

그 세션이 짚은 문서 문제 8가지를 반영했다: 첫 명령 시간(문서 20~40초 → 실제 약 1분, 출력에 시작 시간이 빠짐), 누르기 전에 덤프로 라벨 확인, 탭 전환 판정의 시나리오 예시와 SwiftUI 커스텀 탭바 ID, `wait-any` + `if` 분기 예시, `save`는 커밋 안 함, 보고 근거(`run`), 돌려 보지 못한 분기는 "미검증"으로 기록, `run --serve`가 언제 필요한지.

### R5 결과 (2026-11-07, 시범 앱, iPhone 15 Pro Max iOS 26.3, USB)

방식: 기기 안 실행기는 Mac이 정한 포트(`SERVE_PORT`)로 `127.0.0.1`에 연다. Mac은 usbmuxd(`/var/run/usbmuxd`, Xcode·iproxy와 같은 USB 포트 전달)에 `Connect`를 보내 그 포트로 붙고, 그 소켓 위로 HTTP를 보낸다. 외부 도구 없이 qakit 안 Python으로. 기기는 Mac 파일에 못 쓰므로 준비 여부는 Mac이 `/ping`을 반복해 안다. 서버는 기기에서도 `127.0.0.1`에만 열린다 (같은 Wi-Fi의 다른 기기에서 안 보임).

| 확인 | 결과 |
|---|---|
| 첫 `qakit do ping --device i` | 실행기 빌드 포함 34초 (준비 11초) |
| `qakit do` 탭·`expect`·`use: home` | 0.1~0.5초 (명령 전체 0.5~1초) |
| `qakit do dump` | 0.9초, 기기 화면 구조 그대로 |
| 실패한 단계 | 원인 + `do-fail-dump.txt`, 실행기 유지 |
| 같은 시나리오 (명령 전체) | 상주 실행기 7.0·6.9·7.0초 (평균 7.0) / xcodebuild 12.2·10.9·11.0초 (평균 11.4) → **약 4초(38%) 단축** |
| 상주 실행기로 돈 `run` 실패 | 원인·화면 구조·기기 스크린샷(1290×2796)·`summary.txt`, 종료 코드 1 |
| 실행 중 앱 재설치 (자동 동기화) | 실행기 유지, 다음 시나리오 통과 |
| 시뮬레이터 회귀 (요청 경로를 `http.client`로 바꿈) | `do`·`dump`·실패·`run`·`summarize` 같음 |

배운 것:
- 실기기는 xcodebuild 준비가 시뮬레이터보다 짧다 (시나리오 명령 전체 약 11초). 상주 실행기로 줄어드는 몫도 약 4초.
- usbmuxd는 Wi-Fi로만 연결된 기기를 보지 못한다 → 아래 Wi-Fi 결과.
- 기기 앱이 옛 빌드면 서비스 점검 화면이 떴다. 첫 `run`의 자동 동기화가 다시 설치하자 사라졌다.
- 상주 실행기로 돈 실기기 `run`에서는 시나리오의 `dump:` 단계 파일이 남지 않았다 (기기는 첨부로 남기는데 상주 실행기는 xcresult를 꺼내지 않음) → 2026-11-07 고침: 상주 실행기는 첨부 대신 응답(`files`)으로 받아 같은 곳에 쓴다. 이때 xcodebuild 경로도 깨져 있던 것을 찾았다: 지금 Xcode의 `xcresulttool export attachments`가 첨부 이름의 `:`·`/`를 지워(`qakit-file:dumps/x` → `qakit-filedumpsx`) qakit이 하나도 꺼내지 못했다 (`dump-ui --device`도). 이름에 경로를 16진수로 넣고(`qakit-file-<hex>`), 예전 형식도 읽게 했다.

### R5 Wi-Fi 결과 (2026-11-07, 같은 기기, USB 뺀 상태)

방식: USB가 없으면(usbmuxd에 기기 없음) `devicectl list devices`의 `tunnelIPAddress`(CoreDevice 터널의 기기 쪽 IPv6 주소, 예: `fdd4:7f67:5cdd::1`)를 읽어 `SERVE_HOST`로 넘긴다. 실행기는 **그 주소 하나에만** 열고, Mac은 그 주소로 붙는다. 터널은 페어링된 Mac과 기기 사이의 암호화된 통로라, 서버를 Wi-Fi 전체에 여는 것과 달리 같은 네트워크의 다른 기기에서는 보이지 않는다. 열지 못하면 실행기가 기기 주소 목록을 로그에 남긴다.

| 확인 | 결과 |
|---|---|
| 첫 `qakit do ping --device i` | 실행기 빌드 포함 20초 (준비 13초) |
| `qakit do` launch·`use: home`·탭·dump | 명령 전체 1.2~3초 |
| 실패한 단계 | 원인 + `do-fail-dump.txt`, 실행기 유지 |
| 같은 Wi-Fi에서 기기 IPv4(`172.30.1.72`)·IPv6 링크 주소로 그 포트 | **연결 거부** (터널 주소로만 붙음) |
| 같은 시나리오 (명령 전체) | 상주 실행기 6.9·6.8·7.4초 (평균 7.0) / xcodebuild 14.2·12.1·12.4초 (평균 12.9) → **약 6초(46%) 단축** |
| 상주 실행기로 돈 `run` 실패 | 원인·화면 구조·스크린샷·`summary.txt`, 종료 코드 1 |
| 시뮬레이터 회귀 | `do`·`dump`·`run` 같음 |

### qakit 쪽 준비 시간 (2026-11-07, 시범 앱 홈 시나리오, 시뮬레이터 상주 실행기)

`QAKIT_TIMING=1`로 단계별 시간을 재 보니, 한가할 때는 각 명령이 빠르지만(git 0.04~0.08초, simctl 0.15초) 시나리오가 앱을 다시 띄우는 등 Mac이 바쁠 때 같은 명령이 몇 초씩 걸렸다. 그런 명령이 한 번 실행에 여러 번 불렸다.

| 단계 | 전 | 한 것 |
|---|---|---|
| `app_state` (앱 레포 git status·diff·ls-tree) | 한 실행에 3번, 실행 뒤 것이 0.2~8초 | 한 실행 안에서 재사용. 워크트리 최신화로 커밋이 바뀌면 다시 계산 |
| `ensure_booted` (simctl list) | 한 실행에 2번, 0.3~6.5초 | 한 실행 안에서 재사용 |
| ID 정적 검사 (앱 Swift 742개 파싱 + swiftui-ids list) | 0.7~1.7초 | ID 생성 대상 파일의 경로·수정 시각·크기와 도구가 같으면 저장해 둔 ID 목록 (`.qakit/state/ids-check.json`). 0.05~0.2초 |
| 워크트리 `git fetch` | 0.5~0.95초 | 그대로 매번 하되 시작하자마자 백그라운드로 (ID 검사와 겹침) |

결과 (이전 0.14.1과 번갈아 4번씩, 부하 평균 5~49로 바쁜 Mac): qakit 쪽 시간(명령 전체 − 실행기 안 시간) 중앙값 **5.78초 → 2.55초**, 범위 2.80~10.17초 → 1.73~3.15초. 남은 것은 fetch(~0.5초)·simctl(~0.3초)·기록·README 갱신.

### 단계

| 단계 | 내용 | 완료 조건 |
|---|---|---|
| R1. PoC | `test_serve` + `/ping`·`/step`·`/dump`·`/launch`·`/stop`. 임시 스크립트로 띄우고 `curl`로 명령 | ✅ `127.0.0.1` 연결, 탭 0.2~1초, 실패 뒤 서버 유지 |
| R2. CLI | `qakit serve`/`--stop`/상태, `qakit do`, 상태 파일, 토큰, ping 재시작, 요청 제한 시간 | ✅ 서버를 죽여도 다음 `qakit do`가 다시 띄움, 제한 시간 초과 6초 안 정리 |
| R3. run 통합 | `qakit run`이 서버로 감, 결과 폴더·요약·실패 화면 구조, `--no-serve` | ✅ 홈 11개 같은 결과, 시나리오당 약 8초(23%) 단축 |
| R4. 문서 | README, cli.md, SKILL.md(탐색은 `qakit do`), troubleshooting | ✅ 새 AI 세션이 스킬만 보고 `qakit do`로 탐색, 시나리오 첫 실행 통과 |
| R5. 실기기 | 포트 전달 방식 조사·적용 | ✅ USB(usbmuxd)·Wi-Fi(CoreDevice 터널)로 `qakit do`·`run` 동작, 시나리오당 USB 약 4초(38%)·Wi-Fi 약 6초(46%) 단축 |

### 미결

- ~~시뮬레이터 안 리스너에 Mac `127.0.0.1`로 붙을 수 있는지~~ → R1에서 확인 (붙는다).
- ~~XCTest가 오래 도는 테스트를 끊는 제한이 있는지~~ → 2026-11-07 확인: 상주 실행기를 17분 넘게 띄우고 1분마다 ping, 5분마다 탭 → 끊기지 않음, 로그에 시간 초과 없음 (지금 실행 방식에서는 테스트 시간 제한이 걸리지 않는다).
- 가끔 멈추던 `xcodebuild`가 실행 시작 단계 문제인지, 앱이 조용해지지 않는 문제인지. 상주 실행기는 전자를 피하고, 후자는 요청 제한 시간으로만 막는다.
- `qakit test`(Swift Page 테스트)는 컴파일이 필요해 이 길을 타지 않는다. 그대로 둔다.

## tapflow에서 참고한 것 (2026-11-15)

[tapflow](https://github.com/jo-duchan/tapflow)(MIT, 팀용 시뮬레이터 스트리밍 + YAML 흐름 실행기·MCP)의 자동화 부분에서 우리에게 없는 것을 골라 우리 방식으로 넣었다. 코드는 가져오지 않았다.

| 가져온 것 | 우리 구현 | 확인 (시범 앱 로그아웃 상태, 온보딩·로그인 화면) |
|---|---|---|
| 탭 지점이 멈출 때까지 기다림 | `tap` 직전 요소 위치가 두 번 연달아 같을 때까지 (최대 2초) | 온보딩 페이지 넘김 탭 0.6~0.7초 |
| 탭의 기대 효과 | `tap` + `expect: <조건>`. 누르기 전에 이미 맞으면 실패, 누른 뒤 안 맞으면 "탭이 무시됨"으로 실패 | 효과 있는 탭 통과 / 이미 맞음 → 누르지 않고 실패 / 효과 없는 탭 → 실패 |
| 제품 실패와 환경 실패 구분 | `qakit run` 종료 코드 1(앱 판정 실패) · 2(실행 환경·설정) | 없는 시나리오·태그·시간 초과 2, 앱 실패 1, 섞이면 1 |
| 한 일을 흐름으로 저장 (Flow Capture) | `qakit do` 통과 단계 기록 → `qakit do save <이름>` 초안 + 검사 | 실패 단계는 빠지고, 저장한 초안이 새로 켠 앱에서 통과 |
| CI 연동 | 시나리오 `tags:`, `qakit run --tag/--exclude-tag`, `--junit` | JUnit XML 형식 확인, failure/error 구분 |

가져오지 않은 것: 브라우저 스트리밍·대시보드·팀 권한·앱 배포함(제품 방향이 다름), MCP 서버(AI는 `qakit do` 명령을 그대로 씀), 네트워크 끊기(iOS 필터 설치가 무거움), Android, 여러 기기 병렬(시뮬레이터마다 로그인 필요).

## UI 설계 (다음 단계)

> 상태: U1(결과 보기 + 라이브 화면 보기)·U2(시나리오 선택 목록 + 실행)·U3(라이브 조작)·U4(녹화 → 시나리오)·U5(편집·관리) 구현 (2026-11-15). 다음: 팀원 접속(인증)·기기 여러 대는 필요할 때.

### 왜

지금은 CLI와 AI 스킬만 있어 개발자·AI가 아니면 쓰기 어렵다. UI로 QA·기획·디자이너가 **결과를 보고**, **버튼으로 실행하고**, **화면을 눌러 보며 시나리오를 만들게** 한다. tapflow처럼 스트리밍 플랫폼(팀 계정·앱 배포함 등)을 만들지 않고, 이미 있는 부품 위에 얇은 화면을 얹는다.

| UI 기능 | 쓰는 부품 |
|---|---|
| 화면 조작·화면 구조 | 상주 실행기 `/step`·`/dump` (시뮬레이터·USB·Wi-Fi 실기기) |
| 누른 것 → 시나리오 | `qakit do` 기록, `do save`, 탭+기다림 합치기 |
| 저장 전 검증 | `qakit check`, `qakit run` |
| 결과 | `results/`(요약·스크린샷·덤프·단계별 시간), `history.jsonl`, JUnit |
| 실행 묶음 | 태그, 사전 확인(precheck), 같은 원인 연속 실패면 멈춤 |

### 구조

- `qakit ui` → `http://127.0.0.1:<포트>` 로컬 웹 앱. 서버는 qakit의 Python 기본 HTTP 서버(API), 화면은 **`web/`의 React + TypeScript + Vite + Tailwind** (tapflow 대시보드와 같은 계열, 흑백 위주 디자인). 빌드 결과 `ui/dist`를 저장소에 커밋해 **사용자는 Node 없이** `qakit ui`만 실행한다 (Node는 UI를 고치는 개발자만). 처음(U1~U3 첫 구현)은 순수 HTML이었고 2026-11-15에 React로 옮겼다.
- 127.0.0.1에만 열고 실행마다 무작위 토큰. 비밀값은 화면에서도 가린다.
- UI는 CLI 명령과 파일을 읽고 부르는 얇은 층 — CLI 기능이 늘어도 UI가 따라가야 할 것이 적게.
- 라이브 화면: 처음엔 `simctl io screenshot`을 1초 안팎마다 (한 장 0.5초). 실기기·H.264 스트리밍은 필요해지면.
- 클릭(U3)은 좌표를 화면 구조(덤프)에서 요소로 바꿔 **ID·라벨로** 기록 (AutoID가 강점). 좌표는 마지막 수단.
- 네이티브 macOS 앱(SwiftUI)은 빌드·배포 부담이 커서 웹을 먼저.

### 단계

| 단계 | 내용 | 완료 조건 |
|---|---|---|
| U1. 결과 보기 + 라이브 화면 보기 | 실행 목록·시나리오별 최근 결과·불안정 표시, 실패 상세(원인·마지막 단계·스크린샷·화면 구조·단계별 시간), 시뮬레이터 화면 보기(조작 없음) | 시범 앱 결과를 터미널 없이 모두 볼 수 있고, 시뮬레이터 화면이 브라우저에 보인다 |
| U2. 실행 | **시나리오 선택 목록**(체크박스·검색·태그로 한꺼번에 선택·모두 선택/해제, 목록 순서대로 실행), 옵션(앱 재사용·실패 시 멈춤 방식·사전 확인), 실시간 로그, 멈춤, 종료 코드 뜻 | 기획자가 브라우저에서 smoke를 골라 돌리고 결과를 본다 |
| U3. 라이브 조작 | 화면 위 요소 겹쳐 보기(ID·라벨), 클릭 → 탭, 대기·판정 버튼 | 브라우저에서 한 화면을 탐색 (단계당 1~2초) |
| U4. 녹화 → 시나리오 | 누른 단계 기록 → 이름·태그 → **다시 재생해 통과해야 저장** | 개발자가 아닌 사람이 YAML 없이 통과하는 시나리오를 만든다 |
| U5. 편집·관리 | YAML 편집기(검사·ID 자동 완성), 태그 관리 | 브라우저에서 고치고 바로 검사·실행 |
| 나중 | 같은 네트워크의 팀원 접속(인증), 기기 여러 대 | — |

### U1 결과 (2026-11-15, 시범 앱 작업공간)

`qakit ui`: Python 기본 `ThreadingHTTPServer`(127.0.0.1, 실행마다 토큰 → HttpOnly 쿠키) + `ui/index.html`·`app.js`·`style.css` (빌드 없음). 실행 기록에 결과 폴더 경로(`dir`)를 남기도록 했다 (예전 기록은 이름·시각으로 맞춤).

| 확인 | 결과 |
|---|---|
| 실행 기록 300개 | 0.06초, 결과 연결 297개 (예전 기록 포함) |
| 시나리오 31개 | 0.04초, 최근 10번 결과·태그·불안정 표시 |
| 실패 상세 | 요약(원인·마지막 단계)·스크린샷·화면 구조·단계별 시간·로그 |
| 라이브 화면 | `simctl io screenshot` JPEG 0.5초, 기본 1초 간격, 켜고 끄기 |
| 보안 | 토큰 없으면 401, `../` 경로 404 |

알게 된 것: 실행 기록에 앱 실패와 환경 실패(로그아웃 등)가 구분돼 있지 않아, 로그아웃 때의 실패로 여러 시나리오가 "불안정"으로 보인다 → 다음에 기록에 실패 종류(종료 코드 1/2)를 남긴다.

### U2 결과 (2026-11-15)

- 시나리오 화면을 **선택 목록**으로: 행·체크박스로 고르기, 검색, 태그 버튼으로 그 태그 전부 선택, 보이는 것 모두 선택/해제 (선택은 탭을 닫을 때까지 유지).
- 실행 바: 앱 재사용(`--reuse-app`), 실패하면(같은 원인 2번이면 멈춤 / 끝까지 / 첫 실패에서), 사전 확인. `qakit run`을 따로 띄우고(한 번에 하나, `--serve`) 출력 줄을 1초마다 보여 준다. 끝나면 종료 코드 뜻(0 통과·1 앱 실패·2 환경)과 목록 새로 고침. 다른 화면에서도 위에 "실행 중".
- 실행 요청은 쿠키 + 전용 헤더(`X-Qakit-UI`)가 있어야 받는다 (다른 사이트가 몰래 보내는 요청 막기). 빈 선택·중복 실행은 거절.
- 실행 기록에 실패 종류(`failure: env`) — 시나리오의 최근 결과에 회색으로, 불안정 판정에서는 뺀다.

| 확인 | 결과 |
|---|---|
| 헤더 없는 실행 요청 / 빈 선택 / 실행 중 또 실행 | 401 / 거절 / 거절 |
| home-03·04 (재사용·사전 확인) | 사전 확인 통과 → 2개 통과, 종료 코드 0 |
| 멈춤 | 약 10초 뒤 끝 (Ctrl+C 신호에 바로 끝나지 않아 강제 종료), 남은 프로세스 없음 |

알게 된 것: 멈춤은 `qakit run`을 끝내지만, 상주 실행기는 이미 받은 시나리오를 끝까지 돌 수 있다 (그동안 다음 실행은 잠깐 기다림).

### U3 결과 (2026-11-15)

"라이브 조작" 화면: 시뮬레이터 화면(1초마다) 위에 화면 구조(`qakit do dump`)의 요소 테두리(ID 있음 파랑 / 라벨만 주황 점선). 화면을 누르면 그 지점의 요소(누를 수 있는 종류 우선, 가장 작은 것)를 고르고 **ID 우선, 없으면 종류+라벨**(같은 것이 여럿이면 `index`, 줄바꿈 라벨은 첫 줄 `contains`)로 단계를 만든다. 탭·기다림·보이는지 확인·위/아래로 쓸기·직접 입력·앱 다시 켜기를 `qakit do`로 실행 → 시뮬레이터 잠금·기록·비밀값 가리기가 CLI와 같다. 시나리오 실행(U2) 중에는 조작을 거절한다.

| 확인 (시범 앱) | 결과 |
|---|---|
| 앱 다시 켜기 → `use: home` | 통과 (6초, 1초) |
| 화면 구조 | 요소 58개 3초, 검색 버튼 위치·ID 맞음 |
| 탭 검색 → 탭 뒤로 | 각 1.1초 |
| 없는 버튼 | 실패로 알림, 기록 안 됨 |
| 기록 | 통과한 3단계만 (`launch`부터) |

### React로 옮김 (2026-11-15)

tapflow 대시보드처럼 보이게: 왼쪽 사이드바(실행 기록·시나리오·라이브 세션, 아래에 기기·브랜치·버전), 흑백 위주 토큰(색은 `web/src/index.css`의 CSS 변수, 다크 모드는 변수만), 카드는 그림자 단계, Inter + JetBrains Mono(ID·시간은 모노). 라이브 세션은 기기 틀 안의 화면 + 위 도구 막대(일시정지·간격·앱 다시 켜기·화면 구조·요소) + 오른쪽 점검 패널. 코드·그림은 tapflow에서 가져오지 않고 직접 썼다.

- 빌드: `cd web && npm install && npm run build` → `ui/dist` (JS 189KB, gzip 59KB, 글꼴 포함 528KB). `qakit ui`는 `ui/dist`를 서빙하고, 없으면 빌드 방법을 안내한다.
- 확인: 화면 없는 Chrome으로 세 화면(실행 기록·시나리오·라이브 세션)을 찍어 그려지는 것을 확인 (시뮬레이터 화면·요소 테두리·기록된 단계 포함).

### U4 결과 (2026-11-15)

라이브 세션의 "시나리오로 저장": 이름·제목·설명·태그·시작 단계(`use: home` 등)를 넣고 → **1. 초안 만들기**(기록된 단계, 탭+기다림을 expect로 합침, `.qakit/drafts/`, 형식·ID 검사와 경고) → **2. 재생해서 확인**(앱을 새로 켜고 `qakit run <초안>`, 실시간 로그) → **3. 저장**(재생이 통과했고 그 뒤 초안이 바뀌지 않았을 때만 `scenarios/`로, README 갱신). CLI `qakit do save`도 같은 코드 + `--title`·`--tag`·`--start`.

| 확인 (시범 앱) | 결과 |
|---|---|
| 앱 다시 켜기 → 검색 열고 닫기 기록 → 초안 (`start: home`) | `use: home` + 탭 2개에 expect 합침, 제목·설명·태그, 경고 없음 |
| 재생 전에 저장 | 거절 |
| 재생 통과 → 초안을 고친 뒤 저장 | "초안이 바뀌었습니다"로 거절 |
| 다시 재생 → 저장 | `scenarios/`에 저장, README 목록에 반영 |
| CLI `do save --title --tag --start` | 같은 글 |

### U5 결과 (2026-11-15)

"편집" 화면: 왼쪽 시나리오·공통 단계 목록(찾기, 새로 만들기), 가운데 YAML 편집기(줄 번호, Tab 들여쓰기, ⌘S 저장, 되돌리기), 오른쪽 검사(고칠 때마다 0.8초 뒤 — 형식·`use:` 펼치기·앱에 없는 ID), 태그 칩(추가·삭제하면 `tags:` 줄을 고침), ID 찾기(앱 ID 검색 → 커서 위치에 넣기). 저장된 시나리오는 바로 실행(U2와 같은 실행). 시나리오 목록의 각 행에 "편집". 무거운 편집기 라이브러리 없이.

- 저장: YAML 형식이 맞아야 저장. 앱에 없는 ID는 경고로 알리고 저장은 허용. 연 뒤 파일이 밖에서 바뀌었으면(AI·다른 사람) 덮어쓰지 않는다. 저장하면 README 목록 갱신.
- UI 서버는 오래 떠 있으므로 ID 목록은 매번 파일 지문으로 확인(바뀌지 않았으면 캐시, 0.1초 안팎).

| 확인 (시범 앱) | 결과 |
|---|---|
| 파일 목록·읽기 | 시나리오 31·공통 단계 21 |
| 검사: 그대로 / 형식 오류 / 없는 ID / 없는 공통 단계 | 통과(단계 12, 태그) / "괄호·따옴표·들여쓰기" 안내 / ID 목록 / 단계 이름 |
| 저장: 밖에서 바뀜 / 새로 만들기 / 같은 이름 또 만들기 / 태그 고쳐 저장 | 거절 / 저장 / "이미 있습니다" / 저장(검사 결과 함께) |
| ID 찾기 | 앱 ID 169개 검색 |
| 화면 없는 Chrome | 편집 화면 그려짐 |

### 실시간 화면 (2026-11-15)

스크린샷(`simctl io screenshot`)은 한 장에 0.4~0.6초, 650KB라 초당 2장이 한계였다. tapflow는 SimulatorKit/CoreSimulator(비공개)로 시뮬레이터가 그리는 IOSurface를 바로 읽어 H.264로 보낸다 (창·화면 기록 권한 필요 없음). 같은 방식으로 보기만 가져왔다 — 누르기는 지금처럼 XCUITest가 ID로 (시나리오가 ID로 기록되는 게 핵심).

- `Tools/simscreen/simscreen.swift` (직접 작성, 약 150줄): `SimServiceContext` → 기기 → `io.ioPorts`의 `com.apple.framebuffer.display` → `framebufferSurface`. seed가 바뀔 때만 600px 폭 JPEG로 줄여 길이+JPEG를 stdout으로. `qakit ui`가 처음 쓸 때 `swiftc`로 빌드(소스 해시).
- 브라우저로는 MJPEG(`multipart/x-mixed-replace`) — `<img>`가 그대로 보여 주고 디코더가 필요 없다. 로컬이라 H.264까지는 필요 없었다. 도구 하나를 여러 브라우저가 나눠 보고, 보는 사람이 없으면 30초 뒤 끈다.
- 안 되면(빌드 실패·비공개 API 바뀜·시뮬레이터 꺼짐) 스크린샷 방식으로 자동 전환, 이유 표시.

| 확인 (Xcode 27, iPhone 17) | 결과 |
|---|---|
| 화면 메모리 읽기 | 1206×2622, 색·노치 정상 |
| 화면이 움직일 때 | 초당 약 20장 (목표 24), 장당 약 150KB, 도구 CPU 평균 22% |
| 멈춰 있을 때 | 2초에 한 장 |
| 화면 없는 Chrome: 쓸기 중 0.15초 간격 17장 | 9장이 서로 다름 (시트 올라오는 애니메이션까지) |
| 도구를 강제로 죽임 | "실시간 화면 멈춤 (종료 코드 -9) — 스크린샷으로" |
| 브라우저 닫음 | 36초 안에 도구 종료, 오류로 안 봄 |

### 위험

- Mac 부하: 측정 내내 부하 평균 30~50. 라이브 화면은 켤 때만, 테스트가 도는 동안엔 간격을 늘린다.
- 시뮬레이터 충돌: UI 조작(U3~)과 테스트 실행이 같은 기기를 쓰면 입력이 섞인다 → 지금의 시뮬레이터 잠금을 그대로.
- tapflow와의 관계: "팀이 브라우저로 시뮬레이터를 손으로 만지기"가 주된 필요면 tapflow를 함께 쓰는 편이 낫다. 우리 UI는 ID 기반 시나리오·결과·실패 분석에 집중.

## AI QA 설계 (다음 단계)

> 상태: A1 ✅ A2 ✅ A3 ✅ A4 ✅ (2026-11-15), 문제 보고 영상 ✅. 다음: Codex 실제 확인.

### 왜

지금 AI는 **시나리오를 만들 때만** 쓴다 (스킬 → `qakit do`로 탐색 → `.qa.yml`). 시나리오를 쓰기 전 단계 — "이 화면 한번 QA해 줘", "회원가입부터 끝까지 이상한 데 없는지" — 를 AI가 직접 앱을 조작하며 하게 하고, 그 결과를 **ID 기반 시나리오**로 남겨 다음부터는 토큰 없이 돌린다. ("AI는 만들 때만" 원칙은 그대로: AI QA는 고를 수 있는 탐색 방식이고, 남는 것은 시나리오)

tapflow에서 MCP를 가져오지 않았던 결정(위 "tapflow에서 참고한 것")을 바꾼다: 스킬 + 셸(`qakit do`)은 Claude Code에서만 되고 셸 권한이 넓다. MCP면 Codex 등 다른 AI에서도, 셸 없이 qakit 도구만 허용해 쓸 수 있다.

### tapflow는 어떻게 하나

tapflow는 AI를 직접 연결하지 않는다. **MCP 서버**(`@tapflowio/mcp-server`)를 주고, 사용자가 쓰는 Claude Code·Codex가 도구로 쓴다 (`query_ui_tree`·`tap`·`type_text`·`screenshot`·`run_flow`·`get_testing_guide` …). AI는 화면 구조를 먼저 읽고 사진은 시각적인 것만, 테스트 전에 `get_testing_guide`로 확인 목록·보고 형식을 받는다. 사람은 링크로 AI가 조작하는 기기를 커서·활동 기록과 함께 본다.

### 인증

qakit은 OAuth를 직접 하지 않는다. 사용자가 로그인해 둔 공식 CLI(`claude`, `codex`)를 부르거나(A3), 그 CLI가 qakit MCP를 부른다(A1). 토큰을 qakit이 보관하지 않아 유출·약관 문제를 피한다. 구독 로그인·API 키 사용 범위는 각 CLI 정책을 따른다 (CI는 API 키).

### 단계

| 단계 | 내용 | 결과물 |
|---|---|---|
| **A1. `qakit mcp`** | MCP 서버 (stdio, Python 표준 라이브러리). 도구: `screen`(화면 구조, 텍스트) · `screenshot`(작은 사진) · `launch` · `tap` · `type_text` · `swipe` · `wait_for` · `expect` · `step`(시나리오 단계 한 줄) — 모두 `qakit do` 단계 · `recorded_steps` · `list_scenarios` · `run_scenario` · `save_scenario`(저장 → 앱을 새로 켜고 재생 → 통과해야 남김) · `report_issue`(재현한 문제만, 사진과 함께 `results/ai/<시각>/`) · `get_testing_guide`. 서버 안내(instructions)로 순서·규칙. `qakit mcp install --claude`(작업공간 `.mcp.json`) · `--codex` | Claude Code·Codex에서 "로그인 화면 QA해 줘" |
| **A2. 지켜보기** | 라이브 세션에 "AI 조작 중" + 활동 기록(도구 호출 순서, 이유). 커서·실시간 화면은 이미 있음 | 브라우저에서 AI 작업 보기 |
| **A3. UI에서 시작** | "AI QA" 메뉴: 목표, 엔진(설치·로그인된 `claude`/`codex` 감지), 시간·횟수 한도, 시작/멈춤. 서버가 `claude -p … --mcp-config …` / `codex exec …`를 **qakit 도구만 허용**(셸·파일 수정 막음)으로 돌리고 진행을 보여 줌 | 터미널 없이 AI QA |
| **A4. 결과** | `results/ai/<시각>/`: 보고서(문제·재현 단계·사진·영상), 쓴 단계, **제안 시나리오 초안** → 사람이 재생해 통과하면 저장. 실행 기록에서 보기 | 탐색 → 재사용 시나리오 |

### A1 결과 (2026-11-15)

`qakit mcp`: MCP stdio 서버 (JSON-RPC, 표준 라이브러리), 프로토콜 2025-06-18 / 2025-03-26 / 2024-11-05. 도구 15개는 `qakit do`·`run`·`do save`를 하위 프로세스로 부른다 (UI와 같은 방식, 시뮬레이터 잠금 그대로). 도구 호출은 `results/ai/<시각>/log.jsonl` (A2에서 보여 줄 활동 기록).

| 확인 (시범 앱) | 결과 |
|---|---|
| 흉내 클라이언트: initialize·tools/list·도구 15개 | 통과. 화면 구조 43요소 1초, 탭+expect 2~5초, 사진 18KB 0.2초 |
| `save_scenario` | `use: home` + 기록 2단계 저장 → 새로 켠 앱에서 재생 통과 22초. 잘못된 이름 거절 |
| `report_issue` | `reproduced: false` 거절, true면 `issues.md` + 사진 |
| **실제 Claude Code** (`claude -p`, qakit 도구만 허용) | 지침 읽기 → launch → screen → tap+expect → screen → expect → 뒤로 tap, 55초. 거짓 버그를 보고하지 않음 |

배운 것:
- `install`은 지금 실행 중인 qakit 경로를 등록해야 한다 (처음엔 PATH의 설치본을 등록해 `mcp`가 없는 옛 버전이 불림 → AI가 셸로 우회).
- AI는 "누른 뒤 이전 버튼이 사라짐"(`missing`)을 자연스럽게 쓴다. 덮인 아래 화면 요소는 화면 구조에 남으므로, 탭 `expect` 안의 `missing`·`hidden`을 "누를 수 없음"으로 보게 실행기를 고침 (`visible`→hittable과 같은 이유).
- `qakit do` 실패에도 "대신 이 대상?" 제안을 붙임 (AI가 가장 먼저 쓰는 정보). 같은 요소를 ID·라벨로 두 번 제안하지 않게.

### A2 결과 (2026-11-15)

- MCP: 도구를 부르기 시작할 때 `now.json`(지금 하는 일), 끝나면 `log.jsonl`에 한 줄. 조작 도구에 선택 인자 `why`. 연결한 AI 이름(`clientInfo`)·MCP 프로세스 번호를 `meta.json`에.
- UI `/api/ai`: 가장 최근 세션의 기록(읽은 곳 이후만)·지금 하는 일·보고한 문제. MCP 프로세스가 끝났으면 "끝남".
- 라이브 세션 **AI 활동** 칸: 시각·동작·대상·이유·결과·걸린 시간, 지금 하는 일(경과 초), 실패 원인, 보고한 문제(심각도·사진·issues.md). AI가 조작 중이면 손 조작 잠금(헤더 표시), 세션 중엔 요소 상자 숨김(예전 화면 자리에 남아 헷갈림) → 끝나면 화면 구조 다시 읽기. AI 조작 사이에 화면 구조를 자동으로 읽지 않는다 (실행기를 같이 쓰면 AI 조작이 늦어짐).

| 확인 (흉내 클라이언트 8번 호출 + 화면 없는 Chrome 0.3초 간격) | 결과 |
|---|---|
| 조작 중 | 헤더 "AI(claude-code) 조작 중 — 조작 잠김", 기록이 1→6번으로 쌓임, 지금 하는 일 표시 |
| 일부러 틀린 ID | 빨간 줄로 "2초 안에 나타나지 않음" |
| 문제 보고 | "보고한 문제 1" 심각도·사진·issues.md 링크 |
| MCP 종료 | "연결됨" → "끝남", 잠금 풀림, 상자 0 → 59 (다시 읽음) |

### A3 결과 (2026-11-15)

- **AI QA 메뉴**: 목표, AI(설치·로그인 감지 — `claude auth status`, `codex login status`), 시간 한도(3~30분), 횟수 한도(AI 응답 20~200번), "확인한 경로를 시나리오로 저장", 시작/멈춤. 진행(AI가 하는 말·도구·이유), 보고서, 사용량, 작은 실시간 화면, AI 활동.
- **실행**: `claude -p <목표+규칙> --output-format stream-json --verbose --strict-mcp-config --mcp-config <세션>/mcp.json --tools "" --allowedTools mcp__qakit --permission-mode dontAsk --max-turns N --no-session-persistence` — 기본 도구(셸·파일)를 끄고 qakit 도구만, 묻지 않고 거절. MCP 서버에 `QAKIT_AI_DIR`를 넘겨 에이전트 출력(`agent.jsonl`)과 도구 기록(`log.jsonl`)이 한 폴더에. 시간 한도·멈춤은 프로세스 그룹째 끝냄 (MCP 서버까지).
- **Codex**: `codex exec --json -s read-only -c mcp_servers.qakit…` 어댑터를 넣었지만 이 Mac에 없어 **시험하지 못함** (UI에 표시).
- AI QA 중에는 UI의 손 조작·시나리오 실행을 서버에서도 거절.

| 확인 (시범 앱, 실제 Claude Code 2.1.325, claude.ai 로그인) | 결과 |
|---|---|
| 목표 "검색 화면 열림·빈 검색어 안내·홈 복귀" (3분·20번) | 48초, 응답 8번, $0.15 상당. qakit connected (도구 15개) |
| AI가 쓴 도구 | 지침 → launch → screen → tap+missing → screen → expect(안내 문구·최근 검색어) → 뒤로 tap+visible. 모두 why |
| 보고서 | 확인한 것 4, 문제 없음, 확인하지 못한 것과 이유("최근 검색어를 지우는 건 사용자 데이터라 안 함"), 남길 만한 단계 4 |
| UI | 진행·생각하는 중·경과/한도, 실시간 화면, AI 활동 (화면 없는 Chrome) |

### A4 결과 (2026-11-15)

- `/api/ai/sessions`·`/api/ai/session`: `results/ai/*/`의 meta·log·issues·report·agent.jsonl을 모아 요약/상세. **AI가 통과한 단계** = 마지막으로 성공한 `launch` 이후 성공한 조작(tap·type_text·swipe·wait_for·expect·step)의 결과 첫 줄 `단계: <글>` — 실제로 실행된 글 그대로, 실패한 조작은 빠짐. AI가 `save_scenario`로 남긴 것도 따로.
- 초안 만들기(`/api/draft`)가 `aiSession`을 받으면 그 단계로 (`build_scenario_text(recorded=…)`), 이후 재생 → 저장은 U4와 같은 흐름. 초안 주석에 출처 표시.
- UI: AI QA 아래 **지난 AI QA**, 세션 상세(보고서·문제 사진·진행/도구 기록 탭·통과 단계·시나리오로 저장), **실행 기록**에 AI 세션을 시각 순으로 (문제 있으면 실패 필터 쪽).

| 확인 (흉내 MCP 클라이언트 세션: launch → 검색 → 틀린 ID 실패 → 뒤로 → 문제 보고) | 결과 |
|---|---|
| 통과 단계 | 2개 (틀린 ID 빠짐), launch부터 |
| 초안 → 재생 → 저장 | `use: home` + 2단계, 재생 종료 코드 0, `scenarios/`에 저장 |
| 화면 (화면 없는 Chrome) | 지난 AI QA 목록 · 상세(문제 사진·도구 기록·통과 단계) · 실행 기록에 "문제 1" 행 |

문제 보고 영상 (2026-11-15 추가): 통째 녹화(약 1MB/초) 대신, MCP 세션이 첫 조작 때 `simscreen`(초당 10장·폭 440)을 띄워 **마지막 30초 장면만 메모리에** 두고, `report_issue` 때 `simscreen --encode`(AVFoundation, 장면의 실제 시각대로)로 `issue-N.mp4`. 세션이 끝나면 멈춤. 확인: 탭 2번 뒤 보고 → 4.5초 440×956 mp4, 세션 상세에서 재생. 끄려면 `QAKIT_AI_VIDEO=0`.

### qakit만의 점

AI가 누르는 모든 동작이 ID·라벨 기반 시나리오 단계다 (좌표 탭 없음). 그래서 AI가 한 번 확인한 경로가 그대로 `.qa.yml`이 되고, 이후 AI 없이 돈다.

### 위험

| 위험 | 대응 |
|---|---|
| 토큰 비용 | 화면 구조(텍스트) 우선, 사진은 작게(440px)·요청할 때만. 세션 시간·횟수 한도(A3) |
| AI의 잘못된 버그 보고 | `report_issue`는 재현했다고 밝혀야(`reproduced: true`) 받음. 사진 자동 첨부, A4에서 영상 |
| 비밀번호 | AI는 `{secret:키}`만 씀. 도구 결과는 지금처럼 비밀값 가림 |
| 시뮬레이터 충돌 | `qakit do`·`qakit run`의 시뮬레이터 잠금 그대로 |
| CLI 옵션 변경 | 엔진별 어댑터, 시작할 때 버전 확인 (A3) |

## AI QA 직접 터치 설계 — tapflow 방식 (다음 단계)

> 상태: 시험 ✅ · AutoID ✅ · H1 ✅ 계속 떠 있는 터치 도우미 · H3 ✅ MCP 직접 터치 모드 · H4 ✅ 커서·라이브 세션 직접 터치 (2026-11-16). H2(붙기만)는 아래 정정 때문에 건너뜀.

### 왜

지금 AI QA의 누르기는 XCUITest `element.tap()`이다. 탭 하나에 0.8~2.2초(요소 찾기·위치 멈춤·앱이 조용해질 때까지 기다림)가 들고, 실제 사용자처럼 빨리 누를 때 생기는 버그를 가리며, 길게 누르기·끌기·시스템 화면은 못 한다. tapflow는 손가락처럼 화면에 **터치 신호를 직접** 넣는다. AI QA(문제 찾기)에는 이쪽이 맞다. 시나리오 실행·시나리오 만들기·저장 전 재생은 지금처럼 XCUITest(ID로, 공개 API, 안정적).

### 시험에서 알게 된 것 (macOS 27.0.1 · Xcode 27.0 27A266a · iOS 27.0 시뮬레이터 · 시범 앱)

| 조건 | 직접 터치 |
|---|---|
| qakit 상주 실행기가 **앱을 켜고**(XCUIApplication.launch) 붙어 있을 때 — 지금 qakit | ❌ 무시 (tapflow 자체 도우미 바이너리도 같음) |
| Device Hub를 닫아도 | ❌ (원인 아님) |
| 상주 실행기를 멈추면 | ✅ |
| 상주 실행기가 **앱을 켜지 않고 붙기만**(`--no-launch`, `XCUIApplication(bundleIdentifier:)`로 화면 구조만 읽음) | ✅ 읽기 → 검색 탭 → 읽기(검색 화면) → 뒤로 → 읽기(홈), 읽기 1.0~1.2초 |

- ~~XCUITest가 켠 앱은 자동화 모드라 바깥 터치 신호를 무시한다~~ → **정정 (H1에서 다시 잼)**: 실행기가 앱을 새로 켜고 XCUITest로 누른 뒤에도 직접 터치가 매번 먹혔다 (켠 직후 ✅, XCUITest 탭 뒤 ✅ ✅). 처음 막혔을 때는 실행기가 오래 떠 있었고 화면 구조 읽기가 60초 넘게 멈춘 적이 있었다 — **실행기가 무언가를 기다리며 멈춘 상태**에서 바깥 터치가 막힌 것으로 보이지만 재현이 안 돼 확정 못 함. → 설계: "붙기만"이 꼭 필요하진 않고, 대신 **직접 터치가 무시됐는지 알아채기**(터치 뒤 실시간 화면이 바뀌지 않으면 XCUITest 탭으로 다시)가 필요.
- 터치 경로: `SimDeviceLegacyHIDClient`(SimulatorKit, Xcode 27은 `Contents/SharedFrameworks/`) + IOKit `IOHIDEventCreateDigitizerEvent`/`…FingerEvent` → `IndigoHIDMessageForTrackpadEventFromHIDEventRef` → 메시지 0x6c(와 0x10c)에 경로 표시 `UInt32(0x32)` → `sendWithMessage:freeWhenDone:…`. 좌표는 화면 대비 0~1. 마우스 방식(`IndigoHIDMessageForMouseNSEvent`)은 이 환경에서 막혀 있을 때 시험했고, 풀린 상태에선 디지타이저만 확인.
- 한 번씩 띄우는 도우미는 0.85초(프레임워크 불러오기 0.5 + 준비 0.2 + 보내기 0.1) → **계속 떠 있는 도우미**여야 탭이 0.1초대.

### tapflow는 어떻게 하나

1. 앱은 `simctl launch`로 켠다 (XCUITest가 켜지 않음).
2. 화면 구조는 상주 XCUITest 실행기(`TapflowTreeRunner`)가 `XCUIApplication(bundleIdentifier:).debugDescription`으로 **읽기만** — 켜기·앞으로 가져오기·XCUITest 탭 없음.
3. 누르기는 계속 떠 있는 Swift `touch-helper`(stdin으로 9바이트 프레임: 종류·x·y)가 디지타이저 터치로. 준비됐다고 말하기 전 입력은 버려지므로 기다림. 탭은 최소 50ms 누름(`UISwitch`가 짧은 탭을 무시). 키보드는 `IndigoHIDMessageForKeyboardArbitrary`(한글 조합 포함).
4. AI는 요소로 말하고, 실행기가 그 요소에 실제로 닿는 지점(탭 막대 등이 덮는 경우까지)을 계산해 그 좌표를 누른다.

### AutoID (확인 ✅)

`SIMCTL_CHILD_DYLD_INSERT_LIBRARIES=<QAAutoID.dylib> xcrun simctl launch --terminate-running-process <udid> <bundle> -AppleLanguages "(ko)" -AppleLocale ko_KR`

- 앱 프로세스에 `QAAutoID.dylib`가 올라감 (`lsof`: 넣으면 1, 안 넣으면 0), 언어 인자도 들어감.
- 마이 탭 화면 구조의 ID: XCUITest로 켠 앱 6개 = simctl+AutoID로 켠 앱 6개, 완전히 같음. 홈도 12개 같음 (시범 앱은 SwiftUI라 대부분 빌드 때 넣은 ID).

### 단계

| 단계 | 내용 |
|---|---|
| **H1. 터치 도우미** ✅ | `Tools/simtouch/simtouch.swift` (직접 작성): 계속 떠 있고 stdin 한 줄 명령(tap·press·swipe·down·move·up·ping) → 한 줄 답, 준비되면 `ready`, 디지타이저(없으면 마우스). `TouchHelper`(띄우기·준비 기다리기·죽으면 다시), `qakit touch`(확인용, 실행기가 앱을 켰으면 경고). **탭 왕복 약 90ms(누름 60ms 포함)**, 도우미 준비 0.46초, 쓸기 0.36초 — XCUITest 탭 0.8~2.2초 |
| **H2. 붙기만 하는 실행기** | `qakit serve --attach`: 앱은 simctl+AutoID로 켜고, 실행기는 화면 구조·조건 확인(wait·expect)만. `/dump`는 켠 앱이 없으면 떠 있는 앱에 붙어 읽음 (이 PR에 먼저 넣음) |
| **H3. MCP 직접 터치 모드** ✅ | `QAKIT_TOUCH=direct`일 때만 (UI의 AI QA "직접 터치" 체크, 기본 켬 · 시나리오 만들기·터미널 MCP는 XCUITest 그대로). `launch`는 그대로(실행기가 켬 — 정정 참고). `tap`=대상(id·label·contains·type·index) → 화면 구조(바뀌었거나 5초 지나면 다시 읽음)에서 보이는 부분 가운데 → 직접 터치, 기록은 ID 단계(`do-steps`). expect는 누르기 전·후 `qakit do --no-record`로 확인, expect가 없으면 1.2초 안에 실시간 화면이 안 바뀌면 "무시됐을 수 있음" 경고. 화면에 없거나 밖이거나 도우미가 안 되면 XCUITest 탭으로 넘김, `via: xcuitest`로 고를 수도. 새 도구 `long_press`·`drag`(대상→대상 또는 방향)·`tap_point`(좌표) — 시나리오 단계가 없어 기록 안 함. 글자 입력은 그대로 XCUITest. **시뮬레이터 확인**: 검색 열기(expect) ✅, 뒤로 ✅, 변화 없는 탭 경고 ✅, 끌기로 스크롤 ✅, 길게 누르기 ✅. 탭 자체는 0.8~1.8초(화면 구조 읽기·expect 확인 포함), 터치 신호는 약 0.1초 |
| **H4. 확인·화면** ✅ | 커서: 직접 터치는 실제로 누른 좌표(0~1) 그대로 `taps.jsonl`에 (`touch_mark`), 길게 누르기는 `press`→`press-done`("길게 누르기" 표시), 끌기는 `drag`(시작)→`drag-done`(끝, 0.5초 미끄러짐·"끌기" 표시). 라이브 세션: 도구 막대 **직접 터치 (실험)** 켜면 클릭=탭, 0.5초 넘게 꾹=길게 누르기, 끌기=끌기 → `POST /api/touch`(UI 서버가 터치 도우미 하나를 띄워 둠, 시나리오 실행·AI QA 중엔 거절). 탭이 요소 위이고 화면 구조가 지금 화면 것일 때만 그 단계를 기록 (터치 뒤·화면이 바뀐 뒤엔 다시 읽기 전까지 기록 안 함 — 옛 화면 요소로 잘못 기록하던 것 막음). **확인**: 브라우저(헤드리스 Chrome)에서 검색 열기·뒤로(단계 2개 기록 ✅), 끌기로 스크롤 ✅, 길게 누르기 ✅, 탭 왕복 약 90ms |

그대로인 것: 시나리오 실행·시나리오 만들기·저장 전 재생 = XCUITest. 직접 터치로 확인한 경로도 저장할 땐 XCUITest로 재생해 통과해야 남는다.

### 위험

| 위험 | 대응 |
|---|---|
| 비공개 API가 Xcode 업데이트로 바뀜 (tapflow도 Xcode 27에서 위치가 바뀌어 고침) | 실시간 화면처럼 안 되면 XCUITest 탭으로 자동 전환, 이유 표시 |
| 직접 터치로 된 것이 XCUITest 재생에선 안 됨 (또는 반대) | 저장 전 XCUITest 재생 통과가 거름 |
| AI QA 중 XCUITest로 켠 앱이 섞이면 터치가 조용히 무시됨 | 모드 시작 때 앱을 simctl로 다시 켜고, 탭 뒤 화면이 안 바뀌면 "터치가 무시됨"으로 알림 |

## 맥 앱(DMG) 설계 — 다음 단계

> 상태: D1 ✅ 쓰는 곳 분리 (2026-11-16). 다음 D2 앱 셸.

### 왜

지금은 `git clone` → `install-skill` → 터미널에서 `qakit ui`를 켜고 브라우저 탭으로 본다. Codex·Claude 데스크톱 앱처럼 **DMG를 받아 끌어 넣고, 더블클릭하면 창이 뜨는** 앱이면 터미널을 모르는 QA 담당자도 쓸 수 있고, 작업공간(앱마다 QA 폴더)을 창에서 고르고 바꿀 수 있다.

### 방식 비교

| 방식 | 크기 | 장점 | 단점 |
|---|---|---|---|
| **Swift 앱 + WKWebView (추천)** | 수 MB | 지금 웹 UI를 그대로 띄움. 맥 기본 기능(메뉴 막대·알림·파일 열기)을 바로 씀. 어차피 Xcode가 필요한 도구라 Swift 빌드가 자연스럽다 | 웹뷰 차이(내려받기·확인 창)를 손봐야 함 |
| Tauri | 10MB 안팎 | 웹뷰 + Rust, 자동 업데이트 기본 제공 | Rust 도구가 하나 더 늘어남 |
| Electron | 150MB 이상 | Chrome 그대로라 웹 차이가 없음 | 무겁다, Node 런타임을 통째로 넣음 |

→ **Swift + WKWebView**. 서버(`qakit ui`)·실행기·AI 연결은 지금 Python 코드를 그대로 쓰고, 앱은 **창과 수명 관리만** 한다.

### 구성

```
QA Kit.app
└─ Contents/
   ├─ MacOS/QAKit                  Swift 앱 (창·메뉴 막대·서버 띄우기)
   └─ Resources/kit/               도구 폴더 통째 (bin·lib·Tools·Sources·ScenarioRunner·AndroidRunner·AutoID·ui/dist·skills·templates·VERSION)
```

- **창**: 작업공간 하나에 창 하나. 앱이 `kit/bin/qakit -w <작업공간> ui --no-open --port <고정>`을 띄우고, 출력의 주소(토큰 포함)를 WKWebView로 연다. 창을 닫거나 앱을 끄면 서버를 SIGINT로 멈춘다 (서버가 띄운 실행·AI·녹화도 같이 정리 — 지금 `qakit ui` 종료 처리 그대로).
- **포트는 작업공간마다 고정**: 웹 UI 설정(테마·커서·탭 등)이 localStorage라 주소(포트)가 바뀌면 사라진다 → 작업공간 경로로 정한 포트를 쓰고, 쓰고 있으면 다음 번호.
- **작업공간 고르기**: 처음 화면에 최근 작업공간 목록 + "폴더 열기"(`qakit.yml`이 있는 폴더). 없으면 `qakit init` 안내 (나중에 창에서 만들기).
- **메뉴 막대 아이콘**: 열린 작업공간, 실행 중(시나리오·AI) 표시, 창 열기, 끝내기.
- **처음 점검**: Xcode·xcodegen·python3·(안드로이드면 JDK·SDK)가 있는지 보고 없으면 설치 방법을 보여 준다 (`qakit doctor` 같은 점검 명령을 하나 두고 앱은 그 결과를 그림).
- **명령줄·스킬**: 메뉴 "명령줄 도구 설치" → `~/.local/bin/qakit`을 앱 안 `kit/bin/qakit`으로 링크, Claude Code·Codex 스킬·MCP 설정도 앱 안 경로로 (`install-skill` 그대로). git으로 설치한 것이 있으면 어느 쪽을 쓸지 묻는다.

### 꼭 바꿔야 하는 것 — 도구 폴더에 쓰지 않기

서명한 앱 번들 안은 고치면 안 된다 (서명이 깨지고, `/Applications`는 쓰기 권한도 없을 수 있음). 지금은 도구 폴더(`KIT_DIR`) 안에 빌드 결과를 쓴다:

- `.build/`(시나리오 실행기·AutoID·실기기 실행기·안드로이드 실행기 APK), `Tools/<도구>/.build/`(simscreen·simtouch), `ScenarioRunner/*.xcodeproj`(xcodegen 결과), `AndroidRunner/runner/build/`(Gradle)

→ **쓰는 곳을 `QAKIT_HOME`(기본 `~/Library/Application Support/qakit`)으로 분리**. 읽기 전용 원본(`KIT_DIR`)과 쓰는 곳(`QAKIT_HOME`)을 나누고, Xcode·Gradle 프로젝트는 쓰는 곳에 복사해 빌드한다. git 설치에서는 지금처럼 `KIT_DIR`을 써도 되게 기본값만 다르게.

### 업데이트

- 1차: 앱이 켜질 때 GitHub 최신 릴리스 버전을 보고 새 버전이 있으면 "업데이트" → DMG 내려받기 페이지. (`qakit update`는 git 설치 전용으로 남김)
- 2차: Sparkle(맥 앱 자동 업데이트 표준) — 릴리스에 appcast를 같이 올려 앱 안에서 받아 바꾼다.

### 서명·공증

- **Apple Developer ID(연 $99)가 있으면**: Developer ID로 서명 + hardened runtime + `notarytool` 공증 → 받은 사람이 바로 연다.
- **없으면**: ad-hoc 서명. 처음 열 때 "확인되지 않은 개발자" 경고 → 우클릭 → 열기 (사내 몇 명이면 이걸로 충분).
- 사용자 맥에서 만드는 도구(simscreen·simtouch·실행기)는 그 맥에서 빌드되므로 공증 대상이 아니다.

### 배포

`scripts/release.sh`에 이어서: 앱 빌드(`xcodebuild`, 도구 폴더를 Resources/kit로 복사) → DMG(`hdiutil create -format UDZO`, Applications 바로가기 포함) → (자격이 있으면) 서명·공증·staple → GitHub 릴리스에 `QA-Kit-<버전>.dmg` 첨부. CI(macOS 러너)에서 만들 수도 있다.

### 단계

| 단계 | 내용 |
|---|---|
| **D1. 쓰는 곳 분리** ✅ | `WORK_DIR` = `QAKIT_HOME` → 도구 폴더에 쓸 수 있으면(git 설치) 도구 폴더 그대로 → 아니면 `~/Library/Application Support/qakit`. 빌드 결과(`.build/`: 시나리오 실행기·실기기 실행기·AutoID·안드로이드 실행기·simscreen·simtouch·swiftui-ids)는 `WORK_DIR/.build`, 소스 폴더 안에 쓰는 빌드(xcodegen 프로젝트·SwiftPM·Gradle)는 그 부분만 `WORK_DIR/src`에 복사(`writable_src`, 바뀐 파일만·지운 파일은 지움)해 빌드. git 설치는 경로가 그대로라 다시 빌드하지 않음. **확인**: 도구 사본을 `chmod -R a-w`로 읽기 전용으로 두고 맥 기본 Python 3.9.6으로 — AutoID·시나리오 실행기 빌드 → `do launch`·`dump`·`run`(실패 사진·영상까지) ✅, simscreen 10초·simtouch 2초·안드로이드 실행기 47초·swiftui-ids 4분 44초 빌드 ✅, 도구 폴더에 쓴 파일 0 |
| **D2. 앱 셸** | Swift 앱: 작업공간 고르기·최근 목록, 서버 띄우기·끄기, WKWebView (내려받기 `WKDownload`, `confirm`·`alert` 처리, 바깥 링크는 브라우저로, MJPEG 실시간 화면 확인) |
| **D3. 맥 기능** | 메뉴 막대 아이콘·실행 중 표시, 처음 점검(`qakit doctor`), 명령줄·스킬 설치 메뉴 |
| **D4. 패키징** | release.sh에 앱·DMG·(서명·공증) 추가, 릴리스에 첨부 |
| **D5. 업데이트** | 최신 릴리스 확인 → 이후 Sparkle |

### 확인할 것 · 위험

| 항목 | 내용 |
|---|---|
| Python 버전 | 맥 기본 `/usr/bin/python3`는 3.9.6 (Xcode 명령줄 도구) → **D1에서 확인 ✅**: 단위 테스트 전부·빌드·실행이 3.9.6에서 동작. 최소 3.9로 두고, 3.10 이상 문법을 쓰지 않게 (CI에 3.9 추가 고려) |
| WKWebView 차이 | 실시간 화면(MJPEG `<img>`), 녹화·사진 내려받기, `window.confirm` — Safari 엔진에서 확인 필요 |
| git 설치와 둘 다 있을 때 | MCP·스킬이 가리키는 `qakit`이 어느 쪽인지 섞일 수 있음 → 앱이 지금 연결된 쪽을 보여 주고 바꾸게 |
| 여러 창 | 같은 작업공간을 두 창에서 열면 서버 둘 → 이미 열려 있으면 그 창으로 |

### 정할 것

- Apple Developer ID가 있는가 (없으면 ad-hoc 서명으로 시작)
- 앱 이름 (예: QA Kit)
- git 설치를 계속 함께 지원할지 (추천: 개발자는 git, 그 외는 앱)

## 단계와 결과

| 단계 | 내용 | 결과 |
|---|---|---|
| 0. 주입 검증 | 시뮬레이터 dylib 주입으로 자동 ID | ✅ |
| 1. 도구 핵심 | AutoID, QAKit, CLI | ✅ 시범 앱 로그인 화면 100%, 메인 92% |
| 2. 시범 적용 | 로그인 상태 판별 시나리오 | ✅ |
| 3. ID 상수 + 앱 변경 동기화 | gen-ids, sync, 자동 재빌드 | ✅ 생성 ID와 실행 중 ID 불일치 0 |
| 4. AI 스킬 | SKILL.md, install-skill | ✅ 새 AI 세션이 스킬만 보고 첫 실행에 통과 |
| 5. 범용성 | 두 번째 앱 | ✅ 도구 버그 수정 후 동작 |
| 6. 정기 실행 | — | 하지 않음 |
| 이후 | QA 워크트리, 시나리오 언어, AI 없는 저장·복구, 시뮬레이터 잠금, 앱 설정값 판정(pref/repeat/watch), QA README 자동 생성 | ✅ v0.2.0 ~ v0.4.0 |
| 7. SwiftUI | QA 빌드 직전 소스에 ID 삽입 ([설계](#swiftui-지원-설계-다음-단계)) | S1 ✅ S2 ✅ S3 ✅ (시범 앱 로그인 화면 100%, `build-app`이 삽입·복원 자동). 다음 S4 둘째 앱 |
| 8. 상주 실행기 | 실행기를 한 번 띄워 두고 명령만 주고받기 ([설계](#상주-실행기-설계-다음-단계)) | R1 ✅ R2 ✅ R3 ✅ (`qakit do` 1~2초, `qakit run` 약 8초 단축). R4 ✅ R5 ✅ (실기기 USB·Wi-Fi) |
| 9. UI | `qakit ui` ([설계](#ui-설계-다음-단계)) | U1~U5 ✅, 실시간 화면·커서·캡처 ✅ |
| 10. AI QA | AI가 MCP로 앱을 직접 QA ([설계](#ai-qa-설계-다음-단계)) | A1 ✅ (`qakit mcp`, 실제 Claude Code에서 확인) · A2 ✅ (라이브 세션 AI 활동) · A3 ✅ (UI에서 AI QA 시작, 실제 Claude Code로 끝까지) · A4 ✅ (지난 세션·통과 단계 → 시나리오) |
| 11. AI QA 직접 터치 | tapflow 방식 — 앱은 simctl, 실행기는 읽기만, 누르기는 터치 신호 ([설계](#ai-qa-직접-터치-설계--tapflow-방식-다음-단계)) | 시험 ✅ · AutoID ✅ · H1 ✅ · H3 ✅ · H4 ✅ |
| 12. 맥 앱(DMG) | 더블클릭으로 여는 앱, 웹 UI를 창으로 ([설계](#맥-앱dmg-설계--다음-단계)) | D1 ✅ (읽기 전용 도구 폴더 + Python 3.9). 다음 D2 |

## 주요 결정과 배운 것

- **AI는 만들 때만**: 실행·복구는 파일(시나리오, Swift, 노트)만으로. computer use처럼 매번 토큰을 쓰지 않는다.
- **QA는 앱 레포의 전용 워크트리에**: 개발 폴더와 섞이지 않게. git에 없는 작은 로컬 설정 파일(키가 든 xcconfig 등)은 원래 폴더에서 복사해야 새 워크트리가 빌드된다.
- **시나리오 언어 + 범용 실행기**: 대부분의 QA는 `.qa.yml`로. 실행 전 ID 정적 검사(`qakit check`)가 컴파일 에러 역할. 복잡한 판정만 Swift.
- **동시 실행 금지**: 같은 시뮬레이터에서 두 실행이 앱을 조작하면 입력이 섞인다 → 시뮬레이터 잠금.
- **화면에 없는 상태는 앱 설정값으로**: 지도 줌 같은 값은 UserDefaults로 판정. 앱은 설정을 디스크에 늦게 쓴다(5초 넘게) → timeout, `watch`.
- **핀치**: XCUITest 축소는 음수 속도가 필요. 확대는 대략 `log2(scale) × 0.9` 단계, 축소는 효과가 더 작다. 빠른 핀치는 관성이 있어 값이 멈춘 뒤 판정해야 넘치지 않는다.
- **정적 분석의 한계**: 지역 변수 뷰, 외부 SDK 뷰, 부모 타입으로 선언하고 하위 클래스를 넣은 프로퍼티는 소스만으로 이름을 알 수 없다 → 화면 글자·덤프.
- **SwiftUI는 소스 삽입으로**: 런타임 방식은 비공개 API라 OS마다 깨지고 결국 라벨 기반. 공개 API만 쓰는 소스 삽입을 QA 워크트리에서 빌드하는 동안만 적용한다. 삽입 코드와 ID 상수 생성이 같은 코드를 쓰게 해 규칙 불일치를 막는다. 기성 도구는 없었다 (2026-11 조사).
- **공개 정리 (v0.4.1)**: 저장소를 공개하면서 특정 앱 정보를 담은 예전 기록을 이력에서 제거하고 이 문서를 일반화했다.

## 안드로이드 지원 설계 (진행 중)

> 상태: A0(설치)·A1(화면 파악)·A3(상주 실행기) 완료(2026-11-16, Pixel 7 AVD, Android 15 설정 앱으로 확인). `qakit run`·`qakit do`·`qakit serve`가 안드로이드에서 동작.
> 안드로이드 시범 앱은 Compose만 쓰고 testTag(+testTagsAsResourceId)가 이미 있어 A2는 뒤로 미룬다. 다음은 A4(build-app) → A5(logcat).
> 대상 앱은 XML 뷰와 Compose가 섞인 앱을 전제로 한다. 레포는 이 저장소에 통합하고(`ios-qa-kit` → `qa-kit`), 시나리오·UI·coverage·MCP는 공유, 실행기만 플랫폼별로 둔다.

### iOS와 대응

| iOS | 안드로이드 | 비고 |
|---|---|---|
| Xcode 시뮬레이터 | cmdline-tools + emulator + AVD | Android Studio 불필요. `qakit android setup`이 JDK 17(brew openjdk@17)부터 AVD까지 만든다 |
| AutoID (Mirror로 프로퍼티 이름) | XML 뷰: `resource-id`가 이미 있음 (`com.app:id/loginButton` → `loginButton`) | 런타임 주입이 필요 없다 |
| SwiftUI 소스 삽입 (방식 ②) | Compose: QA 워크트리 빌드 직전 `Modifier.testTag("화면.요소")` + 루트에 `testTagsAsResourceId = true` 삽입, 빌드 뒤 복원 | A2. 삽입 전에는 글자·contentDescription으로 찾는다 |
| 상주 XCUITest 실행기 + QAServer | UiAutomator2 instrumentation APK + HTTP 서버 (같은 명령 프로토콜) | A3. 시나리오 해석은 Kotlin으로 옮긴다 |
| simscreen·simtouch | `screencap`/`screenrecord`(또는 scrcpy) + `input` | A6 |
| `xcodebuild` | `gradlew :<module>:assemble<Variant>` + `adb install -r` | A4 |

### 화면 덤프 (A1)

- `uiautomator dump --compressed` XML을 iOS `dump-ui`와 **같은 줄 형식**으로 바꾼다: `타입 #ID "라벨" value="…" (disabled) @x,y wxh`. 좌표는 dp 정수. 그래서 `ui_parse_dump`·`dump_elements`·실패 시 대상 추천이 그대로 동작한다.
- 이름 없는 레이아웃(FrameLayout·LinearLayout·Compose 중간 노드)은 접고 깊이를 늘리지 않는다.
- 타입: 클래스 이름 끝으로 정함(EditText → TextField, password → SecureTextField, RecyclerView → CollectionView …). Compose는 클래스가 대부분 `View`라서, 클릭 가능하고 글자가 2개 이상이면 `Cell`(목록 행), 아니면 `Button`. 라벨 없는 버튼은 안쪽 아이콘 설명을 라벨로 쓴다(`Button "Navigate up"`).
- ID: 앱·라이브러리 id는 이름만, 프레임워크 id는 `android.<이름>`, Compose testTag(testTagsAsResourceId)는 그대로.
- 머리말: package, Activity(전체 이름), Fragment(`dumpsys activity top`, Glide 등 내부 프래그먼트 제외), ID 비율, ID 없는 요소(목록 행은 첫 글자로 이름).
- 앱 위에 뜬 다른 앱 창(권한 대화상자 등)은 `# (다른 앱 창: <패키지>)`로 표시.
- 비용: dump 1회 ≈ 1~3초(`uiautomator dump`가 화면 정지를 기다림). A3 상주 실행기에서는 instrumentation 안에서 바로 읽어 줄인다.

### qakit.yml (platform: android)

```yaml
platform: android
app:
  project: ../            # Gradle 루트 (settings.gradle(.kts)가 있는 폴더)
  module: app             # 기본 app
  variant: debug          # 기본 debug
  packageName: com.example.app
emulator: qakit           # AVD 이름 (기본 qakit)
```

### 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| A0 환경 | `qakit android setup/doctor/boot` — JDK·SDK·이미지·AVD 설치, 부팅 대기 | 완료 |
| A1 화면 파악 | `qakit android screen/dump`(작업공간 없이), 작업공간 `dump-ui`·`doctor` 안드로이드 분기 | 완료 |
| A2 Compose ID | 소스 삽입 도구 (Kotlin 소스 파싱, `@Composable` 함수의 클릭·입력 요소에 testTag), 빌드 직전 삽입·복원 | 보류 (첫 앱은 이미 testTag 있음) |
| A3 실행기 | UiAutomator2 instrumentation APK + HTTP, `.qa.yml` 단계 해석 (Kotlin) | 완료 |
| A4 CLI 통합 | `build-app`(Gradle → APK 찾기 → 설치 → 권한, 앱 변경 시 자동 재빌드)·`run`·`do` 완료. `init`(Gradle 탐지)·QA 워크트리·MCP 남음 | 부분 |
| A5 로그·네트워크 | 실패 요약에 앱 패키지만 거른 logcat·크래시 스택. OkHttp 로그 우선, 필요하면 mitmproxy | 완료 (mitmproxy는 안 함) |
| A6 라이브 세션 | UI에서 화면 보기·직접 터치·녹화 | 완료 (AI QA는 아직) |

### 미결

- Compose ID 규칙: `화면Composable.요소` 형식으로 할지, 변수·파라미터 이름을 어디서 가져올지 (A2에서 시범 앱으로 정함)
- 실기기(USB): adb는 같지만 권한(`pm grant`)과 설치 서명 차이 확인 필요

### A3 상주 실행기 (2026-11-16)

| 부분 | 내용 |
|---|---|
| 위치 | `AndroidRunner/` (Gradle 9.8.2, AGP 9.5.0 — 시범 앱과 같은 판). 실행기 본체는 `runner/src/androidTest` |
| 구조 | 빈 앱 APK + instrumentation APK. `am instrument -w … ServeTest`가 기기 안 127.0.0.1:7912에 HTTP를 열고, qakit은 `adb forward tcp:0`으로 받은 포트로 붙는다. 상태 파일·`serve_request`·`run_via_serve`·`qakit do`는 iOS와 같다 |
| 화면 읽기 | 접근성 API로 모든 창(`FLAG_RETRIEVE_INTERACTIVE_WINDOWS`)을 직접 읽는다 — 팝업·드롭다운·권한 대화상자 포함, 키보드·상태 표시줄 제외. 조건 한 번 확인 ≈ 20~30ms |
| 덤프 | 실행기는 uiautomator 형식 XML만 보내고 qakit(`android_convert_response`)이 덤프 텍스트로 바꾼다 → 형식 코드 한 곳 |
| 시나리오 | `QAScenarioRunner.swift`를 Kotlin으로 옮김 (`Scenario.kt`). 단계·조건·실패 문구가 같아 실패 요약·추천을 그대로 쓴다 |
| 다른 점 | 글자 입력은 `ACTION_SET_TEXT`(한글 가능, 누른 뒤 입력 포커스 칸에). 앱 실행은 `am start -W --activity-clear-task`(다른 앱 화면이 작업 위에 남는 경우). `pref`는 SharedPreferences(run-as, debuggable 빌드). `hide-keyboard`는 뒤로 가기. 비밀값은 시작 뒤 `/config`로 |
| 아직 | 실패 영상, `--bench`, 라이브 세션 직접 터치, ID 정적 검사(소스 ID 목록 없음 — coverage는 저장된 덤프에서 본 ID 기준) |

함정: `adb root`·`adb unroot`로 adbd가 재시작되면 실행 중인 실행기의 UiAutomation 연결이 끊긴다 (셸 명령이 빈 결과). 실행기를 다시 띄우면 된다.

### 안드로이드 시범 앱 첫 시나리오 (2026-11-16, first-login)

앱 데이터를 지우고(`pm clear` + 권한 미리 허용) 로그인 → 동시 로그인 확인창 → 안내창 3종(interrupts) → 홈. 통과 2회 (36.7초·22.3초).
작업공간은 앱 레포 밖 별도 폴더 (앱 레포는 읽기만). 이 과정에서 고친 실행기 문제:

| 증상 | 원인 → 고침 |
|---|---|
| 스플래시가 끝났는데 옛 화면만 보임 | 접근성 노드 캐시가 안 갱신됨 (Compose 화면 전환) → 읽을 때마다 `clearCache()` |
| `{ type: button, label: 개인 }`을 못 찾음 | 덤프는 버튼 라벨을 안쪽 글자에서 빌려 오는데 실행기는 아니었음 → 같은 규칙으로 |
| `hide-keyboard` 뒤 앱이 닫힘 | 키보드 창이 숨은 뒤에도 남아 "떠 있음"으로 봄 + 이 앱은 키보드가 떠 있어도 뒤로 가기에 닫힘 → `mInputShown`으로 판단, `type`은 누르지 않고 SET_TEXT 먼저(키보드 안 띄움) |
| 비밀번호가 이메일 칸에 들어감 | 비밀번호 칸은 읽은 글자가 •라 확인 실패 → 포커스 칸으로 넣는 대체 경로가 이전 칸(이메일)에 넣음 → 비밀번호 칸은 성공 응답을 믿고, 대체 경로는 대상과 같은 자리의 칸만 |
| 팝업의 "로그인" 대신 아래 화면 "로그인"을 누를 수 있음 | 대상 찾기를 위 창부터 |
| 권한 대화상자 4종 | `permissions: [location, notifications, nearby, background]` |

앱 쪽 관찰(앱 버그 후보)은 앱별 기록(작업공간 NOTES.md)에 둔다. 도구 쪽 교훈: 키보드가 떠 있어도 뒤로 가기에 화면을 닫는 앱이 있다 → hide-keyboard에 기대지 않는다.

### A6 라이브 세션 (2026-11-16)

| 부분 | 안드로이드 |
|---|---|
| 화면 | 상주 실행기 안 `FrameServer` 스레드가 `UiAutomation.takeScreenshot()` → 600px JPEG를 기기 7913으로 계속 보낸다 (iOS simscreen과 같은 [4바이트 길이][JPEG] 형식). qakit은 adb forward로 받아 `qakit android frames`가 표준 출력으로 넘기고, UI 서버의 MJPEG 중계는 그대로. 명령과 다른 스레드라 시나리오가 도는 중에도 나온다 |
| 속도 | 12fps (상한). **AVD GPU 가속이 꺼져 있으면 기기 안 캡처가 한 장에 2.5초 → 1fps 안팎** (`screencap`도 마찬가지, PNG면 4~19초). `hw.gpu.enabled=yes, hw.gpu.mode=host`로 0.37초 → 12fps. `qakit android setup`이 새 AVD에 켜고, 기존 AVD는 doctor가 알려 주고 setup이 고친다 |
| 직접 터치 | `adb shell input tap / swipe` (길게 누르기 = 같은 자리 swipe). 좌표 0~1 → `dumpsys window displays`의 cur=(회전 반영) |
| 녹화 | `adb shell screenrecord`(최대 3분, 안드로이드 제한) → 끝낼 때 `pkill -INT` 후 pull |
| 스크린샷(/api/screen) | 라이브 화면 프레임을 쓴다 |
| 라이브 화면을 열 때 | 실행기가 없으면 앱을 다시 켜지 않고(launch=0) 띄운다 |
| 아직 | 시나리오 실행 중 누르는 자리 커서(iOS QA_TAPS_FILE), AI QA(MCP) |

### 가로 화면·태블릿 (2026-11-16)

- 태블릿 AVD `qakit-tablet` (pixel_tablet 2560x1600). 시범 앱 작업공간은 태블릿 + `orientation: landscape`로 바꿈, first-login 통과 (31.5초·29.7초).
- 방향: `qakit android boot --landscape`, `qakit android rotate`, qakit.yml `orientation:`. 자동 회전 끄고 `user_rotation` — 기본 방향(휴대폰 세로, 태블릿 가로)은 `wm size` Physical로 판단.
- 웹: 안드로이드 덤프에 iOS처럼 `Application` 줄(화면 크기 dp)을 둔다 → UI가 화면 크기·방향을 읽는다 (이전에는 없어서 라이브 화면의 요소 상자·클릭이 안드로이드에서 동작하지 않았음). 라이브 세션·AI QA 기기 틀이 가로 화면이면 넓게.
- 키보드: 태블릿에서 scroll-to 쓸기가 화면 키보드에 닿아 글라이드 입력("see see …")이 이메일 칸에 들어감. `show_ime_with_hard_keyboard=0` + `hw.keyboard=yes`는 이 이미지(Gboard)에서 듣지 않음, `ime disable`은 하나뿐인 키보드라 다시 켜짐 → 에뮬레이터에서 Gboard 앱을 `pm disable-user`(qakit.yml `keyboard: show`면 다시 켬). 실행기도 키보드 내용 영역을 피해 탭·쓸기, 가려진 요소는 hittable 아님.

### A4 build-app (2026-11-16)

- `:<module>:assemble<Variant>` → `output-metadata.json`(variantName 일치, flavor 폴더도)에서 APK·applicationId → packageName 확인 → `adb install -r -t` → permissions 허용 → 앱 상태(커밋·트리 해시, scheme=module, configuration=variant) 기록. `auto_sync`가 iOS처럼 앱 변경 시 다시 빌드 (ID 상수·Swift 컴파일 단계는 건너뜀).
- 함정: `qakit ui`를 열어 둔 채 `qakit run`을 하면, 라이브 화면이 "실행기가 죽었다"고 보고 다시 띄우면서 run의 실행기와 번갈아 죽였다 ("Process crashed"). → 라이브 화면은 기기 잠금(run·do·build-app이 잡음)을 기다리지 않고 확인해, 쓰는 중이면 실행기를 건드리지 않는다. 실행기를 멈출 때·새로 띄우기 전에는 기기 안 프로세스까지 force-stop.

### A5 로그·크래시·네트워크 (2026-11-16)

- 거르기: 앱 로그는 `logcat --uid=<앱 uid>` (`pm list packages -U`). pid로 거르면 재실행·크래시 뒤 새 프로세스를 놓친다. 크래시는 `-b crash`(자바 `FATAL EXCEPTION`·네이티브 `*** *** ***`에서 같은 pid 줄 묶음, `Process: <앱>,`로 이 앱 것만 — `com.app`이 `com.app.debug`에 걸리지 않게), ANR은 `-b system`의 `ActivityManager: ANR in <앱>`과 같은 스레드 설명 줄.
- 기간: run 직전 **기기 시각**(`date +%s.%3N`)을 `logcat -T`에 넣는다 (호스트 시계와 어긋나도 됨). `logcat -t N`은 uid로 거르기 전 줄 수라서 쓰지 않고 다 받아 자른다 (앱 로그 1.7MB ≈ 0.1초).
- 결과: run마다 `logcat.txt`(인증 헤더·토큰·secrets 가림), 크래시·ANR이 있으면 `crash.txt`. 실패 요약은 원인 바로 아래 크래시·ANR·실패한 요청, 화면 구조 뒤에 오류(E) 로그를 숫자만 다른 줄끼리 묶어 많은 순. 통과했는데 크래시가 있었으면 경고. 실행 기록에 `"crash": true`.
- 네트워크: 앱의 OkHttp `HttpLoggingInterceptor` 줄(`--> GET url`, `<-- 401 url (190ms)`, `<-- HTTP FAILED`)을 읽는다. 시범 앱은 debug 빌드만 켠다 → release에서는 "네트워크 로그 없음"으로 알린다. mitmproxy(인증서 설치·release 앱의 network security config)는 필요해질 때.
- 난독화: release는 R8 → `<module>/build/outputs/mapping/<variant>/mapping.txt`가 있으면 SDK `retrace`로 스택을 복원 (첫 줄 "Waiting for stack-trace input..."은 버림). mapping이 설치된 APK와 같은 빌드인지는 보지 않는다 (build-app 직후가 아니면 어긋날 수 있음).
- 확인: `am crash <앱>`으로 일부러 크래시 → `qakit android logs --crash`에 스택. 일부러 실패하는 시나리오로 결과 폴더에 `logcat.txt`.

