"""ServiceNow OAuth Client Credentials 認証ヘルパー

優先順位:
  1. 環境変数 SNOW_CLIENT_ID / SNOW_CLIENT_SECRET があればそれを使用
  2. なければ AWS Secrets Manager から OAuthToken / OAuthSecret を取得
"""
import json
import logging
import time
from typing import Optional

import requests

from .config import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict = {"token": None, "expires_at": 0.0}
_TOKEN_TTL_SEC = 20 * 60  # 20分（実際は約30分有効だが余裕を持って再取得）


def _load_credentials_from_secrets_manager() -> tuple[str, str]:
    """AWS Secrets Manager から OAuth クライアント情報を取得"""
    try:
        import boto3
    except ImportError as e:
        raise RuntimeError("boto3 がインストールされていません") from e

    client = boto3.client("secretsmanager", region_name=settings.aws_region)
    resp = client.get_secret_value(SecretId=settings.snow_secret_name)
    payload = json.loads(resp["SecretString"])
    return payload["OAuthToken"], payload["OAuthSecret"]


def get_oauth_token(force_refresh: bool = False) -> str:
    """OAuth アクセストークンを取得する（キャッシュあり）"""
    now = time.time()
    if not force_refresh and _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now:
        return _TOKEN_CACHE["token"]

    if settings.snow_client_id and settings.snow_client_secret:
        client_id, client_secret = settings.snow_client_id, settings.snow_client_secret
    else:
        client_id, client_secret = _load_credentials_from_secrets_manager()

    token_url = f"{settings.snow_base_url}/oauth_token.do"
    resp = requests.post(
        token_url,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = now + _TOKEN_TTL_SEC
    logger.info("OAuth token refreshed")
    return token


def authorized_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {get_oauth_token()}",
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers
