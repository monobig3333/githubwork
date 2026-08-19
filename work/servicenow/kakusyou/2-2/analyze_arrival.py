#!/usr/bin/env python3
"""2-2: em_event の到達状況を分析し、投入側と ServiceNow 側のどちらが律速かを判定する

em_event には 2 つの時刻がある。
  time_of_event   : Zabbix 側でイベントが発生した時刻（＝投入時刻）
  sys_created_on  : ServiceNow に登録された時刻（＝到達時刻）

この 2 つを比べることで、
  - 投入が何分かかったか（time_of_event の min〜max）
  - ServiceNow への登録が何分かかったか（sys_created_on の min〜max）
  - 1 件あたりの遅延（sys_created_on - time_of_event）
が分かる。

判定の目安:
  投入window ≒ 10 分  → 投入は要件レートを満たしている。遅延は ServiceNow 側
  投入window ≫ 10 分  → 投入側が律速。試験条件を満たしていない

使い方:
    python3 2-2/analyze_arrival.py
    python3 2-2/analyze_arrival.py --node-prefix test-servicenow-monohyouka
    python3 2-2/analyze_arrival.py --json 2-2/result_2_2.json   # 結果を保存
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    import requests
except ImportError:
    sys.exit("requests が未導入です")

try:
    from dotenv import load_dotenv
    if (ROOT / ".env").exists():
        load_dotenv(ROOT / ".env")
except ImportError:
    pass

PAGE = 1000
FMT = "%Y-%m-%d %H:%M:%S"


def _props() -> dict:
    p = ROOT / "jmeter.properties"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def get_token(base: str) -> str:
    pr = _props()
    cid = os.getenv("SNOW_CLIENT_ID") or pr.get("snow.client_id", "")
    sec = os.getenv("SNOW_CLIENT_SECRET") or pr.get("snow.client_secret", "")
    if not cid or not sec:
        sys.exit("OAuth の client_id / secret が見つかりません")
    r = requests.post(f"{base}/oauth_token.do", auth=(cid, sec),
                      data={"grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_all(base: str, token: str, query: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        r = requests.get(
            f"{base}/api/now/table/em_event",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={
                "sysparm_query": f"{query}^ORDERBYsys_created_on",
                "sysparm_fields": "node,time_of_event,sys_created_on,source,type",
                "sysparm_limit": str(PAGE),
                "sysparm_offset": str(offset),
            },
            timeout=120,
        )
        r.raise_for_status()
        batch = r.json().get("result", [])
        rows += batch
        print(f"  取得 {len(rows):,} 件 ...", end="\r", flush=True)
        if len(batch) < PAGE:
            break
        offset += PAGE
    print(f"  取得 {len(rows):,} 件 完了      ")
    return rows


def parse(s: str):
    try:
        return datetime.strptime(s.strip(), FMT)
    except Exception:
        return None


def window(name: str, times: list[datetime]) -> dict:
    lo, hi = min(times), max(times)
    dur = (hi - lo).total_seconds()
    rate = len(times) / dur if dur > 0 else 0
    print(f"\n--- {name} ---")
    print(f"  最初 : {lo:%Y-%m-%d %H:%M:%S}")
    print(f"  最後 : {hi:%Y-%m-%d %H:%M:%S}")
    print(f"  期間 : {dur/60:.1f} 分 ({dur:.0f} 秒)")
    print(f"  平均 : {rate:.1f} 件/秒")
    # 1 分ごとの分布（上位）
    per_min = Counter(t.replace(second=0) for t in times)
    peak = per_min.most_common(1)[0]
    print(f"  ピーク: {peak[1]:,} 件/分 ({peak[0]:%H:%M})")
    print(f"  分あたり平均: {len(times)/max(1,len(per_min)):.0f} 件")
    return {"first": lo.strftime(FMT), "last": hi.strftime(FMT),
            "duration_sec": round(dur, 1), "rate_per_sec": round(rate, 2),
            "peak_per_min": peak[1], "active_minutes": len(per_min)}


def main() -> int:
    ap = argparse.ArgumentParser(description="em_event 到達分析")
    ap.add_argument("--node-prefix", default="test-servicenow-monohyouka")
    ap.add_argument("--query", default="")
    ap.add_argument("--base-url", default=os.getenv(
        "SNOW_BASE_URL", "https://biglobedev.service-now.com"))
    ap.add_argument("--json", default="", help="結果をこのパスに JSON 保存")
    ap.add_argument("--target", type=int, default=30000)
    ap.add_argument("--since", default="",
                    help="この時刻以降のみ対象 (JST, 'YYYY-MM-DD HH:MM:SS' or 'HH:MM')")
    ap.add_argument("--hours-ago", type=int, default=0,
                    help="直近 N 時間のみ対象 (--since より簡便)")
    args = ap.parse_args()

    query = args.query or f"nodeSTARTSWITH{args.node_prefix}"

    # 過去の投入分と混ざらないよう時刻で絞る（削除の代わりになる）
    if args.hours_ago:
        query += f"^sys_created_on>=javascript:gs.hoursAgoStart({args.hours_ago})"
    elif args.since:
        s = args.since.strip()
        if len(s) <= 5 and ":" in s:               # "HH:MM" なら今日の日付を補う
            s = f"{datetime.now():%Y-%m-%d} {s}:00"
        elif len(s) <= 16:                          # 秒が無ければ補う
            s = s if s.count(":") == 2 else s + ":00"
        # ServiceNow の sys_created_on は UTC。JST 入力を UTC へ変換する
        jst = datetime.strptime(s, FMT)
        utc = jst - timedelta(hours=9)
        query += f"^sys_created_on>=javascript:gs.dateGenerate('{utc:%Y-%m-%d}','{utc:%H:%M:%S}')"
        print(f"[INFO] 対象を {jst:%Y-%m-%d %H:%M:%S} JST 以降に限定 "
              f"(UTC {utc:%Y-%m-%d %H:%M:%S})")
    print("=" * 68)
    print(f" em_event 到達分析   条件: {query}")
    print("=" * 68)
    token = get_token(args.base_url)
    rows = fetch_all(args.base_url, token, query)
    if not rows:
        sys.exit("対象イベントが 0 件です")

    ev = [parse(r.get("time_of_event", "")) for r in rows]
    cr = [parse(r.get("sys_created_on", "")) for r in rows]
    pairs = [(e, c) for e, c in zip(ev, cr) if e and c]
    ev = [e for e, _ in pairs]
    cr = [c for _, c in pairs]

    print(f"\n総件数: {len(rows):,} 件 (時刻が取れたもの {len(pairs):,} 件)")
    print(f"ノード重複: {len(rows) - len(set(r['node'] for r in rows)):,} 件")

    w_ev = window("Zabbix 側の投入 (time_of_event)", ev)
    w_cr = window("ServiceNow 登録 (sys_created_on)", cr)

    lags = [(c - e).total_seconds() for e, c in pairs]
    lags_s = sorted(lags)
    print("\n--- 1 件あたりの遅延 (sys_created_on - time_of_event) ---")
    print(f"  最小 {min(lags):.0f}s / 中央 {statistics.median(lags):.0f}s / "
          f"平均 {statistics.mean(lags):.0f}s / 最大 {max(lags):.0f}s")
    print(f"  95%ile {lags_s[int(len(lags_s)*0.95)-1]:.0f}s")

    print("\n" + "=" * 68)
    inj_min = w_ev["duration_sec"] / 60
    median_lag = statistics.median(lags)

    # time_of_event が登録時刻と同値なら、投入側の時刻情報として使えない
    if median_lag <= 2 and abs(w_ev["duration_sec"] - w_cr["duration_sec"]) <= 5:
        verdict = (
            "⚠️ time_of_event と sys_created_on がほぼ同値のため、"
            "time_of_event は Zabbix 側の発生時刻を保持していない。"
            "この数値だけでは投入側 / ServiceNow 側の律速を切り分けられない。"
            "Zabbix サーバ側の投入開始・終了時刻を別途確認すること"
        )
        print(" 判定: **切り分け不能**")
        print(f"   遅延の中央値 {median_lag:.0f}s、両ウィンドウの差 "
              f"{abs(w_ev['duration_sec']-w_cr['duration_sec']):.0f}s")
        print("   → time_of_event が登録時刻で上書きされている")
        print("   → Zabbix 側のログ / スクリプト実行時間で投入所要を確認する必要あり")
    elif inj_min <= 12:
        verdict = ("投入は約 10 分で完了している → ServiceNow 側の処理が律速。"
                   "要件レートでの投入は達成しており、到達までの遅延は ServiceNow 側の特性")
        print(f" 判定材料: 投入 {inj_min:.1f} 分 / 登録 {w_cr['duration_sec']/60:.1f} 分")
        print(f" → {verdict}")
    elif inj_min >= 20:
        verdict = ("投入に 20 分以上かかっている → 投入側 (Zabbix) が律速。"
                   "30,000 件 / 10 分の投入条件を満たせていない")
        print(f" 判定材料: 投入 {inj_min:.1f} 分 / 登録 {w_cr['duration_sec']/60:.1f} 分")
        print(f" → {verdict}")
    else:
        verdict = "投入期間が中間的。投入側と ServiceNow 側の双方の影響を検討する必要がある"
        print(f" 判定材料: 投入 {inj_min:.1f} 分 / 登録 {w_cr['duration_sec']/60:.1f} 分")
        print(f" → {verdict}")

    uniq = len(set(r["node"] for r in rows))
    per_node = len(rows) / uniq if uniq else 0
    print(f"\n ノード数 {uniq:,} / イベント {len(rows):,} = 1 ノードあたり {per_node:.2f} 件")
    if per_node > 1.5:
        print("   → 1 ノードから複数イベント。障害と復旧の 2 イベント、"
              "または投入スクリプトの複数回実行が考えられる")
    print("=" * 68)

    result = {
        "method": "Zabbix サーバ上で zabbix_sender を直接実行 (on.py)",
        "target": args.target,
        "received": len(rows),
        "node_duplicates": len(rows) - len(set(r["node"] for r in rows)),
        "injection_window": w_ev,
        "servicenow_window": w_cr,
        "lag_sec": {
            "min": round(min(lags), 1), "median": round(statistics.median(lags), 1),
            "avg": round(statistics.mean(lags), 1), "max": round(max(lags), 1),
            "p95": round(lags_s[int(len(lags_s) * 0.95) - 1], 1),
        },
        "verdict_hint": verdict,
        "analyzed_at": datetime.now().strftime(FMT),
    }
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"\n保存: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
