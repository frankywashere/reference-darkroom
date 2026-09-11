#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h}"
APP_BUNDLE="$PROJECT_ROOT/Reference Darkroom.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
ICONSET="$SCRIPT_DIR/ReferenceDarkroom.iconset"

mkdir -p "$MACOS" "$RESOURCES"
cp "$SCRIPT_DIR/Info.plist" "$CONTENTS/Info.plist"

/usr/bin/swiftc \
  -parse-as-library \
  -swift-version 5 \
  -O \
  -framework Cocoa \
  -framework WebKit \
  "$SCRIPT_DIR/ReferenceDarkroomApp.swift" \
  -o "$MACOS/ReferenceDarkroom"

rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for specification in \
  "16 icon_16x16.png" \
  "32 icon_16x16@2x.png" \
  "32 icon_32x32.png" \
  "64 icon_32x32@2x.png" \
  "128 icon_128x128.png" \
  "256 icon_128x128@2x.png" \
  "256 icon_256x256.png" \
  "512 icon_256x256@2x.png" \
  "512 icon_512x512.png" \
  "1024 icon_512x512@2x.png"; do
  size="${specification%% *}"
  name="${specification#* }"
  /opt/homebrew/bin/magick -background none "$SCRIPT_DIR/ReferenceDarkroomIcon.svg" -resize "${size}x${size}" "$ICONSET/$name"
done
/usr/bin/iconutil -c icns "$ICONSET" -o "$RESOURCES/ReferenceDarkroom.icns"
rm -rf "$ICONSET"

/usr/bin/codesign --force --deep --sign - "$APP_BUNDLE"
echo "$APP_BUNDLE"
