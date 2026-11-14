#!/usr/bin/env bash
# Mount the shared Drive mirror read-only so fetch() can reuse payloads
# instead of re-downloading from NASA/AWS (sha256 is still checked against
# MANIFEST.json). Unmount with: fusermount3 -u "$MNT"
set -euo pipefail
REMOTE="${CC_DRIVE_REMOTE:-ccdrive}"
MNT="${CC_DRIVE_MOUNT:-$HOME/mnt/cosmic-drive}"
mkdir -p "$MNT"
if mountpoint -q "$MNT"; then echo "already mounted: $MNT"; exit 0; fi
rclone mount "$REMOTE:" "$MNT" --read-only --vfs-cache-mode full \
  --vfs-cache-max-size 20G --dir-cache-time 5m --daemon
echo "mounted $REMOTE: at $MNT (read-only); mirror at $MNT/snapshots"
