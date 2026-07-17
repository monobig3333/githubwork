"""N-* 非正常系試験：イベント到達継続性 検証スクリプト（手元実行）

MID サーバ上でストレス負荷をかけている間、Zabbix → ServiceNow への
イベント到達が途切れないかを継続ポーリングで確認する。

【仕様】
  - auth.json (Google SSO storage_state) を使ったブラウザセッションで
    /api/now/table/em_event を X-UserToken 付きで叩く
  - DURATION 秒間、POLL_INTERVAL 秒間隔でポーリング
  - 連続するイベントの sys_created_on の最大ギャップを集計
  - 閾値 (--max-gap) を超えるギャップが発生したら NG
  - 結果は JSON で出力

【使い方】
  cd /Users/bx0815610/githubwork/work/servicenow/kakusyou
  python3 N-common/verify_continuity.py \\
      --duration 600 --max-gap 60 --output N-1/result.json

【手順 (3 端末構成)】
  端末 A (手元): このスクリプトを起動 → "Press Enter to start" で待機
  端末 B (MID server stg-1): bash stress_*.sh 600
  端末 C (Zabbix 側): 既存の負荷投入を起動 (もしくはバックグラウンド継続)
  端末 A で Enter → 計測スタート
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common.config import settings  # noqa: E402


POLL_INTERVAL = 1.0  # sec


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_utc(s: str) -> float:
    return (
        datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=int, default=600, help="計測秒数 (既定 600)")
    p.add_argument("--max-gap", type=float, default=60.0,
                   help="許容する連続イベント間ギャップ秒 (既定 60)")
    p.add_argument("--output", type=Path, required=True, help="結果 JSON 保存先")
    p.add_argument("--label", default="", help="識別ラベル (N-1, N-2 等)")
    p.add_argument("--no-wait", action="store_true",
                   help="Enter 待ちを省略して即開始")
    args = p.parse_args()

    auth_path = Path(__file__).resolve().parent.parent / "auth.json"
    if not auth_path.exists():
        print(f"NG: auth.json が見つかりません: {auth_path}", file=sys.stderr)
        return 2

    print(f"label    : {args.label or '(none)'}")
    print(f"instance : {settings.snow_base_url}")
    print(f"duration : {args.duration}s")
    print(f"max_gap  : {args.max_gap}s")
    print(f"output   : {args.output}")
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(auth_path))
        page = context.new_page()
        # g_ck を取るためビューワーを開く
        page.goto(settings.snow_base_url + "/em_event_list.do",
                  wait_until="domcontentloaded", timeout=20_000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        g_ck = ""
        try:
            g_ck = page.evaluate("() => (window.g_ck || '')") or ""
        except Exception:
            pass
        if not g_ck:
            print("NG: g_ck (X-UserToken) を取得できませんでした。auth.json 期限切れの可能性",
                  file=sys.stderr)
            browser.close()
            return 3

        if not args.no_wait:
            print("\n" + "=" * 70)
            print(f" 非正常系イベント継続性 検証 ({args.label})")
            print("=" * 70)
            print(" 別端末で MID サーバ側の負荷スクリプトを起動してください。")
            print(" 負荷が乗ったタイミングで Enter を押すと計測スタートします。")
            print("=" * 70)
            input(" Enter で計測開始 > ")

        start_epoch = time.time()
        start_utc = _utc_now_str()
        deadline = start_epoch + args.duration
        print(f"計測開始: {start_utc}")

        # ヘッダー
        api_url = settings.snow_base_url + "/api/now/table/em_event"
        params_base = {
            "sysparm_limit": "1",
            "sysparm_fields": "sys_id,sys_created_on,source",
            "sysparm_display_value": "false",
        }
        headers = {
            "Accept": "application/json",
            "Referer": settings.snow_base_url + "/em_event_list.do",
            "X-UserToken": g_ck,
        }

        last_seen_utc = start_utc
        event_timeline: list[dict] = []
        api_errors = 0
        while time.time() < deadline:
            params = dict(params_base)
            params["sysparm_query"] = (
                f"sys_created_on>{last_seen_utc}^ORDERBYsys_created_on"
            )
            try:
                resp = page.request.get(api_url, params=params, headers=headers,
                                         timeout=15_000)
            except Exception as e:
                api_errors += 1
                event_timeline.append({
                    "ts": _utc_now_str(),
                    "type": "api_exception",
                    "detail": str(e)[:200],
                })
                time.sleep(POLL_INTERVAL)
                continue

            if not resp.ok:
                api_errors += 1
                event_timeline.append({
                    "ts": _utc_now_str(),
                    "type": "api_error",
                    "status": resp.status,
                })
                time.sleep(POLL_INTERVAL)
                continue

            try:
                records = resp.json().get("result", [])
            except Exception:
                records = []

            for rec in records:
                event_timeline.append({
                    "ts_observed_utc": _utc_now_str(),
                    "sys_id": rec.get("sys_id"),
                    "sys_created_on_utc": rec.get("sys_created_on"),
                    "source": rec.get("source"),
                })
                last_seen_utc = rec["sys_created_on"]

            time.sleep(POLL_INTERVAL)

        end_epoch = time.time()
        end_utc = _utc_now_str()
        print(f"計測終了: {end_utc}")

        browser.close()

    # ---- 集計 ----
    events = [e for e in event_timeline if e.get("sys_created_on_utc")]
    n_events = len(events)
    arrival_epochs = [_parse_utc(e["sys_created_on_utc"]) for e in events]
    # 計測区間の境界も含めてギャップを計算
    boundaries = [start_epoch] + sorted(arrival_epochs) + [end_epoch]
    gaps = [boundaries[i+1] - boundaries[i] for i in range(len(boundaries)-1)]
    max_gap = max(gaps) if gaps else 0.0
    avg_gap = sum(gaps) / len(gaps) if gaps else 0.0

    pass_continuity = max_gap <= args.max_gap

    result = {
        "label": args.label,
        "instance": settings.snow_instance,
        "test_start_utc": start_utc,
        "test_end_utc": end_utc,
        "duration_sec": args.duration,
        "max_gap_threshold_sec": args.max_gap,
        "event_count": n_events,
        "api_errors": api_errors,
        "stats": {
            "max_gap_sec": max_gap,
            "avg_gap_sec": avg_gap,
            "events_per_min": (n_events / args.duration * 60) if args.duration else 0,
        },
        "judgment": "OK" if pass_continuity else "NG",
        "events": event_timeline,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print()
    print(f"イベント数      : {n_events}")
    print(f"API エラー数    : {api_errors}")
    print(f"最大ギャップ    : {max_gap:.1f} s  (閾値 {args.max_gap}s)")
    print(f"平均ギャップ    : {avg_gap:.1f} s")
    print(f"判定           : {result['judgment']}")
    print(f"結果保存       : {args.output}")
    return 0 if pass_continuity else 1


if __name__ == "__main__":
    sys.exit(main())
