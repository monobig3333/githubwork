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
import re
import time
from pathlib import Path

import pytest

from _common.playwright_helpers import snow_goto_and_wait, summarize

logger = logging.getLogger(__name__)

# 本番は 1,000 件。動作確認用に PERF_TICKET_COUNT=3 等で絞れる。
TICKET_COUNT = int(os.getenv("PERF_TICKET_COUNT", "1000"))
PROGRESS_STEP = int(os.getenv("PERF_PROGRESS_STEP", "50"))

# --- 分割実行（バッチ）モード -------------------------------------------------
# auth.json のセッションは実測で 1 時間ほどで UI が不安定化するため、
# 1,000 件を一度に流さず 200 件 × 5 回に分けて実行する。
#   PERF_BATCH_LABEL : バッチ名。指定すると 1-4/parts/result_1_4_<label>.json に出力
#   PERF_INDEX_OFFSET: 通し番号の開始位置（バッチ2なら 200）
# 各バッチの前に save_auth_state.py でセッションを取り直すこと。
# 全バッチ完了後 `python3 1-4/merge_parts.py` で result_1_4.json に統合する。
BATCH_LABEL = os.getenv("PERF_BATCH_LABEL", "")
INDEX_OFFSET = int(os.getenv("PERF_INDEX_OFFSET", "0"))

_IS_BATCH = bool(BATCH_LABEL)
# 動作確認時は本番結果を上書きしないよう別ファイルへ出力する
_IS_SMOKE = (not _IS_BATCH) and os.getenv("PERF_TICKET_COUNT") is not None

if _IS_BATCH:
    _PARTS_DIR = Path(__file__).parent / "parts"
    _PARTS_DIR.mkdir(exist_ok=True)
    RESULT_PATH = _PARTS_DIR / f"result_1_4_{BATCH_LABEL}.json"
else:
    RESULT_PATH = Path(__file__).parent / (
        "result_1_4_smoke.json" if _IS_SMOKE else "result_1_4.json"
    )

# ServiceNow Classic UI のコンテンツは iframe#gsft_main の中に描画される。
# トップレベルの page に対して fill/click しても要素は見つからないため、
# snow_goto_and_wait() が返すコンテンツロケーター（FrameLocator）を経由する。
# 既定はナビゲーター経由（iframe#gsft_main の中にフォームが出る）。
# ナビゲーターシェルが不調なときは PERF_INCIDENT_URL=/incident.do で
# フォームを直接開ける（snow_goto_and_wait は /now/nav/ を含まない場合、
# iframe を待たずトップレベルをコンテンツとして扱う）。
URL_INCIDENT_NEW = os.getenv(
    "PERF_INCIDENT_URL", "/now/nav/ui/classic/params/target/incident.do"
)

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
# 保存ボタン
#   既定 (stay)  : 「保存して留まる」。レコードを開いたまま次へ進む
#   PERF_SUBMIT_MODE=submit : 通常の Submit。保存後に一覧へ戻るためセッション側の
#                             リソースが解放される可能性がある（2026/8/19 検証用）
SUBMIT_MODE = os.getenv("PERF_SUBMIT_MODE", "stay").lower()
if SUBMIT_MODE == "submit":
    SEL_INSERT = "button#sysverb_insert"
else:
    SEL_INSERT = "button#sysverb_insert_and_stay, button#sysverb_insert"

# Submit 方式では保存後に一覧へ戻るため、フォーム上では番号を取得できない。
# 情報メッセージ (#output_messages) は常時 DOM に存在し普段は
# outputmsg_hide で非表示なので、可視待ちは不安定（2026/8/19 に実測で判明）。
# → UI からは「フォームを離れたこと」だけを確認し、
#    採番結果は実行後に REST API で突合する。
_INC_RE = re.compile(r"\b(INC\d{5,})\b")

# 実行ごとに一意なタグ。short_description に埋め込み、後から REST で引き当てる
RUN_TAG = os.getenv("PERF_RUN_TAG", "") or f"{int(time.time())}"


def _fetch_created_by_tag(tag: str) -> list[str]:
    """short_description に [run=<tag>] を含む incident の番号を REST で取得する"""
    import requests

    props = {}
    jp = Path(__file__).resolve().parent.parent / "jmeter.properties"
    if jp.exists():
        for line in jp.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                props[k.strip()] = v.strip()
    cid = os.getenv("SNOW_CLIENT_ID") or props.get("snow.client_id", "")
    sec = os.getenv("SNOW_CLIENT_SECRET") or props.get("snow.client_secret", "")
    base = os.getenv("SNOW_BASE_URL", "https://biglobedev.service-now.com")
    if not cid or not sec:
        logger.warning("OAuth 認証情報が無いため REST 突合をスキップします")
        return []

    r = requests.post(f"{base}/oauth_token.do", auth=(cid, sec),
                      data={"grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    token = r.json()["access_token"]

    numbers: list[str] = []
    offset = 0
    while True:
        resp = requests.get(
            f"{base}/api/now/table/incident",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={
                "sysparm_query": f"short_descriptionLIKE[run={tag}]^ORDERBYnumber",
                "sysparm_fields": "number",
                "sysparm_limit": "1000",
                "sysparm_offset": str(offset),
            },
            timeout=60,
        )
        resp.raise_for_status()
        rows = resp.json().get("result", [])
        numbers += [x["number"] for x in rows]
        if len(rows) < 1000:
            break
        offset += 1000
    return numbers

NAV_TIMEOUT_MS = int(os.getenv("PERF_NAV_TIMEOUT_MS", "20000"))
SAVE_TIMEOUT_MS = int(os.getenv("PERF_SAVE_TIMEOUT_MS", "20000"))

# --- 長時間実行の安全策（2026/8/18 追加） -----------------------------------
# 1,000 件を単一のブラウザコンテキストで回すと、数件目以降 page.goto が
# 30 秒タイムアウトし続ける事象が発生した（2026/8/18、成功 5 / 失敗 142）。
# 対策として (a) 一定件数ごとのコンテキスト作り直し、(b) 連続失敗での打ち切り、
# (c) 途中経過の逐次保存 を入れている。
CONTEXT_EVERY = int(os.getenv("PERF_CONTEXT_EVERY", "50"))       # 0 で無効
MAX_CONSECUTIVE_FAILURES = int(os.getenv("PERF_MAX_CONSEC_FAIL", "10"))  # 0 で無効
SLEEP_MS = int(os.getenv("PERF_SLEEP_MS", "0"))                  # 起票間の待機


def _new_authed_page(browser, context_args):
    """storage_state 済みの新しいコンテキストとページを作る"""
    ctx = browser.new_context(**context_args)
    page = ctx.new_page()
    return ctx, page


@pytest.mark.perf
def test_bulk_ticket_creation(browser, browser_context_args):
    """ループ起票（短時間に1000件作成し、成功率・処理時間を測定）"""
    samples: list[float] = []
    success = 0
    failed = 0
    consecutive_failures = 0
    aborted_at = None
    created_numbers: list[str] = []
    context_recreations = 0

    def snapshot(elapsed: float) -> dict:
        stats = summarize(samples)
        return {
            "target_count": TICKET_COUNT,
            "attempted": success + failed,
            "success": success,
            "failed": failed,
            "duplicates": len(created_numbers) - len(set(created_numbers)),
            "elapsed_total_sec": elapsed,
            "per_ticket_stats": stats,
            "smoke": _IS_SMOKE,
            "batch_label": BATCH_LABEL or None,
            "index_offset": INDEX_OFFSET,
            "aborted_at": aborted_at,
            "context_recreations": context_recreations,
            "settings": {
                "context_every": CONTEXT_EVERY,
                "max_consecutive_failures": MAX_CONSECUTIVE_FAILURES,
                "sleep_ms": SLEEP_MS,
            },
            # バッチ／スモークでは全件、通常実行では先頭 20 件を記録
            "created_numbers": (
                created_numbers if (_IS_SMOKE or _IS_BATCH) else created_numbers[:20]
            ),
            # 統合時に統計を再計算するため生サンプルを持たせる
            "samples": samples if _IS_BATCH else None,
        }

    def save(elapsed: float) -> dict:
        r = snapshot(elapsed)
        RESULT_PATH.write_text(json.dumps(r, indent=2, ensure_ascii=False))
        return r

    overall_start = time.perf_counter()
    ctx, page = _new_authed_page(browser, browser_context_args)
    try:
        for i in range(TICKET_COUNT):
            # (a) 一定件数ごとにブラウザコンテキストを作り直す
            if CONTEXT_EVERY and i > 0 and i % CONTEXT_EVERY == 0:
                page.close()
                ctx.close()
                ctx, page = _new_authed_page(browser, browser_context_args)
                context_recreations += 1
                logger.info("ブラウザコンテキストを作り直しました (iter=%d)", i + 1)

            try:
                t0 = time.perf_counter()
                # iframe#gsft_main を解決したコンテンツロケーターを得る
                content = snow_goto_and_wait(
                    page, URL_INCIDENT_NEW,
                    content_selector=SEL_SHORT_DESC,
                    timeout_ms=NAV_TIMEOUT_MS,
                )
                seq = INDEX_OFFSET + i + 1
                short_desc = (
                    f"性能試験1-4 自動起票 #{seq:04d} [run={RUN_TAG}]"
                )
                desc_field = content.locator(SEL_SHORT_DESC).first
                desc_field.fill(short_desc)
                content.locator(SEL_INSERT).first.click()

                if SUBMIT_MODE == "submit":
                    # 一覧へ遷移するので「フォームを離れた」ことだけを確認する。
                    # 番号は実行後に REST でタグ突合して取得する。
                    desc_field.wait_for(state="detached", timeout=SAVE_TIMEOUT_MS)
                    number = short_desc  # 仮置き。後で REST の結果に置き換える
                else:
                    # 保存後、採番された番号が入るまで待つ
                    number_field = content.locator(SEL_NUMBER).first
                    number_field.wait_for(timeout=SAVE_TIMEOUT_MS)
                    number = number_field.input_value()
                    if not number:
                        raise RuntimeError("番号が空。保存が完了していない可能性")
                created_numbers.append(number)
                samples.append(time.perf_counter() - t0)
                success += 1
                consecutive_failures = 0
            except Exception as e:
                logger.warning("Failed at iter=%d: %s", i + 1, e)
                failed += 1
                consecutive_failures += 1

            if (i + 1) % PROGRESS_STEP == 0:
                logger.info("Progress %d/%d (success=%d, failed=%d)",
                            i + 1, TICKET_COUNT, success, failed)
                # (c) 途中経過を逐次保存（中断してもデータが残る）
                save(time.perf_counter() - overall_start)

            # (b) 連続失敗が続いたら打ち切る（空回りで数時間を溶かさないため）
            if MAX_CONSECUTIVE_FAILURES and consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                aborted_at = i + 1
                logger.error(
                    "連続 %d 件失敗したため中断します (iter=%d)。"
                    "環境側の状態を確認してください",
                    consecutive_failures, i + 1,
                )
                break

            if SLEEP_MS:
                time.sleep(SLEEP_MS / 1000.0)
    finally:
        try:
            page.close()
            ctx.close()
        except Exception:
            pass

    # Submit 方式では UI から番号を取れないため、REST でタグ突合して確定させる
    rest_count = None
    if SUBMIT_MODE == "submit":
        try:
            fetched = _fetch_created_by_tag(RUN_TAG)
            rest_count = len(fetched)
            logger.info("REST 突合: run=%s で %d 件の incident を確認 (UI 成功 %d 件)",
                        RUN_TAG, rest_count, success)
            if rest_count != success:
                logger.warning(
                    "UI の成功数 (%d) と ServiceNow 上の件数 (%d) が一致しません",
                    success, rest_count,
                )
            created_numbers[:] = fetched
        except Exception as e:
            logger.warning("REST 突合に失敗しました: %s", e)

    result = save(time.perf_counter() - overall_start)
    result["run_tag"] = RUN_TAG
    result["submit_mode"] = SUBMIT_MODE
    result["rest_verified_count"] = rest_count
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Result: %s", json.dumps(result, indent=2, ensure_ascii=False))

    assert aborted_at is None, (
        f"連続 {MAX_CONSECUTIVE_FAILURES} 件失敗で中断 (iter={aborted_at})。"
        f"成功 {success} / 失敗 {failed}"
    )
    assert success == TICKET_COUNT, f"起票失敗が {failed} 件発生"
    assert result["duplicates"] == 0, f"重複チケット番号 {result['duplicates']} 件検出"
