# 개발 · 기여

도구 자체를 고치는 사람을 위한 문서입니다.

[← README](../README.md)

## 레포 구조

> 테스트: `python3 -m unittest discover -s tests` (시뮬레이터 없이 도는 단위 테스트 — 시나리오 파서, 실패 제안, MCP, AI 세션). PR마다 GitHub Actions(`.github/workflows/ci.yml`)가 이것과 `ui/dist` 최신 여부를 확인합니다.
>
> UI(`qakit ui`)를 고칠 때: `cd web && npm install && npm run dev` (개발 서버, `QAKIT_UI=http://127.0.0.1:<qakit ui 포트>`로 API 연결) → `npm run build`로 `ui/dist`를 다시 만들어 함께 커밋. 사용자는 Node 없이 `ui/dist`를 그대로 씁니다.

<details>
<summary>폴더 구성 보기</summary>

```text
qa-kit/
├── bin/qakit                 CLI 입구 (lib/qakit/*.py를 순서대로 읽음)
├── lib/qakit/                CLI 본체, 구역별 파일 (Python 3 표준 라이브러리만): 00_base · 10_device · 20_build · 30_setup · 40_results_sync · 50_run_serve · 60_bench · 70_save_do · 80_ui_data · 85_mcp_ai · 86_ui_server · 90_update_main
├── AutoID/                   자동 ID 라이브러리 (시뮬레이터 주입용 dylib)
├── Sources/QAKit/            테스트용 Swift 라이브러리 (BasePage, QATestCase, QAWait …)
├── Tools/gen-ids/            앱 소스 → QAID 상수 생성기
├── templates/workspace/      qakit init이 복사하는 작업공간 틀
├── skills/qa-kit/        AI 스킬 (SKILL.md + references)
├── scripts/build-autoid.sh
└── docs/
    ├── PLAN.md               설계·진행 기록
    └── gitflow.md            브랜치 규칙·기여 순서 (Git Flow)
```

</details>

---

## 기여하기

이 저장소는 **Git Flow**를 씁니다.

- 사용자는 `main`을 설치합니다.
- 개발은 `develop`에서 `feature/…` 브랜치 → PR로 합칩니다.
- CI가 없으니 PR 전에 [머지 전 확인](gitflow.md#머지-전-확인)을 직접 돌립니다.

자세한 순서: [docs/gitflow.md](gitflow.md)

---

## 검증 현황

<details>
<summary>검증한 앱과 결과 보기</summary>

| 앱 | 결과 |
|---|---|
| **앱 A** (UIKit + RxSwift + SnapKit, 로그인 있음) | 로그인 화면 ID 100%, 메인 92%. Swift 테스트 6개 통과. 시나리오 파일(초기화 → 로그인 → 검색 → 목록 등록·선택 → 설정 → 지도 확대, 71단계) 통과. QA 폴더 삭제 → AI 없이 복구 → 재실행 통과. 새 AI 세션이 스킬만 보고 Swift·시나리오 파일 테스트를 작성해 통과 |
| **앱 B** (UIKit, 리스트·탭바 위주) | 첫 화면 ID 100%. init → build → dump → 생성 ID 검증 → 테스트 2개 통과 |
| **앱 C** (SwiftUI + TCA, Tuist 모듈, 로그인 있음) | QA 워크트리에서 build-app이 SwiftUI ID 139개를 삽입·빌드·복원 (워크트리 깨끗). 로그인 화면 ID 100%, 온보딩 67%. `gen-ids --verify` 불일치 0. ID로 쓴 시나리오(온보딩 건너뛰기 → 로그인 화면) 통과 |

</details>
