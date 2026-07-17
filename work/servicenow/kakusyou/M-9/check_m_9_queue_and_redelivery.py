"""要件M-9: 全AZ（3AZ）停止時の挙動・復旧後再送確認

【テスト内容】
  ①3AZ全てのMIDサーバを停止
  ②イベントのキューイング状況を確認
  ③全AZを復旧、キューイングされたイベントが漏れなく転送されることを確認

【合否判定基準】
  ・復旧後にキューイングされたイベントが漏れなく転送されること
  ・または全AZ停止時にアラートが発報されること

【実行】
  停止操作と起動操作は手動で行い、その間に投入したイベントが
  最終的に ServiceNow 側で受信されているかを確認する。
"""
import argparse
import json
import logging
import sys
import time
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common.config import settings  # noqa: E402
from _common.servicenow_auth import authorized_headers  # noqa: E402
from _common.snow_client import SnowClient  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def inject_event_via_mid_endpoint(message_key: str, mid_endpoint: str) -> bool:
    """MIDサーバ経由でのイベント投入。停止中は失敗する想定。"""
    payload = {
        "source": "mid-test-M-9",
        "node": f"m9-{message_key}",
        "type": "All AZ Down",
        "severity": "2",
        "message_key": message_key,
        "description": f"all az down test {message_key}",
    }
    try:
        r = requests.post(mid_endpoint, json=payload,
                          headers=authorized_headers(), timeout=10)
        return r.status_code in (200, 201)
    except requests.RequestException:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mid-endpoint", default=f"{settings.snow_base_url}/api/now/table/em_event",
                        help="MIDサーバ経由送信先（ALB or em_event）")
    parser.add_argument("--injection-count", type=int, default=100)
    parser.add_argument("--inject-only", action="store_true",
                        help="投入のみ（その後の確認はせず終了）。AZ停止状態で使う想定")
    parser.add_argument("--verify-only", action="store_true",
                        help="既存の sent_keys.txt で受信確認のみ行う")
    args = parser.parse_args()

    run_dir = Path(__file__).parent
    keys_file = run_dir / "sent_keys.txt"

    if not args.verify_only:
        sent_keys: list[str] = []
        for i in range(args.injection_count):
            key = f"m9-{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}-{i:04d}"
            ok = inject_event_via_mid_endpoint(key, args.mid_endpoint)
            logger.info("inject key=%s ok=%s", key, ok)
            sent_keys.append(key)
            time.sleep(0.5)
        keys_file.write_text("\n".join(sent_keys))
        logger.info("Wrote %d keys to %s", len(sent_keys), keys_file)
        if args.inject_only:
            return

    # 復旧後の受信確認
    if not keys_file.exists():
        raise RuntimeError(f"{keys_file} が存在しません。先に投入を実行してください")
    sent_keys = [k for k in keys_file.read_text().splitlines() if k]

    client = SnowClient()
    received = client.get_table(
        "em_event",
        sysparm_query="source=mid-test-M-9",
        sysparm_fields="message_key",
        sysparm_limit=1000000,
    )
    received_keys = {r["message_key"] for r in received if r.get("message_key")}

    missing = [k for k in sent_keys if k not in received_keys]
    result = {
        "sent": len(sent_keys),
        "received": len(received_keys),
        "missing_count": len(missing),
        "missing_sample": missing[:20],
    }
    (run_dir / "result_m_9.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Result: %s", result)

    assert not missing, f"復旧後も欠損 {len(missing)} 件"


if __name__ == "__main__":
    main()
