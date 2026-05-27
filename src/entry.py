import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from workers import Response

ATOM_NS = "http://www.w3.org/2005/Atom"

SITES = [
    {"name": "GeekNews (Hada)", "key": "hada", "url": "https://news.hada.io/rss/news", "max_articles": 10},
    {"name": "AI Times", "key": "aitimes", "url": "https://www.aitimes.com/rss/allArticle.xml", "max_articles": 10},
    {"name": "Yozm Wishket AI", "key": "yozm", "url": "https://api.wishket.com/yozmit/news/?category=ai", "max_articles": 10, "type": "json_api"},
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


def _parse_date(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _parse_rss(root: ET.Element, max_articles: int) -> list[dict]:
    items = root.findall(".//item")[:max_articles]
    articles = []
    for item in items:
        title = item.findtext("title", "No Title")
        link = item.findtext("link", "")
        desc = item.findtext("description", "")
        pub = item.findtext("pubDate")
        articles.append({
            "title": title,
            "url": link.strip(),
            "summary": strip_html(desc),
            "published_at": _parse_date(pub),
        })
    return articles


def _parse_atom(root: ET.Element, max_articles: int) -> list[dict]:
    entries = root.findall(f"{{{ATOM_NS}}}entry")[:max_articles]
    articles = []
    for entry in entries:
        title = entry.findtext(f"{{{ATOM_NS}}}title", "No Title")
        link_el = entry.find(f"{{{ATOM_NS}}}link")
        link = link_el.get("href", "") if link_el is not None else ""
        summary = entry.findtext(f"{{{ATOM_NS}}}summary", "") or entry.findtext(f"{{{ATOM_NS}}}content", "")
        updated = entry.findtext(f"{{{ATOM_NS}}}updated") or entry.findtext(f"{{{ATOM_NS}}}published")
        articles.append({
            "title": title,
            "url": link.strip(),
            "summary": strip_html(summary),
            "published_at": _parse_date(updated),
        })
    return articles


async def _fetch_json_api(url: str, max_articles: int) -> list[dict]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url, headers={"User-Agent": "DiscordNewsBot/1.0", "Accept-Encoding": "identity"})
        resp.raise_for_status()

    data = resp.json()
    articles = []
    for item in data.get("results", [])[:max_articles]:
        article_url = f"https://yozm.wishket.com/magazine/detail/{item['id']}/"
        articles.append({
            "title": item.get("title", "No Title"),
            "url": article_url,
            "summary": strip_html(item.get("description", "")),
            "published_at": _parse_date(item.get("date_published")),
        })
    return articles


async def fetch_feed(url: str, max_articles: int, feed_type: str = "rss") -> list[dict]:
    if feed_type == "json_api":
        return await _fetch_json_api(url, max_articles)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url, headers={"User-Agent": "DiscordNewsBot/1.0", "Accept-Encoding": "identity"})
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    if root.tag == "rss" or root.find(".//item") is not None:
        return _parse_rss(root, max_articles)
    return _parse_atom(root, max_articles)


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
                headers={"Content-Type": "application/json", "Accept-Encoding": "identity"},
            )


async def _ensure_table(db):
    await db.exec(
        "CREATE TABLE IF NOT EXISTS sent_articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "fingerprint TEXT NOT NULL UNIQUE,"
        "source TEXT NOT NULL,"
        "url TEXT NOT NULL,"
        "title TEXT NOT NULL,"
        "sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
        "CREATE INDEX IF NOT EXISTS idx_fingerprint ON sent_articles(fingerprint);"
        "CREATE INDEX IF NOT EXISTS idx_sent_at ON sent_articles(sent_at);"
    )


async def run_pipeline(env):
    webhook_url = env.DISCORD_WEBHOOK_URL
    db = env.DB
    await _ensure_table(db)

    for site in SITES:
        try:
            articles = await fetch_feed(site["url"], site["max_articles"], site.get("type", "rss"))
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


def _is_within_schedule() -> bool:
    from datetime import timedelta
    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    weekday = now_kst.weekday()  # 0=Mon, 6=Sun
    hour = now_kst.hour
    return weekday < 5 and 6 <= hour < 18


async def on_scheduled(event, env, ctx):
    if not _is_within_schedule():
        return
    await run_pipeline(env)
