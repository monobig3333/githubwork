"""Zabbix コネクタ (em_connector_instance) の状態確認・継続モニタ

【使い方】
  # スポット確認（一度だけ）
  python3 N-common/check_zabbix_connector.py

  # 名前で絞り込み (LIKE 検索)
  python3 N-common/check_zabbix_connector.py --name zabbix

  # 継続モニタ（10 秒間隔で 600 秒）
  python3 N-common/check_zabbix_connector.py --watch 600 --interval 10

  # 異常検知 (status が "Running" でなくなったら exit 1)
  python3 N-common/check_zabbix_connector.py --watch 600 --fail-on-non-running

【表示項目】
  - name             : インスタンス名
  - mid_server       : 担当 MID
  - status           : Running / Failed / Stopped 等
  - last_collected   : 最終ポーリング成功時刻
  - last_modified    : インスタンス更新時刻
  - error_message    : エラーがあれば
  - connector_definition: 紐づく em_connector への参照
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def fetch_records(page, g_ck: str, name_like: str | None) -> list[dict]:
    url = settings.snow_base_url + "/api/now/table/em_connector_instance"
    params = {
        "sysparm_limit": "50",
        "sysparm_fields": (
            "sys_id,name,mid_server,status,last_collected,sys_updated_on,"
            "error_message,connector_definition,active"
        ),
        "sysparm_display_value": "true",
    }
    if name_like:
        params["sysparm_query"] = f"nameLIKE{name_like}"
    headers = {
        "Accept": "application/json",
        "Referer": settings.snow_base_url + "/em_connector_instance_list.do",
        "X-UserToken": g_ck,
    }
    resp = page.request.get(url, params=params, headers=headers, timeout=15_000)
    if not resp.ok:
        sys.stderr.write(f"API status={resp.status} body={resp.text()[:200]}\n")
        return []
    try:
        return resp.json().get("result", [])
    except Exception:
        return []


def print_records(records: list[dict]) -> None:
    if not records:
        print("  (該当 em_connector_instance なし)")
        return
    header = f"  {'name':<28}{'mid':<32}{'status':<12}{'last_collected':<22}{'error'}"
    print(header)
    print('  ' + '-' * (len(header) - 2))
    for r in records:
        name = (r.get('name') or '')[:27]
        mid = str(r.get('mid_server') or '')[:31]
        status = (r.get('status') or '')[:11]
        last = str(r.get('last_collected') or '')[:21]
        err = (r.get('error_message') or '').replace('\n', ' ')[:60]
        print(f"  {name:<28}{mid:<32}{status:<12}{last:<22}{err}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="", help="name LIKE 絞り込み (例: zabbix)")
    p.add_argument("--watch", type=int, default=0, help=">0 なら継続モニタ秒数")
    p.add_argument("--interval", type=int, default=10, help="モニタ間隔秒")
    p.add_argument("--output", type=Path, default=None, help="watch 時に JSON 保存")
    p.add_argument("--fail-on-non-running", action="store_true",
                   help="Running 以外を検知したら exit 1")
    args = p.parse_args()

    auth_path = Path(__file__).resolve().parent.parent / "auth.json"
    if not auth_path.exists():
        sys.stderr.write(f"NG: auth.json が見つかりません: {auth_path}\n")
        return 2

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(auth_path))
        page = context.new_page()
        # g_ck を取得するため何かページを開く
        page.goto(settings.snow_base_url + "/em_connector_instance_list.do",
                  wait_until="domcontentloaded", timeout=20_000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        g_ck = page.evaluate("() => (window.g_ck || '')") or ""
        if not g_ck:
            sys.stderr.write("NG: g_ck (X-UserToken) を取得できません。auth.json 期限切れの可能性\n")
            browser.close()
            return 3

        if args.watch <= 0:
            records = fetch_records(page, g_ck, args.name or None)
            print(f"[{_utc_now()}] em_connector_instance ({len(records)} 件)")
            print_records(records)
            browser.close()
            return 0

        # 継続モニタ
        deadline = time.time() + args.watch
        timeline = []
        rc = 0
        while time.time() < deadline:
            records = fetch_records(page, g_ck, args.name or None)
            print(f"\n[{_utc_now()}] em_connector_instance ({len(records)} 件)")
            print_records(records)
            timeline.append({"ts": _utc_now(), "records": records})
            if args.fail_on_non_running:
                for r in records:
                    if (r.get("status") or "").strip().lower() != "running":
                        print(f"  ⚠ non-running 検知: name={r.get('name')} status={r.get('status')}")
                        rc = 1
            time.sleep(args.interval)

        browser.close()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(timeline, indent=2, ensure_ascii=False))
        print(f"\n結果保存: {args.output}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
