import asyncio
import logging
import sys

from config.manager import ConfigManager
from config.schema import SiteConfig
from db.storage import ArticleStorage
from fetchers.base import Article, BaseFetcher
from fetchers.rss import RSSFetcher
from fetchers.hada import HadaFetcher
from fetchers.aitimes import AItimesFetcher
from fetchers.yozm import YozmFetcher
from notifiers.discord import DiscordNotifier

logger = logging.getLogger(__name__)

FETCHER_MAP: dict[str, type[BaseFetcher]] = {
    "hada": HadaFetcher,
    "aitimes": AItimesFetcher,
    "yozm": YozmFetcher,
}


def get_fetcher(site: SiteConfig) -> BaseFetcher:
    if site.key in FETCHER_MAP:
        return FETCHER_MAP[site.key](max_articles=site.max_articles)
    if site.type == "rss":
        return RSSFetcher(name=site.key, url=site.url, max_articles=site.max_articles)
    return RSSFetcher(name=site.key, url=site.url, max_articles=site.max_articles)


async def run_pipeline(
    config_manager: ConfigManager,
    storage: ArticleStorage,
    notifier: DiscordNotifier,
    schedule_name: str = "manual",
    sites: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    config = config_manager.config

    site_configs = [s for s in config.sites if s.enabled]
    if sites and "all" not in sites:
        site_configs = [s for s in site_configs if s.key in sites]

    summary: dict = {
        "schedule": schedule_name,
        "fetched": 0,
        "new": 0,
        "sent": 0,
        "errors": [],
    }

    all_new_articles: dict[str, list[Article]] = {}

    for site in site_configs:
        try:
            fetcher = get_fetcher(site)
            articles = await fetcher.fetch()
            summary["fetched"] += len(articles)

            new_articles = [a for a in articles if not storage.is_sent(a.fingerprint)]
            summary["new"] += len(new_articles)

            if new_articles:
                all_new_articles[site.name] = new_articles

            storage.log_fetch(site.key, len(articles), len(new_articles))
            logger.info(f"[{site.key}] Fetched {len(articles)}, new: {len(new_articles)}")

        except Exception as e:
            error_msg = f"[{site.key}] Fetch error: {e}"
            logger.error(error_msg)
            summary["errors"].append(error_msg)
            storage.log_fetch(site.key, 0, 0, str(e))

    if dry_run:
        logger.info(f"Dry run - would send {summary['new']} articles")
        return summary

    if all_new_articles:
        for source_name, articles in all_new_articles.items():
            try:
                sent = await notifier.send_articles(articles, source_name)
                summary["sent"] += sent
            except Exception as e:
                error_msg = f"Send error: {e}"
                logger.error(error_msg)
                summary["errors"].append(error_msg)

            for article in articles:
                storage.mark_sent(article.fingerprint, article.source, article.url, article.title)

    logger.info(
        f"Pipeline complete: fetched={summary['fetched']}, "
        f"new={summary['new']}, sent={summary['sent']}"
    )
    return summary


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
