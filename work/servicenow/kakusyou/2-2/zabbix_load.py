"""要件2-2 アラーム処理性能（最大負荷）- Zabbix HTTPS API 経由

zabbix_sender (TCP 10051) を使わず、HTTPS のみで Zabbix にデータ投入する。

【仕組み】
  Zabbix 側に「サーバ上で zabbix_sender を実行する Script」を登録しておき、
  Python から `script.execute` API でその Script を呼び出す。
  Mac 側のスクリプトは HTTPS 443 だけ使う。

【Zabbix 側に Script を作成（管理者作業、一度だけ）】

  Administration → Scripts → Create script
  ┌──────────────────────────────────────────────────────────┐
  │ Name:           PerfTest SendValue                       │
  │ Scope:          Manual host action                       │
  │ Type:           Script                                   │
  │ Execute on:     Zabbix server                            │
  │ Commands:                                                │
  │   /usr/bin/zabbix_sender -z 127.0.0.1 (continued on next line)                  │
  │     -s "{HOST.HOST}" -k "test-hyoka" -o "1"              │
  │ Host group:     All / Selected                           │
  │ User group:     Zabbix administrators                    │
  │ Confirmation:   (空欄)                                   │
  └──────────────────────────────────────────────────────────┘

  作成後 scriptid を控える（URL の sysparm_id か、API で確認）。

【使い方】

  # .env に ZABBIX_SCRIPT_ID を設定
  python3 2-2/zabbix_load.py --total 10 --rate 5

  # 30000ホストに1件ずつ
  python3 2-2/zabbix_load.py --total 30000 --rate 50
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ===== 設定 =====
ZABBIX_URL       = os.getenv("ZABBIX_URL",       "https://10.249.73.66/zabbix/api_jsonrpc.php")
ZABBIX_USER      = os.getenv("ZABBIX_USER",      "")
ZABBIX_PASSWORD  = os.getenv("ZABBIX_PASSWORD",  "")
ZABBIX_TOKEN     = os.getenv("ZABBIX_TOKEN",     "")
ZABBIX_SCRIPT_ID = os.getenv("ZABBIX_SCRIPT_ID", "")  # 作成済み script の sysid
HOST_PREFIX      = os.getenv("ZABBIX_HOST_PREFIX", "test-servicenow-monohyouka-")
HOST_FORMAT      = os.getenv("ZABBIX_HOST_FORMAT", "{prefix}{n:05d}")
VERIFY_TLS       = os.getenv("ZABBIX_VERIFY_TLS", "false").lower() == "true"


class ZabbixAPI:
    """Zabbix JSON-RPC API クライアント（HTTPS のみ）"""

    def __init__(self, url: str, verify_tls: bool = False):
        self.url = url
        self.verify = verify_tls
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # コネクションプールを大きめに（parallel 並列対応）
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.auth_token: str | None = None
        self.req_id = 0

    def _call(self, method: str, params, with_auth: bool = True):
        self.req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.req_id,
        }
        headers = {}
        if ZABBIX_TOKEN and with_auth and method not in ("user.login", "apiinfo.version"):
            headers["Authorization"] = f"Bearer {ZABBIX_TOKEN}"
        elif self.auth_token and with_auth and method not in ("user.login", "apiinfo.version"):
            payload["auth"] = self.auth_token

        r = self.session.post(self.url, data=json.dumps(payload),
                              headers=headers, verify=self.verify, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"{method}: {data['error']}")
        return data["result"]

    def login(self, user: str, password: str) -> None:
        try:
            self.auth_token = self._call("user.login",
                                         {"user": user, "password": password},
                                         with_auth=False)
        except RuntimeError:
            self.auth_token = self._call("user.login",
                                         {"username": user, "password": password},
                                         with_auth=False)
        logger.info("Logged in as %s", user)

    def logout(self) -> None:
        if self.auth_token and not ZABBIX_TOKEN:
            try:
                self._call("user.logout", [])
            except Exception:
                pass
            self.auth_token = None

    def find_host(self, host_name: str) -> str | None:
        """ホスト名から hostid を取得"""
        result = self._call("host.get", {
            "filter": {"host": host_name},
            "output": ["hostid"],
        })
        return result[0]["hostid"] if result else None

    def list_hosts(self, name_prefix: str, limit: int = 30000) -> dict:
        """プレフィックス検索で {host: hostid} の dict を返す"""
        result = self._call("host.get", {
            "search": {"host": name_prefix},
            "startSearch": True,
            "output": ["hostid", "host"],
            "limit": limit,
        })
        return {h["host"]: h["hostid"] for h in result}

    def script_execute(self, scriptid: str, hostid: str) -> dict:
        """script.execute - Zabbix サーバ上でスクリプトを実行"""
        return self._call("script.execute", {
            "scriptid": scriptid,
            "hostid": hostid,
        })

    def list_scripts(self) -> list[dict]:
        """登録済みのスクリプト一覧"""
        return self._call("script.get", {
            "output": ["scriptid", "name", "command", "scope", "type"],
        })


def host_name(n: int) -> str:
    return HOST_FORMAT.format(prefix=HOST_PREFIX, n=n)


def _exec_one(zapi: ZabbixAPI, scriptid: str, hostid: str, host_label: str) -> tuple[bool, str]:
    try:
        r = zapi.script_execute(scriptid, hostid)
        # script.execute は通常 {"response": "success", "value": "..."} を返す
        if isinstance(r, dict) and r.get("response") == "success":
            return True, ""
        return False, f"{host_label}: {r}"
    except Exception as e:
        return False, f"{host_label}: {str(e)[:200]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=30000)
    parser.add_argument("--rate", type=float, default=50.0,
                        help="目標 req/s")
    parser.add_argument("--parallel", type=int, default=20)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=30000)
    parser.add_argument("--single-host", action="store_true",
                        help="--start のホストに集中送信")
    parser.add_argument("--list-scripts", action="store_true",
                        help="Zabbix に登録されたスクリプト一覧を表示して終了")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not ZABBIX_TOKEN and not (ZABBIX_USER and ZABBIX_PASSWORD):
        logger.error("ZABBIX_TOKEN or (ZABBIX_USER + ZABBIX_PASSWORD) must be set in .env")
        sys.exit(1)

    zapi = ZabbixAPI(ZABBIX_URL, verify_tls=VERIFY_TLS)
    try:
        if not ZABBIX_TOKEN:
            zapi.login(ZABBIX_USER, ZABBIX_PASSWORD)

        if args.list_scripts:
            logger.info("=== Registered scripts in Zabbix ===")
            for s in zapi.list_scripts():
                logger.info("  scriptid=%s name=%s type=%s scope=%s",
                            s.get("scriptid"), s.get("name"),
                            s.get("type"), s.get("scope"))
                logger.info("    command: %s", s.get("command", "")[:200])
            return

        if not ZABBIX_SCRIPT_ID:
            logger.error("ZABBIX_SCRIPT_ID is not set in .env. "
                         "Run with --list-scripts to find the scriptid.")
            sys.exit(2)

        # ホストリスト解決（host名 → hostid のマップ取得）
        logger.info("Fetching hostids for prefix %s ...", HOST_PREFIX)
        host_map = zapi.list_hosts(HOST_PREFIX)
        logger.info("Found %d hosts matching prefix", len(host_map))

        # 送信対象のホストリスト
        if args.single_host:
            target_name = host_name(args.start)
            if target_name not in host_map:
                logger.error("Host not found: %s", target_name)
                sys.exit(3)
            host_seq = [(target_name, host_map[target_name])] * args.total
        else:
            names_in_range = [host_name(n) for n in range(args.start, args.end + 1)]
            available = [(n, host_map[n]) for n in names_in_range if n in host_map]
            if not available:
                logger.error("No hosts found in range %d-%d", args.start, args.end)
                sys.exit(4)
            logger.info("In-range hosts: %d / %d requested", len(available),
                        args.end - args.start + 1)
            host_seq = [available[i % len(available)] for i in range(args.total)]

        logger.info("=" * 60)
        logger.info("Zabbix URL:   %s", ZABBIX_URL)
        logger.info("Script ID:    %s", ZABBIX_SCRIPT_ID)
        logger.info("Total sends:  %d", args.total)
        logger.info("Target rate:  %.1f req/s", args.rate)
        logger.info("Parallel:     %d workers", args.parallel)
        logger.info("Verify TLS:   %s", VERIFY_TLS)
        logger.info("=" * 60)

        if args.dry_run:
            logger.info("[DRY_RUN] sample hosts:")
            for h, hid in host_seq[:5]:
                logger.info("  %s (hostid=%s)", h, hid)
            return

        # 流量制御つき並列実行
        interval = 1.0 / args.rate
        start_t = time.perf_counter()
        success = 0
        failed = 0
        errors_sample = []

        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            pending = []
            for i, (hname, hid) in enumerate(host_seq):
                target_t = start_t + i * interval
                now = time.perf_counter()
                if target_t > now:
                    time.sleep(target_t - now)
                pending.append(ex.submit(_exec_one, zapi, ZABBIX_SCRIPT_ID, hid, hname))

                if (i + 1) % 100 == 0:
                    elapsed = time.perf_counter() - start_t
                    logger.info("Progress: %d/%d | effective=%.1f req/s",
                                i + 1, args.total, (i + 1) / elapsed)

            for f in as_completed(pending):
                ok, msg = f.result()
                if ok:
                    success += 1
                else:
                    failed += 1
                    if len(errors_sample) < 5:
                        errors_sample.append(msg)

        overall = time.perf_counter() - start_t

        logger.info("=" * 60)
        logger.info("Total:     %d", args.total)
        logger.info("Success:   %d (%.2f%%)", success, success / args.total * 100)
        logger.info("Failed:    %d (%.2f%%)", failed, failed / args.total * 100)
        logger.info("Elapsed:   %.1fs", overall)
        logger.info("Effective: %.1f req/s", args.total / overall)
        if errors_sample:
            logger.info("Error sample:")
            for e in errors_sample:
                logger.info("  %s", e)

        result = {
            "method": "script.execute via Zabbix HTTPS API",
            "total": args.total,
            "success": success,
            "failed": failed,
            "elapsed_sec": round(overall, 2),
            "effective_rps": round(args.total / overall, 2),
            "target_rps": args.rate,
            "errors_sample": errors_sample,
        }
        out = Path(__file__).parent / "result_2_2.json"
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        logger.info("Result saved: %s", out)

        if failed > 0:
            sys.exit(1)

    finally:
        zapi.logout()


if __name__ == "__main__":
    main()
