from datetime import datetime

from fetchers.base import Article
from fetchers.rss import RSSFetcher


class AItimesFetcher(RSSFetcher):
    """AI Times fetcher (RSS 2.0 with non-standard date format)."""

    # AI Times uses "YYYY-MM-DD HH:MM:SS" which feedparser may not recognise.
    _AITIMES_DATE_FORMATS = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    )

    def __init__(self, max_articles: int = 10):
        super().__init__(
            name="aitimes",
            url="https://www.aitimes.com/rss/allArticle.xml",
            max_articles=max_articles,
        )

    async def fetch(self) -> list[Article]:
        """Fetch articles, falling back to manual date parsing when needed."""
        import feedparser
        import httpx
        from time import mktime

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(
                self.url, headers={"User-Agent": "NewsTelegramBot/1.0"}
            )
            response.raise_for_status()

        feed = feedparser.parse(response.text)
        articles: list[Article] = []

        for entry in feed.entries[: self.max_articles]:
            # Try feedparser's parsed date first
            published = None
            for date_field in ("published_parsed", "updated_parsed"):
                parsed = getattr(entry, date_field, None)
                if parsed:
                    published = datetime.fromtimestamp(mktime(parsed))
                    break

            # If feedparser couldn't parse the date, try manually
            if published is None:
                raw_date = entry.get("published", entry.get("updated", ""))
                if raw_date:
                    published = self._parse_aitimes_date(raw_date.strip())

            link = entry.get("link", "")
            if isinstance(link, dict):
                link = link.get("href", "")

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

    def _parse_aitimes_date(self, raw: str) -> datetime | None:
        """Try several date formats common in AI Times feeds."""
        for fmt in self._AITIMES_DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None
