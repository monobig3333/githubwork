"""N-5 用：ServiceNow 上で MID Server が Down/Warning になることを確認する。

【仕様】
  - ecc_agent テーブルを定期ポーリング (--mid-name または LIKE 検索)
  - status (or sys_class_name=ecc_agent.status) を時系列で記録
  - 期間中に status が "Up" 以外になった瞬間を NG ステータス検出として記録
  - 既定の合否: status が一度でも Up 以外 (Down / Warning / Disconnected) になれば OK

【使い方】
  python3 N-common/verify_mid_status.py \\
      --duration 600 --mid-name mid-server-aws-zabbix-stg-1 \\
      --output N-5/result_mid_status.json
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


POLL_INTERVAL = 2.0  # sec


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=int, default=600)
    p.add_argument("--mid-name", required=True,
                   help="ecc_agent.name の完全一致 or LIKE 文字列")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--like", action="store_true",
                   help="--mid-name を LIKE で照合する")
    p.add_argument("--no-wait", action="store_true")
    args = p.parse_args()

    auth_path = Path(__file__).resolve().parent.parent / "auth.json"
    if not auth_path.exists():
        print(f"NG: auth.json が見つかりません: {auth_path}", file=sys.stderr)
        return 2

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(auth_path))
        page = context.new_page()
        page.goto(settings.snow_base_url + "/em_event_list.do",
                  wait_until="domcontentloaded", timeout=20_000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        g_ck = page.evaluate("() => (window.g_ck || '')") or ""
        if not g_ck:
            print("NG: g_ck (X-UserToken) を取得できませんでした", file=sys.stderr)
            browser.close()
            return 3

        if not args.no_wait:
            print("\n" + "=" * 70)
            print(" 非正常系: MID Status 検出確認 (N-5)")
            print("=" * 70)
            print(f" MID 名前(検索): {args.mid_name}  (LIKE={args.like})")
            print(" 別端末で TCP 枯渇負荷を起動した後、Enter で計測開始。")
            print("=" * 70)
            input(" Enter で計測開始 > ")

        start_utc = _utc_now_str()
        start_epoch = time.time()
        deadline = start_epoch + args.duration
        api_url = settings.snow_base_url + "/api/now/table/ecc_agent"
        if args.like:
            query = f"nameLIKE{args.mid_name}"
        else:
            query = f"name={args.mid_name}"
        params = {
            "sysparm_limit": "5",
            "sysparm_fields": "sys_id,name,status,host_name,validated,last_collected,sys_updated_on",
            "sysparm_query": query,
            "sysparm_display_value": "false",
        }
        headers = {
            "Accept": "application/json",
            "Referer": settings.snow_base_url + "/ecc_agent_list.do",
            "X-UserToken": g_ck,
        }

        timeline: list[dict] = []
        api_errors = 0
        statuses_seen: set[str] = set()
        first_anomaly_at = None

        while time.time() < deadline:
            try:
                resp = page.request.get(api_url, params=params, headers=headers,
                                         timeout=15_000)
            except Exception as e:
                api_errors += 1
                timeline.append({"ts": _utc_now_str(), "type": "api_exception",
                                 "detail": str(e)[:200]})
                time.sleep(POLL_INTERVAL)
                continue
            if not resp.ok:
                api_errors += 1
                timeline.append({"ts": _utc_now_str(), "type": "api_error",
                                 "status": resp.status})
                time.sleep(POLL_INTERVAL)
                continue
            records = resp.json().get("result", [])
            for rec in records:
                st = str(rec.get("status") or "")
                statuses_seen.add(st)
                entry = {
                    "ts": _utc_now_str(),
                    "name": rec.get("name"),
                    "status": st,
                    "validated": rec.get("validated"),
                    "last_collected": rec.get("last_collected"),
                    "sys_updated_on": rec.get("sys_updated_on"),
                }
                timeline.append(entry)
                if st and st.lower() != "up" and first_anomaly_at is None:
                    first_anomaly_at = entry["ts"]
            time.sleep(POLL_INTERVAL)

        browser.close()

    end_utc = _utc_now_str()
    anomaly_detected = first_anomaly_at is not None
    result = {
        "label": "N-5",
        "instance": settings.snow_instance,
        "mid_name": args.mid_name,
        "test_start_utc": start_utc,
        "test_end_utc": end_utc,
        "duration_sec": args.duration,
        "statuses_observed": sorted(statuses_seen),
        "anomaly_detected": anomaly_detected,
        "first_anomaly_at": first_anomaly_at,
        "api_errors": api_errors,
        "judgment": "OK" if anomaly_detected else "NG",
        "timeline": timeline,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print()
    print(f"観測 status   : {sorted(statuses_seen)}")
    print(f"異常検出      : {anomaly_detected}  (初回 {first_anomaly_at})")
    print(f"判定         : {result['judgment']}")
    print(f"結果保存     : {args.output}")
    return 0 if anomaly_detected else 1


if __name__ == "__main__":
    sys.exit(main())
