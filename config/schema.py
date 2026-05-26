from dataclasses import dataclass, field


@dataclass
class SiteConfig:
    name: str
    key: str
    type: str
    url: str
    enabled: bool = True
    max_articles: int = 10
    selectors: dict[str, str] = field(default_factory=dict)


@dataclass
class ScheduleConfig:
    name: str
    cron: str
    timezone: str = "Asia/Seoul"
    sites: list[str] = field(default_factory=lambda: ["all"])


@dataclass
class StorageConfig:
    db_path: str = "news_bot.db"
    retention_days: int = 90


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "news_bot.log"


@dataclass
class AppConfig:
    webhook_url: str = ""
    sites: list[SiteConfig] = field(default_factory=list)
    schedules: list[ScheduleConfig] = field(default_factory=list)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
