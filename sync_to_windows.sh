#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="${1:-$HOME/src/kyoutei/kyoutei_auto_entry/}"
DST_DIR="${2:-/mnt/c/pleiades/2023-03/workspace/kyoutei/kyoutei_auto_entry/}"

rsync_opts=(
  -av
  --info=progress2
  --exclude=.git/
  --exclude=.venv/
  --exclude=venv/
  --exclude=__pycache__/
  --exclude=*.pyc
  --exclude=.pytest_cache/
  --exclude=.mypy_cache/
  --exclude=build/
  --exclude=dist/
)

# `SYNC_DELETE=1 bash ./sync_to_windows.sh` で削除同期を有効化
if [[ "${SYNC_DELETE:-0}" == "1" ]]; then
  rsync_opts+=(--delete)
fi

echo "[sync] source:      ${SRC_DIR}"
echo "[sync] destination: ${DST_DIR}"
if [[ "${SYNC_DELETE:-0}" == "1" ]]; then
  echo "[sync] mode: --delete enabled"
fi

rsync "${rsync_opts[@]}" "${SRC_DIR}" "${DST_DIR}"
echo "[sync] done"
