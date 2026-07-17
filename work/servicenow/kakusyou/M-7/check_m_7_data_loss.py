"""要件M-7: AZ停止中のデータロスなし確認

【テスト内容】
  ①AZ停止前後のイベント送信数と受信数をログで突合
  ②イベントの欠損・重複が発生していないことを確認
  ③1AZ停止・2AZ停止それぞれで実施

【合否判定基準】
  ・AZ停止前後でイベント欠損なし
  ・重複登録なし

【入力】
  - JMeter result.jtl（送信側、message_key を含む csv）
  - ServiceNow em_event テーブル（受信側、Table API で取得）

【出力】
  result_m_7.json … 欠損件数 / 重複件数 / 突合詳細
"""
import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common.snow_client import SnowClient  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _extract_message_keys_from_jtl(jtl_path: Path) -> set[str]:
    """JMeter result.jtl のリクエストボディから message_key を抽出"""
    df = pd.read_csv(jtl_path)
    if "label" not in df.columns:
        raise RuntimeError("JTL に label 列がありません")
    success = df[df.get("success", True) == True]
    # JTL 自体にはbodyが入らないことが多いので、別途 message_keyログを推奨
    # ここでは label に key を含む規約と仮定
    keys = set()
    for v in success.get("URL", []):
        # URLに ?key=... の形なら抽出
        pass
    return keys


def _extract_keys_from_csv(csv_path: Path, key_col: str = "message_key") -> set[str]:
    df = pd.read_csv(csv_path)
    return set(df[key_col].dropna().astype(str).tolist())


def _fetch_received_keys(source: str) -> list[str]:
    """ServiceNow em_event から source 一致レコードの message_key を取得"""
    client = SnowClient()
    results = client.get_table(
        "em_event",
        sysparm_query=f"source={source}",
        sysparm_fields="message_key",
        sysparm_limit=1000000,
    )
    return [r["message_key"] for r in results if r.get("message_key")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sent-csv", type=Path, required=True,
                        help="送信側のCSV（message_key列を含む）")
    parser.add_argument("--source", required=True,
                        help="ServiceNow em_event.source の値")
    args = parser.parse_args()

    sent = _extract_keys_from_csv(args.sent_csv)
    logger.info("Sent count: %d", len(sent))

    received = _fetch_received_keys(args.source)
    received_counter = Counter(received)
    received_set = set(received)
    logger.info("Received unique: %d / total rows: %d", len(received_set), len(received))

    missing = sent - received_set
    extra = received_set - sent
    duplicates = {k: c for k, c in received_counter.items() if c > 1}

    result = {
        "sent": len(sent),
        "received_unique": len(received_set),
        "received_total": len(received),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "duplicate_keys": len(duplicates),
        "missing_sample": list(missing)[:20],
        "extra_sample": list(extra)[:20],
    }
    out_path = Path(__file__).parent / "result_m_7.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Result: %s", result)

    assert not missing, f"欠損 {len(missing)} 件"
    assert not duplicates, f"重複 {len(duplicates)} key"


if __name__ == "__main__":
    main()
