"""環境変数からテスト設定を読み込む"""
import os
from dataclasses import dataclass
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
    snow_client_id: str = os.getenv("SNOW_CLIENT_ID", "")
    snow_client_secret: str = os.getenv("SNOW_CLIENT_SECRET", "")
    snow_user: str = os.getenv("SNOW_USER", "")
    snow_password: str = os.getenv("SNOW_PASSWORD", "")
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
