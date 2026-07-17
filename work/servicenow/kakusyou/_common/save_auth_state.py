"""Playwright 用 storage_state 保存スクリプト (MFA + 永続プロファイル対応)

ServiceNow が Google SSO + MFA (Google Authenticator) で保護されている環境向け。
永続プロファイル (launch_persistent_context) を使うため:
  - Playwright インストルメンテーションのオーバーヘッドが下がり、ブラウザが軽い
  - 一度認証したデバイスを Google が記憶 → 次回 MFA 省略の可能性

【使い方】
  python3 _common/save_auth_state.py             # Playwright 同梱 Chromium で起動
  python3 _common/save_auth_state.py --chrome    # インストール済み Chrome を使用 (推奨)

【手順】
  1. 開いた Chromium/Chrome で
     (a) ユーザ名/パスワード入力
     (b) ★Google Authenticator の MFA コード入力
     (c) ServiceNow のホーム画面まで進む
  2. ターミナルで Enter
  3. 自動検証 OK なら auth.json を保存

プロファイルディレクトリは <kakusyou>/.playwright-profile/ に作成される。
このディレクトリは .gitignore 対象。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright, BrowserContext, Page  # noqa: E402

from _common.config import settings  # noqa: E402


REQUIRED_COOKIES = {"JSESSIONID", "glide_user_route"}


def verify_authenticated(page: Page, context: BrowserContext) -> tuple[bool, str]:
    """ログイン完了済みかを多面的に検証する。"""
    if "/login.do" in page.url:
        return False, f"URL が login.do のまま (URL={page.url})"

    try:
        if page.locator("#user_name").count() > 0:
            return False, "ログインフォーム DOM (#user_name) がまだ表示されています"
    except Exception:
        pass

    try:
        page.goto(settings.snow_base_url + "/navpage.do",
                  wait_until="domcontentloaded", timeout=15_000)
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    if page.locator("#user_name").count() > 0:
        return False, "navpage.do に遷移後ログインフォームに戻されました"

    html = ""
    try:
        html = page.content()
    except Exception:
        pass
    if "user.name = 'guest'" in html or 'user.name = "guest"' in html:
        return False, "ServiceNow セッションが guest ユーザのままです (未認証)"

    cookie_names = {c["name"] for c in context.cookies()}
    missing = REQUIRED_COOKIES - cookie_names
    if missing:
        return False, f"必須 cookie 不足: {sorted(missing)}"

    return True, f"OK (URL={page.url}, cookies={len(cookie_names)})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "auth.json",
    )
    parser.add_argument("--url", default=settings.snow_base_url)
    parser.add_argument(
        "--profile-dir", type=Path,
        default=Path(__file__).resolve().parent.parent / ".playwright-profile",
        help="永続プロファイルディレクトリ",
    )
    parser.add_argument(
        "--chrome", action="store_true",
        help="インストール済み Google Chrome を使用（推奨。軽くて速い）",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="プロファイルを毎回新規作成（古い状態を捨てたいとき）",
    )
    args = parser.parse_args()

    if args.fresh and args.profile_dir.exists():
        import shutil
        shutil.rmtree(args.profile_dir)
        print(f"プロファイルを削除しました: {args.profile_dir}")

    print("=" * 70)
    print(" ServiceNow auth.json 取得 (Google SSO + MFA 対応 / 永続プロファイル)")
    print("=" * 70)
    print(f" Instance     : {args.url}")
    print(f" 保存先 (json) : {args.output}")
    print(f" プロファイル  : {args.profile_dir}")
    print(f" ブラウザ     : {'Google Chrome (channel=chrome)' if args.chrome else 'Playwright Chromium'}")
    print("=" * 70)
    print()
    print(" 手順:")
    print("   1. ブラウザでユーザ名/パスワード入力")
    print("   2. ★Google Authenticator の MFA コード入力")
    print("   3. ServiceNow のホーム画面が完全に表示されるまで待つ")
    print("   4. このターミナルで Enter")
    print()
    print(" ※ 永続プロファイルなので、一度 MFA を通せば次回以降")
    print("   Google が同じデバイスとして記憶し MFA を省略する場合があります。")
    print()

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if args.chrome:
            launch_kwargs["channel"] = "chrome"
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(args.profile_dir),
                **launch_kwargs,
            )
        except Exception as e:
            print(f"\nブラウザ起動失敗: {e}")
            return 1

        # context.new_page() が失敗したら Chrome シングルトン衝突を疑う
        try:
            page = context.pages[0] if context.pages else context.new_page()
        except Exception as e:
            print(
                "\nChromeが即時終了しました。考えられる原因:\n"
                "  - 既に Chrome が起動中 (macOS シングルトン)\n"
                "  - Chrome の設定がプロファイル共有を拒否\n"
                "\n対処:\n"
                "  1. 起動中の Chrome をすべて終了する\n"
                "       osascript -e 'tell application \"Google Chrome\" to quit'\n"
                "  2. 再実行する\n"
                "  または --chrome を外して同梱 Chromium で実行する\n"
                f"\n詳細: {e}"
            )
            try:
                context.close()
            except Exception:
                pass
            return 1
        page.goto(args.url)

        while True:
            try:
                input("\n[Enter] = 保存を試みる   |   Ctrl+C = 中断  > ")
            except KeyboardInterrupt:
                print("\n中断しました")
                context.close()
                return 1

            ok, info = verify_authenticated(page, context)
            print(f"\n認証検証: {info}")
            if ok:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(args.output))
                print(f"\nSaved: {args.output}")
                context.close()
                return 0
            print("→ 保存しませんでした。MFA まで完全に認証してから再度 Enter を押してください。")

if __name__ == "__main__":
    sys.exit(main())
