#!/usr/bin/env python3
"""Zabbix サーバ上で実行する高速イベント投入スクリプト（2-2 / 2-4-5 / 2-6 用）

従来の on.py は 1 イベントごとに zabbix_sender プロセスを起動していたため、
プロセス生成のオーバーヘッドで実効 12.5 件/秒しか出ず、要件の 50 件/秒
(30,000 件 / 10 分) を満たせなかった（2026/8/19 実測）。

本スクリプトは zabbix_sender の `-i -`（標準入力から一括送信）を使い、
1 秒ごとに RATE 件をまとめて 1 プロセスで送ることで目標レートを達成する。

    1 秒目: host-00001 .. host-00050  を 1 回の zabbix_sender で送信
    2 秒目: host-00051 .. host-00100
    ...

■ 使い方（Zabbix サーバ上で実行）

    # 30,000 件を 50 件/秒で（= 10 分）
    python3 send_bulk.py --count 30000 --rate 50

    # 動作確認（10 件・実送信あり）
    python3 send_bulk.py --count 10 --rate 5

    # 送信せず生成内容だけ確認
    python3 send_bulk.py --count 10 --dry-run

    # 範囲を指定して再送（前回 12000 件目で止まった場合など）
    python3 send_bulk.py --start 12001 --count 18000 --rate 50

    # 結果を JSON で保存
    python3 send_bulk.py --count 30000 --rate 50 --json /tmp/send_bulk_result.json

■ 出力

    [  60s]  3,000/30,000 ( 10.0%)  送信 3000 / 失敗 0   実効 50.0/s  残り 9:00

    最後にサマリ（総送信数・失敗数・所要時間・実効レート）を表示する。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime

DEFAULT_SERVER = "localhost"
DEFAULT_KEY = "test-hyoka"
DEFAULT_VALUE = "1"
DEFAULT_PREFIX = "test-servicenow-monohyouka-"
DEFAULT_WIDTH = 5

# zabbix_sender の出力例:
#   info from server: "processed: 50; failed: 0; total: 50; seconds spent: 0.000221"
_STAT = re.compile(r"processed:\s*(\d+);\s*failed:\s*(\d+);\s*total:\s*(\d+)")


def fmt_dur(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def send_chunk(sender: str, server: str, port: int, lines: list[str],
               timeout: int) -> tuple[int, int, str]:
    """1 チャンクを zabbix_sender に標準入力で渡す。(processed, failed, raw) を返す"""
    payload = "\n".join(lines) + "\n"
    cmd = [sender, "-z", server, "-p", str(port), "-i", "-"]
    try:
        r = subprocess.run(cmd, input=payload, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 0, len(lines), "TIMEOUT"
    out = (r.stdout or "") + (r.stderr or "")
    m = _STAT.search(out)
    if m:
        return int(m.group(1)), int(m.group(2)), out.strip()
    # statistics 行が取れない場合は全件失敗扱い（原因を raw に残す）
    return 0, len(lines), out.strip()[:300]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="zabbix_sender 一括送信によるイベント投入",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=30000, help="送信件数 (既定 30000)")
    ap.add_argument("--start", type=int, default=1, help="開始ホスト番号 (既定 1)")
    ap.add_argument("--rate", type=int, default=50, help="1 秒あたりの件数 (既定 50)")
    ap.add_argument("--server", default=DEFAULT_SERVER, help="Zabbix server (既定 localhost)")
    ap.add_argument("--port", type=int, default=10051)
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--value", default=DEFAULT_VALUE)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="ホスト番号の桁数 (既定 5)")
    ap.add_argument("--sender", default="zabbix_sender", help="zabbix_sender のパス")
    ap.add_argument("--timeout", type=int, default=30, help="1 チャンクのタイムアウト秒")
    ap.add_argument("--progress", type=int, default=30, help="進捗表示の間隔・秒 (既定 30)")
    ap.add_argument("--json", default="", help="結果を JSON で保存するパス")
    ap.add_argument("--dry-run", action="store_true", help="送信せず生成内容を表示")
    args = ap.parse_args()

    if args.rate < 1:
        sys.exit("--rate は 1 以上を指定してください")

    end = args.start + args.count - 1
    hosts = [f"{args.prefix}{i:0{args.width}d}" for i in range(args.start, end + 1)]
    chunks = [hosts[i:i + args.rate] for i in range(0, len(hosts), args.rate)]
    est = len(chunks)

    print("=" * 70)
    print(" zabbix_sender 一括送信")
    print(f"  対象     : {hosts[0]} 〜 {hosts[-1]}  ({len(hosts):,} 件)")
    print(f"  key/value: {args.key} = {args.value}")
    print(f"  レート   : {args.rate} 件/秒  → 想定 {fmt_dur(est)} ({est} チャンク)")
    print(f"  送信先   : {args.server}:{args.port}")
    print("=" * 70)

    if args.dry_run:
        print("\n[dry-run] 最初のチャンクの内容:")
        for line in [f"{h} {args.key} {args.value}" for h in chunks[0][:5]]:
            print("   ", line)
        if len(chunks[0]) > 5:
            print(f"    ... 他 {len(chunks[0])-5} 行")
        print(f"\n[dry-run] チャンク数 {est}、送信は行いませんでした")
        return 0

    total_proc = total_fail = 0
    errors: list[str] = []
    t0 = time.time()
    last_report = t0

    try:
        for idx, chunk in enumerate(chunks):
            target = t0 + idx  # 1 チャンク = 1 秒（絶対時刻でドリフトを防ぐ）
            lines = [f"{h} {args.key} {args.value}" for h in chunk]
            proc, fail, raw = send_chunk(args.sender, args.server, args.port,
                                         lines, args.timeout)
            total_proc += proc
            total_fail += fail
            if fail and len(errors) < 5:
                errors.append(f"chunk#{idx+1} ({chunk[0]}..): {raw[:200]}")

            now = time.time()
            if now - last_report >= args.progress or idx == len(chunks) - 1:
                sent = total_proc + total_fail
                el = now - t0
                pct = sent / len(hosts) * 100
                eff = sent / el if el > 0 else 0
                remain = (len(hosts) - sent) / eff if eff > 0 else 0
                print(f"[{el:5.0f}s] {sent:>7,}/{len(hosts):,} ({pct:5.1f}%)  "
                      f"送信 {total_proc:,} / 失敗 {total_fail:,}   "
                      f"実効 {eff:.1f}/s  残り {fmt_dur(remain)}")
                last_report = now

            sleep = target + 1 - time.time()
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        print("\n中断しました")

    elapsed = time.time() - t0
    sent = total_proc + total_fail
    eff = sent / elapsed if elapsed > 0 else 0

    print("\n" + "=" * 70)
    print(f"  送信試行 : {sent:,} 件")
    print(f"  成功     : {total_proc:,} 件")
    print(f"  失敗     : {total_fail:,} 件")
    print(f"  所要     : {fmt_dur(elapsed)} ({elapsed:.1f} 秒)")
    print(f"  実効     : {eff:.1f} 件/秒  (目標 {args.rate} 件/秒)")
    if elapsed <= 600 and total_proc >= 30000:
        print("  → 30,000 件 / 10 分の投入条件を満たしています")
    print("=" * 70)
    if errors:
        print("\n失敗の例:")
        for e in errors:
            print("  ", e)
        print("\n  failed が多い場合はホストまたはアイテム(key)の存在を確認してください:")
        print(f"    zabbix_sender -z {args.server} -s \"{hosts[0]}\" -k {args.key} -o {args.value}")

    if args.json:
        result = {
            "method": "zabbix_sender -i - (batch)",
            "host_range": [hosts[0], hosts[-1]],
            "requested": len(hosts),
            "attempted": sent,
            "processed": total_proc,
            "failed": total_fail,
            "elapsed_sec": round(elapsed, 1),
            "effective_rps": round(eff, 2),
            "target_rps": args.rate,
            "started_at": datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "errors_sample": errors,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n保存: {args.json}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
