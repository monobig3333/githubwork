#!/usr/bin/env python3
"""
sys_id を指定して em_event の1件を表示するスクリプト

使用例:
  python get_event.py 9059de25c3198710e7339b677a013161
  python get_event.py 9059de25c3198710e7339b677a013161 --json
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# eventchk は本番環境 (biglobeprod) を対象とする
os.environ["SNOW_BASE_URL"] = "https://biglobeprod.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api/credentials/biglobeprod/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

FIELDS = [
    "sys_id", "source", "node", "type", "resource", "metric_name",
    "event_class", "message_key", "severity", "description",
    "additional_info", "time_of_event", "state", "resolution_state",
    "sys_created_on", "sys_created_by",
]


def main():
    parser = argparse.ArgumentParser(description="em_event 1件表示")
    parser.add_argument("sys_id", help="表示する sys_id")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    args = parser.parse_args()

    token = snow_client.get_token()
    results = snow_client.table_get(token, "em_event", {
        "sysparm_query":         f"sys_id={args.sys_id}",
        "sysparm_display_value": "true",
        "sysparm_fields":        ",".join(FIELDS),
        "sysparm_limit":         1,
    })

    if not results:
        print(f"見つかりません: sys_id={args.sys_id}", file=sys.stderr)
        sys.exit(1)

    e = results[0]

    if args.json:
        print(json.dumps(e, ensure_ascii=False, indent=2))
        return

    print(f"{'='*60}")
    print(f"sys_id         : {e.get('sys_id','')}")
    print(f"time_of_event  : {e.get('time_of_event','')}")
    print(f"sys_created_on : {e.get('sys_created_on','')}")
    print(f"sys_created_by : {e.get('sys_created_by','')}")
    print(f"state          : {e.get('state','')}")
    print(f"resolution_state: {e.get('resolution_state','')}")
    print(f"{'='*60}")
    print(f"source         : {e.get('source','')}")
    print(f"node           : {e.get('node','')}")
    print(f"type           : {e.get('type','')}")
    print(f"resource       : {e.get('resource','')}")
    print(f"metric_name    : {e.get('metric_name','')}")
    print(f"event_class    : {e.get('event_class','')}")
    print(f"severity       : {e.get('severity','')}")
    print(f"message_key    : {e.get('message_key','')}")
    print(f"{'='*60}")
    print(f"description:\n{e.get('description','')}")
    print(f"{'='*60}")
    ai = e.get("additional_info","") or ""
    print(f"additional_info ({len(ai)}文字):")
    try:
        print(json.dumps(json.loads(ai), ensure_ascii=False, indent=2))
    except Exception:
        print(ai)


if __name__ == "__main__":
    main()
