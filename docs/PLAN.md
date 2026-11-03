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

> 상태: 설계 확정, 구현 전. 2026-11-03 조사 결과를 바탕으로 방식 ②(QA 빌드 직전 소스 삽입)로 결정.

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
| `Tools/swiftui-ids` | SwiftSyntax 기반 Swift 패키지. `list`(ID만 계산, JSON), `insert`(소스 수정 + manifest), `restore`. 첫 빌드는 SwiftSyntax 컴파일로 수 분, `KIT_DIR/.build/swiftui-ids/`에 캐시 |
| gen-ids | SwiftUI ID는 Python으로 다시 구현하지 않고 `swiftui-ids list`를 호출해 합친다. **삽입과 상수 생성이 같은 코드**라 규칙 불일치 버그가 원천 차단된다 |
| qakit CLI | `build-app` 훅, `doctor` 검사, `swiftui-ids --restore`. `check`·`gen-ids --verify`·`dump-ui` 커버리지는 ID 목록만 커지므로 그대로 |
| `qakit.yml` | `swiftui: auto \| off` (기본 auto: `import SwiftUI`가 있는 파일이 있으면 삽입) |
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
| ForEach/List 행 | 행 콘텐츠에 `.accessibilityElement(children: .contain)` + `뷰타입.row` | 행은 여러 개가 같은 ID. 테스트는 index·라벨로 고름 (UIKit 셀과 동일) |
| Text, Image, 컨테이너(VStack 등), 커스텀 뷰 호출부 | 붙이지 않음 | 글자로 찾기. 커스텀 뷰는 자기 body 안에서 자기 타입 접두사를 받음 |

라벨 문자열은 공백·구두점을 `_`로 바꾸고 20자에서 자른다. 그래야 ID 문자열과 `QAID` Swift 상수 이름이 같아진다(Swift 식별자는 한글 허용).

앱이 이미 `.accessibilityIdentifier`를 붙인 식, `.accessibilityHidden(true)`인 식은 건드리지 않는다 (UIKit과 같은 원칙).

### 조사로 확인한 함정 (규칙에 반영)

- **컨테이너 ID는 자식 ID를 덮어쓴다.** VStack에 붙이면 안의 요소가 전부 그 ID가 된다. Apple 엔지니어의 해법은 `.accessibilityElement(children: .contain)`을 먼저 붙이는 것. → 말단 컨트롤에만 붙이고, 행만 `.contain`으로 감싼다.
- **List 행 안 HStack에 붙이면 셀이 아니라 안의 Text에 붙는다.** → 행 규칙.
- **Button은 자식을 합치고 XCUITest는 Button의 accessibilityElement 설정을 무시한다.** → Button 안 Text가 아니라 Button 자체에 붙인다.
- **수식어 순서가 결과를 바꾼다** (introspect 같은 수식어 뒤에 두면 사라진 사례). → 호출식 바로 뒤, 다른 수식어 앞에 삽입.
- **ID는 앱 전체에서 유일하고 정적이어야 한다** (Apple 권고). → 콘텐츠로 ID를 만들지 않는다. 동적 라벨은 순서 번호.
- **SwiftUI TextField의 ID는 안의 UITextField에 전달되지 않는다.** XCUITest 접근성 트리에는 보이므로 테스트에는 문제없음. AutoID의 UIKit 규칙과 섞이지 않게만 주의.

### 단계

| 단계 | 내용 | 완료 조건 |
|---|---|---|
| S1. PoC | 정규식으로 Button·TextField만 잡아 한 화면에 손으로 삽입 → `dump-ui` | 커버리지가 오르고, `.contain` 행·컨테이너 덮어쓰기·Button 합치기 동작이 위 가정과 맞음 |
| S2. 도구 | `Tools/swiftui-ids` (list/insert/restore), 위 규칙 전부 | 시범 앱에서 `list` 결과 = 삽입 후 `dump-ui` 결과 (불일치 0) |
| S3. CLI | build-app 훅, 복원 보장, doctor, gen-ids 통합, `qakit.yml` 항목 | 강제 종료 후에도 워크트리가 깨끗해짐. `gen-ids --verify` 통과 |
| S4. 문서·검증 | 스킬 규칙, README 한계 갱신, 혼합(UIKit+SwiftUI) 앱 한 개 더 | 새 AI 세션이 스킬만 보고 SwiftUI 화면 테스트를 첫 실행에 통과 |

실제 SwiftUI 앱이 들어왔을 때 S1부터 시작한다. S1이 가정과 다르면 규칙을 고친 뒤 S2로 간다.

### 미결

- 커스텀 뷰 호출부 이름 (`PrimaryButton("로그인")` → `LoginView.PrimaryButton.로그인`): 안이 컨트롤 하나면 바깥 ID가 안을 덮어 원하는 결과가 나오지만, 둘 이상이면 안의 ID가 사라진다. 도구가 body를 분석해 컨트롤 하나일 때만 붙이는 방안은 S2 이후 판단.
- `if`/`switch` 양쪽에 같은 라벨 Button이 있으면 `_2`가 붙는다. 한 번에 하나만 보이므로 논리적으로는 같은 버튼. 자주 걸리면 분기별 번호를 없애는 규칙 검토.
- 행 ID의 `.contain`이 List 셀 구조(XCUITest `cells`)와 어떻게 맞물리는지는 S1에서 확인.

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
| 7. SwiftUI | QA 빌드 직전 소스에 ID 삽입 ([설계](#swiftui-지원-설계-다음-단계)) | 설계 완료, 실제 SwiftUI 앱이 들어오면 S1(PoC)부터 |

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
