#!/usr/bin/env bash
#
# N-1: Disk I/O 高負荷の発生 (MID サーバ上でローカル実行)
#
# 並列で dd ループを回し、書き込み + 読み出しの I/O 負荷を発生させる。
# 終了時にテンポラリファイルとプロセスをクリーンアップ。
#
# 使い方 (MID Server stg-1 上で実行):
#   bash stress_disk_io.sh                 # 既定 600 秒
#   bash stress_disk_io.sh 1800
#   PARALLEL=4 WORKDIR=/tmp bash stress_disk_io.sh 600
#
# 環境変数:
#   PARALLEL   並列ワーカー数 (既定 2)
#   WORKDIR    一時ファイル置き場 (既定 /tmp)
#   BLOCK_MB   1 回の書き込みサイズ MB (既定 512)
#
set -uo pipefail

DURATION="${1:-600}"
PARALLEL="${PARALLEL:-2}"
WORKDIR="${WORKDIR:-/tmp}"
BLOCK_MB="${BLOCK_MB:-512}"

PIDS=()
TMPFILES=()

cleanup() {
  echo
  echo "Cleaning up..."
  for p in "${PIDS[@]}"; do
    kill -TERM "$p" 2>/dev/null || true
  done
  sleep 1
  for p in "${PIDS[@]}"; do
    kill -KILL "$p" 2>/dev/null || true
  done
  for f in "${TMPFILES[@]}"; do
    rm -f "$f"
  done
  sync
  echo "Cleanup done."
}
trap cleanup EXIT INT TERM

echo "N-1 Disk I/O stress"
echo "  duration : ${DURATION}s"
echo "  parallel : $PARALLEL"
echo "  workdir  : $WORKDIR"
echo "  block_mb : $BLOCK_MB"
echo

for i in $(seq 1 "$PARALLEL"); do
  out="$WORKDIR/n1_diskio_$i.bin"
  TMPFILES+=("$out")
  (
    while true; do
      dd if=/dev/zero of="$out" bs=1M count="$BLOCK_MB" oflag=sync 2>/dev/null || true
      dd if="$out" of=/dev/null bs=1M 2>/dev/null || true
    done
  ) &
  PIDS+=($!)
  echo "  worker[$i] pid=${PIDS[-1]} -> $out"
done

echo
echo "Sleeping ${DURATION}s. Ctrl-C で停止可。"
sleep "$DURATION"
