# QA 작업공간 ({{NAME}})

이 폴더는 ios-qa-kit 작업공간이다. 테스트 대상 앱: `qakit.yml`의 `app.project`.

AI는 작업 전에 ios-qa-kit 스킬을 따른다:
- 설치된 경우: Claude Code `/ios-qa-kit`, Codex `$ios-qa-kit`
- 아니면: `{{KIT_DIR}}/skills/ios-qa-kit/SKILL.md`를 읽는다

핵심 규칙 (스킬 요약):
1. 대상 앱 레포를 수정하지 않는다. 이 작업공간에만 쓴다.
2. 먼저 `qakit doctor`, 그리고 `NOTES.md`와 `Runner/UITests/Flows/`의 공통 단계를 읽는다.
3. ID는 `Runner/UITests/Generated/QAIDs.swift`의 `QAID` 상수로 (파일이 크니 grep으로 필요한 enum만).
4. 화면 하나 = `Pages/`의 BasePage 하나, 시나리오는 `Flows/`의 QATestCase.
5. `qakit test <필터>` → 실패 요약을 읽고 고친다. 같은 원인 3번이면 멈추고 보고.
6. 비밀값은 `QASecrets`로만. 되돌릴 수 없는 동작(탈퇴·결제·삭제·실제 전송)은 승인 없이 넣지 않는다.
7. 새로 알게 된 앱 특이사항은 `NOTES.md`에 적는다.
8. `README.md`의 QA 목록은 qakit이 자동으로 만든다 (직접 고치지 않음). 시나리오 `name:`·맨 위 주석 1~2줄, Swift `///` 한 줄이 설명이 된다.
9. QA 워크트리 브랜치는 유지한다. 사용자가 명시적으로 요청하지 않는 한 다른 브랜치로 병합하거나 push하지 않는다. develop이 앞서면 `qakit worktree-update`로 가져온다 (test/run 전에 자동).
10. 시나리오를 만들거나 실행 방법(옵션·`--var`·`--bench`·`--device` 등)이 늘어나면 `README.md`의 손으로 쓰는 부분(자동 목록 위, 예: `## 실행 명령`)에 그 명령을 한 줄 설명과 함께 추가한다.
