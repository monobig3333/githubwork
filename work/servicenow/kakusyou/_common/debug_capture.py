"""ServiceNow 画面のスクリーンショット・HTML 構造を取得するデバッグツール

セレクタ調整時、対象ページに実際にどんな要素があるかを確認するために使う。

【使い方】
  python3 _common/debug_capture.py /now/nav/ui/classic/params/target/incident_list.do
  python3 _common/debug_capture.py /incident_list.do --headless
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from _common.config import settings
from _common.playwright_helpers import get_auth_state_path, has_auth_state


def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")[:60]


PROBE_SELECTORS = [
    "table.list_table",
    "a.linked.formlink",
    '[data-name="number"]',
    '[data-name="short_description"]',
    "now-record-list",
    "now-record-form",
    'div[role="grid"]',
    "form#change_request.form",
    "form",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="開く相対パス（複数指定可）")
    parser.add_argument("--outdir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "_debug")
    parser.add_argument("--headless", action="store_true",
                        help="ブラウザを表示せず実行")
    parser.add_argument("--wait", type=int, default=3,
                        help="ページ表示後の待機秒数（描画完了用）")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    if not has_auth_state():
        print("ERROR: auth.json がありません。"
              "python3 _common/save_auth_state.py を先に実行してください")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            storage_state=str(get_auth_state_path()),
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()

        for path in args.paths:
            url = f"{settings.snow_base_url}{path}"
            print(f"\n→ {url}")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(args.wait * 1000)

            slug = slugify(path)

            shot_path = args.outdir / f"{slug}.png"
            page.screenshot(path=str(shot_path), full_page=True)
            print(f"  Screenshot: {shot_path}")

            html_top = args.outdir / f"{slug}_top.html"
            html_top.write_text(page.content())
            print(f"  Top HTML:   {html_top}")

            print("  --- selector counts (top frame) ---")
            for sel in PROBE_SELECTORS:
                cnt = page.locator(sel).count()
                if cnt > 0:
                    print(f"    top  [{cnt:>3}] {sel}")

            # iframe#gsft_main 内も探索
            frame = page.frame(name="gsft_main")
            if frame is not None:
                iframe_html = args.outdir / f"{slug}_iframe.html"
                iframe_html.write_text(frame.content())
                print(f"  iframe HTML: {iframe_html}")
                print("  --- selector counts (iframe) ---")
                for sel in PROBE_SELECTORS:
                    cnt = frame.locator(sel).count()
                    if cnt > 0:
                        print(f"    iframe [{cnt:>3}] {sel}")

        browser.close()

    print(f"\n出力先: {args.outdir}")


if __name__ == "__main__":
    main()
