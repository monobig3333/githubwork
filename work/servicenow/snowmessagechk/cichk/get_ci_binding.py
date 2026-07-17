#!/usr/bin/env python3
"""
sys_id を指定して CI バインディングルールの1件を表示する。

使用例:
  python get_ci_binding.py <sys_id>
  python get_ci_binding.py <sys_id> --json
  python get_ci_binding.py --query "active=true" --limit 5
  python get_ci_binding.py --table sa_event_rule <sys_id>
  python get_ci_binding.py --table em_mapping_rule <sys_id>
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# cichk は本番環境 (biglobeprod) を対象とする
os.environ["SNOW_BASE_URL"] = "https://biglobeprod.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api/credentials/biglobeprod/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

SA_EVENT_RULE_FIELDS = [
    "sys_id", "name", "active", "order", "type", "description",
    "ems_source", "conditions", "ci_class", "script",
    "sys_created_on", "sys_updated_on",
]

BINDING_RULE_FIELDS = [
    "sys_id", "name", "active", "order", "description",
    "rule_type", "cmdb_ci_class", "binding_type",
    "conditions", "field_name", "ci_identifier", "source",
    "sys_created_on", "sys_updated_on",
]

EVENT_RULE_BINDING_FIELDS = [
    "sys_id", "name", "source", "order", "active",
    "override_binding", "binding_type", "ci_class",
    "sys_created_on", "sys_updated_on",
]


def _get_str(rec: dict, fname: str) -> str:
    val = rec.get(fname, "")
    if isinstance(val, dict):
        return str(val.get("display_value") or val.get("value") or "")
    return str(val or "")


def print_sa_event_rule(rec: dict) -> None:
    print(f"{'='*60}")
    print(f"[sa_event_rule]")
    print(f"sys_id        : {_get_str(rec, 'sys_id')}")
    print(f"name          : {_get_str(rec, 'name')}")
    print(f"active        : {_get_str(rec, 'active')}")
    print(f"order         : {_get_str(rec, 'order')}")
    print(f"type          : {_get_str(rec, 'type')}")
    print(f"ems_source    : {_get_str(rec, 'ems_source')}")
    print(f"ci_class      : {_get_str(rec, 'ci_class')}")
    print(f"conditions    : {_get_str(rec, 'conditions')[:200]}")
    script = _get_str(rec, "script")
    print(f"script        : {'(あり)' if script else '(なし)'}")
    desc = _get_str(rec, "description")
    print(f"description   : {desc[:200]}{'...' if len(desc) > 200 else ''}")
    print(f"sys_created_on: {_get_str(rec, 'sys_created_on')}")
    print(f"sys_updated_on: {_get_str(rec, 'sys_updated_on')}")


def print_binding_rule(rec: dict) -> None:
    print(f"{'='*60}")
    print(f"[em_binding_rule]")
    print(f"sys_id        : {_get_str(rec, 'sys_id')}")
    print(f"name          : {_get_str(rec, 'name')}")
    print(f"active        : {_get_str(rec, 'active')}")
    print(f"order         : {_get_str(rec, 'order')}")
    print(f"rule_type     : {_get_str(rec, 'rule_type')}")
    print(f"cmdb_ci_class : {_get_str(rec, 'cmdb_ci_class')}")
    print(f"binding_type  : {_get_str(rec, 'binding_type')}")
    print(f"field_name    : {_get_str(rec, 'field_name')}")
    print(f"ci_identifier : {_get_str(rec, 'ci_identifier')}")
    print(f"source        : {_get_str(rec, 'source')}")
    print(f"conditions    : {_get_str(rec, 'conditions')[:200]}")
    desc = _get_str(rec, "description")
    print(f"description   : {desc[:200]}{'...' if len(desc) > 200 else ''}")
    print(f"sys_created_on: {_get_str(rec, 'sys_created_on')}")
    print(f"sys_updated_on: {_get_str(rec, 'sys_updated_on')}")


def print_event_rule_binding(rec: dict) -> None:
    print(f"{'='*60}")
    print(f"[em_event_rule]")
    print(f"sys_id            : {_get_str(rec, 'sys_id')}")
    print(f"name              : {_get_str(rec, 'name')}")
    print(f"active            : {_get_str(rec, 'active')}")
    print(f"order             : {_get_str(rec, 'order')}")
    print(f"source            : {_get_str(rec, 'source')}")
    print(f"override_binding  : {_get_str(rec, 'override_binding')}")
    print(f"binding_type      : {_get_str(rec, 'binding_type')}")
    print(f"ci_class          : {_get_str(rec, 'ci_class')}")
    print(f"sys_created_on    : {_get_str(rec, 'sys_created_on')}")
    print(f"sys_updated_on    : {_get_str(rec, 'sys_updated_on')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CI バインディングルール 1件表示ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("sys_id", nargs="?", help="sys_id")
    parser.add_argument("--table",
                        choices=["sa_event_rule", "em_binding_rule",
                                 "em_event_rule", "em_mapping_rule"],
                        default="sa_event_rule",
                        help="対象テーブル (default: sa_event_rule)")
    parser.add_argument("--json", action="store_true", help="JSON 形式で出力")
    parser.add_argument("--query", default="", help="sysparm_query（sys_id 未指定時）")
    parser.add_argument("--limit", type=int, default=1,
                        help="取得件数（--query 使用時、default: 1）")
    args = parser.parse_args()

    if not args.sys_id and not args.query:
        parser.error("sys_id または --query が必要です")

    field_map = {
        "sa_event_rule":   SA_EVENT_RULE_FIELDS,
        "em_binding_rule": BINDING_RULE_FIELDS,
        "em_event_rule":   EVENT_RULE_BINDING_FIELDS,
        "em_mapping_rule": EVENT_RULE_BINDING_FIELDS,
    }
    printer_map = {
        "sa_event_rule":   print_sa_event_rule,
        "em_binding_rule": print_binding_rule,
        "em_event_rule":   print_event_rule_binding,
        "em_mapping_rule": print_event_rule_binding,
    }
    fields = field_map[args.table]
    query = f"sys_id={args.sys_id}" if args.sys_id else args.query

    token = snow_client.get_token()
    records = snow_client.table_get(token, args.table, {
        "sysparm_query":         query,
        "sysparm_limit":         args.limit,
        "sysparm_display_value": "true",
        "sysparm_fields":        ",".join(fields),
    })

    if not records:
        print("レコードが見つかりません", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        printer = printer_map[args.table]
        for rec in records:
            printer(rec)


if __name__ == "__main__":
    main()
