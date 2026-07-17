"""要件1-4: チケット起票数（月間処理量）

【テスト内容】
  ①1000件分のチケット起票を連続実施
  ②起票成功率・処理時間を記録
  ③データ整合性を確認

【合否判定基準】
  ・1000件の起票が正常完了すること
  ・データ欠損・重複なし
"""
import json
import logging
import time
from pathlib import Path

import pytest

from _common.playwright_helpers import summarize

logger = logging.getLogger(__name__)

TICKET_COUNT = 1000
PROGRESS_STEP = 50
RESULT_PATH = Path(__file__).parent / "result_1_4.json"


@pytest.mark.perf
def test_bulk_ticket_creation(authed_page):
    """ループ起票（短時間に1000件作成し、成功率・処理時間を測定）"""
    samples: list[float] = []
    success = 0
    failed = 0
    created_numbers: list[str] = []

    overall_start = time.perf_counter()
    for i in range(TICKET_COUNT):
        try:
            t0 = time.perf_counter()
            authed_page.goto(
                "/now/nav/ui/classic/params/target/incident.do",
                wait_until="networkidle",
            )
            short_desc = f"性能試験1-4 自動起票 #{i+1:04d} ({int(time.time())})"
            authed_page.fill("[data-name='short_description'], #incident\\.short_description",
                             short_desc)
            authed_page.click("button#sysverb_insert_and_stay, button#sysverb_insert")
            authed_page.wait_for_selector("[data-name='number']", timeout=15_000)
            number = authed_page.locator("[data-name='number']").first.input_value()
            created_numbers.append(number)
            samples.append(time.perf_counter() - t0)
            success += 1
        except Exception as e:
            logger.warning("Failed at iter=%d: %s", i + 1, e)
            failed += 1
        if (i + 1) % PROGRESS_STEP == 0:
            logger.info("Progress %d/%d (success=%d, failed=%d)",
                        i + 1, TICKET_COUNT, success, failed)

    overall = time.perf_counter() - overall_start
    stats = summarize(samples)
    duplicates = len(created_numbers) - len(set(created_numbers))

    result = {
        "target_count": TICKET_COUNT,
        "success": success,
        "failed": failed,
        "duplicates": duplicates,
        "elapsed_total_sec": overall,
        "per_ticket_stats": stats,
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Result: %s", json.dumps(result, indent=2, ensure_ascii=False))

    assert success == TICKET_COUNT, f"起票失敗が {failed} 件発生"
    assert duplicates == 0, f"重複チケット番号 {duplicates} 件検出"
