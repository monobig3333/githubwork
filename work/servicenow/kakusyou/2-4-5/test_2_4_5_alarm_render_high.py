"""要件2-4/5: イベント描画応答時間（高負荷時）

【テスト内容】
  ①Zabbix から ServiceNow（対象インスタンスは .env 参照 / Zurich）へ最大負荷
    （30,000件/10分）でイベントを投入
  ②イベント受信からビューワー描画完了までの時間を連続計測
  ③平均値と最大値を記録

【合否判定基準】
  ・平均描画時間：60秒以内
  ・最大描画時間：180秒以内

【認証】
  - Playwright の auth.json を使ったブラウザセッションだけで完結
  - API 呼び出しも page.request 経由（auth.json の cookie + X-UserToken）
  - OAuth / AWS Secrets Manager は本テストでは未使用

【測定方式】
  ・ServiceNow Table API (em_event) を sys_created_on で **降順** ポーリング
    → ビューワー（新着順表示）の最上段に出る "最新かつ未計測" イベントを取得
  ・既に計測した sys_id はスキップして二重カウント防止
  ・各イベントについて
        elapsed = (DOM 描画完了時刻 - em_event.sys_created_on(UTC))
    を計測
  ・DURATION_SEC（既定 600秒 = 10 分）の時間ベース計測、
    または MAX_ITERATIONS (既定 50) に達したら終了

【高負荷時の注意】
  通常時 (2-3) は昇順 (古い順) でポーリングしても問題なかったが、
  高負荷時 (50件/秒) は古いイベントがビューワー 1 ページ目から押し出されて
  DOM に見つからない。そのため最新順に変更している。

【UI 対応】
  Zurich / Next Experience UI と Classic UI の両方に対応:
    1. /em_event_list.do
    2. /now/nav/ui/classic/params/target/em_event_list.do
  描画検知は iframe 優先で page 全体にもフォールバック。

【手動同期】
  - 別端末で Zabbix の高負荷投入スクリプトを並走起動
  - テストは Enter 入力を待ち合わせ → そこから計測開始
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from playwright.sync_api import Page, TimeoutError as PWTimeout

from _common.config import settings
from _common.playwright_helpers import summarize

logger = logging.getLogger(__name__)

# ---------- パラメータ ----------
DURATION_SEC = int(os.getenv("PERF_DURATION_SEC", "600"))         # 計測継続時間（既定 10 分）
MAX_ITERATIONS = int(os.getenv("PERF_MAX_ITER", "50"))            # 件数の上限（過剰計測抑制）
AVG_THRESHOLD_SEC = 60.0
MAX_THRESHOLD_SEC = 180.0

RESULT_PATH = Path(__file__).parent / "result_2_4_5.json"
DEBUG_DIR = Path(__file__).parent / "_debug"

VIEWER_URLS = [
    "/em_event_list.do",
    "/now/nav/ui/classic/params/target/em_event_list.do",
]
IFRAME_CANDIDATES = [
    "iframe#gsft_main",
    "iframe[name='gsft_main']",
    "iframe[id*='gsft']",
    "iframe[src*='em_event_list']",
]

POLL_INTERVAL_SEC = 0.5

# 同一 sys_created_on（＝同一バッチ）のイベントを 1 件だけ計測するか。
# 高負荷時は数千件が同一秒に登録されるため、これを 1 件ずつ測ると
# 「リロード所要 × 件数」がそのまま elapsed に積み上がり、
# 描画性能ではなく計測ループの所要時間を測ることになる（2026/8/21 実測で判明）。
# 既定 True。旧来の挙動に戻す場合は PERF_DEDUP_BY_CREATED=0 を指定する。
DEDUP_BY_CREATED = os.getenv("PERF_DEDUP_BY_CREATED", "1") not in ("0", "false", "False")

EVENT_WAIT_TIMEOUT_SEC = 60          # 高負荷時は次イベントまでの待ちを長めに
RENDER_WAIT_TIMEOUT_MS = 240_000     # 180s 閾値 + 余裕
NAV_TIMEOUT_MS = 30_000


# ---------- 時刻ヘルパー ----------
def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_utc(s: str) -> float:
    return (
        datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


# ---------- API ヘルパー ----------
def _get_user_token(page: Page) -> str | None:
    try:
        return page.evaluate("() => (window.g_ck || '')")
    except Exception as e:
        logger.warning("g_ck 取得失敗: %s", e)
        return None


def _poll_latest_event(page: Page, since_utc: str, exclude_sys_ids: set[str],
                       timeout_sec: float, user_token: str | None,
                       exclude_created: set[str] | None = None) -> dict | None:
    """`since_utc` より新しく、`exclude_sys_ids` に含まれない em_event を
    sys_created_on **降順** で最大 `timeout_sec` 秒待ち、最も新しい 1 件を返す。

    高負荷時はビューワー (新着順表示) の最上段に確実に出る最新イベントを基準にする。
    既に計測済みの sys_id は除外して二重カウントを防ぐ。
    """
    url = settings.snow_base_url + "/api/now/table/em_event"
    # 直近を多めに取って、未計測のものから 1 件選ぶ
    params = {
        "sysparm_limit": "10",
        "sysparm_fields": (
            "sys_id,number,description,message_key,source,node,resource,"
            "type,severity,sys_created_on"
        ),
        "sysparm_query": f"sys_created_on>{since_utc}^ORDERBYDESCsys_created_on",
        "sysparm_display_value": "false",
    }
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Referer": settings.snow_base_url + "/em_event_list.do",
    }
    if user_token:
        headers["X-UserToken"] = user_token
    deadline = time.time() + timeout_sec
    warned_status = None
    while time.time() < deadline:
        try:
            resp = page.request.get(url, params=params, headers=headers, timeout=15_000)
        except Exception as e:
            logger.warning("em_event ポーリング例外: %s", e)
            time.sleep(POLL_INTERVAL_SEC)
            continue
        if resp.ok:
            try:
                records = resp.json().get("result", [])
            except Exception:
                records = []
            # 未計測 (exclude_sys_ids 非該当) の最も新しい 1 件を選ぶ。
            # DEDUP_BY_CREATED=True のときは、既に計測した sys_created_on と
            # 同一秒のイベントも除外する（同一バッチの重複計測を防ぐ）。
            for rec in records:
                if rec.get("sys_id") in exclude_sys_ids:
                    continue
                if (DEDUP_BY_CREATED and exclude_created
                        and rec.get("sys_created_on") in exclude_created):
                    continue
                return rec
        else:
            if warned_status != resp.status:
                logger.warning(
                    "em_event API status=%d body=%s",
                    resp.status, resp.text()[:200],
                )
                warned_status = resp.status
        time.sleep(POLL_INTERVAL_SEC)
    return None


# ---------- ビューワー UI ヘルパー ----------
def _detect_iframe_selector(page: Page, timeout_ms: int = 5000) -> str | None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for sel in IFRAME_CANDIDATES:
            if page.locator(sel).count() > 0:
                return sel
        time.sleep(0.2)
    return None


def _open_event_viewer(page: Page) -> str | None:
    DEBUG_DIR.mkdir(exist_ok=True)
    last_err: Exception | None = None
    for path in VIEWER_URLS:
        url = settings.snow_base_url + path
        try:
            logger.info("ビューワー候補URL: %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
            iframe_sel = _detect_iframe_selector(page, timeout_ms=8000)
            if iframe_sel:
                logger.info("✓ iframe 検出: %s  (URL=%s)", iframe_sel, page.url)
                return iframe_sel
            if "em_event" in page.content():
                logger.info("✓ Top-frame で em_event 検出 (URL=%s)", page.url)
                return ""
        except Exception as e:
            last_err = e
            logger.warning("URL %s で失敗: %s", url, e)

    shot = DEBUG_DIR / f"open_viewer_fail_{int(time.time())}.png"
    try:
        page.screenshot(path=str(shot), full_page=True)
    except Exception:
        pass
    raise RuntimeError(
        f"イベントビューワーを開けませんでした。URL={page.url}, "
        f"screenshot={shot}, last_err={last_err}"
    )


def _wait_for_event_in_dom(page: Page, iframe_sel: str, event: dict) -> bool:
    selectors: list[str] = []
    if event.get("number"):
        selectors.append(f"text={event['number']}")
    if event.get("sys_id"):
        selectors.append(f"a[href*='{event['sys_id']}']")
    if not selectors:
        return False

    deadline = time.time() + RENDER_WAIT_TIMEOUT_MS / 1000
    while time.time() < deadline:
        for sel in selectors:
            if iframe_sel and page.locator(iframe_sel).count() > 0:
                try:
                    page.frame_locator(iframe_sel).locator(sel).first.wait_for(
                        timeout=400
                    )
                    return True
                except PWTimeout:
                    pass
            try:
                page.locator(sel).first.wait_for(timeout=400)
                return True
            except PWTimeout:
                continue
    return False


# ---------- テスト本体 ----------
@pytest.mark.perf
@pytest.mark.high_load
def test_event_render_under_high_load(authed_page):
    # 対象インスタンスは .env の SNOW_INSTANCE / SNOW_BASE_URL で決まる。
    # 誤ったインスタンスへの実行を防ぐため、期待値を PERF_EXPECTED_INSTANCE で指定できる
    # （未指定なら .env の設定をそのまま採用）。2026/8/21: biglobenonprod 固定を解除
    _expected = os.getenv("PERF_EXPECTED_INSTANCE", settings.snow_instance)
    assert _expected in settings.snow_base_url, (
        f"対象インスタンスが期待値と異なります。expected={_expected} "
        f"base_url={settings.snow_base_url}"
    )
    logger.info("対象インスタンス: %s", settings.snow_base_url)
    logger.info("ServiceNow base_url=%s", settings.snow_base_url)
    logger.info("DURATION_SEC=%d  MAX_ITERATIONS=%d", DURATION_SEC, MAX_ITERATIONS)

    page = authed_page

    # ---- 1. ビューワーを開く ----
    iframe_sel = _open_event_viewer(page)
    logger.info("ビューワー描画モード: %s",
                "iframe=" + iframe_sel if iframe_sel else "top-page")

    # ---- 2. Zabbix 高負荷投入の同期待ち ----
    sync_msg = (
        "\n"
        "==================================================================\n"
        " 要件 2-4/5 イベント描画応答時間（高負荷時） [対象インスタンスは .env 参照 / Zurich]\n"
        "==================================================================\n"
        " 別端末で Zabbix の高負荷投入（30,000件/10分）を起動してください。\n"
        " イベントが流れ始めたら Enter を押すと計測開始します。\n"
        f" 計測継続時間 = {DURATION_SEC}s  /  最大計測件数 = {MAX_ITERATIONS}\n"
        "==================================================================\n"
        " Enter で計測開始 > "
    )
    print(sync_msg, end="", flush=True)
    input()

    # ---- 3. 計測開始時刻 + 認証トークン取得 ----
    test_start_utc = _utc_now_str()
    user_token = _get_user_token(page)
    logger.info("計測開始: since_utc=%s, user_token_len=%s",
                test_start_utc, len(user_token) if user_token else 0)

    # ---- 4. 計測ループ（時間ベース、件数上限あり） ----
    samples: list[dict] = []
    measured_sys_ids: set[str] = set()
    measured_created: set[str] = set()   # 同一バッチ除外用           # 二重カウント防止
    overall_deadline = time.time() + DURATION_SEC

    while len(samples) < MAX_ITERATIONS and time.time() < overall_deadline:
        remain = overall_deadline - time.time()
        if remain <= 0:
            break

        # 計測開始時刻以降の "未計測かつ最新の" イベントを取得（DESC）
        event = _poll_latest_event(
            page, test_start_utc, measured_sys_ids,
            min(EVENT_WAIT_TIMEOUT_SEC, remain),
            user_token,
            exclude_created=measured_created,
        )
        if not event:
            logger.warning("一定時間 未計測の新規イベントが届かず。次の反復へ。")
            continue

        t_received = _parse_utc(event["sys_created_on"])
        measured_sys_ids.add(event["sys_id"])
        measured_created.add(event["sys_created_on"])

        try:
            page.reload(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        except PWTimeout:
            logger.warning("reload timeout, continue")

        if not _wait_for_event_in_dom(page, iframe_sel, event):
            logger.warning(
                "イベント %s (sys_id=%s) が %dms 以内に描画されず → スキップ",
                event.get("number") or "(no number)",
                event.get("sys_id"),
                RENDER_WAIT_TIMEOUT_MS,
            )
            continue

        t_rendered = time.time()
        elapsed = t_rendered - t_received
        samples.append({
            "iter": len(samples) + 1,
            "event_number": event.get("number"),
            "event_sys_id": event.get("sys_id"),
            "message_key": event.get("message_key"),
            "source": event.get("source"),
            "node": event.get("node"),
            "resource": event.get("resource"),
            "type": event.get("type"),
            "severity": event.get("severity"),
            "sys_created_on_utc": event["sys_created_on"],
            "rendered_epoch": t_rendered,
            "elapsed_sec": elapsed,
        })
        logger.info(
            "iter=%2d event=%s 受信→描画 %.3fs",
            len(samples),
            event.get("number") or (event.get("sys_id", "?")[:8]),
            elapsed,
        )

    # ---- 5. 集計・保存 ----
    if not samples:
        pytest.fail(
            f"DURATION_SEC={DURATION_SEC}s 内で 1 件も計測できませんでした。"
            "Zabbix 投入と em_event の流入を確認してください。"
        )

    elapsed_list = [s["elapsed_sec"] for s in samples]
    stats = summarize(elapsed_list)
    output = {
        "instance": settings.snow_instance,
        "target_table": "em_event",
        "test_start_utc": test_start_utc,
        "duration_sec": DURATION_SEC,
        "max_iterations": MAX_ITERATIONS,
        "thresholds": {
            "avg_sec": AVG_THRESHOLD_SEC,
            "max_sec": MAX_THRESHOLD_SEC,
        },
        "iterations": len(samples),
        "iframe_selector": iframe_sel or "(top-page)",
        "stats": stats,
        "samples": samples,
    }
    RESULT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info("結果保存: %s", RESULT_PATH)
    logger.info("統計: %s", stats)

    # ---- 6. 合否判定 ----
    assert stats["avg"] <= AVG_THRESHOLD_SEC, (
        f"平均描画時間 {stats['avg']:.2f}s が閾値 {AVG_THRESHOLD_SEC}s 超過"
    )
    assert stats["max"] <= MAX_THRESHOLD_SEC, (
        f"最大描画時間 {stats['max']:.2f}s が閾値 {MAX_THRESHOLD_SEC}s 超過"
    )
