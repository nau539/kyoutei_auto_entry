#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
for ed in "AQUA EDGE AI_GOLD" "AQUA EDGE AI_SILVER" "AQUA EDGE AI_BRONZE" "KYOUTEI"; do
  echo "=== BUILD: $ed ==="
  python build_release.py --spec kyoutei_auto_entry.spec --app-name "$ed" --clean
done
echo "=== ALL BUILDS DONE ==="
ls -la dist/*v0.3.27* 2>/dev/null
