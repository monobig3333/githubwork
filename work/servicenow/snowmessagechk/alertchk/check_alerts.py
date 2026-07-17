#!/usr/bin/env python3
"""
ServiceNow em_alert テーブルのアラートをイベントルール仕様書に基づいてチェックする。

使用例:
  python check_alerts.py                            # サマリー表示（全件）
  python check_alerts.py --output detail            # NG項目の詳細表示
  python check_alerts.py --output detail --show-ok  # OK項目も含めて全表示
  python check_alerts.py --output json              # JSON出力
  python check_alerts.py --limit 200                # 200件だけ
  python check_alerts.py --source iMark_AWS         # 変換後ソースで絞り込み
  python check_alerts.py --query "active=true"      # sysparm_query フィルタ
"""

import sys
import os
import json
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# alertchk は本番環境 (biglobeprod) を対象とする
os.environ["SNOW_BASE_URL"] = "https://biglobeprod.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api/credentials/biglobeprod/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client
from alert_validators import validate_alert, AlertResult, SEVERITY_MAP

# em_alert から取得するフィールド一覧
# ※ u_type_big 等のカスタムフィールド名は実際のインスタンスに合わせて調整すること
FETCH_FIELDS = [
    "sys_id", "node", "type", "source", "resource", "metric_name",
    "event_class", "message_key", "severity", "description",
    "additional_info", "classification", "cmdb_ci",
    "u_matched_rules", "u_type_category",
    "u_monitoring_item_number", "u_message_transform_state",
    "anomaly_alert", "u_message_group", "u_monitoring_type",
]

PAGE_SIZE = 1000


def fetch_alerts(max_records: int, query: str) -> list[dict]:
    """ページネーションで em_alert を全件取得する。max_records=0 なら上限なし。"""
    token = snow_client.get_token()
    all_alerts: list[dict] = []
    offset = 0

    while True:
        remaining = max_records - len(all_alerts) if max_records else PAGE_SIZE
        page_size = min(PAGE_SIZE, remaining) if max_records else PAGE_SIZE

        page = snow_client.table_get(token, "em_alert", {
            "sysparm_limit":         page_size,
            "sysparm_offset":        offset,
            "sysparm_orderby":       "sys_created_on",
            "sysparm_query":         query,
            "sysparm_display_value": "true",
            "sysparm_fields":        ",".join(FETCH_FIELDS),
        })
        all_alerts.extend(page)
        print(f"  取得中: {len(all_alerts)} 件...", file=sys.stderr)

        if len(page) < page_size:
            break
        if max_records and len(all_alerts) >= max_records:
            break

        offset += page_size

    return all_alerts


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def _sev_label(val: str) -> str:
    from alert_validators import _normalize_sev
    n = _normalize_sev(val)
    lbl = SEVERITY_MAP.get(n, "")
    return f"{val}({lbl})" if lbl else val


def print_summary(results: list[AlertResult]) -> None:
    by_source: dict = defaultdict(lambda: {"OK": 0, "NG": 0, "UNKNOWN_SOURCE": 0})
    for r in results:
        by_source[r.source_type][r.status] += 1

    total_ok = sum(1 for r in results if r.status == "OK")
    total_ng = sum(1 for r in results if r.status == "NG")
    total_uk = sum(1 for r in results if r.status == "UNKNOWN_SOURCE")

    print(f"\n{'='*66}")
    print(f"アラートチェック結果サマリー  総件数: {len(results)}"
          f"  OK: {total_ok}  NG: {total_ng}  不明ソース: {total_uk}")
    print(f"{'='*66}")
    print(f"{'変換後ソース':<36} {'OK':>5} {'NG':>5} {'不明':>5}")
    print("-" * 55)
    for src, counts in sorted(by_source.items()):
        print(f"{src:<36} {counts['OK']:>5} {counts['NG']:>5} {counts['UNKNOWN_SOURCE']:>5}")


def print_ng_list(results: list[AlertResult]) -> None:
    ng_results = [r for r in results if r.status != "OK"]
    if not ng_results:
        print("\n--- NG件数: 0  すべてのアラートが仕様と一致しています ---")
        return
    print(f"\n--- NG / 不明ソース: {len(ng_results)} 件 ---")
    for r in ng_results:
        ng_fields = [c.field for c in r.checks if c.status == "NG"]
        print(f"  [{r.status}] sys_id={r.sys_id}  ({r.source_type})"
              f"  NG項目: {', '.join(ng_fields)}")


def print_details(results: list[AlertResult], show_ok: bool) -> None:
    print(f"\n{'='*66}")
    print("詳細結果 (NGのみ表示。--show-ok で全項目表示)")
    print(f"{'='*66}")
    for r in results:
        if not show_ok and r.status == "OK":
            continue
        mark = "✓" if r.status == "OK" else "✗" if r.status == "NG" else "?"
        print(f"\n[{mark}] {r.status}  sys_id={r.sys_id}"
              f"  source={r.source!r}  ({r.source_type})")
        for c in r.checks:
            if c.status == "OK" and not show_ok:
                continue
            icon = " OK " if c.status == "OK" else " NG " if c.status == "NG" else "WARN"
            msg = f"  ← {c.message}" if c.message else ""
            print(f"  [{icon}] {c.field}: 期待={c.expected!r}  実際={c.actual!r}{msg}")


def output_json(results: list[AlertResult]) -> None:
    out = []
    for r in results:
        out.append({
            "sys_id":      r.sys_id,
            "source":      r.source,
            "source_type": r.source_type,
            "status":      r.status,
            "ng_count":    r.ng_count,
            "checks": [
                {
                    "field":    c.field,
                    "status":   c.status,
                    "expected": c.expected,
                    "actual":   c.actual,
                    "message":  c.message,
                }
                for c in r.checks
            ],
        })
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ServiceNow em_alert 仕様チェック（イベントルール設計書準拠）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--limit",   type=int, default=0,
                        help="最大取得件数 (default: 0=全件)")
    parser.add_argument("--query",   default="",
                        help="sysparm_query フィルタ (例: active=true)")
    parser.add_argument("--source",  default="",
                        help="変換後ソース値で絞り込み (例: iMark_AWS, HW監視)")
    parser.add_argument("--output",  choices=["summary", "detail", "json"],
                        default="summary",
                        help="出力形式 summary/detail/json (default: summary)")
    parser.add_argument("--show-ok", action="store_true",
                        help="detail 時に OK 項目も表示する")
    args = parser.parse_args()

    query = args.query
    if args.source:
        src_filter = f"source={args.source}"
        query = f"{query}^{src_filter}" if query else src_filter

    print("OAuth トークンを取得中...", file=sys.stderr)
    try:
        alerts = fetch_alerts(args.limit, query)
    except Exception as exc:
        print(f"アラート取得失敗: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"取得件数: {len(alerts)} 件  チェック中...", file=sys.stderr)
    results = [validate_alert(a) for a in alerts]

    if args.output == "json":
        output_json(results)
    elif args.output == "detail":
        print_summary(results)
        print_details(results, args.show_ok)
    else:
        print_summary(results)
        print_ng_list(results)


if __name__ == "__main__":
    main()
