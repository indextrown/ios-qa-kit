# qakit CLI

작업공간(`qakit.yml`) 폴더에서 실행. 전역 옵션은 명령 앞에 쓴다: `qakit --app <경로> test`.

| 명령 | 하는 일 |
|---|---|
| `qakit init <앱 프로젝트> [--name] [--dir] [--scheme] [--force]` | 작업공간 생성. scheme·configuration·bundleId 자동 탐지 |
| `qakit update [--check]` | 도구를 최신 버전으로 받기 (설치 폴더를 git fast-forward). `--check`: 새 버전이 있는지만 |
| `qakit doctor` | 환경·설정·secrets 키 점검 |
| `qakit build-app` | 앱 빌드 → 시뮬레이터 설치 → 권한 허용 |
| `qakit worktree-update [--check] [--from 브랜치]` | QA 워크트리를 따라갈 브랜치(`worktree.base`, 기본 develop. 원격이 앞서면 origin/…)의 새 커밋으로 merge. push·다른 브랜치로 병합은 하지 않음. 미커밋 변경·충돌이면 가져오지 않고 알림. `test`·`run` 전에 자동(`worktree.update: auto`) |
| `qakit sync [--rebuild] [--skip-build]` | 앱 변경 반영: 재빌드·설치 + ID 재생성(추가/삭제 보고) + 테스트 코드 컴파일 확인 |
| `qakit gen-ids [--verify]` | ID 상수 생성 (SwiftUI ID 포함). `--verify`: 저장된 덤프와 비교 |
| `qakit swiftui-ids --list \| --insert \| --restore` | SwiftUI ID 삽입 도구. `--list`: 삽입될 ID 목록. `--insert`: 워크트리 소스에 삽입한 채 둠(diff 확인용). `--restore`: 되돌림. `build-app`은 자동으로 삽입→빌드→복원 |
| `qakit dump-ui [--attach] [--wait-id ID] [--settle 초] [--print]` | 화면 구조 → `results/ui-dump.txt` |
| `qakit serve [--stop\|--status] [--idle 초] [--no-launch] [--device 이름]` | 상주 실행기. 실기기는 `--device`. 포트는 qakit이 정해 넘긴다. USB면 Mac이 usbmuxd로 기기 안 `127.0.0.1:<포트>`에 붙고, Wi-Fi면 실행기를 CoreDevice 터널의 기기 쪽 주소(`devicectl`의 `tunnelIPAddress`, 예: `fdxx::1`)에만 열어 그 주소로 붙는다 (같은 Wi-Fi의 다른 기기에서는 안 보임). 실행기(XCUITest)를 백그라운드로 띄워 두고 명령만 주고받는다. 상태 파일 `~/.qakit/serve/<udid>.json`. `--status`: 떠 있는지, `--stop`: 멈춤, `--idle`: 명령이 없으면 스스로 끝내는 시간(기본 1800초), `--no-launch`: 시작할 때 앱을 띄우지 않음. 떠 있으면 `qakit run`이 자동으로 이쪽으로 돈다. `test`·`dump-ui`는 시작 전에 상주 실행기를 멈춘다 |
| `qakit do '<단계>' [--timeout 초]` | 시나리오 단계 하나를 바로 실행 (1~2초, 없으면 상주 실행기를 띄움 1분 안팎. 그때는 "실행기 시작 포함 전체 N초"도 출력). 단계 문법은 `.qa.yml`과 같다 (`use:`는 펼쳐 실행). 한 번에 단계 하나. 앱 상태·변수는 다음 `qakit do`로 이어진다. 실패하면 ❌ 원인 + `results/do-fail-dump.txt`, 종료 코드 1, 실행기는 유지. `--timeout`(기본 120초)을 넘기면 실행기를 멈춘다(다음 명령 때 다시 띄움) |
| `qakit do dump [--settle 초]` / `launch` / `reset` / `ping` | `dump`: 지금 화면 구조 출력 + `results/ui-dump.txt`. `launch`: 앱 다시 실행 + 변수 비움. `reset`: 변수만 비움(앱 그대로). `ping`: 응답 시간·앱 상태 |
| `qakit test [필터...] [--reset]` | 테스트 실행. 필터 예: `LoginFlowTests`, `LoginFlowTests/test_x`. `--reset`: 앱 재설치+키체인 초기화 |
| `qakit check [시나리오...]` | 시나리오 형식·ID 정적 검사 (실행 없이) |
| `qakit run <시나리오> [--serve\|--no-serve] [--timeout 초]` | 이 작업공간용 상주 실행기가 떠 있으면 자동으로 그쪽으로 돈다 (xcodebuild 준비 생략, 시나리오당 약 8초 빠름). `--serve`: 없으면 띄워서. `--no-serve`: 떠 있어도 xcodebuild로 (상주 실행기는 멈춤). `--timeout`: 상주 실행기로 돌 때 제한 시간(기본 600초). `--reset`이면 실행기를 새로 띄운다. `--bench`는 늘 xcodebuild. 실기기도 상주 실행기로 (시나리오의 `dump:` 단계 파일은 응답으로 받아 같은 곳에 쓴다). 결과 폴더·`latest`·실행 기록(`"via": "serve"`)·실패 요약은 같고, xcresult 대신 `failure.png`·`failure-dump.txt`를 남긴다 |
| `qakit run <시나리오> [--reset] [--var 키=값 ...] [--bench 시간 [--no-profile]] [--no-check]` | 시나리오 파일 실행. `--var`: `vars` 기본값을 이번 실행 값으로 덮어씀 (예: `--var ship="ULTRA FOREST"`). `--bench <시간>`: 시나리오가 끝난 화면 그대로 그 시간 동안 (단위 필수: `30s`·`5m`·`1h`·`1h30m`, `30초`·`5분`·`1시간`도 됨. 단위가 없으면 오류, 최소 5초) CPU·메모리(1초 단위, `ps`) + 함수별 CPU(macOS `sample`, 10ms 간격. 1분 이하는 전체, 더 길면 3분마다 20초씩. 권한 불필요) → 실행 폴더의 `bench-*`. 요약에 직접 CPU를 쓴 함수·앱 코드 기준 상위 10개. `--no-profile`: CPU·메모리만 |
| `qakit run <시나리오> --device [select\|last\|<이름>]` | 실기기에서 실행 (`build-app`·`dump-ui`도 됨). 값을 빼면 방향키 목록(터미널에서만, AI는 이름으로 지정). 앱·실행기를 앱의 개발자 팀으로 서명, AutoID를 앱 `Frameworks/`에 넣고 다시 서명해 `devicectl`로 설치. 시나리오는 base64로 전달, `pref`는 AutoID의 숨은 요소 `QAKit.prefs`로 읽고, 덤프는 첨부(이름에 경로를 16진수로)로 받아 결과 폴더로 꺼낸다. `--bench`는 Time Profiler + Activity Monitor로 CPU %·메모리·함수 목록(`bench.trace`, `bench-cpu.csv`). Time Profiler는 실기기에서만 — 시뮬레이터는 `sample`. 권한 미리 허용 불가, `--reset`은 재설치만(키체인 유지), `qakit test`는 시뮬레이터만 |
| `qakit save -m "…"` | 결과물 목록·해시(`qa.lock.json`) + 보관소 `~/.qakit/archive/<이름>/` 복사. git 커밋은 하지 않음 |
| `qakit restore [--from 이름 --to QA]` | 보관소에서 AI 없이 복구 |
| `qakit summarize [xcresult \| 실행 폴더]` | 실패 요약 (기본: 마지막 실행). 상주 실행기로 돈 `run`은 그 실행 폴더의 `summary.txt` |

환경 변수 `QAKIT_TIMING=1`: 명령이 끝날 때 단계별 걸린 시간을 출력한다 (느릴 때 어디인지 보기).

| 전역 옵션 | 설명 |
|---|---|
| `-w <작업공간>` | 다른 폴더에서 실행할 때 |
| `--app <앱 폴더>` | 다른 브랜치 워크트리 등 앱 경로 일시 변경 |
| `--secrets <파일>` | 다른 계정 파일 |
| `--build debug\|release` | 빌드 종류 (기본 debug = `app.configuration`, release = `app.release.configuration` 기본 `Release`, bundle ID는 자동). 명령 뒤에 써도 됨. 앱의 Release가 실서비스 서버를 쓰면 시나리오도 실서비스에 접속한다 |

## qakit.yml

```yaml
name: my-app
app:
  project: ~/path/App.xcodeproj
  scheme: App-Dev
  configuration: Debug
  bundleId: com.example.app.dev
simulator: iPhone 17
language: ko
locale: ko_KR
permissions: [location-always]   # simctl privacy 이름
secrets: ./secrets.txt
autoid: inject                   # inject(시뮬레이터 주입) | embedded
sync: auto                       # auto | warn | off
  # release:                      # --build release 때 (생략 시 configuration: Release, bundleId 자동)
  #   configuration: Release
worktree:                        # QA 워크트리(init --worktree)일 때
  base: develop                  # 따라갈 브랜치. release/* 처럼 쓰면 버전이 가장 높은 브랜치(예: release/0.6.0)
  update: auto                   # auto(test/run 전 자동으로 가져옴) | warn | off
# ids:
#   sources: [~/path/App/Sources]
```

## 결과 파일 (results/, git 제외)

실행 한 번이 폴더 하나다: `results/<날짜>/<시-분-초>_<종류>[_<이름>][_<실기기>]/`. 종류는 `run`·`test`·`dump`, 성능 측정이면 `bench-<시간>` (예: `results/2026-11-04/14-15-16_run_interpolation-setup/`, `14-20-03_bench-1m_interpolation-setup_iphone-15/`)

| 파일 (실행 폴더 안) | 내용 |
|---|---|
| `output.log` | 테스트 출력 (비밀값 가림) |
| `result.xcresult` | Xcode 결과 (상주 실행기로 돈 `run`은 없음) |
| `summary.txt` | 상주 실행기로 돈 `run`의 요약 (`qakit summarize`가 보여 줌) |
| `failure.png`, `failure-dump.txt` | 상주 실행기로 돈 `run`이 실패했을 때: 실패 시점 스크린샷·화면 구조 (`output.log`에는 메모·지나간 단계) |
| `result-attachments/` | 실패 시점 화면 구조·스크린샷 (`qakit summarize` 때) |
| `build.log` | Swift 테스트 Runner 빌드 로그 (`qakit test`) |
| `bench-summary.txt`, `bench-cpu.csv`, `bench-sample.txt` (긴 측정은 `bench-sample-01.txt`…) | `--bench` 성능 측정 요약·1초 단위 CPU/메모리·함수 호출 트리 원본 (시뮬레이터) |
| `bench.trace`, `bench-calltree.txt` | 실기기 `--bench`: Time Profiler 기록(Instruments로 열기)·그 샘플로 만든 호출 트리 텍스트 |

| 파일 (results/ 바로 아래) | 내용 |
|---|---|
| `latest` → 마지막 실행 폴더, `latest.xcresult` → 그 결과 | 바로가기 (`qakit summarize`가 씀). 마지막 실행이 상주 실행기로 돈 `run`이면 `latest.xcresult`는 없다 |
| `ui-dump.txt`, `dumps/` | 화면 덤프 (마지막 덤프 / 모아 둔 덤프·시나리오 `dump:`). `qakit do dump`도 `ui-dump.txt`에 쓴다 |
| `do-fail-dump.txt` | 마지막으로 실패한 `qakit do` 단계의 실패 시점 화면 구조 |
| `build-app.log` | 앱 빌드 로그 |


### qakit.yml `device` (선택)

```yaml
device:
  team: ABCDE12345   # 실기기 서명 팀. 없으면 앱 빌드 설정의 DEVELOPMENT_TEAM
```
