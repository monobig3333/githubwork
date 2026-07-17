#!/usr/bin/env python3
"""
biglobedev 環境で Zabbix イベントの CI バインドが行われない原因を調査するスクリプト

調査対象:
  - node:     test-interface3-ootb (dscy_router_interface を想定)
  - resource: test-router0         (IP Router CI)
  - イベントルール: Zabbix_アラート作成ルール monotest 版 Device Mapping version (order=300)

使用方法:
  source ./setup.sh && python3 zabbixcibind/diagnose_ci_bind.py
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SNOW_BASE_URL"] = "https://biglobedev.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api-test/biglobedev/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

TARGET_NODE     = "test-interface3-ootb"
TARGET_RESOURCE = "test-router0"
EVENT_CLASS     = "Zabbix"
RULE_NAME_LIKE  = "Device Mapping"


def sep(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def main() -> None:
    token = snow_client.get_token()

    # ─── 1. イベントルール詳細 ───────────────────────────────────────
    sep("1. イベントルール (em_match_rule)")
    rules = snow_client.table_get(token, "em_match_rule", params={
        "sysparm_query": f"nameLIKE{RULE_NAME_LIKE}^event_class={EVENT_CLASS}",
        "sysparm_orderby": "order",
    })
    if not rules:
        print("  該当するイベントルールが見つかりません")
    for r in rules:
        print(f"  name:                {r['name']}")
        print(f"  order:               {r['order']}")
        print(f"  active:              {r['active']}")
        print(f"  bind:                {r['bind']}")
        print(f"  bind_type:           {r['bind_type']}  (1=CI field match / 2=CI Identification Rule)")
        print(f"  ci_type:             {r['ci_type']}")
        print(f"  filter:              {r.get('filter','')}")
        print(f"  event_class:         {r.get('event_class','')}")
        print(f"  sys_id:              {r['sys_id']}")
        ident = r.get("identification_rules", "")
        if ident:
            try:
                parsed = json.loads(ident)
                print(f"  identification_rules (解析済み):")
                print(json.dumps(parsed, ensure_ascii=False, indent=4))
            except json.JSONDecodeError:
                print(f"  identification_rules: {ident}")
        else:
            print("  identification_rules: (空)")
        print()

    # ─── 2. CMDB — dscy_router_interface で node 検索 ────────────────
    sep(f"2. CMDB: dscy_router_interface で name='{TARGET_NODE}' 検索")
    cis_iface = snow_client.table_get(token, "dscy_router_interface", params={
        "sysparm_query": f"name={TARGET_NODE}",
        "sysparm_fields": "sys_id,name,sys_class_name,ip_router,operational_status,install_status",
    })
    if not cis_iface:
        print(f"  → 見つからない (dscy_router_interface.name='{TARGET_NODE}' は未登録)")
    else:
        for ci in cis_iface:
            print(f"  sys_id:           {ci['sys_id']}")
            print(f"  name:             {ci['name']}")
            print(f"  sys_class_name:   {ci['sys_class_name']}")
            print(f"  ip_router:        {ci.get('ip_router','')}")
            print(f"  operational_status: {ci.get('operational_status','')}")
            print()

    # ─── 3. CMDB — cmdb_ci (基底) で node 検索 ───────────────────────
    sep(f"3. CMDB: cmdb_ci (基底) で name='{TARGET_NODE}' 検索")
    cis_base = snow_client.table_get(token, "cmdb_ci", params={
        "sysparm_query": f"name={TARGET_NODE}",
        "sysparm_fields": "sys_id,name,sys_class_name,operational_status",
    })
    if not cis_base:
        print(f"  → 見つからない (cmdb_ci.name='{TARGET_NODE}' は未登録)")
    else:
        for ci in cis_base:
            print(f"  sys_id:           {ci['sys_id']}")
            print(f"  name:             {ci['name']}")
            print(f"  sys_class_name:   {ci['sys_class_name']}")
            print(f"  operational_status: {ci.get('operational_status','')}")
            print()

    # ─── 4. CMDB — cmdb_ci_ip_router で resource 検索 ────────────────
    sep(f"4. CMDB: cmdb_ci_ip_router で name='{TARGET_RESOURCE}' 検索")
    cis_router = snow_client.table_get(token, "cmdb_ci_ip_router", params={
        "sysparm_query": f"name={TARGET_RESOURCE}",
        "sysparm_fields": "sys_id,name,sys_class_name,operational_status",
    })
    if not cis_router:
        print(f"  → 見つからない (cmdb_ci_ip_router.name='{TARGET_RESOURCE}' は未登録)")
    else:
        for ci in cis_router:
            print(f"  sys_id:           {ci['sys_id']}")
            print(f"  name:             {ci['name']}")
            print(f"  sys_class_name:   {ci['sys_class_name']}")
            print(f"  operational_status: {ci.get('operational_status','')}")
            print()

    # ─── 5. 最新 em_event (node=TARGET_NODE) の processing_notes ──────
    sep(f"5. em_event: node='{TARGET_NODE}' の最新5件")
    events = snow_client.table_get(token, "em_event", params={
        "sysparm_query": f"node={TARGET_NODE}^event_class={EVENT_CLASS}",
        "sysparm_orderby": "sys_created_on",
        "sysparm_order_direction": "desc",
        "sysparm_limit": "5",
        "sysparm_fields": "sys_id,source,node,resource,event_class,severity,state,processing_notes,event_rule,sys_created_on",
    })
    if not events:
        print(f"  → 該当イベントなし (node='{TARGET_NODE}', event_class='{EVENT_CLASS}')")
    for ev in events:
        print(f"  sys_id:          {ev['sys_id']}")
        print(f"  source:          {ev.get('source','')}")
        print(f"  node:            {ev.get('node','')}")
        print(f"  resource:        {ev.get('resource','')}")
        print(f"  severity:        {ev.get('severity','')}")
        print(f"  state:           {ev.get('state','')}")
        print(f"  event_rule:      {ev.get('event_rule','')}")
        print(f"  sys_created_on:  {ev.get('sys_created_on','')}")
        notes = ev.get("processing_notes", "")
        if notes:
            print(f"  processing_notes:\n    {notes.replace(chr(10), chr(10)+'    ')}")
        else:
            print(f"  processing_notes: (空)")
        print()

    # ─── 6. 最新 em_alert (node=TARGET_NODE) の cmdb_ci ──────────────
    sep(f"6. em_alert: node='{TARGET_NODE}' の最新5件")
    alerts = snow_client.table_get(token, "em_alert", params={
        "sysparm_query": f"node={TARGET_NODE}^source={EVENT_CLASS}",
        "sysparm_orderby": "sys_created_on",
        "sysparm_order_direction": "desc",
        "sysparm_limit": "5",
        "sysparm_fields": "sys_id,source,node,resource,severity,cmdb_ci,type,processing_engine_processing_notes,sys_created_on",
    })
    if not alerts:
        print(f"  → 該当アラートなし (node='{TARGET_NODE}', source='{EVENT_CLASS}')")
    for al in alerts:
        print(f"  sys_id:          {al['sys_id']}")
        print(f"  node:            {al.get('node','')}")
        print(f"  resource:        {al.get('resource','')}")
        print(f"  severity:        {al.get('severity','')}")
        cmdb = al.get("cmdb_ci") or {}
        if isinstance(cmdb, dict):
            print(f"  cmdb_ci:         {cmdb.get('display_value','(空)')}  (sys_id={cmdb.get('value','')})")
        else:
            print(f"  cmdb_ci:         {cmdb}")
        print(f"  sys_created_on:  {al.get('sys_created_on','')}")
        notes = al.get("processing_engine_processing_notes", "")
        if notes:
            print(f"  processing_notes:\n    {notes.replace(chr(10), chr(10)+'    ')}")
        print()

    # ─── 7. em_binding_device_map で dscy_router_interface を確認 ─────
    sep("7. em_binding_device_map: dscy_router_interface 関連マッピング")
    maps = snow_client.table_get(token, "em_binding_device_map", params={
        "sysparm_query": "ci_type=dscy_router_interface^ORparent_ci_type=dscy_router_interface",
        "sysparm_fields": "sys_id,name,ci_type,parent_ci_type,active",
    })
    if not maps:
        print("  → dscy_router_interface のマッピング定義なし")
    for m in maps:
        print(f"  name:            {m.get('name','')}")
        print(f"  ci_type:         {m.get('ci_type','')}")
        print(f"  parent_ci_type:  {m.get('parent_ci_type','')}")
        print(f"  active:          {m.get('active','')}")
        print()

    sep("調査完了")
    print("""
診断ポイント:
  1. identification_rules の ciType が 'cmdb_ci' → dscy_router_interface クラスの CI
     が cmdb_ci テーブルで name 検索されているか確認
  2. test-interface3-ootb が CMDB に未登録なら CIバインドは常に失敗
  3. 未登録の場合: dscy_router_interface に手動登録するか、
     bind_type=1 (CI field match) + ci_type/field を直接指定する方法を検討
""")


if __name__ == "__main__":
    main()
