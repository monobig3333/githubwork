#!/usr/bin/env python3
"""
Athena (snow_prd.v_em_event) から条件に合うイベントを一括取得し、
biglobedev の em_event へ新規登録するスクリプト

前提: AWS認証情報がシェル環境にセット済みであること (source ../setup.sh)

使用例:
  # Zabbix イベント 7/1〜7/17 を一括送信
  source ./setup.sh && python3 mkevnet2dev/bulk_create_events.py

  # 件数確認のみ（送信しない）
  source ./setup.sh && python3 mkevnet2dev/bulk_create_events.py --dry-run

  # 送信件数を制限（テスト用）
  source ./setup.sh && python3 mkevnet2dev/bulk_create_events.py --limit 10
"""

import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SNOW_BASE_URL"] = "https://biglobedev.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api-test/biglobedev/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

REGION    = "ap-northeast-1"
DATABASE  = "snow_prd"
WORKGROUP = "primary"

# 新規登録時に含めないフィールド
EXCLUDE_FIELDS = {
    "sys_id", "sys_created_on", "sys_created_by",
    "sys_updated_on", "sys_updated_by", "sys_mod_count", "sys_tags",
    "alert", "event_rule", "processed",
    "processing_notes", "processing_duration", "processing_sn_node",
    "bucket", "classification",
}

# 送信対象クエリ（変更可）
ATHENA_QUERY = """
    SELECT * FROM v_em_event
    WHERE source = 'Zabbix'
      AND sys_created_on >= '2026-07-01 00:00:00'
      AND sys_created_on <  '2026-07-18 00:00:00'
    ORDER BY sys_created_on
"""


def fetch_from_athena(limit: int = 0) -> list[dict]:
    athena = boto3.client("athena", region_name=REGION)
    query = ATHENA_QUERY
    if limit > 0:
        query = query.rstrip() + f"\nLIMIT {limit}"

    print("Athena クエリ実行中...", flush=True)
    qid = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": DATABASE},
        WorkGroup=WORKGROUP,
    )["QueryExecutionId"]
    print(f"  QueryExecutionId: {qid}", flush=True)

    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)

    if state != "SUCCEEDED":
        reason = status.get("StateChangeReason", "")
        raise RuntimeError(f"Athena クエリ失敗 ({state}): {reason}")

    events = []
    columns = None
    paginator = athena.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=qid):
        data_rows = page["ResultSet"]["Rows"]
        if columns is None:
            columns = [c["VarCharValue"] for c in data_rows[0]["Data"]]
            data_rows = data_rows[1:]
        for row in data_rows:
            values = [d.get("VarCharValue") for d in row["Data"]]
            events.append(dict(zip(columns, values)))

    print(f"  取得完了: {len(events)} 件", flush=True)
    return events


def build_payload(event: dict) -> dict:
    payload = {k: v for k, v in event.items() if k not in EXCLUDE_FIELDS and v}
    payload["state"] = "Ready"
    return payload


def main():
    parser = argparse.ArgumentParser(description="Athena の em_event を biglobedev へ一括登録")
    parser.add_argument("--dry-run", action="store_true", help="送信せず件数と先頭5件のペイロードを表示")
    parser.add_argument("--limit",   type=int, default=0, help="取得件数を制限（0=全件）")
    parser.add_argument("--workers", type=int, default=10, help="並列スレッド数（デフォルト: 10）")
    args = parser.parse_args()

    events = fetch_from_athena(limit=args.limit)

    if args.dry_run:
        import json
        print(f"\n送信対象: {len(events)} 件（--dry-run のため送信しません）")
        print("\n先頭5件のペイロード:")
        for ev in events[:5]:
            payload = build_payload(ev)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print()
        return

    print(f"\nbiglobedev に {len(events)} 件を送信中 (workers={args.workers})...", flush=True)
    token = snow_client.get_token()

    def send(ev):
        return snow_client.table_post(token, "em_event", build_payload(ev))

    ok = ng = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(send, ev): ev for ev in events}
        for future in as_completed(futures):
            try:
                future.result()
                ok += 1
            except Exception as e:
                ng += 1
                print(f"  送信失敗: {e}", flush=True)
            if (ok + ng) % 200 == 0:
                print(f"  送信済み: {ok+ng}/{len(events)} (成功 {ok} / 失敗 {ng})", flush=True)

    print(f"\n完了: 成功 {ok} 件 / 失敗 {ng} 件")


if __name__ == "__main__":
    main()
