#!/usr/bin/env python3
"""AWS Secrets Manager から ServiceNow OAuth の client_id / secret を取得する

既定の Secret:
    servicenow/api-test/<SNOW_INSTANCE>/admin-ai-api  (既定: biglobedev)

やること:
  1. Secret を取得し、client_id / client_secret に相当するキーを自動判別
  2. 対象インスタンスの /oauth_token.do に client_credentials で疎通確認
  3. --write を付けると jmeter.properties の
     snow.client_id / snow.client_secret / snow.basic_auth を更新

既定は dry-run。--write を付けるまでファイルは書き換えない。

前提: AWS の一時クレデンシャルを取得済みであること。

    source setup.sh big4180 prd

setup.sh は sts assume-role の結果を AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
AWS_SESSION_TOKEN として export する。**同じシェルセッション内で**本スクリプトを実行すること。
セッションは時間で失効するため、期限切れ時は setup.sh を再実行する。

使い方:
    source setup.sh big4180 prd                                # 先に AWS 認証
    python3 _common/fetch_oauth_from_secrets.py                # 取得 + 疎通確認のみ
    python3 _common/fetch_oauth_from_secrets.py --write        # jmeter.properties も更新
    python3 _common/fetch_oauth_from_secrets.py --secret <名前> --host <ホスト>
    python3 _common/fetch_oauth_from_secrets.py --show-keys    # Secret のキー名だけ表示
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    if (ROOT / ".env").exists():
        load_dotenv(ROOT / ".env")
except ImportError:
    pass

# 対象インスタンス: 2026/8/14 に biglobedev へ変更
# nonprod を使う場合は --secret / --host で上書きするか、環境変数 SNOW_OAUTH_SECRET_NAME を指定
DEFAULT_INSTANCE = os.getenv("SNOW_INSTANCE", "biglobedev")
DEFAULT_SECRET = f"servicenow/api-test/{DEFAULT_INSTANCE}/admin-ai-api"
DEFAULT_HOST = f"{DEFAULT_INSTANCE}.service-now.com"
JMETER_PROPS = ROOT / "jmeter.properties"

# Secret のキー名は環境によって揺れるため候補を並べて拾う
ID_KEYS = ["ClientID", "ClientId", "client_id", "clientId", "OAuthToken", "oauth_token"]
SECRET_KEYS = [
    "ClientSecret",
    "client_secret",
    "clientSecret",
    "OAuthSecret",
    "oauth_secret",
]


def _pick(payload: dict, candidates: list[str]) -> tuple[str | None, str | None]:
    """候補キーの中から最初に見つかったものを (key, value) で返す（大小文字無視の再探索つき）"""
    for k in candidates:
        if k in payload and payload[k]:
            return k, str(payload[k])
    lowered = {k.lower(): k for k in payload}
    for k in candidates:
        actual = lowered.get(k.lower())
        if actual and payload[actual]:
            return actual, str(payload[actual])
    return None, None


def fetch_secret(secret_name: str, region: str) -> dict:
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        sys.exit("boto3 が未導入です: pip install boto3 --break-system-packages")

    if not os.getenv("AWS_ACCESS_KEY_ID") and not os.getenv("AWS_PROFILE"):
        sys.exit(
            "AWS の認証情報が見つかりません。先に同じシェルで実行してください:\n"
            "    source setup.sh big4180 prd"
        )

    client = boto3.client("secretsmanager", region_name=region)
    try:
        resp = client.get_secret_value(SecretId=secret_name)
    except NoCredentialsError:
        sys.exit("AWS クレデンシャル未設定です。source setup.sh big4180 prd を実行してください")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"):
            sys.exit(
                "AWS の一時クレデンシャルが失効しています。"
                "source setup.sh big4180 prd を実行し直してください"
            )
        if code == "ResourceNotFoundException":
            sys.exit(f"Secret が見つかりません: {secret_name} (region={region})")
        if code == "AccessDeniedException":
            sys.exit(f"Secret への読み取り権限がありません: {secret_name}")
        raise
    raw = resp.get("SecretString")
    if raw is None:
        raw = base64.b64decode(resp["SecretBinary"]).decode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(f"Secret が JSON ではありません: {secret_name}")
    if not isinstance(payload, dict):
        sys.exit(f"Secret が key-value 形式ではありません: {secret_name}")
    return payload


def verify_oauth(host: str, cid: str, sec: str) -> tuple[bool, str]:
    try:
        import requests
    except ImportError:
        return False, "requests が未導入"
    url = f"https://{host}/oauth_token.do"
    try:
        r = requests.post(
            url, auth=(cid, sec), data={"grant_type": "client_credentials"}, timeout=30
        )
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"
    if r.status_code == 200 and "access_token" in r.text:
        tok = r.json()["access_token"]
        return True, f"200 OK (access_token {len(tok)} 文字)"
    return False, f"status={r.status_code} body={r.text[:160]}"


def update_jmeter_props(cid: str, sec: str) -> Path:
    """jmeter.properties の 3 行を更新し、バックアップパスを返す"""
    if not JMETER_PROPS.exists():
        sys.exit(f"{JMETER_PROPS} がありません")

    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    backup = JMETER_PROPS.with_suffix(
        f".properties.bak_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(JMETER_PROPS, backup)

    text = JMETER_PROPS.read_text(encoding="utf-8")
    for key, val in (
        ("snow.client_id", cid),
        ("snow.client_secret", sec),
        ("snow.basic_auth", basic),
    ):
        pattern = rf"(?m)^{re.escape(key)}=.*$"
        if re.search(pattern, text):
            text = re.sub(pattern, f"{key}={val}", text)
        else:
            text = text.rstrip("\n") + f"\n{key}={val}\n"
    JMETER_PROPS.write_text(text, encoding="utf-8")
    return backup


def main() -> int:
    ap = argparse.ArgumentParser(description="Secrets Manager から OAuth 認証情報を取得")
    ap.add_argument("--secret", default=os.getenv("SNOW_OAUTH_SECRET_NAME", DEFAULT_SECRET))
    ap.add_argument("--region", default=os.getenv("AWS_REGION", "ap-northeast-1"))
    ap.add_argument("--host", default=DEFAULT_HOST, help="疎通確認するインスタンス")
    ap.add_argument("--write", action="store_true", help="jmeter.properties を更新する")
    ap.add_argument("--show-keys", action="store_true", help="Secret のキー名だけ表示して終了")
    ap.add_argument("--skip-verify", action="store_true", help="疎通確認をスキップ")
    args = ap.parse_args()

    print(f"[INFO] secret = {args.secret}")
    print(f"[INFO] region = {args.region}")
    payload = fetch_secret(args.secret, args.region)

    if args.show_keys:
        print(f"[INFO] keys   = {', '.join(sorted(payload))}")
        return 0

    id_key, cid = _pick(payload, ID_KEYS)
    sec_key, sec = _pick(payload, SECRET_KEYS)
    if not cid or not sec:
        print(f"[FAIL] client_id / client_secret を判別できません。keys = {sorted(payload)}")
        print("       --show-keys で確認し、スクリプト先頭の ID_KEYS / SECRET_KEYS に追加してください")
        return 1
    print(f"[ OK ] client_id     <- {id_key}  ({cid[:6]}…{cid[-4:]}, {len(cid)} 文字)")
    print(f"[ OK ] client_secret <- {sec_key} ({len(sec)} 文字)")

    if not args.skip_verify:
        host_label = args.host.split(".")[0]
        ok, detail = verify_oauth(args.host, cid, sec)
        print(f"[{' OK ' if ok else 'FAIL'}] {args.host} /oauth_token.do : {detail}")
        if not ok:
            print(f"       → Secret の値か、{host_label} 側の OAuth アプリ登録を確認してください")
            return 1

    if args.write:
        backup = update_jmeter_props(cid, sec)
        print(f"[ OK ] jmeter.properties を更新（バックアップ: {backup.name}）")
        print("       snow.client_id / snow.client_secret / snow.basic_auth")
    else:
        basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
        print("\n--- jmeter.properties に反映する場合は --write を付けて再実行 ---")
        print("反映される内容:")
        print(f"  snow.client_id={cid[:6]}…（{len(cid)} 文字）")
        print(f"  snow.client_secret=…（{len(sec)} 文字）")
        print(f"  snow.basic_auth=…（{len(basic)} 文字）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
