"""要件1-1: 画面応答時間（通常操作）

【テスト内容】
  ①インシデント一覧画面を開く
  ②インシデント詳細画面を開く
  ③変更管理チケット登録画面を開く
  ④各操作の応答時間を計測（10回平均）

【合否判定基準】
  全ての画面操作において 応答時間が3秒以内であること

【設計上の注意】
  ServiceNow Classic UI は iframe#gsft_main の中にコンテンツが描画される。
  「詳細」テストは go_back() を使わず、対象レコードの sys_id を一度取得して
  直接 URL に sys_id= で遷移することで毎回同等の計測条件にしている。
"""
import json
import logging
import re
from pathlib import Path

import pytest

from _common.playwright_helpers import measure, snow_goto_and_wait, summarize

logger = logging.getLogger(__name__)

ITERATIONS = 10
THRESHOLD_SEC = 3.0
RESULT_PATH = Path(__file__).parent / "result_1_1.json"

URL_INCIDENT_LIST = "/now/nav/ui/classic/params/target/incident_list.do"
URL_CHANGE_NEW = "/now/nav/ui/classic/params/target/change_request.do"
URL_INCIDENT_DETAIL_TMPL = "/now/nav/ui/classic/params/target/incident.do?sys_id={sys_id}"

LIST_SELECTOR = "table.list_table, .list2_body, [data-list-id], table.list_row"
LIST_LINK_SELECTOR = "a.linked.formlink, a[href*='sys_id='], td.linked a"

FORM_SELECTOR = (
    "input[id$='.number']:not([type='hidden']):not([id^='sys_original']):not([id^='sys_display'])"
    ", [data-name='number']:not([data-readonly='true'])"
)
FORM_SHORT_DESC = (
    "textarea[id$='.short_description']:not([id^='sys_original'])"
    ", input[id$='.short_description']:not([type='hidden']):not([id^='sys_original'])"
    ", [data-name='short_description']"
)

SYS_ID_PATTERN = re.compile(r"sys_id=([0-9a-fA-F]{32})")


@pytest.mark.perf
class TestScreenResponse:
    def test_incident_list(self, authed_page):
        """① インシデント一覧"""
        samples: list[float] = []
        for i in range(ITERATIONS):
            with measure(f"incident_list iter={i+1}", samples):
                snow_goto_and_wait(authed_page, URL_INCIDENT_LIST,
                                   content_selector=LIST_SELECTOR,
                                   timeout_ms=15_000)
        self._assert_and_save("incident_list", samples)

    def test_incident_detail(self, authed_page):
        """② インシデント詳細（一覧から sys_id を取得し、以降は直接URLで遷移）"""
        # --- setup: 先頭1件の sys_id を取得 ---
        content = snow_goto_and_wait(authed_page, URL_INCIDENT_LIST,
                                     content_selector=LIST_SELECTOR,
                                     timeout_ms=15_000)
        first_link = content.locator(LIST_LINK_SELECTOR).first
        first_link.wait_for(timeout=15_000)
        href = first_link.get_attribute("href") or ""
        m = SYS_ID_PATTERN.search(href)
        assert m, f"sys_id を抽出できませんでした: href={href!r}"
        sys_id = m.group(1)
        detail_url = URL_INCIDENT_DETAIL_TMPL.format(sys_id=sys_id)
        logger.info("Detail target: sys_id=%s", sys_id)

        # --- 計測ループ: 詳細URLに直接遷移 ---
        samples: list[float] = []
        for i in range(ITERATIONS):
            with measure(f"incident_detail iter={i+1}", samples):
                snow_goto_and_wait(authed_page, detail_url,
                                   content_selector=FORM_SELECTOR,
                                   timeout_ms=15_000)
        self._assert_and_save("incident_detail", samples)

    def test_change_new(self, authed_page):
        """③ 変更管理チケット登録"""
        samples: list[float] = []
        for i in range(ITERATIONS):
            with measure(f"change_new iter={i+1}", samples):
                snow_goto_and_wait(authed_page, URL_CHANGE_NEW,
                                   content_selector=FORM_SHORT_DESC,
                                   timeout_ms=15_000)
        self._assert_and_save("change_new", samples)

    @staticmethod
    def _assert_and_save(label: str, samples: list[float]) -> None:
        stats = summarize(samples)
        logger.info("[%s] %s", label, stats)
        out = {}
        if RESULT_PATH.exists():
            out = json.loads(RESULT_PATH.read_text())
        out[label] = stats
        RESULT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        assert stats["avg"] < THRESHOLD_SEC, \
            f"{label}: 平均応答時間 {stats['avg']:.3f}s が閾値 {THRESHOLD_SEC}s を超過"
