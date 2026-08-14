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
import os
import time
from pathlib import Path

import pytest

from _common.playwright_helpers import snow_goto_and_wait, summarize

logger = logging.getLogger(__name__)

# 本番は 1,000 件。動作確認用に PERF_TICKET_COUNT=3 等で絞れる。
TICKET_COUNT = int(os.getenv("PERF_TICKET_COUNT", "1000"))
PROGRESS_STEP = int(os.getenv("PERF_PROGRESS_STEP", "50"))

# 動作確認時は本番結果を上書きしないよう別ファイルへ出力する
_IS_SMOKE = os.getenv("PERF_TICKET_COUNT") is not None
RESULT_PATH = Path(__file__).parent / (
    "result_1_4_smoke.json" if _IS_SMOKE else "result_1_4.json"
)

# ServiceNow Classic UI のコンテンツは iframe#gsft_main の中に描画される。
# トップレベルの page に対して fill/click しても要素は見つからないため、
# snow_goto_and_wait() が返すコンテンツロケーター（FrameLocator）を経由する。
URL_INCIDENT_NEW = "/now/nav/ui/classic/params/target/incident.do"

# セレクタは 1-1 で実績のあるものを流用する
SEL_SHORT_DESC = (
    "textarea[id$='.short_description']:not([id^='sys_original'])"
    ", input[id$='.short_description']:not([type='hidden']):not([id^='sys_original'])"
    ", [data-name='short_description']"
)
SEL_NUMBER = (
    "input[id$='.number']:not([type='hidden']):not([id^='sys_original']):not([id^='sys_display'])"
    ", [data-name='number']:not([data-readonly='true'])"
)
SEL_INSERT = "button#sysverb_insert_and_stay, button#sysverb_insert"

NAV_TIMEOUT_MS = int(os.getenv("PERF_NAV_TIMEOUT_MS", "20000"))
SAVE_TIMEOUT_MS = int(os.getenv("PERF_SAVE_TIMEOUT_MS", "20000"))


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
            # iframe#gsft_main を解決したコンテンツロケーターを得る
            content = snow_goto_and_wait(
                authed_page, URL_INCIDENT_NEW,
                content_selector=SEL_SHORT_DESC,
                timeout_ms=NAV_TIMEOUT_MS,
            )
            short_desc = f"性能試験1-4 自動起票 #{i+1:04d} ({int(time.time())})"
            content.locator(SEL_SHORT_DESC).first.fill(short_desc)
            content.locator(SEL_INSERT).first.click()
            # 保存後、採番された番号が入るまで待つ
            number_field = content.locator(SEL_NUMBER).first
            number_field.wait_for(timeout=SAVE_TIMEOUT_MS)
            number = number_field.input_value()
            if not number:
                raise RuntimeError("番号が空。保存が完了していない可能性")
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
        "smoke": _IS_SMOKE,
        "created_numbers": created_numbers if _IS_SMOKE else created_numbers[:20],
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Result: %s", json.dumps(result, indent=2, ensure_ascii=False))

    assert success == TICKET_COUNT, f"起票失敗が {failed} 件発生"
    assert duplicates == 0, f"重複チケット番号 {duplicates} 件検出"
