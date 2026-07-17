"""要件2-6: イベント描画応答時間（高負荷継続30分）

【テスト内容】
  ①Zabbix から ServiceNow（biglobenonprod / Zurich）へ最大負荷を 30 分間継続投入
  ②30 分間を通じてイベント受信→描画完了の時間を継続計測
  ③時間経過による性能劣化傾向を分析

【合否判定基準】
  ・30 分継続後も平均 60 秒以内・最大 180 秒以内
  ・描画時間が増加し続けないこと（性能飽和なし）
    → 後半 15 分の平均が前半 15 分の平均の 1.5 倍を超えたら飽和とみなす

【認証】
  - Playwright の auth.json を使ったブラウザセッションだけで完結
  - API 呼び出しも page.request 経由（auth.json の cookie + X-UserToken）

【測定方式】
  ・ServiceNow Table API (em_event) を sys_created_on で **降順** ポーリング
    → ビューワー（新着順表示）の最上段に出る "最新かつ未計測" イベントを取得
  ・既に計測した sys_id はスキップして二重カウント防止
  ・各イベントについて
        elapsed = (DOM 描画完了時刻 - em_event.sys_created_on(UTC))
    を計測
  ・DURATION_SEC（既定 1800 秒 = 30 分）の時間ベース計測、
    または MAX_ITERATIONS (既定 150) に達したら終了

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
DURATION_SEC = int(os.getenv("PERF_DURATION_SEC", "1800"))   # 30 分
MAX_ITERATIONS = int(os.getenv("PERF_MAX_ITER", "150"))      # 件数上限
AVG_THRESHOLD_SEC = 60.0
MAX_THRESHOLD_SEC = 180.0
SATURATION_RATIO = 1.5   # 後半平均 / 前半平均 > この倍率なら飽和

RESULT_PATH = Path(__file__).parent / "result_2_6.json"
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
EVENT_WAIT_TIMEOUT_SEC = 60
RENDER_WAIT_TIMEOUT_MS = 240_000
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
                       timeout_sec: float, user_token: str | None) -> dict | None:
    """`since_utc` より新しく、`exclude_sys_ids` に含まれない em_event を
    sys_created_on **降順** で最大 `timeout_sec` 秒待ち、最も新しい 1 件を返す。
    """
    url = settings.snow_base_url + "/api/now/table/em_event"
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
            for rec in records:
                if rec.get("sys_id") not in exclude_sys_ids:
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
def test_event_render_sustained_30min(authed_page):
    assert "biglobenonprod" in settings.snow_base_url, (
        f"このテストは biglobenonprod 用です。base_url={settings.snow_base_url}"
    )
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
        " 要件 2-6 イベント描画応答時間（高負荷継続30分） [biglobenonprod / Zurich]\n"
        "==================================================================\n"
        " 別端末で Zabbix の高負荷投入を 30 分間継続できる設定で起動してください。\n"
        " ServiceNow にイベントが流れ始めたら Enter を押すと計測開始します。\n"
        f" 計測継続時間 = {DURATION_SEC}s  /  最大計測件数 = {MAX_ITERATIONS}\n"
        "==================================================================\n"
        " Enter で計測開始 > "
    )
    print(sync_msg, end="", flush=True)
    input()

    # ---- 3. 計測開始 ----
    test_start_utc = _utc_now_str()
    test_start_epoch = time.time()
    user_token = _get_user_token(page)
    logger.info("計測開始: since_utc=%s, user_token_len=%s",
                test_start_utc, len(user_token) if user_token else 0)

    # ---- 4. 計測ループ ----
    samples: list[dict] = []
    measured_sys_ids: set[str] = set()
    overall_deadline = test_start_epoch + DURATION_SEC

    while len(samples) < MAX_ITERATIONS and time.time() < overall_deadline:
        remain = overall_deadline - time.time()
        if remain <= 0:
            break

        event = _poll_latest_event(
            page, test_start_utc, measured_sys_ids,
            min(EVENT_WAIT_TIMEOUT_SEC, remain),
            user_token,
        )
        if not event:
            logger.warning("一定時間 未計測の新規イベントが届かず。次の反復へ。")
            continue

        t_received = _parse_utc(event["sys_created_on"])
        measured_sys_ids.add(event["sys_id"])

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
        rel_t = t_rendered - test_start_epoch  # テスト開始からの相対時刻
        samples.append({
            "iter": len(samples) + 1,
            "rel_t_sec": rel_t,
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
        # 進捗ログは 10 件毎にまとめて出す
        if len(samples) % 10 == 1 or len(samples) % 10 == 0:
            logger.info(
                "iter=%3d rel=%6.1fs event=%s 受信→描画 %.3fs",
                len(samples), rel_t,
                event.get("number") or (event.get("sys_id", "?")[:8]),
                elapsed,
            )

    # ---- 5. 集計 ----
    if not samples:
        pytest.fail(
            f"DURATION_SEC={DURATION_SEC}s 内で 1 件も計測できませんでした。"
            "Zabbix 投入と em_event の流入を確認してください。"
        )

    elapsed_only = [s["elapsed_sec"] for s in samples]
    stats_overall = summarize(elapsed_only)

    # 時系列分割（前半 vs 後半）で劣化チェック
    half_t = DURATION_SEC / 2
    first_half = [s["elapsed_sec"] for s in samples if s["rel_t_sec"] < half_t]
    second_half = [s["elapsed_sec"] for s in samples if s["rel_t_sec"] >= half_t]
    stats_first = summarize(first_half)
    stats_second = summarize(second_half)

    saturated = (
        stats_second.get("count", 0) > 0
        and stats_first.get("count", 0) > 0
        and stats_second["avg"] > stats_first["avg"] * SATURATION_RATIO
    )

    output = {
        "instance": settings.snow_instance,
        "target_table": "em_event",
        "test_start_utc": test_start_utc,
        "duration_sec": DURATION_SEC,
        "max_iterations": MAX_ITERATIONS,
        "thresholds": {
            "avg_sec": AVG_THRESHOLD_SEC,
            "max_sec": MAX_THRESHOLD_SEC,
            "saturation_ratio": SATURATION_RATIO,
        },
        "iterations": len(samples),
        "iframe_selector": iframe_sel or "(top-page)",
        "stats": {
            "overall": stats_overall,
            "first_half_15min": stats_first,
            "second_half_15min": stats_second,
            "saturated": saturated,
        },
        "samples": samples,
    }
    RESULT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info("結果保存: %s", RESULT_PATH)
    logger.info("Overall: %s", stats_overall)
    logger.info("First half (0–%.0fs): %s", half_t, stats_first)
    logger.info("Second half (%.0f–%.0fs): %s", half_t, DURATION_SEC, stats_second)
    logger.info("Saturated: %s", saturated)

    # ---- 6. 合否判定 ----
    assert stats_overall["avg"] <= AVG_THRESHOLD_SEC, (
        f"全体平均 {stats_overall['avg']:.2f}s が閾値 {AVG_THRESHOLD_SEC}s 超過"
    )
    assert stats_overall["max"] <= MAX_THRESHOLD_SEC, (
        f"全体最大 {stats_overall['max']:.2f}s が閾値 {MAX_THRESHOLD_SEC}s 超過"
    )
    assert not saturated, (
        f"後半平均 {stats_second.get('avg', 0):.2f}s が "
        f"前半平均 {stats_first.get('avg', 0):.2f}s の "
        f"{SATURATION_RATIO} 倍を超過（性能飽和）"
    )
