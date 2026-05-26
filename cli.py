import asyncio
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from config.manager import ConfigManager
from config.schema import ScheduleConfig, SiteConfig
from db.storage import ArticleStorage
from main import run_pipeline, setup_logging
from notifiers.discord import DiscordNotifier
from scheduler.cron import NewsScheduler

DEFAULT_CONFIG = "config.yaml"


@click.group()
@click.option("--config", "-c", default=DEFAULT_CONFIG, help="Config file path")
@click.pass_context
def cli(ctx, config):
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.pass_context
def run(ctx):
    """Start the scheduler daemon."""
    cm = ConfigManager(ctx.obj["config_path"])
    setup_logging(cm.config.logging.level, cm.config.logging.file)
    storage = ArticleStorage(cm.config.storage.db_path)
    notifier = DiscordNotifier(cm.config.webhook_url)
    scheduler = NewsScheduler()

    async def pipeline_callback(**kwargs):
        await run_pipeline(cm, storage, notifier, **kwargs)

    scheduler.set_pipeline(pipeline_callback)
    scheduler.load_schedules(cm.config.schedules)

    click.echo("News Bot (Discord) started. Press Ctrl+C to stop.")
    for job in scheduler.get_next_runs():
        click.echo(f"  {job['name']} -> next: {job['next_run']}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    scheduler.start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        scheduler.stop()
        loop.close()


@cli.command()
@click.option("--source", "-s", default=None, help="Fetch from specific source key")
@click.pass_context
def fetch(ctx, source):
    """Fetch articles without sending (dry run)."""
    cm = ConfigManager(ctx.obj["config_path"])
    setup_logging(cm.config.logging.level)
    storage = ArticleStorage(cm.config.storage.db_path)
    notifier = DiscordNotifier(cm.config.webhook_url)

    sites = [source] if source else None
    result = asyncio.run(run_pipeline(cm, storage, notifier, dry_run=True, sites=sites))

    click.echo(f"\nResults: fetched={result['fetched']}, new={result['new']}")
    if result["errors"]:
        for err in result["errors"]:
            click.echo(f"  ERROR: {err}")


@cli.command("send-now")
@click.option("--source", "-s", default=None, help="Send from specific source")
@click.pass_context
def send_now(ctx, source):
    """Fetch and send immediately."""
    cm = ConfigManager(ctx.obj["config_path"])
    setup_logging(cm.config.logging.level)
    storage = ArticleStorage(cm.config.storage.db_path)
    notifier = DiscordNotifier(cm.config.webhook_url)

    sites = [source] if source else None
    result = asyncio.run(run_pipeline(cm, storage, notifier, schedule_name="manual", sites=sites))

    click.echo(f"\nSent: {result['sent']} messages ({result['new']} new articles)")
    if result["errors"]:
        for err in result["errors"]:
            click.echo(f"  ERROR: {err}")


@cli.command("add-site")
@click.option("--name", required=True)
@click.option("--key", required=True)
@click.option("--type", "site_type", type=click.Choice(["rss", "scraper"]), required=True)
@click.option("--url", required=True)
@click.option("--max-articles", default=10)
@click.pass_context
def add_site(ctx, name, key, site_type, url, max_articles):
    """Add a news source."""
    cm = ConfigManager(ctx.obj["config_path"])
    site = SiteConfig(name=name, key=key, type=site_type, url=url, max_articles=max_articles)
    cm.add_site(site)
    click.echo(f"Site added: {name} ({key})")


@cli.command("remove-site")
@click.argument("key")
@click.pass_context
def remove_site(ctx, key):
    """Remove a news source by key."""
    cm = ConfigManager(ctx.obj["config_path"])
    cm.remove_site(key)
    click.echo(f"Site removed: {key}")


@cli.command("list-sites")
@click.pass_context
def list_sites(ctx):
    """List all configured sites."""
    cm = ConfigManager(ctx.obj["config_path"])
    for s in cm.config.sites:
        status = "ON" if s.enabled else "OFF"
        click.echo(f"  [{status}] [{s.key}] {s.name} ({s.type}) - {s.url}")


@cli.command("add-schedule")
@click.option("--name", required=True)
@click.option("--cron", required=True)
@click.option("--timezone", default="Asia/Seoul")
@click.pass_context
def add_schedule(ctx, name, cron, timezone):
    """Add a notification schedule."""
    cm = ConfigManager(ctx.obj["config_path"])
    schedule = ScheduleConfig(name=name, cron=cron, timezone=timezone)
    cm.add_schedule(schedule)
    click.echo(f"Schedule added: {name} ({cron}, {timezone})")


@cli.command("remove-schedule")
@click.argument("name")
@click.pass_context
def remove_schedule(ctx, name):
    """Remove a schedule by name."""
    cm = ConfigManager(ctx.obj["config_path"])
    cm.remove_schedule(name)
    click.echo(f"Schedule removed: {name}")


@cli.command("list-schedules")
@click.pass_context
def list_schedules(ctx):
    """List all schedules."""
    cm = ConfigManager(ctx.obj["config_path"])
    for s in cm.config.schedules:
        sites_str = ", ".join(s.sites)
        click.echo(f"  {s.name}: {s.cron} ({s.timezone}) -> sites: [{sites_str}]")


@cli.command()
@click.pass_context
def test(ctx):
    """Send a test message to verify Discord connectivity."""
    cm = ConfigManager(ctx.obj["config_path"])
    notifier = DiscordNotifier(cm.config.webhook_url)

    async def _test():
        ok = await notifier.send_test()
        status = "Success" if ok else "Failed"
        click.echo(f"  {status}")

    asyncio.run(_test())


@cli.command()
@click.pass_context
def status(ctx):
    """Show bot status and statistics."""
    cm = ConfigManager(ctx.obj["config_path"])
    storage = ArticleStorage(cm.config.storage.db_path)
    stats = storage.get_stats()

    click.echo("News Bot (Discord) Status")
    click.echo(f"  Sites: {len(cm.config.sites)}")
    click.echo(f"  Schedules: {len(cm.config.schedules)}")
    click.echo(f"  Total articles sent: {stats.get('total', 0)}")
    if stats.get("sources"):
        click.echo("  By source:")
        for source, count in stats["sources"].items():
            click.echo(f"    {source}: {count}")
    if stats.get("last_fetch"):
        click.echo(f"  Last fetch: {stats['last_fetch']}")


if __name__ == "__main__":
    cli()
