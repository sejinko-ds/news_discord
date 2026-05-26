from fetchers.rss import RSSFetcher


class YozmFetcher(RSSFetcher):
    def __init__(self, max_articles: int = 10):
        super().__init__(
            name="yozm",
            url="https://yozm.wishket.com/magazine/ai/feed/",
            max_articles=max_articles,
        )
