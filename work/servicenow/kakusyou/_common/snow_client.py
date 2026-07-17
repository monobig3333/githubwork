"""ServiceNow Table API / Import Set API クライアント"""
import logging
import time
from typing import Any

import requests

from .config import settings
from .servicenow_auth import authorized_headers, get_oauth_token

logger = logging.getLogger(__name__)


class SnowClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.snow_base_url
        self.session = requests.Session()

    def _request(self, method: str, path: str, retries: int = 3, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        backoff = 1
        for attempt in range(retries):
            headers = kwargs.pop("headers", None) or authorized_headers()
            kwargs["headers"] = {**headers, **(kwargs.pop("extra_headers", {}) or {})}
            resp = self.session.request(method, url, timeout=60, **kwargs)
            if resp.status_code == 401:
                get_oauth_token(force_refresh=True)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning("Retryable status %s, attempt=%d", resp.status_code, attempt + 1)
                time.sleep(backoff)
                backoff *= 2
                continue
            return resp
        resp.raise_for_status()
        return resp

    def get_table(self, table: str, **params) -> list[dict[str, Any]]:
        resp = self._request("GET", f"/api/now/table/{table}", params=params)
        resp.raise_for_status()
        return resp.json().get("result", [])

    def insert_record(self, table: str, payload: dict) -> dict:
        resp = self._request("POST", f"/api/now/table/{table}", json=payload)
        resp.raise_for_status()
        return resp.json().get("result", {})

    def import_xlsx(self, import_set_table: str, xlsx_path: str, transform: bool = True) -> dict:
        url = f"/sys_import.do?sysparm_import_set_tablename={import_set_table}"
        if transform:
            url += "&sysparm_transform_after_load=true"
        with open(xlsx_path, "rb") as f:
            files = {"file": (xlsx_path, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            resp = self._request("POST", url, files=files)
        resp.raise_for_status()
        return resp.json()
