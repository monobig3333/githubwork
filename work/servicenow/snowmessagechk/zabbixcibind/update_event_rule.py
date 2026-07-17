#!/usr/bin/env python3
"""
イベントルール (em_match_rule) の identification_rules を更新するスクリプト

変更内容:
  identification_rules[0].attributes[0].value: "node" → "additional_info.name"

対象ルール:
  Zabbix_アラート作成ルール monotest 版 Device Mapping version
  sys_id: 4575a55e838283906c7d96b6feaad32c

使用方法:
  source ./setup.sh && python3 zabbixcibind/update_event_rule.py
  source ./setup.sh && python3 zabbixcibind/update_event_rule.py --dry-run
"""

import os
import sys
import json
import argparse
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SNOW_BASE_URL"] = "https://biglobedev.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api-test/biglobedev/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

RULE_SYS_ID = "4575a55e838283906c7d96b6feaad32c"
RULE_NAME   = "Zabbix_アラート作成ルール monotest 版 Device Mapping version"

NEW_IDENTIFICATION_RULES = [
    {
        "attributes": [
            {
                "attribute": "name",
                "ciType":    "dscy_router_interface",
                "ruleName":  "name",
                "value":     "additional_info.name",   # node → additional_info.name
            }
        ],
        "ciType": "dscy_router_interface",
    }
]


def get_current_rule(token: str) -> dict:
    rules = snow_client.table_get(token, "em_match_rule", params={
        "sysparm_query": f"sys_id={RULE_SYS_ID}",
        "sysparm_fields": "sys_id,name,identification_rules,bind_type,ci_type",
    })
    return rules[0] if rules else {}


def patch_rule(token: str, sys_id: str, data: dict) -> dict:
    resp = requests.patch(
        f"{snow_client.SNOW_BASE_URL}/api/now/table/em_match_rule/{sys_id}",
        json=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="変更せずに現状と変更内容のみ表示")
    args = parser.parse_args()

    token = snow_client.get_token()

    # 現状確認
    rule = get_current_rule(token)
    if not rule:
        print(f"エラー: ルールが見つかりません (sys_id={RULE_SYS_ID})")
        sys.exit(1)

    print(f"対象ルール: {rule.get('name')}")
    print(f"  bind_type: {rule.get('bind_type')}")
    print(f"  ci_type:   {rule.get('ci_type')}")

    current_json = rule.get("identification_rules", "[]")
    try:
        current = json.loads(current_json)
    except json.JSONDecodeError:
        current = current_json

    print("\n現在の identification_rules:")
    print(json.dumps(current, ensure_ascii=False, indent=2))

    print("\n変更後の identification_rules:")
    print(json.dumps(NEW_IDENTIFICATION_RULES, ensure_ascii=False, indent=2))

    if args.dry_run:
        print("\n--dry-run のため変更しません")
        return

    print("\n更新中...")
    result = patch_rule(token, RULE_SYS_ID, {
        "identification_rules": json.dumps(NEW_IDENTIFICATION_RULES),
    })

    updated_json = result.get("identification_rules", "")
    try:
        updated = json.loads(updated_json)
    except Exception:
        updated = updated_json

    print("更新後の identification_rules:")
    print(json.dumps(updated, ensure_ascii=False, indent=2))
    print("\n完了")


if __name__ == "__main__":
    main()
