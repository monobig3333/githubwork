#!/usr/bin/env python3
"""
ServiceNow CI バインディングルール / アラート変換ルール 仕様チェックツール。

大半の CIバインドルールは sa_event_rule に格納されている（主要テーブル）。
以下のテーブルを対象にチェックする:
  - sa_event_rule          : イベントルール（CIバインディング・フィールドマッピング等）← 主要
  - em_rule_xml            : matchRule（CIバインディング）の完全性チェック
  - em_mapping_rule        : フィールドマッピングルールの完全性チェック
  - u_transformation_rule  : カスタムアラート変換ルールの完全性チェック

使用例:
  python check_ci_bindings.py                              # サマリー表示（全テーブル）
  python check_ci_bindings.py --output detail              # NG/WARN 詳細表示
  python check_ci_bindings.py --output detail --show-ok    # 全項目表示
  python check_ci_bindings.py --output json                # JSON出力
  python check_ci_bindings.py --table sa_event_rules       # sa_event_rule のみ
  python check_ci_bindings.py --table match_rules          # em_rule_xml(matchRule) のみ
  python check_ci_bindings.py --table mapping_rules        # em_mapping_rule のみ
  python check_ci_bindings.py --table transformation_rules # u_transformation_rule のみ
  python check_ci_bindings.py --category ログ変換          # カテゴリ絞り込み
"""

import sys
import os
import json
import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# cichk は本番環境 (biglobeprod) を対象とする
os.environ["SNOW_BASE_URL"] = "https://biglobeprod.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api/credentials/biglobeprod/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client
from ci_validators import (
    RuleResult,
    validate_sa_event_rule,
    validate_match_rule, validate_mapping_rule, validate_transformation_rule,
    check_duplicate_orders_mapping, check_duplicate_orders_transformation,
    _gs, _xt,
)

SA_EVENT_RULE_FIELDS = [
    "sys_id", "name", "active", "order", "type", "description",
    "ems_source", "conditions", "ci_class",
]

TRANSFORMATION_FIELDS = [
    "sys_id", "u_rule_name", "u_order", "u_category",
    "u_active", "u_table_name", "u_conditions", "u_description", "u_data_type",
]


def fetch_table(token: str, table: str, fields: list[str],
                query: str = "", limit: int = 2000) -> list[dict]:
    try:
        return snow_client.table_get(token, table, {
            "sysparm_limit":         limit,
            "sysparm_query":         query,
            "sysparm_display_value": "true",
            "sysparm_fields":        ",".join(fields),
        })
    except Exception as exc:
        print(f"  [{table}] 取得失敗: {exc}", file=sys.stderr)
        return []


def parse_rule_xml_records(recs: list[dict]) -> list[dict]:
    """em_rule_xml から matchRule のみ抽出して返す。"""
    result: list[dict] = []
    for rec in recs:
        xml_str = _gs(rec, "rule_xml")
        if not xml_str:
            continue
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            continue
        if root.tag != "matchRule":
            continue
        mf_list = []
        for mf in root.findall("matchFields"):
            fn = _xt(mf, "field")
            if fn:
                mf_list.append({"field": fn, "regex": _xt(mf, "regex")})
        result.append({
            "sys_id":       _gs(rec, "sys_id"),
            "name":         _xt(root, "displayName") or _xt(root, "name"),
            "source":       _xt(root, "ems"),
            "ci_type":      _xt(root, "ciTypeName"),
            "ignore":       _xt(root, "ignore"),
            "match_fields": mf_list,
        })
    return result


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def print_summary(sa_results: list[RuleResult],
                  match_results: list[RuleResult],
                  mapping_results: list[RuleResult],
                  trans_results: list[RuleResult],
                  dup_mapping: list[str],
                  dup_trans: list[str]) -> None:
    def _count(results: list[RuleResult]) -> dict:
        c: dict = defaultdict(int)
        for r in results:
            c[r.status] += 1
        return c

    print(f"\n{'='*70}")
    print("CI バインディング / アラート変換ルール チェック結果サマリー")
    print(f"{'='*70}")

    if sa_results:
        sc = _count(sa_results)
        print(f"\n[sa_event_rule (イベントルール)] ← 主要  総件数: {len(sa_results)}")
        print(f"  OK: {sc['OK']}  NG: {sc['NG']}  WARN: {sc['WARN']}")

    if match_results:
        mc = _count(match_results)
        print(f"\n[matchRule (CIバインディング / em_rule_xml)]  総件数: {len(match_results)}")
        print(f"  OK: {mc['OK']}  NG: {mc['NG']}  WARN: {mc['WARN']}")

    if mapping_results:
        ec = _count(mapping_results)
        print(f"\n[em_mapping_rule (フィールドマッピング)]  総件数: {len(mapping_results)}")
        print(f"  OK: {ec['OK']}  NG: {ec['NG']}  WARN: {ec['WARN']}")
        if dup_mapping:
            print(f"  ※ order値の重複: {len(dup_mapping)} 件")
            for d in dup_mapping[:3]:
                print(f"    - {d[:100]}")
            if len(dup_mapping) > 3:
                print(f"    ... 他 {len(dup_mapping)-3} 件")

    if trans_results:
        tc = _count(trans_results)
        print(f"\n[u_transformation_rule (アラート変換ルール)]  総件数: {len(trans_results)}")
        print(f"  OK: {tc['OK']}  NG: {tc['NG']}  WARN: {tc['WARN']}")
        # カテゴリ別集計
        by_cat: dict = defaultdict(lambda: defaultdict(int))
        for r in trans_results:
            # status は RuleResult なので元のカテゴリを rec から取れないため
            # ここでは status 集計のみ（detail で確認）
            by_cat[r.table][r.status] += 1
        if dup_trans:
            print(f"  ※ order値の重複: {len(dup_trans)} 件")

    all_results = sa_results + match_results + mapping_results + trans_results
    total_ng   = sum(r.ng_count for r in all_results)
    total_warn = sum(1 for r in all_results if r.status == "WARN")
    print(f"\n{'='*70}")
    print(f"合計NG項目数: {total_ng}  WARN件数: {total_warn}")


def print_category_summary(trans_recs: list[dict],
                            trans_results: list[RuleResult]) -> None:
    """u_transformation_rule のカテゴリ別集計を表示する。"""
    cat_stat: dict = defaultdict(lambda: {"total": 0, "OK": 0, "NG": 0, "WARN": 0})
    for rec, r in zip(trans_recs, trans_results):
        cat = _gs(rec, "u_category") or "(未分類)"
        cat_stat[cat]["total"] += 1
        cat_stat[cat][r.status] += 1
    print(f"\n  {'カテゴリ':<20} {'総数':>5} {'OK':>5} {'NG':>5} {'WARN':>5}")
    print("  " + "-" * 42)
    for cat, s in sorted(cat_stat.items()):
        print(f"  {cat:<20} {s['total']:>5} {s['OK']:>5} {s['NG']:>5} {s['WARN']:>5}")


def print_ng_list(results: list[RuleResult]) -> None:
    ng = [r for r in results if r.status != "OK"]
    if not ng:
        print("\n--- NG/WARN件数: 0  すべてのルールが正常です ---")
        return
    print(f"\n--- NG / WARN: {len(ng)} 件 ---")
    for r in ng:
        ng_fields = [c.field for c in r.checks if c.status in ("NG", "WARN")]
        print(f"  [{r.status}] {r.table}  name={r.name!r}"
              f"  sys_id={r.sys_id}  項目: {', '.join(ng_fields)}")


def print_details(results: list[RuleResult], show_ok: bool) -> None:
    print(f"\n{'='*70}")
    print("詳細結果 (NG/WARN のみ表示。--show-ok で全項目表示)")
    print(f"{'='*70}")
    for r in results:
        if not show_ok and r.status == "OK":
            continue
        mark = "✓" if r.status == "OK" else "✗" if r.status == "NG" else "△"
        print(f"\n[{mark}] {r.status}  {r.table}  name={r.name!r}  sys_id={r.sys_id}")
        for c in r.checks:
            if c.status == "OK" and not show_ok:
                continue
            icon = " OK " if c.status == "OK" else " NG " if c.status == "NG" else "WARN"
            msg = f"  ← {c.message}" if c.message else ""
            print(f"  [{icon}] {c.field}: 期待={c.expected!r}  実際={c.actual!r}{msg}")


def output_json(sa_results: list[RuleResult],
                match_results: list[RuleResult],
                mapping_results: list[RuleResult],
                trans_results: list[RuleResult]) -> None:
    def _s(r: RuleResult) -> dict:
        return {
            "sys_id": r.sys_id, "name": r.name, "table": r.table,
            "status": r.status, "ng_count": r.ng_count,
            "checks": [{"field": c.field, "status": c.status,
                        "expected": c.expected, "actual": c.actual,
                        "message": c.message} for c in r.checks],
        }
    print(json.dumps({
        "sa_event_rules":       [_s(r) for r in sa_results],
        "match_rules":          [_s(r) for r in match_results],
        "mapping_rules":        [_s(r) for r in mapping_results],
        "transformation_rules": [_s(r) for r in trans_results],
    }, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ServiceNow CI バインディング / アラート変換ルール 仕様チェック",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--table",
                        choices=["all", "sa_event_rules", "match_rules",
                                 "mapping_rules", "transformation_rules"],
                        default="all",
                        help="チェック対象 (default: all)")
    parser.add_argument("--category", default="",
                        help="u_transformation_rule のカテゴリ絞り込み")
    parser.add_argument("--output",
                        choices=["summary", "detail", "json"],
                        default="summary",
                        help="出力形式 summary/detail/json (default: summary)")
    parser.add_argument("--show-ok", action="store_true",
                        help="detail 時に OK 項目も表示する")
    args = parser.parse_args()

    print("OAuth トークンを取得中...", file=sys.stderr)
    try:
        token = snow_client.get_token()
    except Exception as exc:
        print(f"認証失敗: {exc}", file=sys.stderr)
        sys.exit(1)

    sa_results: list[RuleResult] = []
    match_results: list[RuleResult] = []
    mapping_results: list[RuleResult] = []
    mapping_recs: list[dict] = []
    trans_results: list[RuleResult] = []
    trans_recs: list[dict] = []

    if args.table in ("all", "sa_event_rules"):
        print("sa_event_rule を取得中...", file=sys.stderr)
        sa_recs = fetch_table(token, "sa_event_rule", SA_EVENT_RULE_FIELDS,
                              limit=2000)
        print(f"  sa_event_rule: {len(sa_recs)} 件", file=sys.stderr)
        sa_results = [validate_sa_event_rule(r) for r in sa_recs]

    if args.table in ("all", "match_rules"):
        print("em_rule_xml を取得中...", file=sys.stderr)
        rule_xml_recs = fetch_table(token, "em_rule_xml", ["sys_id", "name", "rule_xml"])
        match_parsed = parse_rule_xml_records(rule_xml_recs)
        print(f"  matchRule: {len(match_parsed)} 件", file=sys.stderr)
        match_results = [validate_match_rule(r) for r in match_parsed]

    if args.table in ("all", "mapping_rules"):
        print("em_mapping_rule を取得中...", file=sys.stderr)
        mapping_recs = fetch_table(token, "em_mapping_rule", [
            "sys_id", "name", "active", "order", "mapping_type",
            "from_field", "to_field", "alert_field", "value",
        ])
        print(f"  em_mapping_rule: {len(mapping_recs)} 件", file=sys.stderr)
        mapping_results = [validate_mapping_rule(r) for r in mapping_recs]

    if args.table in ("all", "transformation_rules"):
        print("u_transformation_rule を取得中...", file=sys.stderr)
        query = f"u_category={args.category}" if args.category else ""
        trans_recs = fetch_table(token, "u_transformation_rule",
                                 TRANSFORMATION_FIELDS, query)
        print(f"  u_transformation_rule: {len(trans_recs)} 件", file=sys.stderr)
        trans_results = [validate_transformation_rule(r) for r in trans_recs]

    dup_mapping = check_duplicate_orders_mapping(mapping_results, mapping_recs)
    dup_trans   = check_duplicate_orders_transformation(trans_results, trans_recs)
    all_results = sa_results + match_results + mapping_results + trans_results

    print("チェック完了", file=sys.stderr)

    if args.output == "json":
        output_json(sa_results, match_results, mapping_results, trans_results)
    elif args.output == "detail":
        print_summary(sa_results, match_results, mapping_results, trans_results,
                      dup_mapping, dup_trans)
        if trans_recs:
            print_category_summary(trans_recs, trans_results)
        print_details(all_results, args.show_ok)
    else:
        print_summary(sa_results, match_results, mapping_results, trans_results,
                      dup_mapping, dup_trans)
        if trans_recs:
            print_category_summary(trans_recs, trans_results)
        print_ng_list(all_results)


if __name__ == "__main__":
    main()
