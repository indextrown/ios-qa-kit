# ios-qa-kit 설계와 진행 기록

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

> 상태: R1(PoC)·R2(CLI)·R3(run 통합) 완료 (2026-11-06). R4 문서 작성 (2026-11-07), 새 AI 세션 확인 남음. 시뮬레이터 먼저, 실기기는 나중.

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
- 명령 전체와 실행기 안 시간 사이에 약 6~7초가 남는다 (앱 변경 확인·ID 검사·기록·README 갱신 등 qakit 쪽 일). 두 경로가 함께 쓰는 비용이라 따로 줄일 수 있다 (미결).
- 다른 날·다른 도구로 잰 시간과 비교하면 틀린다. 같은 조건에서 번갈아 여러 번 잰다.

### 단계

| 단계 | 내용 | 완료 조건 |
|---|---|---|
| R1. PoC | `test_serve` + `/ping`·`/step`·`/dump`·`/launch`·`/stop`. 임시 스크립트로 띄우고 `curl`로 명령 | ✅ `127.0.0.1` 연결, 탭 0.2~1초, 실패 뒤 서버 유지 |
| R2. CLI | `qakit serve`/`--stop`/상태, `qakit do`, 상태 파일, 토큰, ping 재시작, 요청 제한 시간 | ✅ 서버를 죽여도 다음 `qakit do`가 다시 띄움, 제한 시간 초과 6초 안 정리 |
| R3. run 통합 | `qakit run`이 서버로 감, 결과 폴더·요약·실패 화면 구조, `--no-serve` | ✅ 홈 11개 같은 결과, 시나리오당 약 8초(23%) 단축 |
| R4. 문서 | README, cli.md, SKILL.md(탐색은 `qakit do`), troubleshooting | 문서 ✅. 남은 확인: 새 AI 세션이 `qakit do`로 탐색해 시나리오를 만든다 |
| R5. 실기기 | 포트 전달 방식 조사·적용 | 실기기에서 `qakit do` 동작 |

### 미결

- ~~시뮬레이터 안 리스너에 Mac `127.0.0.1`로 붙을 수 있는지~~ → R1에서 확인 (붙는다).
- XCTest가 오래 도는 테스트를 끊는 제한이 있는지 (`executionTimeAllowance`, xctestrun 설정).
- 가끔 멈추던 `xcodebuild`가 실행 시작 단계 문제인지, 앱이 조용해지지 않는 문제인지. 상주 실행기는 전자를 피하고, 후자는 요청 제한 시간으로만 막는다.
- `qakit test`(Swift Page 테스트)는 컴파일이 필요해 이 길을 타지 않는다. 그대로 둔다.
- 상주 실행기로 돈 `run`은 `results/latest.xcresult`를 바꾸지 않아 `qakit summarize`가 예전 결과를 보여 준다. 지금은 문서로 안내. `latest.xcresult`를 지우거나 `summarize`가 결과 폴더의 `failure-dump.txt`를 읽게 할지.
- qakit 쪽 사전 작업(약 6~7초)을 줄일지: 앱 변경 확인(git status·diff)과 ID 정적 검사 결과를 캐시하는 방안.

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
| 8. 상주 실행기 | 실행기를 한 번 띄워 두고 명령만 주고받기 ([설계](#상주-실행기-설계-다음-단계)) | R1 ✅ R2 ✅ R3 ✅ (`qakit do` 1~2초, `qakit run` 약 8초 단축). R4 문서 ✅, 새 AI 세션 확인 남음 |

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
