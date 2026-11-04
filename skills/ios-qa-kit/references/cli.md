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
| `qakit test [필터...] [--reset]` | 테스트 실행. 필터 예: `LoginFlowTests`, `LoginFlowTests/test_x`. `--reset`: 앱 재설치+키체인 초기화 |
| `qakit check [시나리오...]` | 시나리오 형식·ID 정적 검사 (실행 없이) |
| `qakit run <시나리오> [--reset] [--var 키=값 ...] [--bench 시간 [--no-profile]] [--no-check]` | 시나리오 파일 실행. `--var`: `vars` 기본값을 이번 실행 값으로 덮어씀 (예: `--var ship="ULTRA FOREST"`). `--bench <시간>`: 시나리오가 끝난 화면 그대로 그 시간 동안 (단위 필수: `30s`·`5m`·`1h`·`1h30m`, `30초`·`5분`·`1시간`도 됨. 단위가 없으면 오류, 최소 5초) CPU·메모리(1초 단위, `ps`) + 함수별 CPU(macOS `sample`, 10ms 간격. 1분 이하는 전체, 더 길면 3분마다 20초씩. 권한 불필요) → 실행 폴더의 `bench-*`. 요약에 직접 CPU를 쓴 함수·앱 코드 기준 상위 10개. `--no-profile`: CPU·메모리만 |
| `qakit summarize [xcresult]` | 실패 요약 (기본: 마지막 결과) |

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
  base: develop                  # 따라갈 브랜치
  update: auto                   # auto(test/run 전 자동으로 가져옴) | warn | off
# ids:
#   sources: [~/path/App/Sources]
```

## 결과 파일 (results/, git 제외)

실행 한 번이 폴더 하나다: `results/<날짜>/<시각>-<종류>[-<이름>]/` (예: `results/2026-11-04/104609-run-interpolation-setup/`)

| 파일 (실행 폴더 안) | 내용 |
|---|---|
| `output.log` | 테스트 출력 (비밀값 가림) |
| `result.xcresult` | Xcode 결과 |
| `result-attachments/` | 실패 시점 화면 구조·스크린샷 (`qakit summarize` 때) |
| `build.log` | Swift 테스트 Runner 빌드 로그 (`qakit test`) |
| `bench-summary.txt`, `bench-cpu.csv`, `bench-sample.txt` (긴 측정은 `bench-sample-01.txt`…) | `--bench` 성능 측정 요약·1초 단위 CPU/메모리·함수 호출 트리 원본 |

| 파일 (results/ 바로 아래) | 내용 |
|---|---|
| `latest` → 마지막 실행 폴더, `latest.xcresult` → 그 결과 | 바로가기 (`qakit summarize`가 씀) |
| `ui-dump.txt`, `dumps/` | 화면 덤프 (마지막 덤프 / 모아 둔 덤프·시나리오 `dump:`) |
| `build-app.log` | 앱 빌드 로그 |
