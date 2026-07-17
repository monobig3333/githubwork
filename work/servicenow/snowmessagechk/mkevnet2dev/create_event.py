#!/usr/bin/env python3
"""
Athena (snow_prd.v_em_event) から sys_id 指定で1件取得し、
time_of_event を現在時刻に更新して ServiceNow biglobedev インスタンスの
em_event テーブルへ新規登録するスクリプト

前提: AWS認証情報がシェル環境にセット済みであること (source ../setup.sh)
      biglobedev の API キーは AWS Secrets Manager
      servicenow/api-test/biglobedev/admin-ai-api (bgl-big4180-prd アカウント) に格納

使用例:
  python create_event.py <event_sysid>
  python create_event.py <event_sysid> --dry-run
"""

import sys
import os
import time
import json
import argparse
import datetime

import boto3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# mkevnet2dev は開発インスタンス (biglobedev) への登録を対象とする
os.environ["SNOW_BASE_URL"] = "https://biglobedev.service-now.com"
os.environ["SNOW_SECRET_NAME"] = "servicenow/api-test/biglobedev/admin-ai-api"
os.environ["SNOW_CLIENT_ID"] = ""
os.environ["SNOW_CLIENT_SECRET"] = ""

import snow_client

REGION    = "ap-northeast-1"
DATABASE  = "snow_prd"
TABLE     = "v_em_event"
WORKGROUP = "primary"  # ManagedQueryResultsConfiguration 有効。OutputLocation指定不要

# 新規登録時に含めない列（ServiceNow が自動採番・管理する項目）
EXCLUDE_FIELDS = {
    "sys_id", "sys_created_on", "sys_created_by",
    "sys_updated_on", "sys_updated_by", "sys_mod_count", "sys_tags",
    # 処理済みメタデータ — devで再処理させるために除外
    "alert", "event_rule", "processed",
    "processing_notes", "processing_duration", "processing_sn_node",
    "bucket", "classification",
}


def fetch_event_from_athena(client, sys_id: str) -> dict:
    escaped = sys_id.replace("'", "''")
    query = f"SELECT * FROM {TABLE} WHERE sys_id = '{escaped}'"

    exec_id = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": DATABASE},
        WorkGroup=WORKGROUP,
    )["QueryExecutionId"]

    while True:
        status = client.get_query_execution(QueryExecutionId=exec_id)["QueryExecution"]["Status"]
        state = status["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)

    if state != "SUCCEEDED":
        reason = status.get("StateChangeReason", "")
        raise RuntimeError(f"Athena クエリ失敗 ({state}): {reason}")

    rows = []
    columns = None
    paginator = client.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=exec_id):
        data_rows = page["ResultSet"]["Rows"]
        if columns is None:
            columns = [c["VarCharValue"] for c in data_rows[0]["Data"]]
            data_rows = data_rows[1:]
        for row in data_rows:
            values = [d.get("VarCharValue") for d in row["Data"]]
            rows.append(dict(zip(columns, values)))

    if not rows:
        raise RuntimeError(f"見つかりません: sys_id={sys_id}")
    return rows[0]


def build_payload(event: dict) -> dict:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {k: v for k, v in event.items() if k not in EXCLUDE_FIELDS and v is not None}
    payload["time_of_event"] = now_str
    payload["state"] = "Ready"  # Processed のまま登録するとイベントエンジンにスキップされる
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Athena の em_event を元に biglobedev へイベント新規登録"
    )
    parser.add_argument("event_sysid", help="元にする em_event の sys_id (Athena snow_prd.v_em_event)")
    parser.add_argument("--dry-run", action="store_true", help="登録せずペイロードのみ表示")
    args = parser.parse_args()

    print(f"Athena から取得中: sys_id={args.event_sysid}", file=sys.stderr)
    athena = boto3.client("athena", region_name=REGION)
    event = fetch_event_from_athena(athena, args.event_sysid)

    payload = build_payload(event)
    print("登録ペイロード:", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)

    if args.dry_run:
        print("--dry-run のため登録は行いません。", file=sys.stderr)
        return

    print(f"\n登録先: {os.environ['SNOW_BASE_URL']} (em_event)", file=sys.stderr)
    token = snow_client.get_token()
    result = snow_client.table_post(token, "em_event", payload)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n登録完了: sys_id={result.get('sys_id')}", file=sys.stderr)


if __name__ == "__main__":
    main()
