# 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| 요소를 못 찾음 (있는데) | 팝업·시트가 위에 떠서 아래 요소가 접근성 구조에서 가려짐 | 실패 요약의 화면 구조 끝부분(최상단 요소)을 본다 → 팝업 처리 |
| 요소를 못 찾음 (ID 없음) | 지역 변수로 만든 뷰, 외부 SDK 뷰 | 라벨(`text("…")`)이나 덤프의 좌표 사용 |
| 덤프에 ID가 하나도 없음 | 앱이 qakit 밖에서 실행됨 (`--attach`) | `qakit dump-ui` (새로 실행) 또는 테스트를 먼저 돌린 뒤 `--attach` |
| 같은 ID가 여러 개 | 셀·반복 컴포넌트 | `page.cell(QAID.X.id, labelID: QAID.X.titleLabel, label: "…")` 또는 `.element(boundBy: i)` |
| 닫았는데 계속 `exists == true` | 시트·드로어가 화면 밖에 남음 | `page.waitUntilGone()` / `isVisibleOnScreen` |
| 상수는 있는데 요소가 없음 | 공통 컴포넌트의 일부 버튼만 실제로 붙음 | 앱 소스의 `isHidden`/`addSubview` 확인 또는 `qakit dump-ui --attach` |
| `zsh: no matches found: --include=*.swift` | zsh 글롭 | `--include='*.swift'` |
| `typeText` 실패 / 키보드 없음 | 탭이 입력칸 컨테이너에 감 | 덤프에서 실제 `TextField`/`SecureTextField` ID 사용 |
| 버튼이 키보드에 가림 | `isHittable == false` | 키보드 내리기 후 탭 |
| 앱이 예전 버전 같음 | 동기화 꺼짐 또는 다른 경로 빌드 | `qakit sync` (필요 시 `--rebuild`) |
| 화면에는 ID가 있는데 `QAIDs.swift`에 없음 | 프로퍼티를 부모 타입으로 선언(`var x: UIView?`)하고 실제로는 앱의 하위 클래스를 넣음 → 소스만 읽는 생성기는 안쪽을 모름 | 덤프에 나온 ID를 문자열로 쓴다 (`gen-ids --verify`는 "선언 타입 차이"로 분류) |
| `QAID…has no member` 컴파일 에러 | 앱 프로퍼티 이름 변경 | `qakit sync` 출력의 삭제/추가 목록대로 Page 수정 |
| 시뮬레이터 권한 팝업 반복 | 권한 미허용 | `qakit.yml permissions`에 추가 → `qakit build-app` |
| 로그인 상태가 테스트마다 다름 | 테스트끼리 상태 공유 | 시작을 공통 단계(예: `ensureLoggedIn`)로 통일, 로그아웃 상태가 필요하면 `--reset` |
| 테스트가 매우 느림 | 앱 애니메이션·긴 timeout | timeout을 필요한 만큼만, `QAWait.forAny`로 분기 |
| 빌드 중 앱 레포 파일이 바뀌었다는 경고 | 패키지 해석이 앱 레포를 수정 | 사용자에게 알리고 `git -C <앱> checkout -- <파일>` 여부를 묻는다 |
| SwiftUI 화면인데 덤프에 ID가 없음 | 앱 폴더가 QA 워크트리가 아니거나 `swiftui: off`, 또는 `qakit swiftui-ids --list`에 그 뷰가 없음 (`ids.sources` 밖, 레포 밖 패키지, 동적 라벨은 `Button.N`) | `qakit doctor` → 워크트리 확인. `qakit swiftui-ids --list`로 뷰 이름 확인 |
| "이전 SwiftUI ID 삽입이 복원되지 않았습니다" | 빌드 중 강제 종료 | `qakit swiftui-ids --restore` (manifest의 원본으로 되돌림) |
| "워크트리의 Swift 소스에 커밋되지 않은 변경" | 워크트리에서 소스를 직접 고침 | 워크트리는 개발 브랜치와 같아야 한다. `git -C <워크트리> checkout -- .` 또는 커밋 |
| 같은 SwiftUI ID가 여러 요소에 | 동적 라벨 버튼(`X.Button.0`)이 반복 컴포넌트 안에, 또는 행(`X.row`) | 라벨·index로 고른다 (`{ id, label }`, `.element(boundBy:)`) |
| 빌드 에러가 `.accessibilityIdentifier(` 줄을 가리킴 | 삽입 도구가 수식어를 붙일 수 없는 자리에 붙임 | `qakit swiftui-ids --insert` 뒤 `git diff`로 위치 확인 → 도구 버그로 보고. 임시로 `swiftui: off` |
