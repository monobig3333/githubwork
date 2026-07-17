#!/usr/bin/env python3
"""
sys_id を指定して Athena (snow_prd.v_em_event) から1件取得して JSON表示するスクリプト

前提: AWS認証情報がシェル環境にセット済みであること (source ../setup.sh)

使用例:
  python get_event_athena.py 9059de25c3198710e7339b677a013161
"""

import sys
import time
import json
import argparse

import boto3

REGION    = "ap-northeast-1"
DATABASE  = "snow_prd"
TABLE     = "v_em_event"
WORKGROUP = "primary"  # ManagedQueryResultsConfiguration 有効。OutputLocation指定不要


def run_query(client, sys_id: str) -> list[dict]:
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
        raise RuntimeError(f"クエリ失敗 ({state}): {reason}")

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

    return rows


def main():
    parser = argparse.ArgumentParser(description="v_em_event (Athena/snow_prd) 1件表示")
    parser.add_argument("ssys_id", help="表示する sys_id")
    args = parser.parse_args()

    client = boto3.client("athena", region_name=REGION)
    results = run_query(client, args.ssys_id)

    if not results:
        print(f"見つかりません: sys_id={args.ssys_id}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(results[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
