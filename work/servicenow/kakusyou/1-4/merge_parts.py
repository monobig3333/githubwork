#!/usr/bin/env python3
"""1-4 の分割実行（バッチ）結果を 1 つの result_1_4.json に統合する

前提:
  各バッチを PERF_BATCH_LABEL 付きで実行し、
  1-4/parts/result_1_4_<label>.json が出力されていること。

    PERF_BATCH_LABEL=part1 PERF_INDEX_OFFSET=0   PERF_TICKET_COUNT=200 pytest 1-4/ -v -s
    PERF_BATCH_LABEL=part2 PERF_INDEX_OFFSET=200 PERF_TICKET_COUNT=200 pytest 1-4/ -v -s
    ...

使い方:
    python3 1-4/merge_parts.py                 # 統合して result_1_4.json を作成
    python3 1-4/merge_parts.py --dry-run       # 集計結果の表示のみ
    python3 1-4/merge_parts.py --target 1000   # 目標件数を指定（既定 1000）
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARTS_DIR = HERE / "parts"
OUT_PATH = HERE / "result_1_4.json"


def summarize(samples: list[float]) -> dict:
    if not samples:
        return {"count": 0}
    arr = sorted(samples)
    return {
        "count": len(arr),
        "min": arr[0],
        "max": arr[-1],
        "avg": statistics.mean(arr),
        "median": statistics.median(arr),
        "p95": arr[int(len(arr) * 0.95) - 1] if len(arr) >= 20 else arr[-1],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="1-4 のバッチ結果を統合")
    ap.add_argument("--target", type=int, default=1000, help="目標起票件数（既定 1000）")
    ap.add_argument("--dry-run", action="store_true", help="ファイルを書かず結果表示のみ")
    args = ap.parse_args()

    if not PARTS_DIR.exists():
        sys.exit(f"{PARTS_DIR} がありません。バッチを PERF_BATCH_LABEL 付きで実行してください")

    files = sorted(PARTS_DIR.glob("result_1_4_*.json"))
    if not files:
        sys.exit(f"{PARTS_DIR} にバッチ結果がありません")

    parts = []
    all_numbers: list[str] = []
    all_samples: list[float] = []
    success = failed = attempted = 0
    elapsed = 0.0
    aborted = []

    print(f"統合対象 {len(files)} ファイル")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        label = d.get("batch_label") or f.stem
        nums = d.get("created_numbers") or []
        smp = d.get("samples") or []
        success += d.get("success", 0)
        failed += d.get("failed", 0)
        attempted += d.get("attempted", 0)
        elapsed += d.get("elapsed_total_sec", 0.0)
        all_numbers += nums
        all_samples += smp
        if d.get("aborted_at"):
            aborted.append({"batch": label, "aborted_at": d["aborted_at"]})
        parts.append({
            "batch_label": label,
            "file": f.name,
            "index_offset": d.get("index_offset"),
            "attempted": d.get("attempted"),
            "success": d.get("success"),
            "failed": d.get("failed"),
            "elapsed_total_sec": d.get("elapsed_total_sec"),
            "aborted_at": d.get("aborted_at"),
        })
        print(f"  {label:<10} success={d.get('success'):>4} failed={d.get('failed'):>4} "
              f"numbers={len(nums):>4} {'*中断*' if d.get('aborted_at') else ''}")

    duplicates = len(all_numbers) - len(set(all_numbers))
    stats = summarize(all_samples)

    result = {
        "target_count": args.target,
        "attempted": attempted,
        "success": success,
        "failed": failed,
        "duplicates": duplicates,
        "elapsed_total_sec": elapsed,
        "per_ticket_stats": stats,
        "smoke": False,
        "merged_from_batches": True,
        "batch_count": len(parts),
        "batches": parts,
        "aborted_batches": aborted,
        "created_numbers": all_numbers[:20],
        "created_numbers_total": len(all_numbers),
    }

    print()
    print("=" * 56)
    print(f" 目標        : {args.target} 件")
    print(f" 試行        : {attempted} 件")
    print(f" 成功        : {success} 件")
    print(f" 失敗        : {failed} 件")
    print(f" 重複        : {duplicates} 件")
    if stats.get("count"):
        print(f" 1件あたり   : avg {stats['avg']:.3f}s / median {stats['median']:.3f}s / max {stats['max']:.3f}s")
    print(f" 合計所要    : {elapsed/60:.1f} 分")
    if aborted:
        print(f" ⚠ 中断バッチ: {aborted}")
    print("=" * 56)

    judged_ok = (success == args.target and duplicates == 0 and not aborted)
    print(f" 判定: {'OK（全件成功・重複なし）' if judged_ok else 'NG または未達'}")
    result["judgement"] = "OK" if judged_ok else "NG"

    if args.dry_run:
        print("\n--dry-run のため result_1_4.json は更新していません")
        return 0

    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n書き出し: {OUT_PATH}")
    return 0 if judged_ok else 1


if __name__ == "__main__":
    sys.exit(main())
