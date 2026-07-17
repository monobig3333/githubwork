"""要件4-1: 構成情報データ件数上限確認（100万件）

【テスト内容】
  ①100万件の構成情報データをインポート
  ②全件正常登録されたことを確認
  ③登録後の検索・参照性能を計測

【合否判定基準】
  ・1,000,000件のデータ保持が可能
  ・登録後の検索応答時間が許容範囲内（3秒以内）

【方式】
  ServiceNow Import Set API (sys_import.do) に xlsx を分割アップロード。
  REST直接 insert は1件ずつでレートリミットに引っかかりやすいため Import Set を採用。
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import openpyxl

# _common を import 可能に
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common.snow_client import SnowClient  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TOTAL_ROWS = 1_000_000
ROWS_PER_FILE = 50_000   # Import Set 1回あたり
IMPORT_SET_TABLE = "u_perf_cmdb_load"  # 事前に作成済みの想定
TRANSFORM_MAP = "perf_cmdb_load_to_cmdb_ci"  # 同上
RESPONSE_THRESHOLD_SEC = 3.0


def generate_xlsx(path: Path, start: int, count: int) -> None:
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("data")
    ws.append(["name", "u_resource_id", "asset_tag", "category", "sys_class_name"])
    for i in range(start, start + count):
        ws.append([f"PERF-CI-{i:08d}", f"perf-res-{i:08d}",
                   f"AT{i:08d}", "Hardware", "cmdb_ci_server"])
    wb.save(str(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=TOTAL_ROWS)
    parser.add_argument("--chunk", type=int, default=ROWS_PER_FILE)
    parser.add_argument("--import-set", default=IMPORT_SET_TABLE)
    parser.add_argument("--skip-load", action="store_true",
                        help="ファイル生成のみ実行（投入はスキップ）")
    args = parser.parse_args()

    client = SnowClient()
    chunks = (args.total + args.chunk - 1) // args.chunk
    work_dir = Path(__file__).parent / "tmp_chunks"
    work_dir.mkdir(exist_ok=True)
    result_path = Path(__file__).parent / "result_4_1.json"

    upload_times = []
    overall_start = time.perf_counter()

    for c in range(chunks):
        start = c * args.chunk
        count = min(args.chunk, args.total - start)
        xlsx_path = work_dir / f"chunk_{c:04d}.xlsx"
        logger.info("Generating chunk %d (%d rows)", c + 1, count)
        generate_xlsx(xlsx_path, start, count)

        if args.skip_load:
            continue

        t0 = time.perf_counter()
        resp = client.import_xlsx(args.import_set, str(xlsx_path), transform=True)
        elapsed = time.perf_counter() - t0
        upload_times.append(elapsed)
        logger.info("Chunk %d/%d uploaded in %.2fs (status=%s)",
                    c + 1, chunks, elapsed,
                    resp.get("import_set", {}).get("transform_map_results") or resp)
        xlsx_path.unlink()

    overall = time.perf_counter() - overall_start
    logger.info("All uploaded in %.1fs", overall)

    # 検索性能計測
    query_times = []
    for q in ["sysparm_query=u_resource_id=perf-res-00500000",
              "sysparm_query=nameSTARTSWITHPERF-CI&sysparm_limit=100"]:
        t0 = time.perf_counter()
        client.get_table("cmdb_ci_server", **{"sysparm_query": q.split("=", 1)[1] if "=" in q else q})
        query_times.append(time.perf_counter() - t0)

    # 総件数確認
    rows = client.get_table("cmdb_ci_server",
                            sysparm_query="nameSTARTSWITHPERF-CI",
                            sysparm_count="true",
                            sysparm_limit=1)
    result = {
        "target_total": args.total,
        "chunks": chunks,
        "upload_elapsed_sec": overall,
        "upload_avg_per_chunk_sec": sum(upload_times)/len(upload_times) if upload_times else None,
        "query_times_sec": query_times,
        "post_load_query_count_response": rows,
    }
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Result: %s", result)

    assert max(query_times) < RESPONSE_THRESHOLD_SEC, \
        f"検索応答 {max(query_times):.2f}s が閾値 {RESPONSE_THRESHOLD_SEC}s 超過"


if __name__ == "__main__":
    main()
