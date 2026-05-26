import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    title: str
    url: str
    source: str
    summary: str = ""
    published_at: datetime | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()


class BaseFetcher(ABC):
    def __init__(self, name: str, url: str, max_articles: int = 10):
        self.name = name
        self.url = url
        self.max_articles = max_articles

    @abstractmethod
    async def fetch(self) -> list[Article]:
        ...
