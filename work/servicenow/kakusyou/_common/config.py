"""環境変数からテスト設定を読み込む"""
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass


@dataclass
class Settings:
    snow_instance: str = os.getenv("SNOW_INSTANCE", "biglobedev")
    snow_base_url: str = os.getenv(
        "SNOW_BASE_URL", f"https://{os.getenv('SNOW_INSTANCE', 'biglobedev')}.service-now.com"
    )
    snow_client_id: str = field(default_factory=lambda: os.getenv("SNOW_CLIENT_ID", ""), repr=False)
    snow_client_secret: str = field(default_factory=lambda: os.getenv("SNOW_CLIENT_SECRET", ""), repr=False)
    snow_user: str = os.getenv("SNOW_USER", "")
    # repr=False: pytest のアサーション失敗時などに平文で出力されるのを防ぐ (2026/8/21)
    snow_password: str = field(default_factory=lambda: os.getenv("SNOW_PASSWORD", ""), repr=False)
    aws_region: str = os.getenv("AWS_REGION", "ap-northeast-1")
    snow_secret_name: str = os.getenv(
        "SNOW_SECRET_NAME",
        f"servicenow/api/credentials/{os.getenv('SNOW_INSTANCE', 'biglobedev')}/user-api",
    )
    mid_hosts: list = None
    mid_ssh_user: str = os.getenv("MID_SSH_USER", "midserver")
    mid_ssh_key: str = os.getenv("MID_SSH_KEY", "~/.ssh/id_rsa")

    def __post_init__(self):
        hosts = os.getenv("MID_HOSTS", "")
        self.mid_hosts = [h.strip() for h in hosts.split(",") if h.strip()]


settings = Settings()
