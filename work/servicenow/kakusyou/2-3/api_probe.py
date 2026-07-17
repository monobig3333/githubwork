"""2-3 用：auth.json 経由のブラウザセッションで REST API が叩けるか確認

  1. auth.json を読み込んだブラウザコンテキストでビューワーを開く
  2. /api/now/table/sys_user?sysparm_limit=1 を 3 通りで試す:
       (a) cookie のみ
       (b) cookie + X-UserToken (window.g_ck)
       (c) page.evaluate 経由でブラウザ内 fetch
  3. それぞれの結果（HTTP status / body 先頭）を表示
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from _common.config import settings  # noqa: E402


def main() -> int:
    auth_path = Path(__file__).resolve().parent.parent / "auth.json"
    if not auth_path.exists():
        print(f"NG: auth.json が見つかりません: {auth_path}")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(auth_path))
        page = context.new_page()

        # 何かのページを開いて g_ck を取れるようにする
        page.goto(settings.snow_base_url + "/em_alert_list.do",
                  wait_until="domcontentloaded", timeout=20_000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        cookies = context.cookies()
        cookie_names = [c["name"] for c in cookies if "service-now" in c.get("domain", "")]
        print(f"[INFO] page.url={page.url}")
        print(f"[INFO] ServiceNow cookies={cookie_names}")

        g_ck = ""
        try:
            g_ck = page.evaluate("() => (window.g_ck || '')") or ""
        except Exception as e:
            print(f"[WARN] g_ck 取得失敗: {e}")
        print(f"[INFO] g_ck length={len(g_ck)}")

        url = settings.snow_base_url + "/api/now/table/sys_user"
        params = {"sysparm_limit": "1", "sysparm_fields": "user_name"}

        def show(label, resp):
            body = resp.text()[:200].replace("\n", " ")
            print(f"  [{label}] status={resp.status} body={body}")

        print("\n--- (a) cookie only ---")
        r = page.request.get(url, params=params,
                             headers={"Accept": "application/json"})
        show("a", r)

        print("\n--- (b) cookie + X-UserToken + Referer ---")
        r = page.request.get(
            url, params=params,
            headers={
                "Accept": "application/json",
                "X-UserToken": g_ck,
                "Referer": settings.snow_base_url + "/em_alert_list.do",
            },
        )
        show("b", r)

        print("\n--- (c) browser internal fetch (page.evaluate) ---")
        try:
            data = page.evaluate(
                """async (params) => {
                    const q = new URLSearchParams(params).toString();
                    const r = await fetch('/api/now/table/sys_user?' + q, {
                        method: 'GET',
                        credentials: 'include',
                        headers: { 'Accept': 'application/json' },
                    });
                    const text = await r.text();
                    return { status: r.status, body: text.slice(0, 200) };
                }""",
                params,
            )
            print(f"  [c] status={data['status']} body={data['body']}")
        except Exception as e:
            print(f"  [c] EXCEPTION: {e}")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
