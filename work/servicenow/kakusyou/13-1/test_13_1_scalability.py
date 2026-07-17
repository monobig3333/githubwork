"""要件13-1: 拡張性確認（ユーザ数・データ量2倍）

【テスト内容】
  ①JMeterのスレッド数を通常の2倍に設定して性能テスト(1-2/1-3相当)を再実施
  ②Playwrightで2倍データ量環境での画面応答時間を計測
  ③拡張前後の結果を比較

【合否判定基準】
  ・ユーザ数2倍でも性能要件を満たすこと
  ・データ量2倍でも性能劣化が許容範囲内であること
"""
import json
import logging
from pathlib import Path

import pytest

from _common.playwright_helpers import measure, summarize

logger = logging.getLogger(__name__)

ITERATIONS = 10
# 2倍負荷下では応答3秒以内維持を狙う
THRESHOLD_SEC = 3.0
RESULT_PATH = Path(__file__).parent / "result_13_1.json"
BASELINE_PATH = Path(__file__).parent.parent / "1-1" / "result_1_1.json"


@pytest.mark.scalability
def test_scalability_screen_response(authed_page):
    """2倍負荷下での画面応答時間"""
    samples: list[float] = []
    for i in range(ITERATIONS):
        with measure(f"scalability_incident_list iter={i+1}", samples):
            authed_page.goto("/now/nav/ui/classic/params/target/incident_list.do",
                             wait_until="networkidle")
            authed_page.wait_for_selector("table.list_table, .list2_body", timeout=15_000)

    stats = summarize(samples)
    result = {"current": stats}

    # ベースライン(1-1)があれば差分を表示
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text()).get("incident_list", {})
        if baseline.get("avg"):
            degradation = (stats["avg"] - baseline["avg"]) / baseline["avg"]
            result["baseline_avg"] = baseline["avg"]
            result["degradation_ratio"] = degradation
            logger.info("Baseline avg=%.3fs / Current avg=%.3fs / degradation=%.1f%%",
                        baseline["avg"], stats["avg"], degradation * 100)

    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    assert stats["avg"] < THRESHOLD_SEC, \
        f"2倍負荷下で平均 {stats['avg']:.3f}s が閾値 {THRESHOLD_SEC}s 超過"
