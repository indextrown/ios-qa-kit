#!/usr/bin/env bash
# 맥 앱(QA Kit.app) 만들기: Swift 셸(App/) + 도구 폴더(Contents/Resources/kit). DMG는 scripts/build-dmg.sh.
#
#   scripts/build-app.sh            # dist/QA Kit.app
#   scripts/build-app.sh --open     # 만든 뒤 켜기
#
# 도구 폴더에는 git이 다루는 파일만 넣는다 (빌드 결과·web 소스·테스트 제외). 앱 안 도구 폴더는 읽기 전용으로 쓰이고
# 빌드 결과는 ~/Library/Application Support/qakit에 쌓인다 (D1).
# 개발 중에는 앱을 다시 만들지 않고 저장소를 바로 쓰게 할 수 있다: QAKIT_KIT=$PWD "dist/QA Kit.app/Contents/MacOS/QAKit"
set -euo pipefail
cd "$(dirname "$0")/.."

OPEN=0
[ "${1:-}" = "--open" ] && OPEN=1
VERSION="$(cat VERSION)"
APP="dist/QA Kit.app"
BIN="$APP/Contents/MacOS/QAKit"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/kit" dist/obj

# 인텔·애플 실리콘 둘 다 (lipo)
for arch in arm64 x86_64; do
  xcrun swiftc -O -target "$arch-apple-macos13.0" -module-name QAKitApp -o "dist/obj/QAKit-$arch" App/Sources/*.swift
done
lipo -create -output "$BIN" dist/obj/QAKit-arm64 dist/obj/QAKit-x86_64

sed "s/__VERSION__/$VERSION/g" App/Info.plist > "$APP/Contents/Info.plist"
cp App/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
printf 'APPL????' > "$APP/Contents/PkgInfo"

# git에 있거나 새로 만든(무시되지 않는) 파일 중 지금 있는 것 (UI를 다시 빌드하면 ui/dist 파일 이름이 바뀐다)
git ls-files -z -co --exclude-standard -- bin lib Tools Sources ScenarioRunner AndroidRunner AutoID ui/dist skills templates scripts/build-autoid.sh VERSION Package.swift \
  | while IFS= read -r -d '' f; do [ -f "$f" ] && printf '%s\0' "$f"; done \
  | rsync -a --from0 --files-from=- . "$APP/Contents/Resources/kit/"

# 서명: QAKIT_SIGN_ID(예: "Developer ID Application: 이름 (팀ID)")가 있으면 그것으로 + hardened runtime(공증 조건),
# 없으면 ad-hoc (받은 사람이 처음 열 때 한 번 허용해야 함 — docs/web-ui.md "맥 앱")
if [ -n "${QAKIT_SIGN_ID:-}" ]; then
  codesign --force --options runtime --timestamp --sign "$QAKIT_SIGN_ID" "$APP"
else
  codesign --force --sign - "$APP" 2>/dev/null
fi
codesign --verify --strict "$APP"
echo "✅ $APP ($VERSION, $(du -sh "$APP" | cut -f1))"
[ "$OPEN" = 1 ] && open "$APP"
exit 0
