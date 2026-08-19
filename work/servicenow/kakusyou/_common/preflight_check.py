#!/usr/bin/env python3
"""再測定 実行前の環境チェック (read-only)

負荷は一切かけない。以下を順に確認して PASS / WARN / FAIL を表示する。

  env     .env の必須キー
  tools   jmeter / java / python パッケージ
  auth    auth.json の存在とセッション cookie 有効期限
  oauth   /oauth_token.do (client_credentials)
  snow    OAuth トークンで em_event / ecc_agent を 1 件読めるか
  mid     ecc_agent の MID Server が Up か
  zabbix  Zabbix API 疎通 / scriptid の存在 / 負荷用ホスト件数

使い方:
    python3 _common/preflight_check.py
    python3 _common/preflight_check.py --only zabbix,mid
    python3 _common/preflight_check.py --skip oauth
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:  # pragma: no cover
    print("FAIL: requests が未導入です。 pip install -r requirements.txt")
    sys.exit(2)

try:
    from dotenv import load_dotenv

    if (ROOT / ".env").exists():
        load_dotenv(ROOT / ".env")
except ImportError:
    pass


# --------------------------------------------------------------------------
# 表示ヘルパ
# --------------------------------------------------------------------------
RESULTS: list[tuple[str, str, str]] = []  # (level, check, message)


def _log(level: str, check: str, msg: str) -> None:
    mark = {"PASS": "  OK ", "WARN": " WARN", "FAIL": " FAIL", "INFO": " ... "}[level]
    print(f"[{mark}] {check:<8} {msg}")
    if level != "INFO":
        RESULTS.append((level, check, msg))


def section(title: str) -> None:
    print(f"\n--- {title} " + "-" * max(0, 60 - len(title)))


# --------------------------------------------------------------------------
# 設定
# --------------------------------------------------------------------------
SNOW_BASE = os.getenv("SNOW_BASE_URL") or (
    f"https://{os.getenv('SNOW_INSTANCE', 'biglobedev')}.service-now.com"
)
TIMEOUT = 30

# 対象インスタンス: 2026/7/31 は biglobenonprod、2026/8/14 に biglobedev へ変更
EXPECTED_INSTANCE = os.getenv("EXPECTED_INSTANCE", "biglobedev")

# 今回の再測定で実際に使う JMX (旧 JMX や実施済み項目の JMX はチェック対象外)
TARGET_JMX = [
    "1-2/1-2_concurrent_165.jmx",
    "1-3/1-3_concurrent_330_readonly.jmx",
    "2-1/2-1_alarm_viewer_165.jmx",
    "3-1/3-1_workflow_parallel.jmx",
    "M-1/M-1_mid_throughput_normal.jmx",
    "M-2/M-2_mid_throughput_max.jmx",
    "M-3/M-3_mid_sustained_load.jmx",
]

REQUIRED_ENV = [
    "SNOW_INSTANCE",
    "SNOW_BASE_URL",
    "MID_HOSTS",
    "ZABBIX_URL",
    "ZABBIX_USER",
    "ZABBIX_PASSWORD",
    "ZABBIX_SCRIPT_ID",
]
OPTIONAL_ENV = ["SNOW_USER", "SNOW_PASSWORD", "ZABBIX_HOST_PREFIX", "ZABBIX_TOKEN", "MID_SSH_USER"]

_token_cache: dict[str, str] = {}


def _jmeter_props() -> dict[str, str]:
    """jmeter.properties を key=value の dict として読む"""
    p = ROOT / "jmeter.properties"
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _oauth_creds() -> tuple[str, str, str]:
    """(client_id, client_secret, 取得元) を返す。.env が空なら jmeter.properties にフォールバック"""
    cid = os.getenv("SNOW_CLIENT_ID", "")
    sec = os.getenv("SNOW_CLIENT_SECRET", "")
    if cid and sec:
        return cid, sec, ".env"
    jp = _jmeter_props()
    cid2, sec2 = jp.get("snow.client_id", ""), jp.get("snow.client_secret", "")
    if cid2 and sec2:
        return cid2, sec2, "jmeter.properties"
    return cid or cid2, sec or sec2, "(未設定)"


# --------------------------------------------------------------------------
# 各チェック
# --------------------------------------------------------------------------
def check_env() -> None:
    section("env")
    if not (ROOT / ".env").exists():
        _log("FAIL", "env", ".env が存在しません")
        return
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        _log("FAIL", "env", f"必須キーが未設定: {', '.join(missing)}")
    else:
        _log("PASS", "env", f"必須キー {len(REQUIRED_ENV)} 件すべて設定済み")
    opt_missing = [k for k in OPTIONAL_ENV if not os.getenv(k)]
    if opt_missing:
        _log("WARN", "env", f"任意キーが未設定: {', '.join(opt_missing)}")
    _log("INFO", "env", f"SNOW_BASE_URL = {SNOW_BASE}")

    # インスタンスが EXPECTED_INSTANCE に統一されているか (計画書 2-4節)
    if EXPECTED_INSTANCE in SNOW_BASE:
        _log("PASS", "env", f"SNOW_BASE_URL は {EXPECTED_INSTANCE} を指している")
    else:
        _log(
            "FAIL",
            "env",
            f"SNOW_BASE_URL が {EXPECTED_INSTANCE} ではありません ({SNOW_BASE}) "
            f"— 再測定は全項目 {EXPECTED_INSTANCE} で実施する方針",
        )

    jhost = _jmeter_props().get("snow.host", "")
    if not jhost:
        _log("WARN", "env", "jmeter.properties に snow.host がありません")
    elif EXPECTED_INSTANCE in jhost:
        _log("PASS", "env", f"jmeter.properties snow.host={jhost}")
    else:
        _log(
            "FAIL",
            "env",
            f"jmeter.properties snow.host={jhost} が {EXPECTED_INSTANCE} ではありません",
        )

    # 今回使う JMX のフォールバック既定値も揃っているか
    stale = []
    for rel in TARGET_JMX:
        p = ROOT / rel
        if not p.exists():
            _log("FAIL", "env", f"JMX が見つかりません: {rel}")
            continue
        if EXPECTED_INSTANCE not in p.read_text(encoding="utf-8", errors="ignore"):
            stale.append(rel)
    if stale:
        _log("FAIL", "env", f"JMX の既定ホストが未統一: {', '.join(stale)}")
    else:
        _log("PASS", "env", f"対象 JMX {len(TARGET_JMX)} 本の既定ホストはすべて {EXPECTED_INSTANCE}")


def check_tools() -> None:
    section("tools")
    for cmd, level in (("jmeter", "FAIL"), ("java", "FAIL"), ("ssh", "WARN")):
        path = shutil.which(cmd)
        if path:
            ver = ""
            try:
                out = subprocess.run(
                    [cmd, "--version" if cmd == "jmeter" else "-version"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                ver = (out.stdout or out.stderr).strip().splitlines()[0][:60]
            except Exception:
                pass
            _log("PASS", "tools", f"{cmd}: {path} {ver}")
        else:
            _log(level, "tools", f"{cmd} が PATH にありません")

    for mod in ("playwright", "pytest", "pandas", "requests", "openpyxl"):
        try:
            __import__(mod)
            _log("PASS", "tools", f"python module {mod} 導入済み")
        except ImportError:
            _log("FAIL", "tools", f"python module {mod} 未導入 (pip install -r requirements.txt)")


def check_auth() -> None:
    section("auth")
    p = ROOT / "auth.json"
    if not p.exists():
        _log("FAIL", "auth", "auth.json がありません → python3 _common/save_auth_state.py")
        return
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        _log("FAIL", "auth", f"auth.json が読めません: {e}")
        return

    cookies = data.get("cookies", [])
    session = [c for c in cookies if c.get("expires", -1) > 0]
    now = time.time()
    if not session:
        _log("WARN", "auth", f"有効期限付き cookie がありません (取得 {mtime:%Y-%m-%d %H:%M})")
        return
    soonest = min(c["expires"] for c in session)
    exp_dt = datetime.fromtimestamp(soonest)
    if soonest < now:
        _log(
            "FAIL",
            "auth",
            f"セッション cookie 失効済み ({exp_dt:%Y-%m-%d %H:%M}) "
            "→ python3 _common/save_auth_state.py で再取得",
        )
    elif soonest - now < 3600:
        _log("WARN", "auth", f"セッション cookie の残り {int((soonest-now)/60)} 分 ({exp_dt:%H:%M})")
    else:
        _log("PASS", "auth", f"セッション cookie 有効 (〜{exp_dt:%Y-%m-%d %H:%M})")
    _log("INFO", "auth", f"auth.json 取得日時 {mtime:%Y-%m-%d %H:%M} / cookie {len(cookies)} 件")


def _fetch_token(base: str) -> tuple[str | None, str]:
    """指定インスタンスから client_credentials token を取る。(token, 詳細) を返す"""
    cid, sec, _src = _oauth_creds()
    if not cid or not sec:
        return None, "client_id/secret 未設定"
    try:
        r = requests.post(
            f"{base}/oauth_token.do",
            auth=(cid, sec),
            data={"grant_type": "client_credentials"},
            timeout=TIMEOUT,
        )
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:80]}"
    if r.status_code == 200 and "access_token" in r.text:
        return r.json()["access_token"], "200"
    return None, f"status={r.status_code} body={r.text[:100]}"


def _get_token() -> str | None:
    """snow / mid チェック用。SNOW_BASE_URL のトークンをキャッシュして返す"""
    if "t" in _token_cache:
        return _token_cache["t"] or None
    tok, _ = _fetch_token(SNOW_BASE)
    _token_cache["t"] = tok or ""
    return tok


def _oauth_targets() -> list[str]:
    """OAuth を確認すべきインスタンス URL の一覧 (SNOW_BASE_URL と JMeter の snow.host)"""
    targets = [SNOW_BASE]
    jhost = _jmeter_props().get("snow.host", "")
    if jhost:
        jbase = jhost if jhost.startswith("http") else f"https://{jhost}"
        if jbase.rstrip("/") != SNOW_BASE.rstrip("/"):
            targets.append(jbase)
    return targets


def check_oauth() -> None:
    section("oauth")
    cid, sec, src = _oauth_creds()
    if not cid or not sec:
        _log("FAIL", "oauth", "client_id/secret が .env にも jmeter.properties にもありません")
        return
    _log("INFO", "oauth", f"client_id 取得元: {src}")
    for base in _oauth_targets():
        tok, detail = _fetch_token(base)
        label = base.replace("https://", "")
        if tok:
            _log("PASS", "oauth", f"{label}: client_credentials 取得成功 (token {len(tok)} 文字)")
        else:
            _log(
                "FAIL",
                "oauth",
                f"{label}: token を取得できません ({detail}) "
                f"— OAuth アプリはインスタンス単位。{EXPECTED_INSTANCE} 側で client_id/secret を"
                " 発行し jmeter.properties を更新すること (計画書 B5)",
            )


def _table_get(table: str, params: dict) -> tuple[int, dict | None]:
    tok = _get_token()
    if not tok:
        return 0, None
    try:
        r = requests.get(
            f"{SNOW_BASE}/api/now/table/{table}",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
            params=params,
            timeout=TIMEOUT,
        )
    except Exception:
        return 0, None
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def check_snow() -> None:
    section("snow")
    st, body = _table_get("em_event", {"sysparm_limit": "1", "sysparm_fields": "sys_id,source,node,sys_created_on"})
    if st == 200 and body is not None:
        rows = body.get("result", [])
        _log("PASS", "snow", f"em_event 読み取り OK ({len(rows)} 件取得)")
        if rows:
            r = rows[0]
            _log(
                "INFO",
                "snow",
                f"最新 em_event: source={r.get('source')} node={r.get('node')} "
                f"created={r.get('sys_created_on')}",
            )
            _log(
                "WARN",
                "snow",
                "イベントルール改版で source/node の書式が変わっていないか目視確認すること "
                "(計画書 7章 リスク)",
            )
    elif st == 0:
        _log("FAIL", "snow", "em_event へ到達できません (token 未取得 or ネットワーク)")
    else:
        _log("FAIL", "snow", f"em_event 読み取り失敗 status={st}")


def check_mid() -> None:
    section("mid")
    st, body = _table_get(
        "ecc_agent", {"sysparm_limit": "20", "sysparm_fields": "name,status,validated"}
    )
    if st != 200 or body is None:
        _log("FAIL", "mid", f"ecc_agent を読めません status={st}")
        return
    rows = body.get("result", [])
    if not rows:
        _log("FAIL", "mid", "ecc_agent に MID Server が 1 台もありません")
        return
    up = [r for r in rows if str(r.get("status", "")).lower() == "up"]
    for r in rows:
        _log("INFO", "mid", f"{r.get('name')}: status={r.get('status')} validated={r.get('validated')}")
    if len(up) >= 3:
        _log("PASS", "mid", f"MID Server {len(up)}/{len(rows)} 台が Up (3AZ 要件を満たす)")
    else:
        _log("FAIL", "mid", f"Up の MID Server が {len(up)} 台 (3AZ 構成の 3 台に不足)")

    env_hosts = [h.strip() for h in os.getenv("MID_HOSTS", "").split(",") if h.strip()]
    if env_hosts:
        _log("INFO", "mid", f".env MID_HOSTS = {', '.join(env_hosts)}")
    else:
        _log("WARN", "mid", "MID_HOSTS が未設定 (M-1 のログ収集で必要)")


def _zbx(method: str, params, auth: str | None):
    url = os.getenv("ZABBIX_URL", "")
    verify = os.getenv("ZABBIX_VERIFY_TLS", "false").lower() in ("1", "true", "yes")
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    headers = {"Content-Type": "application/json-rpc"}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
        payload["auth"] = auth
    r = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT, verify=verify)
    return r.json()


def check_zabbix() -> None:
    section("zabbix")
    url = os.getenv("ZABBIX_URL", "")
    if not url:
        _log("FAIL", "zabbix", "ZABBIX_URL が未設定")
        return

    try:
        ver = _zbx("apiinfo.version", {}, None)
        _log("PASS", "zabbix", f"API 疎通 OK version={ver.get('result')}")
    except Exception as e:
        _log("FAIL", "zabbix", f"API に到達できません: {e}")
        return

    token = os.getenv("ZABBIX_TOKEN", "")
    if not token:
        try:
            res = _zbx(
                "user.login",
                {"username": os.getenv("ZABBIX_USER", ""), "password": os.getenv("ZABBIX_PASSWORD", "")},
                None,
            )
            token = res.get("result", "")
        except Exception as e:
            _log("FAIL", "zabbix", f"login 失敗: {e}")
            return
    if not token:
        _log("FAIL", "zabbix", "認証トークンを取得できません (ZABBIX_USER/PASSWORD/TOKEN を確認)")
        return
    _log("PASS", "zabbix", "認証 OK")

    # scriptid
    want = os.getenv("ZABBIX_SCRIPT_ID", "")
    try:
        scripts = _zbx("script.get", {"output": ["scriptid", "name", "execute_on"]}, token).get(
            "result", []
        )
        ids = {s["scriptid"]: s for s in scripts}
        if want in ids:
            s = ids[want]
            _log("PASS", "zabbix", f"ZABBIX_SCRIPT_ID={want} 存在 (name={s['name']})")
        else:
            _log(
                "FAIL",
                "zabbix",
                f"ZABBIX_SCRIPT_ID={want} が見つかりません。登録済み: "
                + ", ".join(f"{k}:{v['name']}" for k, v in list(ids.items())[:10]),
            )
    except Exception as e:
        _log("WARN", "zabbix", f"script.get 失敗: {e}")

    # 負荷用ホスト
    prefix = os.getenv("ZABBIX_HOST_PREFIX", "test-servicenow-monohyouka-")
    try:
        # searchWildcardsEnabled=true は "*" 必須で、付けないと完全一致になる。
        # 前方一致は startSearch を使う（2026/8/19 に誤検知を修正）
        hosts = _zbx(
            "host.get",
            {"output": ["hostid", "host"], "search": {"host": prefix}, "startSearch": True},
            token,
        ).get("result", [])
        n = len(hosts)
        if n >= 30000:
            _log("PASS", "zabbix", f"負荷用ホスト {n} 件 (prefix={prefix})")
        elif n > 0:
            _log(
                "WARN",
                "zabbix",
                f"負荷用ホストが {n} 件しかありません (30,000 件想定)。"
                " 不足分は zabbixtool/zabbix_bulk_copy_1.py で作成",
            )
        else:
            _log(
                "FAIL",
                "zabbix",
                f"prefix={prefix} のホストが 0 件。zabbixtool/zabbix_bulk_copy_1.py で作成が必要",
            )
    except Exception as e:
        _log("WARN", "zabbix", f"host.get 失敗: {e}")


CHECKS = {
    "env": check_env,
    "tools": check_tools,
    "auth": check_auth,
    "oauth": check_oauth,
    "snow": check_snow,
    "mid": check_mid,
    "zabbix": check_zabbix,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="再測定 実行前の環境チェック")
    ap.add_argument("--only", help="実行するチェックをカンマ区切りで指定")
    ap.add_argument("--skip", help="スキップするチェックをカンマ区切りで指定")
    args = ap.parse_args()

    names = list(CHECKS)
    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip() in CHECKS]
    if args.skip:
        skip = {n.strip() for n in args.skip.split(",")}
        names = [n for n in names if n not in skip]

    print("=" * 68)
    print(f" 再測定 preflight check   {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f" repo: {ROOT}")
    print("=" * 68)

    for n in names:
        try:
            CHECKS[n]()
        except Exception as e:  # 個別チェックの失敗で全体を止めない
            _log("FAIL", n, f"チェック中に例外: {e}")

    fails = [r for r in RESULTS if r[0] == "FAIL"]
    warns = [r for r in RESULTS if r[0] == "WARN"]
    print("\n" + "=" * 68)
    print(f" 結果: FAIL {len(fails)} / WARN {len(warns)} / PASS {len(RESULTS)-len(fails)-len(warns)}")
    for lv, c, m in fails + warns:
        print(f"   [{lv}] {c}: {m}")
    print("=" * 68)
    if fails:
        print(" → FAIL を解消してから実測に進むこと (詳細: 再測定_実行計画.md 2章)")
        return 1
    print(" → 実測に進んで問題なし (WARN は内容を確認)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
