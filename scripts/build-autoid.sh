#!/usr/bin/env bash
# QAAutoID.dylib를 iOS 시뮬레이터(arm64)용으로 빌드한다.
# 사용: build-autoid.sh [출력 폴더]   (기본: <kit>/.build/autoid)
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$KIT_DIR/AutoID"
OUT="${1:-$KIT_DIR/.build/autoid}"
TARGET="arm64-apple-ios17.0-simulator"
SDK="$(xcrun --sdk iphonesimulator --show-sdk-path)"

mkdir -p "$OUT"

xcrun --sdk iphonesimulator clang -c "$SRC/Loader.m" \
  -target "$TARGET" -isysroot "$SDK" -fobjc-arc -o "$OUT/Loader.o"

xcrun --sdk iphonesimulator swiftc -emit-library \
  -module-name QAAutoID -target "$TARGET" -sdk "$SDK" -O \
  "$SRC/AutoID.swift" "$OUT/Loader.o" \
  -Xlinker -install_name -Xlinker @rpath/QAAutoID.dylib \
  -o "$OUT/QAAutoID.dylib"

codesign --force --sign - "$OUT/QAAutoID.dylib" >/dev/null
echo "$OUT/QAAutoID.dylib"
