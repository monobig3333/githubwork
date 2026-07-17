#!/usr/bin/env bash
#
# 要件M-4: MIDサーバ高負荷時リソース使用率確認（ローカル実行版）
#
# 各 MID サーバ上で直接実行し、CPU/メモリ/スレッド数/Load を一定間隔で記録する。
# SSH 不要。3 AZ ある場合は 3 台それぞれで同じ時間帯に実行する。
#
# 合否基準:
#   - CPU 使用率 80% 以下
#   - メモリ使用率 90% 以下
#   - スレッド数が極端に増加しないこと（参考値）
#
# 使い方（MID サーバ上で実行）:
#   bash monitor_local.sh                 # 既定 600 秒 (10 分)
#   bash monitor_local.sh 1800            # 30 分
#   DURATION=600 INTERVAL=5 bash monitor_local.sh
#
# 出力:
#   ./M-4_<hostname>_<UTC_TS>.csv         # メトリクス時系列
#   ./M-4_<hostname>_<UTC_TS>.summary.txt # 最大値・合否判定
#
# 依存: bash, awk, top, free (or /proc/meminfo), ps, uptime
#       MID プロセスの自動検出には pgrep を使う（無くても継続）。

set -uo pipefail

DURATION="${1:-${DURATION:-600}}"
INTERVAL="${INTERVAL:-5}"
CPU_THRESHOLD="${CPU_THRESHOLD:-80}"
MEM_THRESHOLD="${MEM_THRESHOLD:-90}"

HOST="$(hostname -s 2>/dev/null || hostname)"
TS_FILE="$(date -u +%Y%m%dT%H%M%SZ)"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUT_CSV="${SCRIPT_DIR}/M-4_${HOST}_${TS_FILE}.csv"
OUT_SUM="${SCRIPT_DIR}/M-4_${HOST}_${TS_FILE}.summary.txt"

# ---------- 関数 ----------
get_cpu_pct() {
  # 直近 1 秒 のシステム全体 CPU 利用率（user+sys+wait）= 100 - %idle
  # top -bn1 でも取得可能だが軽量化のため /proc/stat 差分でも近い値が出る
  awk -v RS='' '/^cpu / {
    u=$2+$3; n=$4; s=$5; i=$6; w=$7; irq=$8; sirq=$9; st=$10
    total=u+n+s+i+w+irq+sirq+st
    busy=total-i
    printf "%.1f\n", (total>0 ? busy/total*100 : 0)
  }' /proc/stat
}

get_cpu_pct_topfallback() {
  # /proc/stat を 1 サンプルだけ読むと起動からの累計になるため、
  # top -bn1 の Cpu(s) 行から %idle を引き算する方が瞬間値に近い
  top -bn1 2>/dev/null | awk '
    /Cpu\(s\)/ {
      # locale により表記が異なるため id ラベルで検索
      for (i=1; i<=NF; i++) if ($i ~ /id,?$/) idle=$(i-1)
      gsub(",", ".", idle)
      printf "%.1f\n", 100 - idle
      exit
    }
  '
}

get_mem() {
  # /proc/meminfo から MemTotal, MemAvailable を取って利用率を計算
  awk '
    /^MemTotal:/   {total=$2}
    /^MemAvailable:/ {avail=$2}
    END {
      used=total-avail
      pct=(total>0 ? used/total*100 : 0)
      printf "%d,%d,%.1f\n", used, total, pct
    }
  ' /proc/meminfo
}

get_load() {
  uptime | awk -F'load average:' '{print $2}' \
         | tr -d ',' \
         | awk '{printf "%s,%s,%s\n", $1, $2, $3}'
}

get_mid_proc_stats() {
  # MID Server のメイン Java プロセスを wrapper の親PID から推定
  # 取得失敗時は空欄でログ続行
  local pid pid_threads pid_cpu pid_rss
  pid="$(pgrep -fa 'wrapper\|MIDServer\|com.glide' 2>/dev/null | grep -i 'mid\|servicenow' | awk '{print $1}' | head -n1)"
  if [ -z "${pid:-}" ]; then
    pid="$(pgrep -a java 2>/dev/null | head -n1 | awk '{print $1}')"
  fi
  if [ -n "${pid:-}" ] && [ -d "/proc/$pid" ]; then
    pid_threads="$(awk '/^Threads:/{print $2}' "/proc/$pid/status")"
    pid_cpu="$(ps -p "$pid" -o %cpu= | tr -d ' ')"
    pid_rss="$(awk '/^VmRSS:/{print $2}' "/proc/$pid/status")"
    echo "${pid},${pid_cpu:-0},${pid_rss:-0},${pid_threads:-0}"
  else
    echo ",0,0,0"
  fi
}

# ---------- 計測開始 ----------
echo "Host       : $HOST"
echo "Duration   : ${DURATION}s"
echo "Interval   : ${INTERVAL}s"
echo "Thresholds : CPU<=${CPU_THRESHOLD}%  MEM<=${MEM_THRESHOLD}%"
echo "Output CSV : $OUT_CSV"
echo

echo "ts,host,cpu_pct,mem_used_kb,mem_total_kb,mem_pct,load1,load5,load15,mid_pid,mid_cpu_pct,mid_rss_kb,mid_threads" > "$OUT_CSV"

end=$(( $(date +%s) + DURATION ))
samples=0
trap 'echo "interrupted, finalizing..."; end=0' INT TERM

while [ "$(date +%s)" -lt "$end" ]; do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cpu_pct="$(get_cpu_pct_topfallback)"
  [ -z "$cpu_pct" ] && cpu_pct="$(get_cpu_pct)"
  mem_csv="$(get_mem)"
  load_csv="$(get_load)"
  mid_csv="$(get_mid_proc_stats)"
  echo "${ts},${HOST},${cpu_pct},${mem_csv},${load_csv},${mid_csv}" >> "$OUT_CSV"
  samples=$((samples+1))
  sleep "$INTERVAL"
done

# ---------- 集計 ----------
echo
echo "=== 集計 ==="
{
  echo "host         : $HOST"
  echo "samples      : $samples"
  echo "start..end   : $(head -2 "$OUT_CSV" | tail -1 | cut -d, -f1) .. $(tail -1 "$OUT_CSV" | cut -d, -f1)"

  awk -F, '
    NR==1 {next}
    $3+0 > cpu_max {cpu_max=$3+0}
    $6+0 > mem_max {mem_max=$6+0}
    $7+0 > load_max {load_max=$7+0}
    $11+0 > mid_cpu_max {mid_cpu_max=$11+0}
    $13+0 > mid_threads_max {mid_threads_max=$13+0}
    {
      cpu_sum += $3+0
      mem_sum += $6+0
      mid_cpu_sum += $11+0
      mid_threads_sum += $13+0
      cnt++
    }
    END {
      if (cnt > 0) {
        printf "cpu          : avg=%.1f%%  max=%.1f%%\n", cpu_sum/cnt, cpu_max
        printf "mem          : avg=%.1f%%  max=%.1f%%\n", mem_sum/cnt, mem_max
        printf "load1        : max=%.2f\n", load_max
        printf "mid_proc_cpu : avg=%.1f%%  max=%.1f%%\n", mid_cpu_sum/cnt, mid_cpu_max
        printf "mid_threads  : avg=%.0f   max=%.0f\n", mid_threads_sum/cnt, mid_threads_max
      } else {
        print "no samples"
      }
    }
  ' "$OUT_CSV"

  echo
  echo "=== 判定 ==="
  awk -F, -v cput="$CPU_THRESHOLD" -v memt="$MEM_THRESHOLD" '
    NR==1 {next}
    $3+0 > cput {cpu_ng=1; cpu_at=$1; cpu_v=$3}
    $6+0 > memt {mem_ng=1; mem_at=$1; mem_v=$6}
    END {
      cpu_status = cpu_ng ? "NG (peak " cpu_v "% at " cpu_at ")" : "OK"
      mem_status = mem_ng ? "NG (peak " mem_v "% at " mem_at ")" : "OK"
      printf "cpu (<=%d%%) : %s\n", cput, cpu_status
      printf "mem (<=%d%%) : %s\n", memt, mem_status
      if (!cpu_ng && !mem_ng) {
        print "result      : OK"
      } else {
        print "result      : NG"
        exit 1
      }
    }
  ' "$OUT_CSV"
} | tee "$OUT_SUM"
RC=${PIPESTATUS[1]:-0}

echo
echo "CSV     : $OUT_CSV"
echo "Summary : $OUT_SUM"
exit "$RC"
