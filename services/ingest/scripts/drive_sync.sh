#!/usr/bin/env bash
# Mirror local snapshot payloads to the shared Google Drive folder.
#   Drive folder: https://drive.google.com/drive/folders/1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_
#   rclone remote: ccdrive (root_folder_id = that folder), set up once with
#   `rclone config create ccdrive drive scope=drive root_folder_id=1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_`
# Uses `copy`, never `sync`: nothing on Drive is ever deleted by this script.
# MANIFEST.json (tracked in git) stays the source of truth for hashes.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
REMOTE="${CC_DRIVE_REMOTE:-ccdrive}"
rclone copy "$REPO/data/snapshots" "$REMOTE:snapshots" \
  --exclude '*.part' --exclude '_derived/**' \
  --transfers 4 --checkers 8 --drive-chunk-size 64M \
  --stats 30s --stats-one-line "$@"
rclone copyto "$REPO/data/snapshots/MANIFEST.json" "$REMOTE:snapshots/MANIFEST.json"
