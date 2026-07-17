#!/usr/bin/env python3
"""
syslog アラート（4/1以降）の
  u_monitoring_type / u_monitoring_item_number / type(アラートタイプ) / u_type_category
の組み合わせ集計。
"""

import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SNOW_BASE_URL"] = "https://biglobeprod.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api/credentials/biglobeprod/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

FIELDS = [
    "sys_id", "source", "u_alert_type", "u_type_category",
    "u_monitoring_type", "u_monitoring_item_number",
    "node", "resource", "severity",
]
PAGE_SIZE = 1000
QUERY = "source=syslog^sys_created_on>=2026-04-01 00:00:00"


def fetch_all():
    token = snow_client.get_token()
    records = []
    offset = 0
    while True:
        page = snow_client.table_get(token, "em_alert", {
            "sysparm_limit":         PAGE_SIZE,
            "sysparm_offset":        offset,
            "sysparm_query":         QUERY,
            "sysparm_display_value": "true",
            "sysparm_fields":        ",".join(FIELDS),
        })
        records.extend(page)
        print(f"  取得: {len(records)} 件...", file=sys.stderr)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return records


def main():
    records = fetch_all()
    print(f"\n総件数: {len(records)} 件 (syslog, 4/1以降)\n")

    def get_display(rec, field):
        v = rec.get(field, "")
        if isinstance(v, dict):
            return v.get("display_value") or ""
        return v or ""

    # 組み合わせ別カウント
    combo: dict[tuple, int] = defaultdict(int)
    for r in records:
        key = (
            get_display(r, "u_monitoring_type") or "(空)",
            get_display(r, "u_monitoring_item_number") or "(空)",
            get_display(r, "u_alert_type") or "(空)",
            get_display(r, "u_type_category") or "(空)",
        )
        combo[key] += 1

    # 件数降順でソート
    sorted_combo = sorted(combo.items(), key=lambda x: -x[1])

    header = f"{'件数':>6}  {'u_monitoring_type':<30}  {'u_monitoring_item_number':<28}  {'u_alert_type(アラートタイプ)':<30}  {'u_type_category'}"
    print(header)
    print("-" * len(header))
    for (mt, mn, tp, tc), cnt in sorted_combo:
        print(f"{cnt:>6}  {mt:<30}  {mn:<28}  {tp:<30}  {tc}")

    print(f"\n組み合わせ種類: {len(sorted_combo)} 種")


if __name__ == "__main__":
    main()
