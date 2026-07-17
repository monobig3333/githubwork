"""要件M-8: 停止AZの自動復旧確認

【テスト内容】
  ①停止したAZのMIDサーバを起動する
  ②自動的にクラスタへ復帰し、イベント転送が再開されることを確認
  ③ServiceNow管理コンソールでMIDサーバのステータスを確認

【合否判定基準】
  ・手動介入なしでクラスタへ自動復帰すること
  ・復帰後にイベント転送が正常再開されること
  ・管理コンソールでステータスが「UP」になること

【注意】
  MIDサーバの起動操作（systemctl start mid 等）は本スクリプトの対象外。
  起動後、Playwright で MID Server 管理画面（ecc_agent）を監視し、
  ステータスが「Up」「Online」になることを確認する。
"""
import json
import logging
import time
from pathlib import Path

import pytest

from _common.config import settings

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 600  # 復帰まで最大10分待つ
POLL_INTERVAL_SEC = 15
RESULT_PATH = Path(__file__).parent / "result_m_8.json"


@pytest.mark.mid
@pytest.mark.availability
def test_mid_server_auto_recovery(authed_page):
    """MIDサーバを起動して、自動的に管理コンソールでUpになるか"""
    if not settings.mid_hosts:
        pytest.skip("MID_HOSTS が未設定。.env に対象MIDサーバ名を設定してください")

    target_host = settings.mid_hosts[0]
    logger.info("Monitoring MID server: %s", target_host)

    authed_page.goto(
        f"/now/nav/ui/classic/params/target/ecc_agent_list.do?sysparm_query=name={target_host}",
        wait_until="networkidle",
    )

    deadline = time.time() + TIMEOUT_SEC
    last_status = "Unknown"
    history: list[dict] = []
    while time.time() < deadline:
        authed_page.reload(wait_until="networkidle")
        # ecc_agent の status 列を取得
        row = authed_page.locator(f"tr:has-text('{target_host}')").first
        if row.count() > 0:
            status_cell = row.locator("td").nth(2)
            last_status = status_cell.inner_text().strip()
        history.append({"t": time.time(), "status": last_status})
        logger.info("[%ds] status=%s",
                    int(time.time() - (deadline - TIMEOUT_SEC)), last_status)
        if last_status.lower() in ("up", "online"):
            break
        time.sleep(POLL_INTERVAL_SEC)

    result = {
        "host": target_host,
        "final_status": last_status,
        "history": history[-10:],
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    assert last_status.lower() in ("up", "online"), \
        f"MID Server {target_host} が {TIMEOUT_SEC}s 以内にUpになりませんでした (last={last_status})"
