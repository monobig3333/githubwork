"""CI（cmdb_ci）件数カウントスクリプト

ServiceNow Stats API を使って CI 件数を集計する。

【使い方】
  # 全 CI の合計
  python3 _common/count_ci.py

  # クラス別の内訳（sys_class_name でグループ集計）
  python3 _common/count_ci.py --by-class

  # 特定テーブルだけ
  python3 _common/count_ci.py --table cmdb_ci_server

  # クエリで絞り込み（ServiceNow エンコーディング規則）
  python3 _common/count_ci.py --query "nameSTARTSWITHPERF-CI"

  # 複数の組み合わせ
  python3 _common/count_ci.py --table cmdb_ci_server --by-class --query "operational_status=1"
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common.snow_client import SnowClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def stats(client: SnowClient, table: str, query: str | None = None,
          group_by: str | None = None) -> dict:
    params = {"sysparm_count": "true"}
    if query:
        params["sysparm_query"] = query
    if group_by:
        params["sysparm_group_by"] = group_by
    resp = client._request("GET", f"/api/now/stats/{table}", params=params)
    resp.raise_for_status()
    return resp.json().get("result", {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="cmdb_ci",
                        help="対象テーブル名（デフォルト cmdb_ci = 全CI）")
    parser.add_argument("--query", default=None,
                        help="絞り込みクエリ（例: nameSTARTSWITHPERF-CI）")
    parser.add_argument("--by-class", action="store_true",
                        help="sys_class_name で集計")
    parser.add_argument("--by-field", default=None,
                        help="任意フィールドで集計（例: operational_status）")
    args = parser.parse_args()

    client = SnowClient()
    group_by = "sys_class_name" if args.by_class else args.by_field

    print(f"[Stats] table={args.table} query={args.query!r} group_by={group_by}")
    result = stats(client, args.table, args.query, group_by)

    if isinstance(result, dict) and "stats" in result and "count" in result["stats"]:
        # 単純カウント
        print(f"\nTotal: {int(result['stats']['count']):>10,} 件")
    elif isinstance(result, list):
        # グループ集計
        rows = []
        for r in result:
            count = int(r["stats"]["count"])
            label = ",".join(f["value"] for f in r.get("groupby_fields", []))
            rows.append((count, label))
        rows.sort(reverse=True)
        total = sum(c for c, _ in rows)
        width = max(len(l) for _, l in rows) if rows else 10
        print()
        print(f"{'class/value':<{width}}  {'count':>10}  {'pct':>6}")
        print("-" * (width + 21))
        for cnt, label in rows:
            pct = cnt / total * 100 if total else 0
            print(f"{label:<{width}}  {cnt:>10,}  {pct:>5.1f}%")
        print("-" * (width + 21))
        print(f"{'TOTAL':<{width}}  {total:>10,}  {100.0:>5.1f}%")
    else:
        print(result)


if __name__ == "__main__":
    main()
