#!/usr/bin/env bash
# QAAutoID.dylib를 빌드한다.
# 사용: build-autoid.sh [출력 폴더] [simulator|device]   (기본: <kit>/.build/autoid, simulator)
#   simulator: iOS 시뮬레이터(arm64)용, ad-hoc 서명 (DYLD_INSERT_LIBRARIES로 주입)
#   device:    실기기(arm64)용, 서명 없음 (qakit이 앱 안 Frameworks/에 넣고 앱과 같은 인증서로 서명)
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$KIT_DIR/AutoID"
OUT="${1:-$KIT_DIR/.build/autoid}"
PLATFORM="${2:-simulator}"
if [ "$PLATFORM" = "device" ]; then
  SDK_NAME=iphoneos; TARGET="arm64-apple-ios17.0"
else
  SDK_NAME=iphonesimulator; TARGET="arm64-apple-ios17.0-simulator"
fi
SDK="$(xcrun --sdk $SDK_NAME --show-sdk-path)"

mkdir -p "$OUT"

xcrun --sdk $SDK_NAME clang -c "$SRC/Loader.m" \
  -target "$TARGET" -isysroot "$SDK" -fobjc-arc -o "$OUT/Loader.o"

xcrun --sdk $SDK_NAME swiftc -emit-library \
  -module-name QAAutoID -target "$TARGET" -sdk "$SDK" -O \
  "$SRC/AutoID.swift" "$OUT/Loader.o" \
  -Xlinker -install_name -Xlinker @rpath/QAAutoID.dylib \
  -o "$OUT/QAAutoID.dylib"

if [ "$PLATFORM" != "device" ]; then
  codesign --force --sign - "$OUT/QAAutoID.dylib" >/dev/null
fi
echo "$OUT/QAAutoID.dylib"
