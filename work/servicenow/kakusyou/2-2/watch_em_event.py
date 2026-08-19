#!/usr/bin/env python3
"""2-2: ServiceNow 側の em_event 到達件数を定期的に監視する

Zabbix サーバから投入している間、Mac 側で流しっぱなしにして到達状況を追う。

  - 一定間隔で件数をカウントし、増分・実効レート・ETA を表示
  - OAuth トークンは自動で再取得（長時間実行対応）
  - Ctrl-C で停止時にサマリを表示
  - --csv で時系列ログをファイルに残せる

使い方:
    python3 2-2/watch_em_event.py                      # 30 秒間隔・目標 30000
    python3 2-2/watch_em_event.py --interval 15
    python3 2-2/watch_em_event.py --target 3000
    python3 2-2/watch_em_event.py --once               # 1 回だけ表示して終了
    python3 2-2/watch_em_event.py --csv 2-2/watch.csv
    python3 2-2/watch_em_event.py --node-prefix test-servicenow-monohyouka
    python3 2-2/watch_em_event.py --stop-after-idle 5  # 5 回連続で増加なしなら終了
"""
from __future__ import annotations

import argparse
import csv as csvmod
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent

try:
    import requests
except ImportError:
    sys.exit("requests が未導入です: pip install requests")

try:
    from dotenv import load_dotenv
    if (ROOT / ".env").exists():
        load_dotenv(ROOT / ".env")
except ImportError:
    pass

DEFAULT_PREFIX = "test-servicenow-monohyouka"
TOKEN_TTL_SEC = 20 * 60  # 実際は 30 分だが余裕を持って再取得


def _jmeter_props() -> dict:
    p = ROOT / "jmeter.properties"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


class Snow:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        props = _jmeter_props()
        self.cid = os.getenv("SNOW_CLIENT_ID") or props.get("snow.client_id", "")
        self.sec = os.getenv("SNOW_CLIENT_SECRET") or props.get("snow.client_secret", "")
        if not self.cid or not self.sec:
            sys.exit("OAuth の client_id / secret が見つかりません "
                     "(.env または jmeter.properties)")
        self._token = ""
        self._token_at = 0.0

    def token(self) -> str:
        if self._token and time.time() - self._token_at < TOKEN_TTL_SEC:
            return self._token
        r = requests.post(f"{self.base}/oauth_token.do", auth=(self.cid, self.sec),
                          data={"grant_type": "client_credentials"}, timeout=30)
        r.raise_for_status()
        self._token = r.json()["access_token"]
        self._token_at = time.time()
        return self._token

    def count(self, query: str) -> int:
        for attempt in (1, 2):
            r = requests.get(
                f"{self.base}/api/now/stats/em_event",
                headers={"Authorization": f"Bearer {self.token()}",
                         "Accept": "application/json"},
                params={"sysparm_count": "true", "sysparm_query": query},
                timeout=60,
            )
            if r.status_code == 401 and attempt == 1:
                self._token = ""       # 失効とみなして再取得
                continue
            r.raise_for_status()
            return int(r.json()["result"]["stats"]["count"])
        return -1

    def latest(self, query: str, limit: int = 3) -> list[dict]:
        r = requests.get(
            f"{self.base}/api/now/table/em_event",
            headers={"Authorization": f"Bearer {self.token()}",
                     "Accept": "application/json"},
            params={"sysparm_query": f"{query}^ORDERBYDESCsys_created_on",
                    "sysparm_fields": "node,source,type,sys_created_on",
                    "sysparm_limit": str(limit)},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("result", [])


def fmt_dur(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="em_event 到達件数のモニタ")
    ap.add_argument("--interval", type=int, default=30, help="ポーリング間隔・秒 (既定 30)")
    ap.add_argument("--target", type=int, default=30000, help="目標件数 (既定 30000)")
    ap.add_argument("--node-prefix", default=DEFAULT_PREFIX, help="node の前方一致条件")
    ap.add_argument("--query", default="", help="sysparm_query を直接指定（--node-prefix より優先）")
    ap.add_argument("--baseline", type=int, default=None,
                    help="投入前の件数。省略時は初回取得値を 0 起点として扱う")
    ap.add_argument("--once", action="store_true", help="1 回だけ表示して終了")
    ap.add_argument("--csv", default="", help="時系列を CSV に追記")
    ap.add_argument("--stop-after-idle", type=int, default=0,
                    help="N 回連続で増加が無ければ終了 (0 で無効)")
    ap.add_argument("--base-url", default=os.getenv(
        "SNOW_BASE_URL", "https://biglobedev.service-now.com"))
    ap.add_argument("--hours-ago", type=int, default=0,
                    help="直近 N 時間に登録された分のみ数える（過去分と分離できる）")
    args = ap.parse_args()

    query = args.query or f"nodeSTARTSWITH{args.node_prefix}"
    if args.hours_ago:
        query += f"^sys_created_on>=javascript:gs.hoursAgoStart({args.hours_ago})"
    snow = Snow(args.base_url)

    print("=" * 72)
    print(f" em_event モニタ   {args.base_url.replace('https://','')}")
    print(f" 条件   : {query}")
    print(f" 目標   : {args.target:,} 件   間隔: {args.interval} 秒")
    print("=" * 72)

    first = snow.count(query)
    baseline = args.baseline if args.baseline is not None else first
    t0 = time.time()
    print(f"[{datetime.now():%H:%M:%S}] ベースライン {baseline:,} 件 (現在 {first:,} 件)")

    if args.once:
        got = first - baseline
        print(f"到達 {got:,} / {args.target:,} 件")
        return 0

    writer = None
    fh = None
    if args.csv:
        newfile = not Path(args.csv).exists()
        fh = open(args.csv, "a", newline="", encoding="utf-8")
        writer = csvmod.writer(fh)
        if newfile:
            writer.writerow(["timestamp", "elapsed_sec", "count", "received", "delta", "rate_per_sec"])

    prev = first
    prev_t = t0
    idle = 0
    peak_rate = 0.0
    try:
        while True:
            time.sleep(args.interval)
            now = time.time()
            cur = snow.count(query)
            delta = cur - prev
            dt = now - prev_t
            rate = delta / dt if dt > 0 else 0.0
            peak_rate = max(peak_rate, rate)
            received = cur - baseline
            elapsed = now - t0
            avg_rate = received / elapsed if elapsed > 0 else 0.0

            remain = args.target - received
            if remain > 0 and rate > 0.05:
                eta = fmt_dur(remain / rate)
            elif remain <= 0:
                eta = "達成"
            else:
                eta = "—"

            pct = received / args.target * 100 if args.target else 0
            bar_n = int(pct / 5)
            bar = "#" * min(bar_n, 20) + "." * max(0, 20 - bar_n)

            print(f"[{datetime.now():%H:%M:%S}] {received:>7,}/{args.target:,} "
                  f"[{bar}] {pct:5.1f}%  +{delta:<5,} "
                  f"{rate:5.1f}/s (平均 {avg_rate:4.1f}/s)  経過 {fmt_dur(elapsed)}  ETA {eta}")

            if writer:
                writer.writerow([datetime.now().isoformat(timespec="seconds"),
                                 round(elapsed, 1), cur, received, delta, round(rate, 2)])
                fh.flush()

            if delta == 0:
                idle += 1
                if args.stop_after_idle and idle >= args.stop_after_idle:
                    print(f"\n{idle} 回連続で増加が無いため終了します")
                    break
            else:
                idle = 0

            prev, prev_t = cur, now
    except KeyboardInterrupt:
        print("\n中断しました")
    finally:
        if fh:
            fh.close()

    total = snow.count(query) - baseline
    elapsed = time.time() - t0
    print("\n" + "=" * 72)
    print(f" 到達合計   : {total:,} / {args.target:,} 件 ({total/args.target*100:.1f}%)"
          if args.target else f" 到達合計   : {total:,} 件")
    print(f" 監視時間   : {fmt_dur(elapsed)}")
    print(f" 平均レート : {total/elapsed:.1f} 件/秒" if elapsed > 0 else "")
    print(f" ピーク     : {peak_rate:.1f} 件/秒")
    if total < args.target:
        print(f" 不足       : {args.target - total:,} 件")
    print("=" * 72)

    try:
        rows = snow.latest(query)
        if rows:
            print(" 直近のイベント:")
            for r in rows:
                print(f"   {r.get('sys_created_on')}  node={r.get('node')}  "
                      f"source={r.get('source')}  type={r.get('type')}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
