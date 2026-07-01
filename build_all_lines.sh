#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

for ed in GOLD SILVER BRONZE; do
  app_name="AQUA EDGE AI_${ed}"
  echo "=== BUILD CLEARISM: $app_name ==="
  python build_release.py --spec kyoutei_auto_entry.spec --line clearism --edition "$ed" --auth-module auth_clear --app-name "$app_name" --clean
done

echo "=== BUILD MASTER: kyoutei_auto_trade ==="
python build_release.py --spec kyoutei_auto_entry.spec --line aqua --edition TRADE --auth-module auth_master --app-name kyoutei_auto_trade --no-version-suffix --clean

echo "=== ALL 4 BUILDS DONE ==="
ls -la dist/AQUA\ EDGE\ AI_*v0.3.28.exe dist/kyoutei_auto_trade.exe
