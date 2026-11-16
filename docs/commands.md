# 명령 요약

작업공간 폴더에서 실행합니다. 옵션까지 전부는 [cli.md](../skills/qa-kit/references/cli.md).

[← README](../README.md)

## 하고 싶은 것별

| 하고 싶은 것 | 명령 |
|---|---|
| 전체 테스트 실행 (토큰 0) | `qakit test` |
| 테스트 하나만 | `qakit test LoginTests` |
| 시나리오 파일 실행 | `qakit run <시나리오>` |
| 여러 시나리오를 한 번에 | `qakit run 'home-*' --reuse-app` (끝에 통과·실패 요약) |
| 시나리오를 빠르게 반복 실행 | `qakit run <시나리오> --serve` ([상주 실행기](scenarios.md#빠르게-돌리고-눌러-보기-qakit-serve--qakit-do)) |
| 화면을 한 단계씩 눌러 보기 | `qakit do 'tap: <ID>'` · `qakit do dump` |
| 눌러 본 단계를 시나리오로 | `qakit do save <이름>` (`qakit do launch`부터 통과한 단계로 초안) |
| CI에서 태그로 골라 보고서까지 | `qakit run --tag smoke --junit report.xml` (종료 코드 1 앱 실패 · 2 환경 문제) · GitHub Actions 예시: [CI에서 돌리기](scenarios.md#ci에서-돌리기-github-actions) |
| 값을 바꿔 실행 (매개변수) | `qakit run <시나리오> --var item=라떼` |
| 마지막 실패 다시 보기 | `qakit summarize` |
| 무엇이 아직 테스트되지 않았나 | `qakit coverage [--unused]` (앱 ID 중 시나리오가 쓰는 것, 화면별) · UI **커버리지**에서 빈 화면을 AI QA로 |
| 시뮬레이터 화면 띄우기 (로그인 등) | `qakit show` (Xcode 27은 Device Hub) |
| 브라우저로 결과 보기·골라 실행·화면 조작 | `qakit ui` (실행 기록·실패 상세·시나리오 선택 실행·시뮬레이터 화면을 눌러 조작, [사용법](web-ui.md)) |
| 성능 측정 (시나리오 후 30분) | `qakit run <시나리오> --bench 30m` |
| Release 빌드로 | `qakit run <시나리오> --build release` |
| 도구 최신화 | `qakit update` |

## 명령별

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

**안드로이드**: [android.md](android.md)

**실행·결과**

| 명령 | 하는 일 |
|---|---|
| `qakit test [클래스[/테스트]] [--reset]` | Swift 테스트 실행 (`--reset`: 앱 재설치+키체인 초기화 = 로그아웃 상태) |
| `qakit run <시나리오> [--reset] [--var 키=값]` | 시나리오 파일 실행 (`--var`: `vars` 기본값 대신 이번 실행에 쓸 값. 여러 번 가능) |
| `qakit run <시나리오> --bench <시간> [--no-profile]` | 시나리오가 끝난 화면 그대로 그 시간 동안 CPU·메모리(1초 단위) + 함수별 CPU(`sample`) 기록. Time Profiler는 실기기(`--device`)에서만. 시간은 단위 필수: `30s`·`5m`·`1h`·`1h30m` (`30초`·`5분`·`1시간`도 됨, 최소 5초). 1분 이하는 전체를, 더 길면 3분마다 20초씩 함수를 찍는다. 권한 불필요. `--no-profile`: CPU·메모리만 |
| `qakit run <시나리오> --device [select\|last\|이름]` | 실기기에서 실행. 값을 빼면 방향키 목록에서 고름. `--bench`와 같이 쓰면 Time Profiler로 측정 ([실기기에서 실행](device.md)) |
| `qakit run <시나리오> <시나리오> …` · `qakit run 'home-*'` | 여러 개를 차례로 (준비는 한 번, 끝에 요약, 하나라도 실패하면 종료 코드 1) |
| `qakit run <시나리오> --reuse-app` | 앱이 이미 시작 화면(`start:`)이면 다시 켜지 않음 |
| `qakit run <시나리오> --serve \| --no-serve` | 상주 실행기로 / xcodebuild로 실행 (기본: 상주 실행기가 떠 있으면 그쪽으로) |
| `qakit serve [--stop\|--status]` | 상주 실행기 띄우기·멈추기·상태 (실기기는 `--device`, USB·Wi-Fi) ([설명](scenarios.md#빠르게-돌리고-눌러-보기-qakit-serve--qakit-do)) |
| `qakit do '<단계>'` · `qakit do dump\|launch\|reset` | 시나리오 단계 하나를 바로 실행 (1~2초) · 화면 구조 · 앱 다시 실행 · 변수 비우기 |
| `qakit ui [--port N] [--no-open] [--device …]` | 브라우저 UI: 실행 기록, 시나리오 골라 실행, 라이브 세션(화면 보며 조작·시나리오 만들기), 편집 ([사용법](web-ui.md)) |
| `qakit check` | 시나리오 형식·ID 정적 검사 |
| `qakit summarize` | 마지막 실패 요약 다시 보기 |
| `qakit history [-n 20]` | 실행 기록 |

**저장·문서**

| 명령 | 하는 일 |
|---|---|
| `qakit save -m "…"` | 결과물 저장 (보관소 복사, git 커밋은 안 함) |
| `qakit restore [--from 이름 --to QA]` | AI 없이 복구 |
| `qakit readme` | QA 폴더 README.md의 QA 목록 갱신 (run·test·check·save 때 자동) |

**전역 옵션**

| 옵션 | 용도 |
|---|---|
| `--app <다른 앱 폴더>` | 다른 브랜치 워크트리 검증 |
| `--secrets <파일>` | 다른 계정 |
| `-w <작업공간>` | 작업공간 지정 |
| `--build debug\|release` | 빌드 종류 (기본 debug = `qakit.yml`의 `app.configuration`, release = `app.release.configuration` 기본 `Release`) |

상세: [cli.md](../skills/qa-kit/references/cli.md) · QAKit API: [qakit-api.md](../skills/qa-kit/references/qakit-api.md)
