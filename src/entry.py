import hashlib
import json
import re
from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

from workers import Response

SITES = [
    {"name": "GeekNews (Hada)", "key": "hada", "url": "https://news.hada.io/rss/news", "max_articles": 10},
    {"name": "AI Times", "key": "aitimes", "url": "https://www.aitimes.com/rss/allArticle.xml", "max_articles": 10},
    {"name": "Yozm Wishket AI", "key": "yozm", "url": "https://yozm.wishket.com/magazine/ai/feed/", "max_articles": 10},
]

SOURCE_COLORS = {
    "hada": 0xFF6600,
    "aitimes": 0x2196F3,
    "yozm": 0x4CAF50,
}
DEFAULT_COLOR = 0x3498DB

SOURCE_LOGOS = {
    "hada": "https://news.hada.io/apple-touch-icon.png",
    "aitimes": "https://cdn.aitimes.com/image/logo/toplogo3.png",
    "yozm": "https://media.wishket.com/images/yozm/og_default.png",
}

HTML_TAG_RE = re.compile(r"<[^>]+>")


def make_fingerprint(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def strip_html(text: str) -> str:
    text = HTML_TAG_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text[:197] + "..." if len(text) > 200 else text


async def fetch_feed(url: str, max_articles: int) -> list[dict]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url, headers={"User-Agent": "DiscordNewsBot/1.0"})
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    articles = []
    for entry in feed.entries[:max_articles]:
        published = None
        for date_field in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, date_field, None)
            if parsed:
                published = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc).isoformat()
                break

        link = entry.get("link", "")
        if isinstance(link, dict):
            link = link.get("href", "")

        summary = entry.get("summary", entry.get("description", ""))
        summary = strip_html(summary)

        articles.append({
            "title": entry.get("title", "No Title"),
            "url": link,
            "summary": summary,
            "published_at": published,
        })
    return articles


async def is_sent(db, fp: str) -> bool:
    result = await db.prepare(
        "SELECT 1 FROM sent_articles WHERE fingerprint = ?"
    ).bind(fp).first()
    return result is not None


async def mark_sent(db, fp: str, source: str, url: str, title: str):
    await db.prepare(
        "INSERT OR IGNORE INTO sent_articles (fingerprint, source, url, title) VALUES (?, ?, ?, ?)"
    ).bind(fp, source, url, title).run()


async def send_to_discord(webhook_url: str, embeds: list[dict]):
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(embeds), 10):
            batch = embeds[i:i + 10]
            await client.post(
                webhook_url,
                content=json.dumps({"embeds": batch}),
                headers={"Content-Type": "application/json"},
            )


async def run_pipeline(env):
    webhook_url = env.DISCORD_WEBHOOK_URL
    db = env.DB

    for site in SITES:
        try:
            articles = await fetch_feed(site["url"], site["max_articles"])
            new_articles = []

            for article in articles:
                fp = make_fingerprint(article["url"])
                if not await is_sent(db, fp):
                    new_articles.append(article)

            if not new_articles:
                continue

            color = SOURCE_COLORS.get(site["key"], DEFAULT_COLOR)
            logo_url = SOURCE_LOGOS.get(site["key"], "")
            date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            embeds = []
            for article in new_articles:
                embed = {
                    "title": article["title"],
                    "url": article["url"],
                    "color": color,
                    "footer": {"text": f"{site['name']} | {date_str}"},
                }
                if logo_url:
                    embed["thumbnail"] = {"url": logo_url}
                if article["summary"]:
                    embed["description"] = article["summary"][:200]
                embeds.append(embed)

            await send_to_discord(webhook_url, embeds)

            for article in new_articles:
                fp = make_fingerprint(article["url"])
                await mark_sent(db, fp, site["key"], article["url"], article["title"])

        except Exception as e:
            print(f"[{site['key']}] Error: {e}")


async def on_fetch(request, env):
    return Response("Discord News Bot is running")


async def on_scheduled(event, env, ctx):
    await run_pipeline(env)
