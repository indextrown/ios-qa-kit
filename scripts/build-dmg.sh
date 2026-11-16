#!/usr/bin/env bash
# 맥 앱 DMG 만들기: QA Kit.app + Applications 바로가기 → dist/QA-Kit-<버전>.dmg (끌어다 놓아 설치)
#
#   scripts/build-dmg.sh                  # ad-hoc 서명 (사내 몇 명이면 충분 — 처음 열 때 한 번 허용)
#   QAKIT_SIGN_ID="Developer ID Application: 이름 (팀ID)" \
#   QAKIT_NOTARY_PROFILE=qakit scripts/build-dmg.sh   # 서명 + 공증 + staple (받은 사람이 바로 연다)
#
# 공증 준비(한 번): xcrun notarytool store-credentials qakit --apple-id <id> --team-id <팀ID> --password <앱 암호>
set -euo pipefail
cd "$(dirname "$0")/.."

scripts/build-app.sh >/dev/null
VERSION="$(cat VERSION)"
APP="dist/QA Kit.app"
DMG="dist/QA-Kit-$VERSION.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -quiet -volname "QA Kit $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO -imagekey zlib-level=9 -ov "$DMG"

if [ -n "${QAKIT_SIGN_ID:-}" ]; then
  codesign --force --timestamp --sign "$QAKIT_SIGN_ID" "$DMG"
  if [ -n "${QAKIT_NOTARY_PROFILE:-}" ]; then
    xcrun notarytool submit "$DMG" --keychain-profile "$QAKIT_NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"
    SIGNED="Developer ID 서명 + 공증"
  else
    SIGNED="Developer ID 서명 (공증 안 함 — QAKIT_NOTARY_PROFILE)"
  fi
else
  SIGNED="ad-hoc 서명 (처음 열 때 허용 필요)"
fi
hdiutil verify -quiet "$DMG"
echo "✅ $DMG ($(du -h "$DMG" | cut -f1), $SIGNED)"
