#!/usr/bin/env bash
#
# 要件M-4: MIDサーバ高負荷時リソース使用率確認
#
# 3AZの全MIDサーバ（.env の MID_HOSTS）でCPU/メモリ/スレッド数を並行計測し、
# 1ホスト1ファイルでログを保存する。
#
# 合否基準:
#   - CPU使用率 80%以下
#   - メモリ使用率 90%以下
#   - スレッド数が上限に達しない（jstat / ps -L）
#
# 実行:
#   bash M-4/monitor_m_4_resources.sh [duration_sec]
#

set -euo pipefail

DURATION="${1:-600}"
INTERVAL=5
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# .env から MID_HOSTS, MID_SSH_USER, MID_SSH_KEY を読み込み
if [ -f "$ROOT_DIR/.env" ]; then
  set -a; source "$ROOT_DIR/.env"; set +a
fi

IFS=',' read -ra HOSTS <<<"${MID_HOSTS:-}"
SSH_USER="${MID_SSH_USER:-midserver}"
SSH_KEY="${MID_SSH_KEY:-~/.ssh/id_rsa}"

if [ ${#HOSTS[@]} -eq 0 ]; then
  echo "ERROR: MID_HOSTS が未設定です。 .env を確認してください。"
  exit 1
fi

monitor_host() {
  local host="$1"
  local logfile="$LOG_DIR/${host//\//_}.log"
  echo "ts,host,cpu_pct,mem_used_kb,mem_total_kb,mem_pct,thread_count,load1,load5,load15" > "$logfile"

  local end=$(( $(date +%s) + DURATION ))
  while [ "$(date +%s)" -lt "$end" ]; do
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "${SSH_USER}@${host}" '
      ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      cpu=$(top -bn1 | awk "/Cpu\\(s\\)/ {print 100 - \$8}")
      mem_used=$(free | awk "/^Mem:/ {print \$3}")
      mem_total=$(free | awk "/^Mem:/ {print \$2}")
      mem_pct=$(awk "BEGIN{printf \"%.1f\", $mem_used/$mem_total*100}")
      threads=$(ps -eLf | grep -E "java|mid" | grep -v grep | wc -l)
      load=$(uptime | awk -F"load average:" "{print \$2}" | tr -d , )
      load1=$(echo "$load" | awk "{print \$1}")
      load5=$(echo "$load" | awk "{print \$2}")
      load15=$(echo "$load" | awk "{print \$3}")
      echo "${ts},'"$host"',${cpu},${mem_used},${mem_total},${mem_pct},${threads},${load1},${load5},${load15}"
    ' >> "$logfile" 2>/dev/null || echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$host,ERROR,,,,,,," >> "$logfile"
    sleep "$INTERVAL"
  done
}

PIDS=()
for h in "${HOSTS[@]}"; do
  monitor_host "$h" &
  PIDS+=($!)
  echo "Started monitoring $h (pid=$!)"
done

trap "echo 'Stopping...'; for p in ${PIDS[*]}; do kill \$p 2>/dev/null; done" INT TERM

for p in "${PIDS[@]}"; do wait "$p"; done

echo "=== Monitoring finished ==="
echo "Logs:"
ls -la "$LOG_DIR/"

# 簡易閾値判定
echo ""
echo "=== Threshold check (CPU<=80%, MEM<=90%) ==="
for logfile in "$LOG_DIR"/*.log; do
  host=$(basename "$logfile" .log)
  max_cpu=$(awk -F, 'NR>1 && $3!="ERROR" {if ($3+0 > m) m=$3+0} END {print m+0}' "$logfile")
  max_mem=$(awk -F, 'NR>1 && $6!="" {if ($6+0 > m) m=$6+0} END {print m+0}' "$logfile")
  status="OK"
  if (( $(echo "$max_cpu > 80" | bc -l 2>/dev/null) )); then status="NG(CPU)"; fi
  if (( $(echo "$max_mem > 90" | bc -l 2>/dev/null) )); then status="${status}/NG(MEM)"; fi
  printf "%-30s max_cpu=%.1f%% max_mem=%.1f%% %s\n" "$host" "$max_cpu" "$max_mem" "$status"
done
