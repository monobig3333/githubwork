"""要件M-4 ローカル計測 集計

各 MID サーバで monitor_local.sh を実行して取得した CSV を集めて、
3 台分の最大値・平均値を一覧化し、合否を出す。

使い方:
    # MID サーバから手元へ CSV を回収後
    python3 M-4/aggregate.py M-4/*.csv

    # 閾値を上書き
    python3 M-4/aggregate.py --cpu 80 --mem 90 M-4/*.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean


def analyze_file(path: Path) -> dict:
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    if not rows:
        return {"host": path.stem, "samples": 0}
    host = rows[0].get("host", path.stem)
    cpu_vals = [float(r["cpu_pct"]) for r in rows if r.get("cpu_pct") not in ("", "ERROR", None)]
    mem_vals = [float(r["mem_pct"]) for r in rows if r.get("mem_pct") not in ("", "ERROR", None)]
    mid_cpu_vals = [float(r["mid_cpu_pct"] or 0) for r in rows]
    mid_thr_vals = [int(r["mid_threads"] or 0) for r in rows]
    load1 = [float(r["load1"] or 0) for r in rows]
    return {
        "host": host,
        "file": str(path),
        "samples": len(rows),
        "start": rows[0]["ts"],
        "end": rows[-1]["ts"],
        "cpu_avg": mean(cpu_vals) if cpu_vals else 0,
        "cpu_max": max(cpu_vals) if cpu_vals else 0,
        "mem_avg": mean(mem_vals) if mem_vals else 0,
        "mem_max": max(mem_vals) if mem_vals else 0,
        "load1_max": max(load1) if load1 else 0,
        "mid_cpu_max": max(mid_cpu_vals) if mid_cpu_vals else 0,
        "mid_threads_max": max(mid_thr_vals) if mid_thr_vals else 0,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("csvs", nargs="+", help="monitor_local.sh が出力した CSV ファイル")
    p.add_argument("--cpu", type=float, default=80.0)
    p.add_argument("--mem", type=float, default=90.0)
    p.add_argument("--json", action="store_true", help="JSON で詳細を出力")
    args = p.parse_args()

    results = []
    for path_str in args.csvs:
        path = Path(path_str)
        if not path.exists():
            print(f"WARN: {path} not found", file=sys.stderr)
            continue
        results.append(analyze_file(path))

    if not results:
        print("ERROR: 解析対象が無し", file=sys.stderr)
        return 1

    print(f"{'host':<24} {'samples':>7}  {'cpu_avg':>7}  {'cpu_max':>7}  "
          f"{'mem_avg':>7}  {'mem_max':>7}  {'load1':>6}  {'mid_thr':>7}  status")
    print("-" * 110)
    overall_ok = True
    for r in results:
        cpu_ng = r["cpu_max"] > args.cpu
        mem_ng = r["mem_max"] > args.mem
        status = "OK"
        if cpu_ng or mem_ng:
            status = "NG(" + ",".join(
                x for x, b in [("CPU", cpu_ng), ("MEM", mem_ng)] if b
            ) + ")"
            overall_ok = False
        print(f"{r['host']:<24} {r['samples']:>7}  "
              f"{r['cpu_avg']:>6.1f}%  {r['cpu_max']:>6.1f}%  "
              f"{r['mem_avg']:>6.1f}%  {r['mem_max']:>6.1f}%  "
              f"{r['load1_max']:>6.2f}  {r['mid_threads_max']:>7}  {status}")

    print()
    print(f"閾値        : CPU <= {args.cpu}%   MEM <= {args.mem}%")
    print(f"全体判定    : {'OK' if overall_ok else 'NG'}")

    if args.json:
        print()
        print(json.dumps({
            "thresholds": {"cpu_pct": args.cpu, "mem_pct": args.mem},
            "overall": "OK" if overall_ok else "NG",
            "hosts": results,
        }, indent=2, ensure_ascii=False))

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
