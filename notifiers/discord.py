import logging
from datetime import datetime

import httpx

from fetchers.base import Article

logger = logging.getLogger(__name__)

# Discord embed color per source
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


class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_articles(self, articles: list[Article], source_label: str) -> int:
        """Send articles as Discord embeds. Returns number of sent messages."""
        if not articles:
            return 0

        embeds = self._format_embeds(articles, source_label)
        sent = 0
        for embed_batch in embeds:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        self.webhook_url,
                        json={"embeds": embed_batch},
                    )
                    resp.raise_for_status()
                    sent += 1
            except Exception as e:
                logger.error(f"Failed to send to Discord: {e}")
        return sent

    async def send_test(self) -> bool:
        """Send a test message."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.webhook_url,
                    json={"content": "✅ Discord News Bot 연결 테스트 성공!"},
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Test message failed: {e}")
            return False

    def _format_embeds(self, articles: list[Article], source_label: str) -> list[list[dict]]:
        """Format articles as Discord embeds. Discord allows max 10 embeds per message."""
        source_key = articles[0].source if articles else ""
        color = SOURCE_COLORS.get(source_key, DEFAULT_COLOR)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        logo_url = SOURCE_LOGOS.get(source_key, "")

        all_embeds = []
        for article in articles:
            embed = {
                "title": article.title,
                "url": article.url,
                "color": color,
                "footer": {"text": f"{source_label} | {date_str}"},
            }
            if logo_url:
                embed["thumbnail"] = {"url": logo_url}
            if article.summary:
                embed["description"] = article.summary[:200]
            all_embeds.append(embed)

        # Discord allows max 10 embeds per message
        batches = []
        for i in range(0, len(all_embeds), 10):
            batches.append(all_embeds[i : i + 10])

        return batches
