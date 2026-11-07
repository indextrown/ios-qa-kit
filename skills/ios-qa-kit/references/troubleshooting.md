# 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| 요소를 못 찾음 (있는데) | 팝업·시트가 위에 떠서 아래 요소가 접근성 구조에서 가려짐 | 실패 요약의 화면 구조 끝부분(최상단 요소)을 본다 → 팝업 처리 |
| 요소를 못 찾음 (ID 없음) | 지역 변수로 만든 뷰, 외부 SDK 뷰 | 라벨(`text("…")`)이나 덤프의 좌표 사용 |
| 실기기에서 `dump-ui --device`·시나리오 `dump:` 단계를 돌려도 `results/ui-dump.txt`·`results/dumps/`가 그대로 (qakit 0.14.0 이하) | 새 Xcode가 첨부 이름의 `:`·`/`를 지워 qakit이 덤프를 꺼내지 못함 | `qakit update` (0.14.1부터 고침) |
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

## 상주 실행기 (`qakit serve` · `qakit do`)

| 증상 | 원인 | 해결 |
|---|---|---|
| "상주 실행기가 시작되지 않았습니다" (실기기 케이블을 막 꽂은 직후 등) | 기기 쪽 테스트 실행이 일시적으로 실패 | 다시 실행한다 (대개 바로 뜸). 반복되면 `~/.qakit/serve/<udid>.failed.log`의 `[qakit-serve]`·error 줄을 본다 |
| `qakit run`이 실행기 안 시간보다 몇 초 이상 더 걸림 | Mac이 바쁠 때 git·simctl 같은 준비 명령이 느려짐 | `QAKIT_TIMING=1 qakit run …`으로 어느 단계인지 본다 |
| 첫 `qakit do`가 1분 안팎 걸림 (출력의 단계 시간은 짧음) | 상주 실행기를 띄우는 중 (실행기 코드가 바뀌었으면 빌드까지). 단계 시간에는 빠지고 "실행기 시작 포함 전체 N초"로 따로 나온다 | 정상. 다음 명령부터 1~2초 |
| 라벨로 `tap`했는데 10초 기다리다 실패 | NOTES·소스에 적힌 이름과 화면의 실제 라벨이 다름 (예: "즐겨찾기(찜)" ↔ "찜") | `results/do-fail-dump.txt` 또는 `qakit do dump`에서 실제 라벨을 보고 다시 |
| `expect: { selected: … }`가 늘 실패 | SwiftUI 커스텀 세그먼트·버튼은 선택 상태가 접근성에 안 나옴 | 선택 상태 대신 그 선택으로 보이는 요소로 판정 |
| `qakit do`가 갑자기 다시 20초 걸림 | `qakit test`·`dump-ui`·`run --no-serve`가 상주 실행기를 멈췄거나, 30분 동안 명령이 없어 스스로 끝남, 또는 `qakit update`로 실행기 코드가 바뀜 | 정상. 알아서 다시 띄운다 |
| "N초 안에 끝나지 않아 상주 실행기를 멈췄습니다" | 앱이 계속 움직이는 화면(애니메이션·로딩)이라 XCUITest가 조용해지길 기다리며 멈춤 | 다음 명령이 다시 띄운다. 정말 오래 걸리는 단계면 `--timeout`을 늘린다. 반복되면 그 화면을 사용자에게 보고 |
| "대상 앱이 화면 맨 앞에 없음" | 다른 앱이나 시스템 화면이 앞에 있음, 또는 앱이 꺼짐 (`build-app`으로 재설치 등) | `qakit do launch` |
| `qakit do`의 결과가 예상과 다름 (이미 로그인됨, 이전 화면에 있음) | 앱 상태·변수가 이전 `qakit do`에서 이어진다 | 처음부터 보려면 `qakit do launch`, 변수만 비우려면 `qakit do reset`. 로그아웃 상태가 필요하면 `qakit run <시나리오> --reset` 또는 `qakit test --reset` 뒤에 `qakit do` |
| `qakit do`에서 통과한 단계가 `qakit run`에서 실패 | 시나리오는 앱을 새로 실행해 처음부터 돈다. `qakit do`는 그 전 상태에 기대고 있었음 | 시나리오 시작(`reset`, `use: login` 등)과 화면 대기(`wait`)를 넣는다 |
| "단계는 '이름: 값' 형식이어야 합니다" | 한 번에 단계 여러 개, 또는 YAML 형식 오류 | `qakit do`는 단계 하나씩. 따옴표로 감싼다: `qakit do 'wait: { for: X, timeout: 10 }'` |
| "…에 연결할 길이 없습니다 (USB 아님, CoreDevice 터널 없음)" | 케이블도 없고 Wi-Fi 터널도 열리지 않음 (기기 잠김·다른 네트워크·잠자기) | 기기 잠금을 풀고 같은 Wi-Fi인지 확인, 또는 USB 연결. `xcrun devicectl list devices`에서 기기가 보여야 한다 |
| Wi-Fi 실기기에서 상주 실행기가 시작되지 않고 로그에 "…에 열지 못함" | 터널 주소가 기기 안에서 바뀜 (터널이 다시 연결됨) | 다시 실행하면 새 주소로 띄운다. 로그(`~/.qakit/serve/<udid>.log`)에 기기 주소 목록이 있다 |
| 실기기 `qakit do`가 "기기 포트 …에 연결 거부" | 기기 안 실행기가 끝났거나(잠금·앱 전환·케이블 뺌) 아직 준비 전 | 다시 실행하면 새로 띄운다. 반복되면 `qakit serve --stop --device …` 뒤 다시 |
| 실기기 첫 `qakit run`이 몇 분 걸림 | 앱 소스가 바뀌어 자동 동기화가 앱을 다시 빌드·설치 (`results/build-app.log`) | 정상. 상주 실행기와는 무관하고, 다음부터는 몇 초 |
| `qakit run`이 상주 실행기와 xcodebuild에서 결과가 다름 | 상주 실행기 쪽 문제일 수 있음 | `qakit run <시나리오> --no-serve`로 비교하고, 다르면 도구 버그로 보고 |
| 상주 실행기가 남아 있는지 모르겠음 | — | `qakit serve --status`, 멈추려면 `qakit serve --stop` |
