from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    app_token: str
    product_table_id: str
    daily_table_id: str
    rule_table_id: str
    link_table_id: str = ""
    base_url: str = "https://open.feishu.cn/open-apis"


@dataclass(frozen=True)
class AppConfig:
    feishu: FeishuConfig
    lookback_days: int = 30


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_config() -> AppConfig:
    load_dotenv()
    feishu = FeishuConfig(
        app_id=require_env("FEISHU_APP_ID"),
        app_secret=require_env("FEISHU_APP_SECRET"),
        app_token=require_env("FEISHU_APP_TOKEN"),
        product_table_id=require_env("FEISHU_PRODUCT_TABLE_ID"),
        daily_table_id=require_env("FEISHU_DAILY_TABLE_ID"),
        rule_table_id=os.getenv("FEISHU_RULE_TABLE_ID", "").strip(),
        link_table_id=os.getenv("FEISHU_LINK_TABLE_ID", "").strip(),
        base_url=os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn/open-apis").rstrip("/"),
    )
    lookback_days = int(os.getenv("CD_RACING_LOOKBACK_DAYS", "30"))
    return AppConfig(feishu=feishu, lookback_days=lookback_days)


def load_feishu_schema_config() -> FeishuConfig:
    load_dotenv()
    return FeishuConfig(
        app_id=require_env("FEISHU_APP_ID"),
        app_secret=require_env("FEISHU_APP_SECRET"),
        app_token=require_env("FEISHU_APP_TOKEN"),
        product_table_id=os.getenv("FEISHU_PRODUCT_TABLE_ID", "").strip(),
        daily_table_id=os.getenv("FEISHU_DAILY_TABLE_ID", "").strip(),
        rule_table_id=os.getenv("FEISHU_RULE_TABLE_ID", "").strip(),
        link_table_id=os.getenv("FEISHU_LINK_TABLE_ID", "").strip(),
        base_url=os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn/open-apis").rstrip("/"),
    )
