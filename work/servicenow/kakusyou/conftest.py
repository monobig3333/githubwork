"""pytest 共通フィクスチャ（Google SSO / storage_state 対応）"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.config import settings  # noqa: E402
from _common.playwright_helpers import (  # noqa: E402
    assert_logged_in,
    get_auth_state_path,
    has_auth_state,
    snow_login_form,
)

logging.basicConfig(level=logging.INFO)


@pytest.fixture(scope="session")
def base_url():
    return settings.snow_base_url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """画面サイズ・タイムアウトの共通設定 + storage_state自動読込

    auth.json があれば storage_state として読み込み、ログイン済み状態で起動する。
    """
    args = {
        **browser_context_args,
        "viewport": {"width": 1440, "height": 900},
        "ignore_https_errors": False,
    }
    if has_auth_state():
        args["storage_state"] = str(get_auth_state_path())
    return args


@pytest.fixture
def authed_page(page, base_url):
    """ログイン済みページを返す

    優先順位:
      1. auth.json があれば storage_state で起動済み → そのまま返却
      2. なければ snow_login_form() でローカルフォームログイン
         （SSO バイパス可能なユーザが SNOW_USER/SNOW_PASSWORD に設定されている前提）
    """
    if has_auth_state():
        assert_logged_in(page)
    elif settings.snow_user and settings.snow_password:
        snow_login_form(page)
    else:
        pytest.skip(
            "auth.json が存在せず、SNOW_USER/SNOW_PASSWORD も未設定です。"
            "python3 _common/save_auth_state.py を実行してauth.jsonを作成してください"
        )
    yield page
