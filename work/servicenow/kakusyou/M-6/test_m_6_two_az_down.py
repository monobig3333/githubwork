"""要件M-6: 2AZ停止時のイベント転送継続確認

【テスト内容】
  ①イベントを継続投入した状態で2AZのMIDサーバを停止
  ②残り1AZでイベント転送が継続されることを確認
  ③Playwrightでアラームビューワーへの描画継続を確認

【合否判定基準】
  ・2AZ停止後も残り1AZでイベント転送が継続
  ・アラームビューワーへの描画が継続されること
  ・サービス断なし
"""
import json
import logging
import time
import uuid
from pathlib import Path

import pytest

from _common.snow_client import SnowClient

logger = logging.getLogger(__name__)

MONITOR_SEC = 300
POLL_INTERVAL_SEC = 5
RESULT_PATH = Path(__file__).parent / "result_m_6.json"


@pytest.mark.mid
@pytest.mark.availability
def test_alarm_viewer_continues_during_2az_down(authed_page):
    client = SnowClient()
    authed_page.goto("/now/nav/ui/classic/params/target/em_alert_list.do",
                     wait_until="networkidle")
    history: list[dict] = []
    start = time.time()
    success = 0
    failed = 0
    while time.time() - start < MONITOR_SEC:
        key = f"m6-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        try:
            client.insert_record("em_event", {
                "source": "mid-test-M-6",
                "node": f"m6-node-{key}",
                "type": "2AZ Down Continuity",
                "severity": "3",
                "message_key": key,
                "description": f"m6 monitor {key}",
            })
            authed_page.reload(wait_until="networkidle")
            visible = authed_page.locator(f"text={key}").count() > 0
            history.append({"t": time.time() - start, "key": key, "visible": visible})
            if visible:
                success += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            history.append({"t": time.time() - start, "key": key, "error": str(e)})
        time.sleep(POLL_INTERVAL_SEC)

    result = {"success": success, "failed": failed, "history": history[-30:]}
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    assert failed == 0, f"2AZ停止中に {failed} 回の転送/描画失敗が発生"
