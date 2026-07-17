#!/usr/bin/env bash
#
# N-2: CPU 高負荷の発生 (MID サーバ上でローカル実行)
#
# busy-loop プロセスを CPU 数 (または指定数) だけ起動し CPU を 100% に張り付ける。
#
# 使い方:
#   bash stress_cpu.sh           # 既定 600 秒 / nproc 個
#   bash stress_cpu.sh 1800
#   CPUS=4 bash stress_cpu.sh 600
#
set -uo pipefail

DURATION="${1:-600}"
CPUS="${CPUS:-$(nproc 2>/dev/null || echo 2)}"
PIDS=()

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
  echo "Done"
}
trap cleanup EXIT INT TERM

echo "N-2 CPU stress"
echo "  duration : ${DURATION}s"
echo "  workers  : $CPUS  (vCPU)"
echo

for i in $(seq 1 "$CPUS"); do
  (
    # busy loop in awk to avoid heavy fork in shell
    awk 'BEGIN{ while(1) {x++} }'
  ) &
  PIDS+=($!)
  echo "  worker[$i] pid=${PIDS[-1]}"
done

echo
echo "Sleeping ${DURATION}s. Ctrl-C で停止可。"
sleep "$DURATION"
