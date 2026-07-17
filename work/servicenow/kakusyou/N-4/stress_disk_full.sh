#!/usr/bin/env bash
#
# N-4: Disk Full の発生 (MID サーバ上でローカル実行)
#
# 指定したパスのファイルシステムを「残空き LEAVE_FREE_MB」まで埋める。
# 既定は LEAVE_FREE_MB=0 で、ENOSPC が出るまで詰め込み 100% 使用率にする。
#
# 使い方:
#   bash stress_disk_full.sh                    # 既定 600 秒, /tmp, 100% 埋め
#   bash stress_disk_full.sh 1800
#   TARGET=/var/tmp/n4.bin bash stress_disk_full.sh 600
#   LEAVE_FREE_MB=50 bash stress_disk_full.sh 600   # 50MB だけ残す
#
# 注意:
#   - 100% 使用率にすると syslog / journal / MID Server のログ書き込みが失敗
#     する可能性あり。ログが必要なシステムでは LEAVE_FREE_MB を指定すること。
#   - 終了時に必ず TARGET を削除する。kill -9 された場合は手動削除:
#       rm -f /tmp/n4_diskfull.bin
#
set -uo pipefail

DURATION="${1:-600}"
TARGET="${TARGET:-/tmp/n4_diskfull.bin}"
LEAVE_FREE_MB="${LEAVE_FREE_MB:-0}"

cleanup() {
  echo
  echo "Cleaning up $TARGET..."
  rm -f "$TARGET"
  sync
  df -h "$(dirname "$TARGET")" || true
  echo "Done"
}
trap cleanup EXIT INT TERM

DIR="$(dirname "$TARGET")"
mkdir -p "$DIR"

df_free_mb() {
  df -m "$1" | awk 'NR==2 {print $4}'
}

FREE_MB=$(df_free_mb "$DIR")
FILL_MB=$(( FREE_MB - LEAVE_FREE_MB ))

echo "N-4 Disk Full stress"
echo "  target          : $TARGET"
echo "  duration        : ${DURATION}s"
echo "  free now        : ${FREE_MB} MB"
echo "  leave_free_mb   : ${LEAVE_FREE_MB} MB"
echo "  initial fill    : ${FILL_MB} MB"
echo

if [ "$FILL_MB" -le 0 ]; then
  echo "WARN: 既に空きがありません (${FREE_MB}MB free). スキップして hold へ進む。"
else
  # 一次充填: fallocate (高速)
  if command -v fallocate >/dev/null 2>&1; then
    echo "[phase 1] fallocate -l ${FILL_MB}M ..."
    fallocate -l "${FILL_MB}M" "$TARGET" 2>/dev/null \
      || dd if=/dev/zero of="$TARGET" bs=1M count="$FILL_MB" status=progress 2>&1 \
      || true
  else
    echo "[phase 1] dd bs=1M count=${FILL_MB}"
    dd if=/dev/zero of="$TARGET" bs=1M count="$FILL_MB" status=progress 2>&1 || true
  fi
  sync
fi

# 二次充填: 残空きが LEAVE_FREE_MB を超えていれば 1MB ずつ append して ENOSPC まで
echo "[phase 2] top-up to ENOSPC (or leave ${LEAVE_FREE_MB}MB) ..."
TOPUP=0
while true; do
  CUR_FREE=$(df_free_mb "$DIR")
  if [ "$CUR_FREE" -le "$LEAVE_FREE_MB" ]; then
    break
  fi
  # 1 MB を追記。書けなければループ脱出
  if ! dd if=/dev/zero bs=1M count=1 status=none 2>/dev/null >> "$TARGET"; then
    break
  fi
  TOPUP=$((TOPUP+1))
done
sync
echo "  top-up appended : ${TOPUP} MB"
echo

df -h "$DIR"
echo
echo "Holding ${DURATION}s..."
sleep "$DURATION"
