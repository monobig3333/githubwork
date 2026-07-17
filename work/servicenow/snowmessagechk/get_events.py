#!/usr/bin/env python3
"""ServiceNow イベントテーブルからレコードを取得するスクリプト"""

import sys
import json
import argparse
import snow_client


def main():
    parser = argparse.ArgumentParser(description="ServiceNow イベント取得")
    parser.add_argument("--table", default="sysevent",
                        help="テーブル名 (default: sysevent / em_event など)")
    parser.add_argument("--limit", type=int, default=20, help="取得件数 (default: 20)")
    parser.add_argument("--query", default="",
                        help="sysparm_query フィルタ条件 (例: state=ready)")
    args = parser.parse_args()

    print("OAuth トークンを取得中...", file=sys.stderr)
    token = snow_client.get_token()

    print(f"イベントを取得中: table={args.table}, limit={args.limit}", file=sys.stderr)
    events = snow_client.table_get(token, args.table, {
        "sysparm_limit":         args.limit,
        "sysparm_orderby":       "sys_created_on",
        "sysparm_query":         args.query,
        "sysparm_display_value": "true",
    })

    print(json.dumps(events, ensure_ascii=False, indent=2))
    print(f"\n取得件数: {len(events)} 件", file=sys.stderr)


if __name__ == "__main__":
    main()
