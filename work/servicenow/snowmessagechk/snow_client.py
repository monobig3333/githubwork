"""ServiceNow API 共通クライアント"""

import os
import json
import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

SNOW_BASE_URL      = os.environ["SNOW_BASE_URL"]
SNOW_CLIENT_ID     = os.environ.get("SNOW_CLIENT_ID", "")
SNOW_CLIENT_SECRET = os.environ.get("SNOW_CLIENT_SECRET", "")
SNOW_SECRET_NAME   = os.environ.get("SNOW_SECRET_NAME", "")


def _get_credentials() -> tuple[str, str]:
    if SNOW_CLIENT_ID and SNOW_CLIENT_SECRET:
        return SNOW_CLIENT_ID, SNOW_CLIENT_SECRET
    if not SNOW_SECRET_NAME:
        raise RuntimeError(
            "SNOW_CLIENT_ID/SNOW_CLIENT_SECRET が未設定で SNOW_SECRET_NAME も空です。"
            ".env を確認してください。"
        )
    client = boto3.client("secretsmanager", region_name="ap-northeast-1")
    resp   = client.get_secret_value(SecretId=SNOW_SECRET_NAME)
    secret = json.loads(resp["SecretString"])
    # シークレットのキー名はインスタンスによって異なる
    # (biglobeprod: OAuthToken/OAuthSecret, biglobedev: ClientID/ClientSecret)
    for id_key, secret_key in (("OAuthToken", "OAuthSecret"), ("ClientID", "ClientSecret")):
        if id_key in secret and secret_key in secret:
            return secret[id_key], secret[secret_key]
    raise RuntimeError(
        f"シークレット {SNOW_SECRET_NAME} に想定するキーが見つかりません: {list(secret.keys())}"
    )


def get_token() -> str:
    client_id, client_secret = _get_credentials()
    resp = requests.post(
        f"{SNOW_BASE_URL}/oauth_token.do",
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def table_get(token: str, table: str, params: dict) -> list[dict]:
    resp = requests.get(
        f"{SNOW_BASE_URL}/api/now/table/{table}",
        params=params,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def table_post(token: str, table: str, data: dict) -> dict:
    resp = requests.post(
        f"{SNOW_BASE_URL}/api/now/table/{table}",
        json=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})
