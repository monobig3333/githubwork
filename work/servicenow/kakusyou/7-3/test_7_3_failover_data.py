"""要件7-3: 系切り替え後のデータ継続性確認

【テスト内容】
  ①Playwrightでテストチケット・アラームを投入
  ②ServiceNow担当者と調整してフェイルオーバーを実施
   （不可の場合は仕様書確認で代替）
  ③切り替え後にPlaywrightで投入データの存在を確認

【合否判定基準】
  ・系切り替え後に未処理データが正常に処理されること
  ・データロスが発生しないこと

【注意】
  SaaSのためフェイルオーバーは ServiceNow 担当者依頼制。
  本スクリプトは「投入」と「切替後の確認」を分離して実行する。
"""
import json
import logging
import time
import uuid
from pathlib import Path

import pytest

from _common.snow_client import SnowClient

logger = logging.getLogger(__name__)

INJECT_PATH = Path(__file__).parent / "injected_ids.json"


def _persist_inject(ids: dict) -> None:
    INJECT_PATH.write_text(json.dumps(ids, indent=2, ensure_ascii=False))


def _load_inject() -> dict:
    if not INJECT_PATH.exists():
        pytest.skip("injected_ids.json が存在しない。先にinjectを実行してください")
    return json.loads(INJECT_PATH.read_text())


def test_inject_before_failover(authed_page):
    """事前: チケット・アラーム投入

    フェイルオーバー前にこのテストを実行し、injected_ids.json を生成する。
    """
    client = SnowClient()
    run_id = f"failover-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    # インシデント1件
    incident = client.insert_record("incident", {
        "short_description": f"[7-3] failover test {run_id}",
        "category": "inquiry",
    })
    incident_no = incident.get("number")

    # アラーム1件
    client.insert_record("em_event", {
        "source": "perf-test-7-3",
        "node": f"failover-node-{run_id}",
        "type": "Failover Test",
        "severity": "3",
        "message_key": run_id,
        "description": f"[7-3] failover test alarm {run_id}",
    })

    ids = {"run_id": run_id, "incident_number": incident_no}
    _persist_inject(ids)
    logger.info("Injected: %s", ids)


def test_verify_after_failover(authed_page):
    """事後: フェイルオーバー実施後のデータ存在確認"""
    ids = _load_inject()
    run_id = ids["run_id"]
    incident_no = ids["incident_number"]

    # インシデント確認
    authed_page.goto(
        f"/now/nav/ui/classic/params/target/incident.do?sysparm_query=number={incident_no}",
        wait_until="networkidle",
    )
    assert authed_page.locator(f"text={incident_no}").count() > 0, \
        f"インシデント {incident_no} が見つかりません（データロス）"

    # アラーム確認
    authed_page.goto(
        f"/now/nav/ui/classic/params/target/em_alert_list.do?sysparm_query=message_key={run_id}",
        wait_until="networkidle",
    )
    assert authed_page.locator(f"text={run_id}").count() > 0, \
        f"アラーム {run_id} が見つかりません（データロス）"

    logger.info("Failover data continuity OK: incident=%s alarm=%s",
                incident_no, run_id)
