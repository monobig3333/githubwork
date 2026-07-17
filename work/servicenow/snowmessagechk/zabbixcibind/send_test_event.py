#!/usr/bin/env python3
"""
biglobedev に Zabbix テストイベントを投入して CI バインドを確認するスクリプト

投入するイベント:
  source: Zabbix
  node:   test-interface3-ootb  (dscy_router_interface CI)
  resource: (空)
  severity: 3 (軽度)
  event_class: Zabbix

使用方法:
  source ./setup.sh && python3 zabbixcibind/send_test_event.py
  source ./setup.sh && python3 zabbixcibind/send_test_event.py --dry-run
  source ./setup.sh && python3 zabbixcibind/send_test_event.py --wait 30
"""

import os
import sys
import json
import time
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SNOW_BASE_URL"] = "https://biglobedev.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api-test/biglobedev/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

TARGET_NODE      = ""   # 空欄: additional_info の name で CI 識別
TARGET_RESOURCE  = ""
EVENT_CLASS      = "Zabbix"
SOURCE           = "Zabbix"
ADDITIONAL_INFO  = {"name": "test-interface3-ootb"}


def send_event(token: str, dry_run: bool = False) -> dict | None:
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    payload = {
        "source":          SOURCE,
        "event_class":     EVENT_CLASS,
        "node":            TARGET_NODE,
        "resource":        TARGET_RESOURCE,
        "severity":        "2",   # フィルタ対象: 0/1/2/4/5
        "state":           "Ready",
        "time_of_event":   now_str,
        "description":     f"CIバインドテスト: additional_info.name=test-interface3-ootb / {now_str}",
        "message_key":     f"zabbix-citest-{ts}",  # 毎回ユニーク → 新規アラート生成
        "additional_info": json.dumps(ADDITIONAL_INFO, ensure_ascii=False),
    }
    print("投入ペイロード:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if dry_run:
        print("\n--dry-run のため登録しません")
        return None

    result = snow_client.table_post(token, "em_event", payload)
    print(f"\n登録完了: sys_id={result.get('sys_id')}")
    return result


def check_event(token: str, event_sys_id: str) -> dict | None:
    """em_event の処理結果を確認する"""
    events = snow_client.table_get(token, "em_event", params={
        "sysparm_query": f"sys_id={event_sys_id}",
        "sysparm_fields": "sys_id,state,processing_notes,event_rule,alert",
    })
    return events[0] if events else None


def check_alert(token: str, alert_sys_id: str) -> dict | None:
    """em_alert の CI バインド結果を確認する"""
    alerts = snow_client.table_get(token, "em_alert", params={
        "sysparm_query": f"sys_id={alert_sys_id}",
        "sysparm_fields": "sys_id,node,resource,cmdb_ci,severity,state,sys_created_on",
    })
    return alerts[0] if alerts else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Zabbix テストイベントを biglobedev に投入して CI バインドを確認")
    parser.add_argument("--dry-run", action="store_true", help="投入せずペイロードのみ表示")
    parser.add_argument("--wait", type=int, default=20, help="処理待機秒数 (デフォルト: 20秒)")
    args = parser.parse_args()

    token = snow_client.get_token()

    # イベント投入
    result = send_event(token, dry_run=args.dry_run)
    if not result:
        return

    event_sys_id = result.get("sys_id")
    if not event_sys_id:
        print("エラー: sys_id が取得できませんでした")
        return

    # 処理を待機
    print(f"\n{args.wait}秒待機中 (イベントエンジンの処理を待つ)...", flush=True)
    for i in range(args.wait, 0, -5):
        time.sleep(5)
        print(f"  残り {i-5}秒...", flush=True)

    # em_event の処理結果確認
    print("\n=== em_event 処理結果 ===")
    ev = check_event(token, event_sys_id)
    if not ev:
        print("  → em_event が見つかりません（アーカイブ済みの可能性）")
        return

    print(f"  state:        {ev.get('state')}")
    event_rule = ev.get("event_rule")
    if isinstance(event_rule, dict):
        print(f"  event_rule:   {event_rule.get('display_value', event_rule.get('value',''))}")
    else:
        print(f"  event_rule:   {event_rule}")
    notes = ev.get("processing_notes", "")
    if notes:
        print(f"  processing_notes:\n{chr(10).join('    '+l for l in notes.splitlines())}")
    else:
        print("  processing_notes: (空)")

    # em_alert の CI バインド確認
    alert_ref = ev.get("alert")
    if isinstance(alert_ref, dict):
        alert_sys_id = alert_ref.get("value", "")
    elif isinstance(alert_ref, str):
        alert_sys_id = alert_ref
    else:
        alert_sys_id = ""

    if not alert_sys_id:
        print("\n  アラートが生成されていません")
        return

    print(f"\n=== em_alert CI バインド結果 (sys_id={alert_sys_id}) ===")
    al = check_alert(token, alert_sys_id)
    if not al:
        print("  → em_alert が見つかりません")
        return

    print(f"  node:        {al.get('node')}")
    print(f"  severity:    {al.get('severity')}")

    cmdb = al.get("cmdb_ci")
    if isinstance(cmdb, dict) and cmdb.get("value"):
        print(f"  cmdb_ci:     {cmdb.get('display_value','(表示名なし)')}  (sys_id={cmdb.get('value')})")
        print("\n  → CI バインド成功！")
    elif isinstance(cmdb, str) and cmdb:
        print(f"  cmdb_ci:     sys_id={cmdb}")
        print("\n  → CI バインド成功！")
    else:
        print("  cmdb_ci:     (空) → CI バインド失敗")


if __name__ == "__main__":
    main()
