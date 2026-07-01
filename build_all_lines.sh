#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
for ed in \
  "AQUA EDGE AI_GOLD" "AQUA EDGE AI_SILVER" "AQUA EDGE AI_BRONZE" \
  "AQUA EDGE AI CLEARISM_GOLD" "AQUA EDGE AI CLEARISM_SILVER" "AQUA EDGE AI CLEARISM_BRONZE" \
  "KYOUTEI"; do
  echo "=== BUILD: $ed ==="
  python build_release.py --spec kyoutei_auto_entry.spec --app-name "$ed" --clean
done
echo "=== ALL 7 BUILDS DONE ==="
ls -la dist/*v0.3.28.exe
