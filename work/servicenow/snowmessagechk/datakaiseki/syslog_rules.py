#!/usr/bin/env python3
"""
syslog イベントルール解析。

調査対象:
  1. em_alert.u_matched_rules   — 実際に適用されたルール名（全件集計）
  2. u_transformation_rule      — syslog 関連の変換ルール＋適用中ルール詳細
  3. em_rule_xml (matchRule)    — CIバインディングルール
  4. em_mapping_rule            — フィールドマッピングルール
  ※ sa_event_rule は Table API 非対応のため直接取得不可
"""

import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SNOW_BASE_URL"] = "https://biglobeprod.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api/credentials/biglobeprod/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

PAGE = 1000


def fetch(token, table, fields, query=""):
    recs, offset = [], 0
    while True:
        page = snow_client.table_get(token, table, {
            "sysparm_limit":         PAGE,
            "sysparm_offset":        offset,
            "sysparm_query":         query,
            "sysparm_display_value": "true",
            "sysparm_fields":        ",".join(fields),
        })
        recs.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    return recs


def gs(rec, key):
    v = rec.get(key, "")
    if isinstance(v, dict):
        return v.get("display_value") or v.get("value") or ""
    return v or ""


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def main():
    token = snow_client.get_token()

    # ----------------------------------------------------------------
    # 1. em_alert.u_matched_rules — 全 syslog アラートで適用されたルール
    # ----------------------------------------------------------------
    section("① em_alert.u_matched_rules（4/1以降 syslog 全件集計）")

    print("  em_alert 取得中...", end="", flush=True)
    alerts = fetch(token, "em_alert", ["sys_id", "u_matched_rules"],
                   query="source=syslog^sys_created_on>=2026-04-01 00:00:00")
    print(f" {len(alerts)} 件\n")

    counter = Counter()
    for a in alerts:
        mr = gs(a, "u_matched_rules")
        counter[mr or "(空)"] += 1

    for val, cnt in counter.most_common():
        print(f"  {cnt:>6} 件  {val}")

    # u_matched_rules から sys_id を抽出（形式: "ルール名(sys_id)"）
    applied_ids: set[str] = set()
    for val in counter:
        if val != "(空)" and "(" in val:
            sid = val.rsplit("(", 1)[-1].rstrip(")")
            if len(sid) == 32:
                applied_ids.add(sid)

    # ----------------------------------------------------------------
    # 2. u_transformation_rule — 適用中ルール詳細 + syslog 関連
    # ----------------------------------------------------------------
    section("② u_transformation_rule（適用中ルール詳細 + syslog 関連）")

    print("  u_transformation_rule 全件取得中...", end="", flush=True)
    all_tr = fetch(token, "u_transformation_rule", [
        "sys_id", "u_rule_name", "u_order", "u_category", "u_active",
        "u_table_name", "u_conditions", "u_description", "u_data_type",
    ])
    print(f" {len(all_tr)} 件")

    # sys_id の辞書化
    tr_by_id = {gs(r, "sys_id"): r for r in all_tr}

    # syslog 関連（名前・条件・説明に "syslog" を含む）
    syslog_tr = [r for r in all_tr if any(
        "syslog" in gs(r, k).lower()
        for k in ["u_rule_name", "u_conditions", "u_description"]
    )]

    # 適用中ルール（u_matched_rules に出てきた sys_id）
    applied_tr = [tr_by_id[sid] for sid in applied_ids if sid in tr_by_id]

    # 両方まとめて重複排除
    target_ids = {gs(r, "sys_id") for r in syslog_tr} | applied_ids
    target_tr = [r for r in all_tr if gs(r, "sys_id") in target_ids]

    print(f"\n  対象ルール（syslog関連 + 適用中）: {len(target_tr)} 件")
    if applied_tr:
        print(f"  うち実際に適用されているルール: {len(applied_tr)} 件")

    # detail を全件取得
    print("  u_transformation_rule_detail 全件取得中...", end="", flush=True)
    all_det = fetch(token, "u_transformation_rule_detail", [
        "sys_id", "u_parent", "u_field_name",
        "u_target_string", "u_transformed_string",
    ])
    print(f" {len(all_det)} 件")

    det_by_parent: dict[str, list] = {}
    for d in all_det:
        pid = gs(d, "u_parent")
        if pid in target_ids:
            det_by_parent.setdefault(pid, []).append(d)

    print()
    for r in sorted(target_tr, key=lambda x: gs(x, "u_order")):
        sid = gs(r, "sys_id")
        applied_mark = " ★適用中" if sid in applied_ids else ""
        print(f"  [{gs(r,'u_order'):>4}] {gs(r,'u_rule_name')} "
              f"(active={gs(r,'u_active')}){applied_mark}")
        print(f"         category   : {gs(r,'u_category')}")
        print(f"         data_type  : {gs(r,'u_data_type')}")
        cond = gs(r, "u_conditions")
        print(f"         conditions : {cond[:300]}{'...' if len(cond)>300 else ''}")
        desc = gs(r, "u_description")
        if desc:
            print(f"         description: {desc[:200]}{'...' if len(desc)>200 else ''}")
        for d in det_by_parent.get(sid, []):
            print(f"         detail     : {gs(d,'u_field_name')} "
                  f"'{gs(d,'u_target_string')}' -> '{gs(d,'u_transformed_string')}'")
        print()

    # ----------------------------------------------------------------
    # 3. em_rule_xml — matchRule・fieldMappingRule で syslog 関連
    # ----------------------------------------------------------------
    section("③ em_rule_xml（syslog 関連）")

    rule_xml_recs = fetch(token, "em_rule_xml", ["sys_id", "name", "rule_xml"])
    syslog_xml = [r for r in rule_xml_recs
                  if "syslog" in gs(r, "name").lower()
                  or "syslog" in gs(r, "rule_xml").lower()]
    print(f"  全 {len(rule_xml_recs)} 件中 syslog 関連: {len(syslog_xml)} 件")
    for r in syslog_xml:
        print(f"\n  name: {gs(r,'name')}")
        xml = gs(r, "rule_xml")
        print(f"  rule_xml:\n{xml}")

    # ----------------------------------------------------------------
    # 4. em_mapping_rule — syslog 関連
    # ----------------------------------------------------------------
    section("④ em_mapping_rule（syslog 関連）")

    mapping_recs = fetch(token, "em_mapping_rule", [
        "sys_id", "name", "active", "order", "source",
        "event_class", "type", "resource", "conditions",
        "field_mappings", "description",
    ])
    syslog_map = [r for r in mapping_recs if any(
        "syslog" in gs(r, k).lower()
        for k in ["name", "source", "conditions", "description"]
    )]
    print(f"  全 {len(mapping_recs)} 件中 syslog 関連: {len(syslog_map)} 件")
    for r in sorted(syslog_map, key=lambda x: gs(x, "order")):
        print(f"\n  [{gs(r,'order'):>4}] {gs(r,'name')} (active={gs(r,'active')})")
        print(f"         source    : {gs(r,'source')}")
        print(f"         type      : {gs(r,'type')}")
        print(f"         resource  : {gs(r,'resource')}")
        cond = gs(r, "conditions")
        print(f"         conditions: {cond[:300]}{'...' if len(cond)>300 else ''}")
        fm = gs(r, "field_mappings")
        if fm:
            print(f"         field_mappings: {fm[:300]}{'...' if len(fm)>300 else ''}")


if __name__ == "__main__":
    main()
