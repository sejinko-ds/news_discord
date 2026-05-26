import os
from pathlib import Path

import yaml

from config.schema import (
    AppConfig,
    LoggingConfig,
    ScheduleConfig,
    SiteConfig,
    StorageConfig,
)


class ConfigManager:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load()

    def _load(self) -> AppConfig:
        if not self.config_path.exists():
            return AppConfig()

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw = f.read()

        expanded = os.path.expandvars(raw)
        data = yaml.safe_load(expanded) or {}

        discord_data = data.get("discord", {})
        webhook_url = discord_data.get("webhook_url", "")

        sites = []
        for s in data.get("sites", []):
            sites.append(
                SiteConfig(
                    name=s["name"],
                    key=s["key"],
                    type=s.get("type", "rss"),
                    url=s.get("url", ""),
                    enabled=s.get("enabled", True),
                    max_articles=s.get("max_articles", 10),
                    selectors=s.get("selectors", {}),
                )
            )

        schedules = []
        for sc in data.get("schedules", []):
            schedules.append(
                ScheduleConfig(
                    name=sc["name"],
                    cron=sc["cron"],
                    timezone=sc.get("timezone", "Asia/Seoul"),
                    sites=sc.get("sites", ["all"]),
                )
            )

        storage_data = data.get("storage", {})
        storage = StorageConfig(
            db_path=storage_data.get("db_path", "news_bot.db"),
            retention_days=storage_data.get("retention_days", 90),
        )

        logging_data = data.get("logging", {})
        logging_cfg = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            file=logging_data.get("file", "news_bot.log"),
        )

        return AppConfig(
            webhook_url=webhook_url,
            sites=sites,
            schedules=schedules,
            storage=storage,
            logging=logging_cfg,
        )

    def _to_dict(self) -> dict:
        return {
            "discord": {
                "webhook_url": "${DISCORD_WEBHOOK_URL}",
            },
            "sites": [
                {
                    "name": s.name,
                    "key": s.key,
                    "type": s.type,
                    "url": s.url,
                    "enabled": s.enabled,
                    "max_articles": s.max_articles,
                    **({"selectors": s.selectors} if s.selectors else {}),
                }
                for s in self.config.sites
            ],
            "schedules": [
                {
                    "name": sc.name,
                    "cron": sc.cron,
                    "timezone": sc.timezone,
                    "sites": sc.sites,
                }
                for sc in self.config.schedules
            ],
            "storage": {
                "db_path": self.config.storage.db_path,
                "retention_days": self.config.storage.retention_days,
            },
            "logging": {
                "level": self.config.logging.level,
                "file": self.config.logging.file,
            },
        }

    def save(self) -> None:
        data = self._to_dict()
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def add_site(self, site: SiteConfig) -> None:
        self.config.sites = [s for s in self.config.sites if s.key != site.key]
        self.config.sites.append(site)
        self.save()

    def remove_site(self, key: str) -> None:
        self.config.sites = [s for s in self.config.sites if s.key != key]
        self.save()

    def add_schedule(self, schedule: ScheduleConfig) -> None:
        self.config.schedules = [s for s in self.config.schedules if s.name != schedule.name]
        self.config.schedules.append(schedule)
        self.save()

    def remove_schedule(self, name: str) -> None:
        self.config.schedules = [s for s in self.config.schedules if s.name != name]
        self.save()
