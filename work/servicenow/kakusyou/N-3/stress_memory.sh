#!/usr/bin/env bash
#
# N-3: メモリ高負荷の発生 (MID サーバ上でローカル実行)
#
# Python で大容量 bytearray を確保しメモリ不足状態を起こす。
# MID Server の Java Max ヒープ (既定 4096MB) と OS バッファを残し、
# 残りを圧迫する設計。
#
# OOM Killer に MID Server プロセスが選ばれないよう、本スクリプトの
# oom_score_adj を上げて自分が真っ先に殺されるようにする。
#
# 使い方:
#   bash stress_memory.sh                       # 既定 600s, 残り (Total - 4096MB - 512MB) を確保
#   bash stress_memory.sh 1800
#   MB=2048 bash stress_memory.sh 600           # 直接 MB 指定
#   PCT=70 bash stress_memory.sh 600            # メモリ全体の % 指定 (旧モード)
#   MID_MAX_MB=4096 OS_BUFFER_MB=512 bash stress_memory.sh 600
#
# 環境変数:
#   MB             固定 MB 値で指定 (最優先)
#   PCT            メモリ全体に対する % (MB 未指定時の旧モード)
#   MID_MAX_MB     MID Server Java の最大ヒープ MB (既定 4096)
#   OS_BUFFER_MB   OS および他プロセス用に残す MB (既定 512)
#
# 算出ロジック (MB 未指定時):
#   MB = MemTotal - MID_MAX_MB - OS_BUFFER_MB
#   ※ PCT が指定されていればそちらを優先 (上限は MemTotal - 100MB)
#
set -uo pipefail

DURATION="${1:-600}"
MB="${MB:-}"
PCT="${PCT:-}"
MID_MAX_MB="${MID_MAX_MB:-4096}"
OS_BUFFER_MB="${OS_BUFFER_MB:-512}"

MEM_TOTAL_KB=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
MEM_TOTAL_MB=$(( MEM_TOTAL_KB / 1024 ))

if [ -z "$MB" ]; then
  if [ -n "$PCT" ]; then
    MB=$(( MEM_TOTAL_MB * PCT / 100 ))
    SOURCE="PCT=${PCT}% of ${MEM_TOTAL_MB}MB"
  else
    MB=$(( MEM_TOTAL_MB - MID_MAX_MB - OS_BUFFER_MB ))
    SOURCE="Total ${MEM_TOTAL_MB} - MID_MAX_MB ${MID_MAX_MB} - OS_BUFFER_MB ${OS_BUFFER_MB}"
  fi
fi

# Safety floor
if [ "$MB" -lt 100 ]; then
  echo "WARN: 計算結果 ${MB}MB が小さすぎる。MID/OS 用空き不足の可能性。100MB に切り上げ。"
  MB=100
  SOURCE="$SOURCE (clamped to 100)"
fi

PID=

cleanup() {
  echo
  echo "Cleaning up..."
  if [ -n "${PID:-}" ]; then
    kill -TERM "$PID" 2>/dev/null || true
    sleep 1
    kill -KILL "$PID" 2>/dev/null || true
  fi
  echo "Done"
}
trap cleanup EXIT INT TERM

echo "N-3 Memory stress"
echo "  duration       : ${DURATION}s"
echo "  MemTotal       : ${MEM_TOTAL_MB} MB"
echo "  reserved       : MID_MAX_MB=${MID_MAX_MB}  OS_BUFFER_MB=${OS_BUFFER_MB}"
echo "  target_mb      : ${MB} MB  (${SOURCE})"
echo

python3 <<PY &
import os, sys, time
# OOM Killer 優先度を上げる (自分が先に殺される)
try:
    with open(f"/proc/{os.getpid()}/oom_score_adj", "w") as f:
        f.write("1000")
except Exception as e:
    print(f"oom_score_adj set failed: {e}", file=sys.stderr)

mb = $MB
chunks = []
print(f"[N-3] PID={os.getpid()} allocating up to {mb} MB", flush=True)
for i in range(mb):
    try:
        chunks.append(bytearray(1024 * 1024))
    except MemoryError:
        print(f"[N-3] MemoryError at {i} MB", flush=True)
        break
    if (i+1) % 100 == 0:
        print(f"[N-3] allocated {i+1} MB", flush=True)

print(f"[N-3] holding {len(chunks)} MB for {$DURATION}s", flush=True)
time.sleep($DURATION)
PY
PID=$!
echo "  pid=$PID"
wait "$PID" 2>/dev/null || true
