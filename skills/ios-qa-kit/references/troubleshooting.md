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
