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
| `qakit summarize [xcresult]` | 실패 요약 (기본: 마지막 결과) |

| 전역 옵션 | 설명 |
|---|---|
| `-w <작업공간>` | 다른 폴더에서 실행할 때 |
| `--app <앱 폴더>` | 다른 브랜치 워크트리 등 앱 경로 일시 변경 |
| `--secrets <파일>` | 다른 계정 파일 |

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
worktree:                        # QA 워크트리(init --worktree)일 때
  base: develop                  # 따라갈 브랜치
  update: auto                   # auto(test/run 전 자동으로 가져옴) | warn | off
# ids:
#   sources: [~/path/App/Sources]
```

## 결과 파일 (results/, git 제외)

| 파일 | 내용 |
|---|---|
| `test-<시각>.log` | 테스트 출력 (비밀값 가림) |
| `test-<시각>.xcresult`, `latest.xcresult` | Xcode 결과 |
| `test-<시각>-attachments/` | 실패 시점 화면 구조·스크린샷 |
| `ui-dump.txt`, `dumps/` | 화면 덤프 |
| `build-app.log` | 앱 빌드 로그 |
