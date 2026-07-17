"""Playwright 用ヘルパー：ログイン、計測、iframe対応、storage_state"""
import logging
import statistics
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional, Union

from playwright.sync_api import BrowserContext, FrameLocator, Page

from .config import settings

logger = logging.getLogger(__name__)

# ServiceNow Classic UIのコンテンツは iframe#gsft_main 内に表示される
SNOW_CONTENT_IFRAME = "iframe#gsft_main"


def get_auth_state_path() -> Path:
    return Path(__file__).resolve().parent.parent / "auth.json"


def has_auth_state() -> bool:
    p = get_auth_state_path()
    return p.exists() and p.stat().st_size > 0


def snow_login_form(page: Page, user: Optional[str] = None,
                    password: Optional[str] = None) -> None:
    """SSOバイパス可能なローカルユーザでフォーム認証

    ログイン後にフォームDOMが残っている場合は認証失敗とみなして例外を投げる。
    """
    user = user or settings.snow_user
    password = password or settings.snow_password
    if not user or not password:
        raise RuntimeError("SNOW_USER / SNOW_PASSWORD を .env で設定してください")

    logger.info("ローカル form login 開始: user=%s", user)
    page.goto(f"{settings.snow_base_url}/login.do",
              wait_until="networkidle", timeout=20_000)
    page.fill("#user_name", user)
    page.fill("#user_password", password)
    page.click("#sysverb_login")
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:
        pass

    # 認証成否を検証：ログインフォームが残っていればNG
    if page.locator("#user_name").count() > 0:
        # 画面上のエラーメッセージを拾う
        err_msg = ""
        for sel in [
            "#output_messages",
            ".outputmsg_text",
            ".alert-danger",
            "#login_message",
            ".login_error",
        ]:
            loc = page.locator(sel)
            if loc.count() > 0:
                try:
                    err_msg = loc.first.inner_text(timeout=2000).strip()
                    if err_msg:
                        break
                except Exception:
                    continue
        raise RuntimeError(
            f"ローカルログイン失敗 (user={user}, URL={page.url})。"
            f"パスワード誤り or アカウント無効 or Adaptive Auth の可能性。"
            f"画面メッセージ: {err_msg or '(取得不可)'}"
        )
    logger.info("ローカル form login 成功 (URL=%s)", page.url)


def assert_logged_in(page: Page) -> None:
    """auth.json で認証済みかを検証する。

    URL チェックだけでなく、ログインフォーム DOM (#user_name) の存在も確認する。
    SSO 未完了で /navpage.do などに着地しているケースも検出できる。
    """
    page.goto(settings.snow_base_url + "/navpage.do",
              wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    if "/login" in page.url or "accounts.google.com" in page.url:
        raise RuntimeError(
            "auth.json のセッションが期限切れの可能性 (URL=/login)。"
            "python3 _common/save_auth_state.py を再実行してください"
        )
    # ログインフォームが見えている＝未認証
    if page.locator("#user_name").count() > 0 or page.locator(
        "input[name='user_name']"
    ).count() > 0:
        raise RuntimeError(
            f"未認証セッションです (URL={page.url})。"
            "auth.json を再取得するか、auth.json を退避して "
            "SNOW_USER/SNOW_PASSWORD でフォームログインを使ってください。"
        )


def snow_content(page: Page, *, prefer_iframe: bool = True) -> Union[Page, FrameLocator]:
    """ServiceNow コンテンツへのロケーターを返す

    - Classic UI（/now/nav/...）→ iframe#gsft_main の中
    - Polaris/Workspace → トップフレーム
    - 自動判定：iframe が存在すればframe_locator、なければ page を返す
    """
    if prefer_iframe and page.locator(SNOW_CONTENT_IFRAME).count() > 0:
        return page.frame_locator(SNOW_CONTENT_IFRAME)
    return page


def snow_goto_and_wait(page: Page, path: str, *,
                      content_selector: str = "body",
                      timeout_ms: int = 15000) -> Union[Page, FrameLocator]:
    """ServiceNow ページを開き、コンテンツ読み込み完了を待ち、コンテンツロケーターを返す

    `path` は相対パス（例: "/incident_list.do" or "/now/nav/ui/classic/params/target/incident_list.do"）
    """
    page.goto(path, wait_until="domcontentloaded")
    # ナビゲータ経由なら iframe を待つ
    if "/now/nav/" in path:
        page.wait_for_selector(SNOW_CONTENT_IFRAME, timeout=timeout_ms)
        content = page.frame_locator(SNOW_CONTENT_IFRAME)
    else:
        content = page
    # コンテンツ側で body が現れるのを待つ
    if isinstance(content, FrameLocator):
        content.locator(content_selector).first.wait_for(timeout=timeout_ms)
    else:
        content.wait_for_selector(content_selector, timeout=timeout_ms)
    return content


@contextmanager
def measure(label: str, samples: Optional[list[float]] = None):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    logger.info("[measure] %s: %.3fs", label, elapsed)
    if samples is not None:
        samples.append(elapsed)


def summarize(samples: Iterable[float]) -> dict:
    arr = list(samples)
    if not arr:
        return {"count": 0}
    return {
        "count": len(arr),
        "min": min(arr),
        "max": max(arr),
        "avg": statistics.mean(arr),
        "median": statistics.median(arr),
        "p95": statistics.quantiles(arr, n=20)[-1] if len(arr) >= 20 else max(arr),
    }
