import re

import feedparser
import httpx
from datetime import datetime
from time import mktime

from fetchers.base import Article, BaseFetcher


class RSSFetcher(BaseFetcher):
    """Generic RSS/Atom feed fetcher."""

    _HTML_TAG_RE = re.compile(r"<[^>]+>")

    async def fetch(self) -> list[Article]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(
                self.url, headers={"User-Agent": "NewsTelegramBot/1.0"}
            )
            response.raise_for_status()

        feed = feedparser.parse(response.text)
        articles: list[Article] = []

        for entry in feed.entries[: self.max_articles]:
            # Handle both RSS (pubDate) and Atom (published/updated)
            published = None
            for date_field in ("published_parsed", "updated_parsed"):
                parsed = getattr(entry, date_field, None)
                if parsed:
                    published = datetime.fromtimestamp(mktime(parsed))
                    break

            # Get link - handle Atom format where link can be a dict
            link = entry.get("link", "")
            if isinstance(link, dict):
                link = link.get("href", "")

            # Get summary/description and strip HTML tags
            summary = entry.get("summary", entry.get("description", ""))
            summary = self._strip_html(summary)

            articles.append(
                Article(
                    title=entry.get("title", "No Title"),
                    url=link,
                    source=self.name,
                    summary=summary,
                    published_at=published,
                )
            )

        return articles

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags and truncate to 200 characters."""
        text = self._HTML_TAG_RE.sub("", text).strip()
        # Collapse whitespace left behind by removed tags
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 200:
            text = text[:197] + "..."
        return text
