#!/bin/bash
# Build a standalone PodcastSync.app bundle and create a branded DMG installer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"
APP_NAME="PodcastSync"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
DMG_PATH="$BUILD_DIR/$APP_NAME.dmg"
APP_VERSION="${PODCASTSYNC_VERSION:-$(sed -nE 's/^version = "([^"]+)"/\1/p' "$PROJECT_DIR/pyproject.toml" | head -n 1)}"
ICONSET_DIR="$BUILD_DIR/$APP_NAME.iconset"
ICON_MASTER_PNG="$BUILD_DIR/$APP_NAME-1024.png"
ICON_TIFF_DIR="$BUILD_DIR/$APP_NAME.icon-tiff"
ICON_FAMILY_TIFF="$BUILD_DIR/$APP_NAME.icon-family.tiff"
ICON_FILE="$BUILD_DIR/$APP_NAME.icns"
TOOLS_SCRIPT="$SCRIPT_DIR/bundle_macos_tool.sh"
SWIFT_CACHE_DIR="$BUILD_DIR/swift-cache"
PREBUILT_APP_BIN="$BUILD_DIR/$APP_NAME.app/Contents/MacOS/$APP_NAME"
FALLBACK_LAUNCHER_BIN="$BUILD_DIR/$APP_NAME-launcher"
SIGN_IDENTITY="${PODCASTSYNC_SIGNING_IDENTITY:--}"
DMG_STAGE="$BUILD_DIR/dmg-stage"
RW_DMG="$BUILD_DIR/$APP_NAME-temp.dmg"
TMP_RSRC="$BUILD_DIR/$APP_NAME.rsrc"
ATTACH_PLIST="$BUILD_DIR/$APP_NAME-attach.plist"
MOUNT_POINT=""

cleanup() {
    if [ -n "$MOUNT_POINT" ]; then
        hdiutil detach -force "$MOUNT_POINT" >/dev/null 2>&1 || true
    fi
    rm -rf "$DMG_STAGE"
    rm -f "$RW_DMG" "$TMP_RSRC" "$ATTACH_PLIST"
}
trap cleanup EXIT

if [ -z "$APP_VERSION" ]; then
    echo "ERROR: Could not determine PodcastSync version from pyproject.toml."
    exit 1
fi

mkdir -p "$BUILD_DIR"
mkdir -p "$SWIFT_CACHE_DIR/clang" "$SWIFT_CACHE_DIR/swiftpm"

if [ "${PODCASTSYNC_ALLOW_LAUNCHER_FALLBACK:-0}" = "1" ] && [ -x "$PREBUILT_APP_BIN" ]; then
    cp "$PREBUILT_APP_BIN" "$FALLBACK_LAUNCHER_BIN"
fi

echo "=== Building bundled backend ==="
"$SCRIPT_DIR/build_backend.sh"

echo "=== Generating app icon ==="
CLANG_MODULE_CACHE_PATH="$SWIFT_CACHE_DIR/clang" \
swift "$SCRIPT_DIR/generate_app_icon.swift" "$ICONSET_DIR"
rm -f "$ICON_FILE"
sips -s format png "$ICONSET_DIR/icon_512x512@2x.png" --out "$ICON_MASTER_PNG" >/dev/null
rm -rf "$ICON_TIFF_DIR"
mkdir -p "$ICON_TIFF_DIR"
for size in 16 32 48 128 256 512 1024; do
    sips -z "$size" "$size" -s format tiff "$ICON_MASTER_PNG" \
        --out "$ICON_TIFF_DIR/icon-${size}.tiff" >/dev/null
done
tiffutil -cat \
    "$ICON_TIFF_DIR/icon-16.tiff" \
    "$ICON_TIFF_DIR/icon-32.tiff" \
    "$ICON_TIFF_DIR/icon-48.tiff" \
    "$ICON_TIFF_DIR/icon-128.tiff" \
    "$ICON_TIFF_DIR/icon-256.tiff" \
    "$ICON_TIFF_DIR/icon-512.tiff" \
    "$ICON_TIFF_DIR/icon-1024.tiff" \
    -out "$ICON_FAMILY_TIFF" >/dev/null
tiff2icns "$ICON_FAMILY_TIFF" "$ICON_FILE" >/dev/null

echo "=== Building Swift menu bar app ==="
cd "$PROJECT_DIR/macos/PodcastSync"
SWIFT_BIN=""

if CLANG_MODULE_CACHE_PATH="$SWIFT_CACHE_DIR/clang" \
   SWIFTPM_MODULECACHE_OVERRIDE="$SWIFT_CACHE_DIR/swiftpm" \
   swift build -c release 2>&1; then
    SWIFT_BIN="$(
        CLANG_MODULE_CACHE_PATH="$SWIFT_CACHE_DIR/clang" \
        SWIFTPM_MODULECACHE_OVERRIDE="$SWIFT_CACHE_DIR/swiftpm" \
        swift build -c release --show-bin-path
    )/PodcastSync"
fi

if [ -z "$SWIFT_BIN" ] || [ ! -f "$SWIFT_BIN" ]; then
    if [ "${PODCASTSYNC_ALLOW_LAUNCHER_FALLBACK:-0}" = "1" ] && [ -x "$FALLBACK_LAUNCHER_BIN" ]; then
        echo "  Reusing existing menu bar launcher binary at $FALLBACK_LAUNCHER_BIN"
        SWIFT_BIN="$FALLBACK_LAUNCHER_BIN"
    else
        echo "ERROR: Swift launcher build failed; refusing to use a stale launcher binary." >&2
        exit 1
    fi
fi

echo "=== Assembling $APP_NAME.app ==="
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

cp "$SWIFT_BIN" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
cp "$ICON_FILE" "$APP_BUNDLE/Contents/Resources/$APP_NAME.icns"

BACKEND_DIST="$BUILD_DIR/backend-dist/podcastsync-backend"
if [ ! -d "$BACKEND_DIST" ] || [ ! -x "$BACKEND_DIST/podcastsync-backend" ]; then
    echo "ERROR: Bundled backend not found at $BACKEND_DIST"
    exit 1
fi
echo "  Embedding bundled Python backend..."
cp -R "$BACKEND_DIST" "$APP_BUNDLE/Contents/Resources/backend"

echo "=== Bundling ffmpeg and ffprobe ==="
FFMPEG_BIN="$(command -v ffmpeg 2>/dev/null || true)"
FFPROBE_BIN="$(command -v ffprobe 2>/dev/null || true)"
TOOLS_ROOT="$APP_BUNDLE/Contents/Resources/tools"

if [ -z "$FFMPEG_BIN" ] || [ -z "$FFPROBE_BIN" ] || [ ! -x "$FFMPEG_BIN" ] || [ ! -x "$FFPROBE_BIN" ]; then
    echo "ERROR: ffmpeg and ffprobe are required to build. Install: brew install ffmpeg" >&2
    exit 1
fi

rm -rf "$TOOLS_ROOT"
"$TOOLS_SCRIPT" "$FFMPEG_BIN" "$TOOLS_ROOT"
"$TOOLS_SCRIPT" "$FFPROBE_BIN" "$TOOLS_ROOT"

cat > "$APP_BUNDLE/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.podcastsync.app</string>
    <key>CFBundleName</key>
    <string>PodcastSync</string>
    <key>CFBundleDisplayName</key>
    <string>PodcastSync</string>
    <key>CFBundleVersion</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>PodcastSync</string>
    <key>CFBundleIconFile</key>
    <string>PodcastSync</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026 Shay Prasad. MIT License.</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.entertainment</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

echo "  .app bundle created at $APP_BUNDLE"

echo "=== Code signing (ad-hoc, inside-out) ==="
xattr -cr "$APP_BUNDLE"

sign_nested() {
    codesign --force --sign - "$1"
}

# Sign dylibs first
find "$APP_BUNDLE" -name "*.dylib" -print0 | while IFS= read -r -d '' f; do
    sign_nested "$f"
done
find "$APP_BUNDLE" -name "*.so" -print0 | while IFS= read -r -d '' f; do
    sign_nested "$f"
done

# Sign bundled tool binaries
sign_nested "$APP_BUNDLE/Contents/Resources/tools/bin/ffprobe"
sign_nested "$APP_BUNDLE/Contents/Resources/tools/bin/ffmpeg"

# Sign the PyInstaller backend executable
sign_nested "$APP_BUNDLE/Contents/Resources/backend/podcastsync-backend"

# Strip all resource forks / Finder info before signing the outer bundle.
# Embedded code signatures survive ditto --norsrc (they live in the binary's
# __LINKEDIT segment, not in xattrs), so the nested signatures stay intact.
CLEAN_APP="${APP_BUNDLE}.clean"
ditto --norsrc "$APP_BUNDLE" "$CLEAN_APP"
rm -rf "$APP_BUNDLE"
mv "$CLEAN_APP" "$APP_BUNDLE"

if [ "$SIGN_IDENTITY" = "-" ]; then
    codesign --force --sign - "$APP_BUNDLE"
else
    codesign --force --sign "$SIGN_IDENTITY" --options runtime --timestamp "$APP_BUNDLE"
fi
codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
spctl --assess --type execute "$APP_BUNDLE" || echo "note: spctl fails for ad-hoc (expected until notarized)"
echo "  Signed."

echo "=== Creating DMG ==="
rm -f "$DMG_PATH"

rm -rf "$DMG_STAGE"
rm -f "$RW_DMG" "$TMP_RSRC"
mkdir -p "$DMG_STAGE"
cp -R "$APP_BUNDLE" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
cp "$ICON_FILE" "$DMG_STAGE/.VolumeIcon.icns"

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_STAGE" \
    -ov \
    -format UDRW \
    "$RW_DMG" 2>&1

hdiutil attach -plist -readwrite -noverify -noautoopen "$RW_DMG" > "$ATTACH_PLIST"
for index in $(seq 0 9); do
    candidate="$(/usr/libexec/PlistBuddy -c "Print :system-entities:${index}:mount-point" "$ATTACH_PLIST" 2>/dev/null || true)"
    if [ -n "$candidate" ]; then
        MOUNT_POINT="$candidate"
    fi
    if [[ "$candidate" == /Volumes/* ]]; then
        break
    fi
done
if [[ "$MOUNT_POINT" != /Volumes/* ]]; then
    echo "ERROR: Failed to mount $RW_DMG"
    exit 1
fi

cp "$ICON_FILE" "$MOUNT_POINT/.VolumeIcon.icns"
SetFile -a V "$MOUNT_POINT/.VolumeIcon.icns"
SetFile -a C "$MOUNT_POINT"
bless --folder "$MOUNT_POINT" --openfolder "$MOUNT_POINT" >/dev/null 2>&1 || true
hdiutil detach "$MOUNT_POINT" >/dev/null
MOUNT_POINT=""

hdiutil convert "$RW_DMG" -ov -format UDZO -o "$DMG_PATH" 2>&1

sips -i "$ICON_FILE" >/dev/null
DeRez -only icns "$ICON_FILE" > "$TMP_RSRC"
Rez -append "$TMP_RSRC" -o "$DMG_PATH"
SetFile -a C "$DMG_PATH"

echo ""
echo "=== Build complete! ==="
echo "  App:  $APP_BUNDLE"
echo "  DMG:  $DMG_PATH"
echo "  Size: $(du -sh "$DMG_PATH" | cut -f1)"
