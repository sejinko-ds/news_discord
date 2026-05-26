from fetchers.rss import RSSFetcher


class HadaFetcher(RSSFetcher):
    """GeekNews Hada fetcher (Atom 1.0 feed via Feedburner)."""

    def __init__(self, max_articles: int = 10):
        super().__init__(
            name="hada",
            url="https://news.hada.io/rss/news",
            max_articles=max_articles,
        )
