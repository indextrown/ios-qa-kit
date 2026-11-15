#!/usr/bin/env bash
# develop → main 릴리스를 한 번에: 점검 → 버전 → git flow release → 태그·push → GitHub 릴리스.
#
#   scripts/release.sh minor              # 0.30.0 → 0.31.0 (patch | minor | major | X.Y.Z)
#   scripts/release.sh patch --dry-run    # 점검과 계획만 (아무것도 바꾸지 않음)
#   scripts/release.sh 0.31.0 --notes notes.md
#
# 릴리스 노트: --notes 파일이 없으면 지난 태그 이후 develop에 병합된 PR 제목으로 만든다.
# 금지어 검사: 시범 앱 이름 등 저장소에 들어가면 안 되는 말은 저장소에 적을 수 없으므로
#   환경 변수 QAKIT_FORBIDDEN (정규식, 예: 'appname|앱이름') 또는 ~/.config/qakit/forbidden-words (한 줄 정규식)에서 읽는다.
# 필요한 것: git flow (git-flow-avh), gh (로그인), python3, npm.
set -euo pipefail
cd "${QAKIT_REPO:-$(dirname "$0")/..}"   # QAKIT_REPO: 다른 체크아웃에서 시험할 때

say() { printf '\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  ✅ %s\n' "$*"; }
die() { printf '  ❌ %s\n' "$*" >&2; exit 1; }

BUMP="${1:-}"; shift || true
DRY=0; NOTES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --notes) NOTES="$2"; shift ;;
    *) die "모르는 인자: $1" ;;
  esac
  shift
done
[ -n "$BUMP" ] || die "버전을 주세요: patch | minor | major | X.Y.Z  (예: scripts/release.sh minor --dry-run)"

say "1. 전제"
[ "$(git branch --show-current)" = "develop" ] || die "develop 브랜치에서 실행하세요"
[ -z "$(git status --porcelain)" ] || die "커밋하지 않은 변경이 있습니다"
git fetch -q origin develop main --tags
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" ] || die "develop이 origin/develop과 다릅니다 (git pull / push 먼저)"
command -v gh >/dev/null && gh auth status >/dev/null 2>&1 || die "gh 로그인이 필요합니다 (gh auth login)"
git flow version >/dev/null 2>&1 || die "git flow가 필요합니다 (brew install git-flow-avh)"
ok "develop = origin/develop, 깨끗함"

CUR="$(cat VERSION)"
IFS=. read -r MA MI PA <<<"$CUR"
case "$BUMP" in
  patch) NEW="$MA.$MI.$((PA + 1))" ;;
  minor) NEW="$MA.$((MI + 1)).0" ;;
  major) NEW="$((MA + 1)).0.0" ;;
  [0-9]*.[0-9]*.[0-9]*) NEW="$BUMP" ;;
  *) die "버전 형식: patch | minor | major | X.Y.Z" ;;
esac
git rev-parse -q --verify "refs/tags/v$NEW" >/dev/null && die "태그 v${NEW}가 이미 있습니다"
ok "버전 $CUR → $NEW"

say "2. 점검"
python3 -m py_compile bin/qakit Tools/gen-ids/gen_ids.py Tools/scenario/scenario_tools.py && ok "컴파일"
if [ -d tests ]; then
  python3 -m unittest discover -s tests >/tmp/qakit-release-tests.log 2>&1 || { tail -30 /tmp/qakit-release-tests.log; die "테스트 실패"; }
  ok "테스트 ($(grep -o 'Ran [0-9]* tests' /tmp/qakit-release-tests.log))"
else
  printf '  ⚠️  tests/ 없음 — 테스트 건너뜀\n'
fi
(cd web && { [ -d node_modules ] || npm ci --silent; } && npm run build >/tmp/qakit-release-web.log 2>&1) || { tail -20 /tmp/qakit-release-web.log; die "UI 빌드 실패"; }
[ -z "$(git status --porcelain ui/dist)" ] || { git status --porcelain ui/dist; die "ui/dist가 web/ 소스와 다릅니다 — 빌드 결과를 커밋하세요"; }
for f in $(grep -o 'assets/[^"]*' ui/dist/index.html); do
  git ls-files --error-unmatch "ui/dist/$f" >/dev/null 2>&1 || die "커밋 안 된 빌드 파일: ui/dist/$f"
done
ok "UI 빌드 = 커밋된 ui/dist"
PATTERN="${QAKIT_FORBIDDEN:-}"
[ -z "$PATTERN" ] && [ -f "$HOME/.config/qakit/forbidden-words" ] && PATTERN="$(head -1 "$HOME/.config/qakit/forbidden-words")"
if [ -n "$PATTERN" ]; then
  HITS="$(grep -rniE "$PATTERN" --exclude-dir=.build --exclude-dir=docs --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=.git . || true)"
  [ -z "$HITS" ] || { echo "$HITS" | head -10; die "금지어가 있습니다"; }
  ok "금지어 없음"
else
  printf '  ⚠️  금지어 검사 건너뜀 (QAKIT_FORBIDDEN 또는 ~/.config/qakit/forbidden-words 없음)\n'
fi

say "3. 릴리스 노트"
LAST="$(git describe --tags --abbrev=0 origin/main 2>/dev/null || true)"
BODY="$(mktemp)"
if [ -n "$NOTES" ]; then
  cp "$NOTES" "$BODY"
else
  {
    echo "## 바뀐 것"
    git log "${LAST:+$LAST..}origin/develop" --merges --first-parent --format='%s%n%b' |
      awk '/^Merge pull request #/ {pr=$4; getline; if ($0 != "") print "- " $0 " (" pr ")"}'
    echo
    echo "업데이트: \`qakit update\`"
  } >"$BODY"
fi
grep -q '^- ' "$BODY" || [ -n "$NOTES" ] || die "지난 태그($LAST) 이후 병합된 PR이 없습니다"
sed 's/^/  │ /' "$BODY"

if [ "$DRY" = 1 ]; then
  say "미리 보기만 (--dry-run): git flow release $NEW → main·develop·v$NEW push → gh release v$NEW"
  rm -f "$BODY"
  exit 0
fi

say "4. 릴리스 $NEW"
git branch -f main origin/main   # 로컬 main이 뒤처져 있으면 finish가 옛 main에 합친다
git flow release start "$NEW" >/dev/null
echo "$NEW" >VERSION
git commit -qam "chore(release): $NEW"
GIT_MERGE_AUTOEDIT=no git flow release finish -m "v$NEW" "$NEW" >/dev/null 2>&1
[ "$(git tag --points-at main)" = "v$NEW" ] || die "태그 v${NEW}가 main에 없습니다 — git flow 출력을 확인하세요"
git push -q origin main develop "v$NEW"
gh release create "v$NEW" --title "v$NEW" --notes-file "$BODY" >/dev/null
rm -f "$BODY"
git switch -q develop
ok "https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/v$NEW"
echo "  설치본 갱신: qakit update"
