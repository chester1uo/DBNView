#!/bin/sh
# Wrap a built DBNView.app into a compressed disk image with an Applications shortcut.
#     packaging/make_dmg.sh dist/DBNView.app DBNView-0.5.0-macOS-arm64.dmg
set -eu
APP=${1:-dist/DBNView.app}
OUT=${2:-DBNView.dmg}
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/DBNView.app"
ln -s /Applications "$STAGE/Applications"
rm -f "$OUT"
hdiutil create -volname DBNView -srcfolder "$STAGE" -fs HFS+ -format UDZO -imagekey zlib-level=9 -ov "$OUT" >/dev/null
echo "$OUT"
