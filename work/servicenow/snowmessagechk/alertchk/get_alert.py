#!/usr/bin/env python3
"""
sys_id を指定して em_alert の1件を表示する。

使用例:
  python get_alert.py <sys_id>
  python get_alert.py <sys_id> --json
  python get_alert.py --query "source=iMark_AWS^active=true" --limit 5
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# alertchk は本番環境 (biglobeprod) を対象とする
os.environ["SNOW_BASE_URL"] = "https://biglobeprod.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api/credentials/biglobeprod/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

FETCH_FIELDS = [
    "sys_id", "node", "type", "source", "resource", "metric_name",
    "event_class", "message_key", "severity", "description",
    "additional_info", "classification", "cmdb_ci", "status",
    "u_matched_rules", "u_type_category",
    "u_monitoring_item_number", "u_message_transform_state",
    "anomaly_alert", "u_message_group", "u_monitoring_type",
    "sys_created_on", "sys_updated_on",
]


def _get_str(rec: dict, fname: str) -> str:
    val = rec.get(fname, "")
    if isinstance(val, dict):
        return str(val.get("display_value") or val.get("value") or "")
    return str(val or "")


def print_alert(rec: dict) -> None:
    print(f"{'='*60}")
    print(f"sys_id    : {_get_str(rec, 'sys_id')}")
    print(f"source    : {_get_str(rec, 'source')}")
    print(f"node      : {_get_str(rec, 'node')}")
    print(f"type      : {_get_str(rec, 'type')}")
    print(f"resource  : {_get_str(rec, 'resource')}")
    print(f"severity  : {_get_str(rec, 'severity')}")
    print(f"metric_name: {_get_str(rec, 'metric_name')}")
    print(f"event_class: {_get_str(rec, 'event_class')}")
    print(f"message_key: {_get_str(rec, 'message_key')}")
    print(f"status    : {_get_str(rec, 'status')}")
    print(f"cmdb_ci   : {_get_str(rec, 'cmdb_ci')}")
    print(f"classification: {_get_str(rec, 'classification')}")
    print(f"u_type_category: {_get_str(rec, 'u_type_category')}")
    print(f"u_matched_rules: {_get_str(rec, 'u_matched_rules')}")
    print(f"u_monitoring_item_number: {_get_str(rec, 'u_monitoring_item_number')}")
    print(f"u_message_transform_state: {_get_str(rec, 'u_message_transform_state')}")
    print(f"anomaly_alert: {_get_str(rec, 'anomaly_alert')}")
    print(f"u_message_group: {_get_str(rec, 'u_message_group')}")
    print(f"u_monitoring_type: {_get_str(rec, 'u_monitoring_type')}")
    print(f"sys_created_on: {_get_str(rec, 'sys_created_on')}")
    desc = _get_str(rec, 'description')
    print(f"description: {desc[:200]}{'...' if len(desc) > 200 else ''}")
    ai = _get_str(rec, 'additional_info')
    print(f"additional_info: {ai[:300]}{'...' if len(ai) > 300 else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="em_alert 1件表示ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("sys_id", nargs="?", help="em_alert の sys_id")
    parser.add_argument("--json", action="store_true", help="JSON 形式で出力")
    parser.add_argument("--query", default="",
                        help="sysparm_query（sys_id 未指定時）")
    parser.add_argument("--limit", type=int, default=1,
                        help="取得件数（--query 使用時、default: 1）")
    args = parser.parse_args()

    if not args.sys_id and not args.query:
        parser.error("sys_id または --query が必要です")

    token = snow_client.get_token()

    query = f"sys_id={args.sys_id}" if args.sys_id else args.query
    records = snow_client.table_get(token, "em_alert", {
        "sysparm_query":         query,
        "sysparm_limit":         args.limit,
        "sysparm_display_value": "true",
        "sysparm_fields":        ",".join(FETCH_FIELDS),
    })

    if not records:
        print("レコードが見つかりません", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        for rec in records:
            print_alert(rec)


if __name__ == "__main__":
    main()
