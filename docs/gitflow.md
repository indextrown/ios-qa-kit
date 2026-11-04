# Git Flow

이 저장소는 Git Flow 브랜치 모델을 쓴다. 명령은 `git-flow-next`(git-flow의 현재 관리판)로 실행한다.
문서 구성과 설명은 marine-algorithms 저장소의 `docs/gitflow.md`를 따랐고, 이 저장소에 맞게 **CI 대신 직접 돌리는 머지 전 확인 목록**을 더했다.

- 저장소: https://github.com/indextrown/ios-qa-kit (공개, 기본 브랜치 `develop`)

- 처음이면 [1부](#1부-처음-쓰는-사람을-위한-안내)를 위에서부터 읽는다.
- 쓰는 법을 알면 [2부](#2부-참고)에서 명령을 찾는다.

---

# 1부. 처음 쓰는 사람을 위한 안내

## Git Flow가 해결하는 문제

브랜치를 `main` 하나만 쓰면 이런 일이 생긴다.

- 반쯤 만든 기능이 `main`에 들어가 있어서, 지금 상태로는 다른 사람에게 설치하라고 줄 수 없다.
- 이미 쓰고 있는 버전에서 급한 버그가 나왔는데, 그 뒤에 들어간 미완성 코드 때문에 고친 것만 따로 내기 어렵다.
- 어느 커밋이 실제로 배포(설치)된 것인지 헷갈린다.

Git Flow는 **"배포된 코드"와 "개발 중인 코드"를 다른 브랜치에 두고, 그 사이를 오가는 길을 정해 둔 규칙**이다.

| 비유 | 브랜치 |
|---|---|
| 가게 진열대. 사용자가 설치해 가는 완성품만 놓는다 | `main` |
| 작업실 공용 작업대. 다음에 진열할 것들을 모아 맞춰 본다 | `develop` |
| 개인 작업 책상. 기능 하나를 만들고 다 되면 공용 작업대에 올린다 | `feature/…` |
| 진열 전 검수대. 가격표(버전)를 붙이고 마지막 점검을 한다 | `release/…` |
| 진열된 물건에 문제가 생겼을 때 바로 고치는 수리대 | `hotfix/…` |

**이 저장소에서 "배포"란** 다른 사람이 `main`을 받아 `qakit install-skill`로 설치해 쓰는 것이다. `install-skill`은 받아 둔 폴더를 심볼릭 링크로 연결하므로, **설치한 사람의 폴더가 어느 브랜치에 있느냐가 곧 그 사람이 쓰는 버전**이다. 그래서 사용자는 `main`(또는 태그)을 받아 쓰고, 개발은 `develop`에서 한다.

## 어떤 브랜치로 시작할까

| 지금 하려는 일 | 시작 명령 | 어디서 갈라져 어디로 합쳐지나 |
|---|---|---|
| 새 기능, 리팩터링, 문서, 새 ID 규칙 | `git flow feature start <이름>` | `develop` → `develop` |
| 아직 배포 안 된 코드(develop)의 버그 수정 | `git flow bugfix start <이름>` | `develop` → `develop` |
| 지금까지 모은 것을 새 버전으로 배포 | `git flow release start <버전>` | `develop` → `main` (태그 `v<버전>`, develop에도 반영) |
| **이미 배포된 버전**의 급한 버그 수정 (예: 새 앱에 붙였더니 `qakit init`이 깨짐) | `git flow hotfix start <버전>` | `main` → `main` (태그 `v<버전>`, develop에도 반영) |

헷갈리면 "이 수정이 이미 배포된 코드에 있나?"를 묻는다. 있으면 hotfix, 없으면 bugfix다.

## 연습해 보기

처음이라면 실제 저장소 대신 빈 연습 저장소에서 `init → feature → release → hotfix`를 한 번 따라 해 본다. 순서와 실제 출력은 marine-algorithms `docs/gitflow.md`의 "처음부터 따라 하기"와 같다 (같은 git-flow-next 2.1.0).

```sh
mkdir ~/gitflow-practice && cd ~/gitflow-practice
git init -b main && echo "# practice" > README.md && git add . && git commit -m "첫 커밋"
git flow init --preset=classic --defaults
git flow feature start hello
echo 'print("hello")' > hello.py && git add . && git commit -m "hello 추가"
git flow feature finish --no-ff          # develop에 병합, feature/hello 삭제
git log --oneline --graph --all          # 결과 확인
rm -rf ~/gitflow-practice                # 끝나면 지운다
```

## git flow가 대신 해 주는 일

git flow 명령은 일반 git 명령 여러 줄을 묶은 것이다. 직접 쳐도 결과는 같다.

| git flow 명령 | 같은 일을 하는 git 명령 |
|---|---|
| `git flow init` | `git branch develop main` + git-flow 설정 기록 |
| `git flow feature start x` | `git switch -c feature/x develop` |
| `git flow feature finish --no-ff` | `git switch develop`<br>`git merge --no-ff feature/x`<br>`git branch -d feature/x` |
| `git flow release start 0.1.0` | `git switch -c release/0.1.0 develop` |
| `git flow release finish -m "…"` | `git switch main`<br>`git merge release/0.1.0`<br>`git tag -a v0.1.0 -m "…"`<br>`git switch develop`<br>`git merge main`<br>`git branch -d release/0.1.0` |
| `git flow hotfix start 0.1.1` | `git switch -c hotfix/0.1.1 main` |

## 이 저장소에서 기능 하나 만들기

연습에서는 `feature finish`로 로컬에서 합쳤다. **이 저장소에서는 PR로 합친다.** 변경 기록이 PR로 남고, 머지 전 확인 결과를 PR 본문에 남길 수 있기 때문이다. CI는 없으므로 [머지 전 확인](#머지-전-확인)을 직접 돌린다.

```
 내 컴퓨터                                   GitHub
 ─────────                                   ──────
 ① develop 최신으로 (git pull)
 ② feature start  ── feature/x 생김
 ③ 작업·커밋 (여러 번)
 ④ 머지 전 확인 (CI 대신)
 ⑤ publish / push  ───────────────────────▶  origin/feature/x
 ⑥                                           PR: feature/x → develop (확인 결과를 본문에)
 ⑦                                           병합 → develop에 들어감, feature/x 삭제
 ⑧ develop 받고 정리 ◀──────────────────────
```

예: 새 ID 규칙(예: 스테퍼 버튼)을 추가하는 기능

### ① develop을 최신으로

```sh
git switch develop
git pull
```

**꼭 먼저 한다.** `git flow feature start`는 브랜치를 **내 로컬 develop**에서 만든다. 로컬 develop이 뒤처져 있으면 다른 컴퓨터에서 올린 커밋이 빠진 채로 시작한다.

### ② 기능 시작

```sh
git flow feature start stepper-id
```
```
Created branch 'feature/stepper-id' from 'develop'
```

- 이름은 영어 소문자와 `-`. `feature/`는 자동으로 붙으니 쓰지 않는다.
- 지금 어느 브랜치인지 헷갈리면 `git branch --show-current`.

### ③ 작업하고 커밋

```sh
git add AutoID/AutoID.swift Tools/gen-ids/gen_ids.py
git commit -m "feat(autoid): UIStepper 증감 버튼에 ID를 붙인다"
```

### ④ 머지 전 확인

[머지 전 확인](#머지-전-확인)의 표에서 바꾼 부분에 해당하는 줄을 돌린다. **ID 규칙(AutoID)을 바꿨다면 생성기(gen-ids)도 같이 바꿨는지**, 작업공간에서 `qakit gen-ids --verify`가 `불일치 0`인지 꼭 본다.

### ⑤ GitHub에 올리기

```sh
git flow publish        # 처음 한 번: 원격에 feature/stepper-id 를 만들고 연결
git push                # 그다음 커밋부터는 그냥 push
```

### ⑥ PR 만들기

```sh
gh pr create --fill
```

- 기본 브랜치가 `develop`이라 `--base develop`을 안 붙여도 develop으로 간다.
- 본문에 ④에서 돌린 확인과 결과를 적는다 (예: `qakit test 5/5 통과`, `gen-ids --verify 불일치 0`).

### ⑦ 병합

| 어디서 | 방법 | 로컬 feature 브랜치 |
|---|---|---|
| 터미널 | `gh pr merge --merge --delete-branch` | gh가 원격·로컬 브랜치를 모두 지우고 `develop`으로 옮겨 준다 |
| GitHub 웹 | PR 화면에서 **Create a merge commit** → **Delete branch** | 원격만 지워진다. 로컬은 남아 있다 |

### ⑧ 로컬 정리

```sh
git switch develop
git pull                                        # 병합된 develop 받기
git flow feature delete stepper-id              # 웹에서 병합했을 때만. gh로 병합했으면 이미 지워졌다
git fetch --prune                               # 지워진 원격 브랜치 표시 정리
```

### 하는 중에 develop이 바뀌었다면 (필요할 때만)

```sh
git switch develop && git pull
git switch feature/stepper-id
git flow update                                 # develop 위로 내 커밋을 옮긴다 (rebase)
git push --force-with-lease                     # 이미 올린 브랜치라 그냥 push 는 거부된다
```

`--force-with-lease`는 **내 feature 브랜치에만** 쓴다. `develop`·`main`에는 절대 쓰지 않는다.

### PR 방식에서 하지 않는 것

| 하지 말 것 | 이유 |
|---|---|
| `git flow feature finish` | 로컬에서 develop에 합쳐 버린다. 그대로 push 하면 PR을 건너뛴다 |
| `develop`에서 바로 커밋 | 기능 브랜치 없이 develop이 바뀐다 |
| 다른 기능을 같은 브랜치에 섞기 | PR 하나에 기능 하나 |

### 한 장 요약

| 단계 | 명령 |
|---|---|
| ① 최신으로 | `git switch develop && git pull` |
| ② 시작 | `git flow feature start <이름>` |
| ③ 작업 | `git add …` / `git commit -m "…"` |
| ④ 확인 | [머지 전 확인](#머지-전-확인) |
| ⑤ 올리기 | `git flow publish` (처음) / `git push` (이후) |
| ⑥ PR | `gh pr create --fill` (본문에 확인 결과) |
| ⑦ 병합 | `gh pr merge --merge --delete-branch` |
| ⑧ 정리 | `git switch develop && git pull && git fetch --prune` |

## 머지 전 확인

CI가 없으므로 합치기 전에 직접 돌린다. 바꾼 부분에 해당하는 줄만 돌려도 되지만, 배포(release) 전에는 전부 돌린다.

| 바꾼 것 | 확인 명령 | 통과 기준 |
|---|---|---|
| 항상 | `python3 -m py_compile bin/qakit Tools/gen-ids/gen_ids.py` | 출력 없음 |
| 항상 | `grep -rniE "<시범 앱 이름들>" --exclude-dir=.build --exclude-dir=docs .` | 앱 전용 이름 0건 (도구 레포는 범용만) |
| `AutoID/` | `scripts/build-autoid.sh` | dylib 경로 출력 |
| `AutoID/`, `Tools/gen-ids/` | 작업공간에서 `qakit dump-ui` → `qakit gen-ids --verify` | `불일치 0` |
| `Sources/QAKit/`, `templates/` | 작업공간에서 `qakit test` | 기존 테스트 전부 통과 |
| `bin/qakit` | 작업공간에서 `qakit doctor` + 바꾼 명령 직접 실행 | ✅ |
| `skills/` | 새 AI 세션에서 스킬만 보고 간단한 시나리오 1개 작성 | 수정 3회 이내 통과 |

작업공간은 이 저장소 밖(`~/work/qa-workspaces/<앱>`)에 있고 **git으로 관리하지 않는다** (자주 바뀌고 쉽게 지우고 다시 만들 수 있다: `qakit init <앱>`). 확인용으로 마음대로 써도 된다.

## 실수했을 때

| 상황 | 메시지·증상 | 해결 |
|---|---|---|
| 새로 받은 컴퓨터에서 바로 git flow 명령 | `Error: git flow is not initialized` | [이 저장소에서 처음 한 번](#이-저장소에서-처음-한-번) 실행 |
| 같은 이름으로 다시 start | `Error: branch 'feature/x' already exists` | `git flow feature checkout x`로 이동하거나 다른 이름 |
| 브랜치 이름을 잘못 지음 | — | 그 브랜치 위에서 `git flow rename <새 이름>` |
| feature 없이 `develop`에 바로 커밋함 (아직 push 안 함) | — | `git switch -c feature/<이름>`로 커밋을 새 브랜치에 담고<br>`git switch develop && git reset --hard origin/develop`로 되돌림 |
| finish 중 충돌 | `Merge conflict detected while finishing feature/x` | 충돌 파일을 고치고 `git add <파일>`<br>`git flow feature finish x --continue` (그만두려면 `--abort`) |
| 만들던 기능을 버림 | — | `git flow feature delete <이름>` |
| 설치한 qakit/스킬이 개발 중 코드로 바뀜 | `install-skill`이 링크라서, 설치 폴더에서 브랜치를 바꾸면 바로 반영된다 | 쓰는 폴더는 `main`에 두고, 개발은 별도 클론이나 `git worktree`에서 한다 |

충돌이 나면 이미 `develop`으로 이동한 상태라 짧은 명령 `git flow finish --continue`는 동작하지 않는다. **종류와 이름을 붙인다**(`feature finish x --continue`).

---

# 2부. 참고

## 브랜치

| 브랜치 | 어디서 만드나 | 어디로 합치나 | 하는 일 |
|---|---|---|---|
| `main` | — | — | 배포된 버전만. 배포마다 `vX.Y.Z` 태그. 사용자는 여기를 설치한다 |
| `develop` | `main` | — | 다음 버전을 모으는 곳. 기능은 모두 여기로 |
| `feature/<이름>` | `develop` | `develop` | 기능 하나 |
| `bugfix/<이름>` | `develop` | `develop` | 아직 배포 안 된 코드의 버그 수정 |
| `release/<버전>` | `develop` | `main` (그리고 `develop`에 반영) | 배포 준비: README·PLAN 정리, 머지 전 확인 전부. 끝내면 태그 |
| `hotfix/<버전>` | `main` | `main` (그리고 `develop`에 반영) | 배포된 버전의 급한 수정. 끝내면 태그 |

```
main     ──●───────────────────●────────────●──   (v0.1.0)  (v0.1.1)
            \                 / \          /
release      \       ●──●────●   \        /
              \     /             \      /
hotfix         \   /               ●────●
                \ /                      \
develop  ────────●───●───●────────●───────●──
                      \     /
feature                ●───●
```

## 설치

```sh
brew install git-flow-next
git flow version        # 2.1.0 (git-flow-next)
```

Homebrew의 `git-flow`(원조, 2026-12-19 비활성화 예정)나 `git-flow-avh`(이미 빠짐)는 쓰지 않는다. 다른 환경은 https://git-flow.sh/ 참고.

## 이 저장소에서 처음 한 번

git-flow 설정은 `.git/config`에 저장되고 커밋되지 않는다. **저장소를 새로 받은 컴퓨터마다** 한 번 실행한다.

```sh
git clone https://github.com/indextrown/ios-qa-kit.git && cd ios-qa-kit
git switch main && git pull
git flow init --preset=classic --defaults          # main, develop, feature/ … 기본 이름
git config gitflow.branch.release.tagprefix v      # 태그를 0.1.0 이 아니라 v0.1.0 으로
git config gitflow.branch.hotfix.tagprefix v
git flow overview                                  # 설정 확인
```

`develop`이 원격에 이미 있으면 `init`은 그것을 그대로 쓴다.

## 명령어

### 상태 보기

| 명령 | 하는 일 |
|---|---|
| `git flow overview` | 기본 브랜치 관계와 진행 중인 주제 브랜치 |
| `git flow feature list` | 진행 중인 기능 브랜치 (`release list`, `hotfix list`도 같음) |

### 기능 (feature) — `bugfix`도 같다

| 명령 | 하는 일 |
|---|---|
| `git flow feature start <이름>` | `develop`에서 `feature/<이름>`을 만들고 이동 |
| `git flow feature finish --no-ff [이름]` | 로컬에서 `develop`에 합친다 (**이 저장소는 PR로 합치므로 쓰지 않는다**) |
| `git flow feature update` | `develop`의 새 커밋을 내 기능 브랜치로 (rebase) |
| `git flow feature publish` | 원격에 올리기 (`git push -u`) |
| `git flow feature checkout <이름>` / `rename <새 이름>` / `delete <이름>` | 이동 / 이름 바꾸기 / 합치지 않고 지우기 |

### 릴리스 · 핫픽스

| 명령 | 하는 일 |
|---|---|
| `git flow release start <버전>` | `develop`에서 `release/<버전>`. 버전은 `v` 없이 `0.1.0` |
| `git flow release finish -m "Release <버전>"` | `main`에 합치고 `v<버전>` 태그, `develop`에도 반영, 브랜치 삭제 |
| `git flow hotfix start <버전>` | `main`에서 `hotfix/<버전>` |
| `git flow hotfix finish -m "Hotfix <버전>"` | `main`에 합치고 태그, `develop`에도 반영 |

### finish에 자주 붙이는 옵션

| 옵션 | 하는 일 |
|---|---|
| `--no-ff` | 병합 커밋을 만든다. **기본값은 fast-forward**라서 기록을 남기려면 붙인다 |
| `-m "<메시지>"` | 태그 메시지 (release·hotfix) |
| `-k`, `--keep` | 끝낸 뒤에도 브랜치를 지우지 않는다 |
| `--continue` / `--abort` | 충돌 해결 후 이어 가기 / 그만두기 (종류와 이름을 붙인다) |

## 이 저장소의 작업 순서

### 기능 하나

1부 [이 저장소에서 기능 하나 만들기](#이-저장소에서-기능-하나-만들기)의 ①~⑧. 요약:

```sh
git switch develop && git pull                   # ①
git flow feature start <이름>                     # ②
# … 작업, 커밋 …                                  # ③
# 머지 전 확인                                    # ④
git flow publish                                 # ⑤
gh pr create --fill                              # ⑥ 본문에 확인 결과
gh pr merge --merge --delete-branch              # ⑦
git switch develop && git pull && git fetch --prune   # ⑧
```

### 버전 배포

```sh
git switch develop && git pull
git flow release start 0.2.0
# README의 "검증 현황", docs/PLAN.md 진행 기록 정리 → 커밋
# 머지 전 확인 전부
git flow release finish -m "Release 0.2.0"       # main 병합, v0.2.0 태그, develop 반영
git push origin main develop --tags
```

사용자는 `git switch main && git pull`(또는 `git checkout v0.2.0`)로 새 버전을 받는다. 설치는 링크라서 다시 `install-skill`을 할 필요가 없다.

### 배포 준비(release) 중에 다른 기능 만들기

`release/0.2.0`을 점검하는 동안 다음 기능을 만들어야 할 때의 순서다. 새 기능이 **release에만 있는 코드에 의존하는지**에 따라 시작 방법이 다르다.

#### 먼저 확인: release에만 있는 커밋

```sh
git fetch
git log --oneline origin/develop..origin/release/0.2.0
```

release를 만든 뒤 release에 들어간 커밋(README·PLAN 정리, 점검 중 수정)이 나온다. 새 기능이 이 커밋의 코드(새 함수, 바뀐 CLI 옵션, 바뀐 ID 규칙)를 쓰는지 본다.

| 새 기능이 release 코드에 | 시작 방법 |
|---|---|
| 의존하지 않음 | A. `develop`에서 바로 시작 |
| 의존함 | B. release를 `develop`에 먼저 PR로 합치고 시작 |

#### A. 의존하지 않을 때

```sh
git switch develop && git pull
git flow feature start <이름>
```

- release 수정은 `git flow release finish`가 `develop`에도 반영한다. feature는 그 뒤에 `git flow update`로 받으면 된다.
- 개발 중에 의존이 생기면 그때 B의 1을 하고, feature에서 `git flow update`를 한다.

#### B. 의존할 때

```sh
# 1. release를 develop에 먼저 합친다 (develop에 직접 커밋하지 않으므로 PR로)
git push origin release/0.2.0
gh pr create --base develop --head release/0.2.0 --fill
gh pr merge --merge                              # --delete-branch 를 붙이지 않는다

# 2. 합쳐진 develop에서 시작
git switch develop && git pull
git flow feature start <이름>
```

- release 브랜치는 지우지 않는다. 점검은 release에서 계속하고, 끝나면 `release finish`한다.
- 점검에서 또 수정이 나오고 feature에 필요하면 같은 순서를 되풀이한다: release 수정 → PR로 `develop`에 합치기 → feature에서 `git flow update`.
- release에 아직 없는 코드(점검 중 고치는 중인 코드)에는 의존하지 않는다. release에 커밋되고 `develop`에 합쳐진 뒤에 쓴다.

#### 둘 다 지킬 것

| 단계 | 어디서 | 할 일 |
|---|---|---|
| 점검 중 수정 | `release/0.2.0` | 점검에서 나온 버그는 여기에만 고친다. feature에서 고치지 않는다 |
| 수정 전달 | `release` → `develop` → `feature` | 이 순서로만 흐른다 |

```sh
# feature에 develop 받기
git switch develop && git pull
git switch feature/<이름>
git flow update
git push --force-with-lease                      # 이미 올린 feature 브랜치일 때
```

- **`release`를 `feature`에 바로 합치지 않는다.** 그러면 release 수정이 `develop`을 거치지 않고 feature를 통해 들어간다. 나중에 `develop`에 같은 수정이 두 경로로 들어오고, 어디서 온 수정인지 추적하기 어렵다.

### 배포된 버전의 급한 수정

```sh
git switch main && git pull
git flow hotfix start 0.2.1
# … 수정, 커밋, 머지 전 확인 …
git flow hotfix finish -m "Hotfix 0.2.1"
git push origin main develop --tags
```

## 규칙

- `main`과 `develop`에 직접 커밋하지 않는다.
- 브랜치 이름은 영어 소문자와 `-`: `feature/stepper-id`, `bugfix/init-scheme-pick`.
- 커밋 메시지: `<종류>(<범위>): <무엇을 왜>` — 종류 `feat`·`fix`·`docs`·`refactor`·`chore`, 범위 `autoid`·`qakit`·`gen-ids`·`skill`·`template`.
- 버전은 [유의적 버전](https://semver.org/lang/ko/). 1.0 전에는 깨는 변경(ID 규칙 변경, CLI 옵션 변경)도 부 버전(0.x)을 올린다.
- **ID 규칙을 바꾸면 기존 작업공간의 테스트가 깨질 수 있다.** 릴리스 노트(태그 메시지)에 바뀐 규칙을 적는다.
- 태그는 `release`·`hotfix` finish가 단다. 손으로 태그를 만들지 않는다.
- 작업공간(`qa-workspaces/`)은 git으로 관리하지 않는다.
