"""SNOW_USER / SNOW_PASSWORD でフォームログインが通るかを単体検証する。

使い方:
    python3 _common/check_form_login.py [--headed]

オプション:
    --headed   ブラウザを表示する (デフォルトはヘッドレス)
    --user     ユーザ名を上書き (.env を無視)
    --password パスワードを上書き

成功時 exit 0、失敗時 exit 1。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from _common.config import settings  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--headed", action="store_true")
    p.add_argument("--user", default=settings.snow_user)
    p.add_argument("--password", default=settings.snow_password)
    args = p.parse_args()

    if not args.user or not args.password:
        print("ERROR: .env に SNOW_USER / SNOW_PASSWORD を設定してください")
        return 1

    print(f"Instance : {settings.snow_base_url}")
    print(f"User     : {args.user}")
    print(f"Password : {'*' * len(args.password)} ({len(args.password)} chars)")
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(settings.snow_base_url + "/login.do", wait_until="networkidle")
        page.fill("#user_name", args.user)
        page.fill("#user_password", args.password)
        page.click("#sysverb_login")
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass

        # 判定
        if page.locator("#user_name").count() > 0:
            print(f"NG: ログイン失敗。最終URL={page.url}")
            # 画面メッセージを拾う
            for sel in ["#output_messages", ".outputmsg_text", ".alert-danger"]:
                loc = page.locator(sel)
                if loc.count() > 0:
                    try:
                        msg = loc.first.inner_text(timeout=1000).strip()
                        if msg:
                            print(f"   画面メッセージ: {msg}")
                            break
                    except Exception:
                        pass
            # スクリーンショット
            shot = Path(__file__).resolve().parent.parent / "login_check_fail.png"
            page.screenshot(path=str(shot), full_page=True)
            print(f"   screenshot: {shot}")
            browser.close()
            return 1

        # MFA 要求画面に着地していないか（ログインフォームは消えるので誤判定しやすい）
        if "multifactor" in page.url.lower() or "mfa" in page.url.lower():
            print(f"NG: MFA が要求されました。最終URL={page.url}")
            print("    このアカウントは SSO バイパスできても MFA が有効なため、")
            print("    テスト内での自動再ログインには使用できません。")
            print("    自動化するには MFA 免除のテスト用アカウントが必要です。")
            shot = Path(__file__).resolve().parent.parent / "login_check_mfa.png"
            page.screenshot(path=str(shot), full_page=True)
            print(f"    screenshot: {shot}")
            browser.close()
            return 1

        print(f"OK: ログイン成功。最終URL={page.url}")
        # 確認のため認証済 API を一発叩く
        api_url = f"{settings.snow_base_url}/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=user_name"
        page.goto(api_url, wait_until="domcontentloaded")
        body = page.content()
        if "user_name" in body and "guest" not in body:
            print("OK: 認証済み API 呼び出し成功")
        else:
            print("WARN: API 確認が想定外の結果")
        browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
