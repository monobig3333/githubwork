"""要件2-3: イベント描画応答時間（通常時） - Zabbix外部投入版 (Zurich対応)

【テスト内容】
  ①Zabbix から ServiceNow（biglobenonprod / Zurich）へ標準負荷でイベントを流す
  ②イベント受信からイベントビューワー描画完了までの時間を 20 回計測

【合否判定基準】
  イベント受信から描画完了まで 3秒以内であること
  ※ 「描画」は em_event テーブルのレコードがビューワー (em_event_list.do)
     画面に表示された時点

【認証】
  - Playwright の auth.json を使ったブラウザセッションだけで完結
  - API 呼び出しも page.request 経由（auth.json の cookie + X-UserToken）
  - OAuth / AWS Secrets Manager は本テストでは未使用

【測定方式】
  ・ServiceNow Table API (em_event) を ORDERBYsys_created_on で昇順ポーリング
    → ブラウザの認証済みセッションを再利用 (page.request.get + X-UserToken)
  ・各イベントについて
        elapsed = (DOM 描画完了時刻 - em_event.sys_created_on(UTC))
    を計測

【UI 対応】
  Zurich / Next Experience UI と Classic UI の両方に対応:
    1. /em_event_list.do                                    （Classic 直接）
    2. /now/nav/ui/classic/params/target/em_event_list.do   （Next Exp 経由）
  各候補URLに対し iframe / 直接 page を試行。
  描画検知は iframe があれば iframe 内、無ければ page 全体に対して
  text=<event.number> で wait_for。

【手動同期】
  - 別端末で Zabbix の負荷投入を並走起動する想定
  - テストは Enter 入力を待ち合わせ → そこから計測開始
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from playwright.sync_api import Page, TimeoutError as PWTimeout

from _common.config import settings
from _common.playwright_helpers import summarize

logger = logging.getLogger(__name__)

# ---------- パラメータ ----------
ITERATIONS = 20
THRESHOLD_SEC = 3.0
RESULT_PATH = Path(__file__).parent / "result_2_3.json"
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
EVENT_WAIT_TIMEOUT_SEC = 30
RENDER_WAIT_TIMEOUT_MS = 10_000
NAV_TIMEOUT_MS = 20_000
OVERALL_TIMEOUT_SEC = 600


# ---------- 時刻ヘルパー ----------
def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_utc(s: str) -> float:
    return (
        datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


# ---------- API ヘルパー（ブラウザセッション cookie + X-UserToken を使用） ----------
def _get_user_token(page: Page) -> str | None:
    """ServiceNow の CSRF トークン (window.g_ck) を取得"""
    try:
        return page.evaluate("() => (window.g_ck || '')")
    except Exception as e:
        logger.warning("g_ck 取得失敗: %s", e)
        return None


def _poll_new_event(page: Page, since_utc: str, timeout_sec: float,
                    user_token: str | None) -> dict | None:
    """`since_utc` より新しい em_event を最大 `timeout_sec` 秒待ち、最も古い 1 件を返す。

    認証:
      - cookie: BrowserContext と共有 (page.request)
      - CSRF : X-UserToken に window.g_ck を載せる
    """
    url = settings.snow_base_url + "/api/now/table/em_event"
    params = {
        "sysparm_limit": "1",
        "sysparm_fields": (
            "sys_id,number,description,message_key,source,node,resource,"
            "type,severity,sys_created_on"
        ),
        "sysparm_query": f"sys_created_on>{since_utc}^ORDERBYsys_created_on",
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
            resp = page.request.get(url, params=params, headers=headers, timeout=10_000)
        except Exception as e:
            logger.warning("em_event ポーリング例外: %s", e)
            time.sleep(POLL_INTERVAL_SEC)
            continue
        if resp.ok:
            try:
                records = resp.json().get("result", [])
            except Exception:
                records = []
            if records:
                return records[0]
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
    html_dump = DEBUG_DIR / f"open_viewer_fail_{int(time.time())}.html"
    try:
        html_dump.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    raise RuntimeError(
        f"イベントビューワーを開けませんでした。最後の URL={page.url}, "
        f"screenshot={shot}, html={html_dump}, last_err={last_err}"
    )


def _wait_for_event_in_dom(page: Page, iframe_sel: str, event: dict) -> bool:
    """em_event ビューワー DOM に該当イベントが現れるのを待つ。

    優先順位:
      1. event['number'] テキスト（auto-numbered フィールド）
      2. sys_id を含むリンク（list 行は通常 /em_event.do?sys_id=... を持つ）
    """
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
            # iframe 側
            if iframe_sel and page.locator(iframe_sel).count() > 0:
                try:
                    page.frame_locator(iframe_sel).locator(sel).first.wait_for(
                        timeout=400
                    )
                    return True
                except PWTimeout:
                    pass
            # 直下
            try:
                page.locator(sel).first.wait_for(timeout=400)
                return True
            except PWTimeout:
                continue
    return False


# ---------- テスト本体 ----------
@pytest.mark.perf
def test_event_render_time(authed_page):
    assert "biglobenonprod" in settings.snow_base_url, (
        f"このテストは biglobenonprod 用です。現在の base_url={settings.snow_base_url}"
    )
    logger.info("ServiceNow base_url=%s", settings.snow_base_url)

    page = authed_page

    # ---- 1. イベントビューワーを開く ----
    iframe_sel = _open_event_viewer(page)
    logger.info("ビューワー描画モード: %s",
                "iframe=" + iframe_sel if iframe_sel else "top-page")

    # ---- 2. Zabbix 負荷投入の同期待ち ----
    sync_msg = (
        "\n"
        "==================================================================\n"
        " 要件 2-3 イベント描画応答時間（通常時） [biglobenonprod / Zurich]\n"
        "==================================================================\n"
        " 別端末で Zabbix の負荷投入スクリプトを起動してください。\n"
        " ServiceNow にイベントが流れ始めたら Enter を押すと計測開始します。\n"
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

    # ---- 4. 計測ループ ----
    samples: list[dict] = []
    last_seen_utc = test_start_utc
    overall_deadline = time.time() + OVERALL_TIMEOUT_SEC

    while len(samples) < ITERATIONS:
        if time.time() > overall_deadline:
            pytest.fail(
                f"全体タイムアウト({OVERALL_TIMEOUT_SEC}s)。"
                f"{len(samples)}/{ITERATIONS} 件のみ取得"
            )

        event = _poll_new_event(page, last_seen_utc, EVENT_WAIT_TIMEOUT_SEC, user_token)
        if not event:
            pytest.fail(
                f"{EVENT_WAIT_TIMEOUT_SEC}s 以内に新規イベントが届きません。"
                "Zabbix 投入を確認してください。"
            )

        t_received = _parse_utc(event["sys_created_on"])
        last_seen_utc = event["sys_created_on"]

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
            event.get("number") or event.get("sys_id", "?")[:8],
            elapsed,
        )

    # ---- 5. 集計・保存 ----
    elapsed_list = [s["elapsed_sec"] for s in samples]
    stats = summarize(elapsed_list)
    output = {
        "instance": settings.snow_instance,
        "target_table": "em_event",
        "test_start_utc": test_start_utc,
        "threshold_sec": THRESHOLD_SEC,
        "iterations": len(samples),
        "iframe_selector": iframe_sel or "(top-page)",
        "stats": stats,
        "samples": samples,
    }
    RESULT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info("結果保存: %s", RESULT_PATH)
    logger.info("統計: %s", stats)

    # ---- 6. 合否判定 ----
    assert stats["max"] < THRESHOLD_SEC, (
        f"最大描画時間 {stats['max']:.3f}s が閾値 {THRESHOLD_SEC}s を超過"
    )
