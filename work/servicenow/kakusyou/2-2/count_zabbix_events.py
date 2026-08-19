#!/usr/bin/env python3
"""指定時間帯に Zabbix 側で生成されたイベント数を数える

ServiceNow への到達数と突き合わせることで、欠損が
  「Zabbix でイベントが生成されなかった」のか
  「生成されたがコネクタ / MID で失われた」のか
を切り分ける。

使い方:
    # 投入時間帯を指定 (JST)
    python3 2-2/count_zabbix_events.py --from "21:13" --to "21:35"

    # 日付をまたぐ場合はフル指定
    python3 2-2/count_zabbix_events.py --from "2026-08-19 21:13:00" --to "2026-08-19 21:35:00"

    # トリガーの現在状態も表示（PROBLEM のまま残っていないかの確認）
    python3 2-2/count_zabbix_events.py --from "21:13" --to "21:35" --show-problems
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    sys.exit("requests が未導入です")

try:
    from dotenv import load_dotenv
    if (ROOT / ".env").exists():
        load_dotenv(ROOT / ".env")
except ImportError:
    pass

FMT = "%Y-%m-%d %H:%M:%S"


class Zbx:
    def __init__(self):
        self.url = os.getenv("ZABBIX_URL", "")
        if not self.url:
            sys.exit("ZABBIX_URL が未設定です")
        self.verify = os.getenv("ZABBIX_VERIFY_TLS", "false").lower() in ("1", "true", "yes")
        self.token = os.getenv("ZABBIX_TOKEN", "") or self._login()

    def _login(self) -> str:
        r = self._raw("user.login", {
            "username": os.getenv("ZABBIX_USER", ""),
            "password": os.getenv("ZABBIX_PASSWORD", "")}, auth=None)
        return r

    def _raw(self, method: str, params, auth: str | None = "USE"):
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        headers = {"Content-Type": "application/json-rpc"}
        tok = self.token if auth == "USE" else auth
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
            payload["auth"] = tok
        r = requests.post(self.url, json=payload, headers=headers,
                          verify=self.verify, timeout=180)
        r.raise_for_status()
        d = r.json()
        if "error" in d:
            sys.exit(f"Zabbix API エラー: {d['error']}")
        return d["result"]

    def call(self, method: str, params):
        return self._raw(method, params)


def parse_jst(s: str) -> datetime:
    s = s.strip()
    if len(s) <= 5 and ":" in s:
        s = f"{datetime.now():%Y-%m-%d} {s}:00"
    elif s.count(":") == 1:
        s += ":00"
    return datetime.strptime(s, FMT)


def main() -> int:
    ap = argparse.ArgumentParser(description="Zabbix イベント生成数のカウント")
    ap.add_argument("--from", dest="frm", required=True, help="開始 (JST)")
    ap.add_argument("--to", dest="to", required=True, help="終了 (JST)")
    ap.add_argument("--prefix", default=os.getenv(
        "ZABBIX_HOST_PREFIX", "test-servicenow-monohyouka-"))
    ap.add_argument("--show-problems", action="store_true",
                    help="現在 PROBLEM のトリガー数も表示")
    args = ap.parse_args()

    t0, t1 = parse_jst(args.frm), parse_jst(args.to)
    z = Zbx()
    print("=" * 68)
    print(f" Zabbix イベント集計   {t0:%Y-%m-%d %H:%M:%S} 〜 {t1:%H:%M:%S} (JST)")
    print(f" 対象ホスト prefix: {args.prefix}")
    print("=" * 68)

    # 注意: searchWildcardsEnabled=true にすると "*" を明示しない限り完全一致になる。
    # 前方一致は startSearch=true を使う（2026/8/19 に誤りを修正）
    hosts = z.call("host.get", {"output": ["hostid", "host"],
                                "search": {"host": args.prefix},
                                "startSearch": True})
    print(f"\n対象ホスト数: {len(hosts):,}")
    if not hosts:
        print("  前方一致で 0 件。部分一致でも探します ...")
        hosts = z.call("host.get", {"output": ["hostid", "host"],
                                    "search": {"host": args.prefix}})
        print(f"  部分一致: {len(hosts):,} 件")
    if not hosts:
        all_hosts = z.call("host.get", {"output": ["host"], "limit": 20})
        print("\n  ホスト名の例 (先頭 20):")
        for h in all_hosts:
            print("   ", h["host"])
        sys.exit("該当ホストがありません。--prefix を実際の名前に合わせてください")
    hostids = [h["hostid"] for h in hosts]

    events = z.call("event.get", {
        "output": ["eventid", "clock", "value", "name"],
        "hostids": hostids,
        "source": 0,          # trigger
        "object": 0,
        "time_from": int(t0.timestamp()),
        "time_till": int(t1.timestamp()),
        "limit": 200000,
    })
    problems = [e for e in events if e.get("value") == "1"]
    recovers = [e for e in events if e.get("value") == "0"]

    print(f"\n期間内のイベント総数 : {len(events):,}")
    print(f"  障害 (value=1)     : {len(problems):,}")
    print(f"  復旧 (value=0)     : {len(recovers):,}")

    if problems:
        per_min = Counter(datetime.fromtimestamp(int(e["clock"])).replace(second=0)
                          for e in problems)
        peak = per_min.most_common(1)[0]
        lo = min(int(e["clock"]) for e in problems)
        hi = max(int(e["clock"]) for e in problems)
        dur = hi - lo
        print(f"\n  最初  : {datetime.fromtimestamp(lo):%H:%M:%S}")
        print(f"  最後  : {datetime.fromtimestamp(hi):%H:%M:%S}")
        print(f"  期間  : {dur/60:.1f} 分")
        print(f"  平均  : {len(problems)/dur:.1f} 件/秒" if dur else "")
        print(f"  ピーク: {peak[1]:,} 件/分 ({peak[0]:%H:%M})")

    if args.show_problems:
        cur = z.call("problem.get", {"output": ["eventid"], "hostids": hostids,
                                     "recent": False, "limit": 200000})
        print(f"\n現在 PROBLEM 状態のトリガー: {len(cur):,} 件 / ホスト {len(hosts):,}")
        if len(cur) > len(hosts) * 0.3:
            print("  ⚠️ 多数のトリガーが PROBLEM のまま残っています。")
            print("     この状態では再投入しても OK→PROBLEM の遷移が起きず、")
            print("     新しいイベントが生成されません。先に復旧させてください:")
            print("       python3 send_bulk.py --count 30000 --rate 50 --value 0")

    print("\n" + "=" * 68)
    print(" 突合の指針")
    print(f"   Zabbix 生成 (障害) : {len(problems):,} 件")
    print("   ServiceNow 到達    : 13,500 件 (今回の実測値と比較してください)")
    print("   両者が一致        → 欠損なし。不足分は Zabbix でイベント未生成")
    print("   Zabbix > ServiceNow → コネクタ / MID 経路で欠損")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
