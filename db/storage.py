import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


class ArticleStorage:
    """SQLite-backed deduplication and logging for fetched articles."""

    def __init__(self, db_path: str = "news_bot.db"):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS sent_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_fingerprint ON sent_articles(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_sent_at ON sent_articles(sent_at);

            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                fetched_count INTEGER DEFAULT 0,
                new_count INTEGER DEFAULT 0,
                error TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._conn.commit()

    # ── dedup ────────────────────────────────────────────────────

    def is_sent(self, fingerprint: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM sent_articles WHERE fingerprint = ?", (fingerprint,)
        )
        return cur.fetchone() is not None

    def mark_sent(self, fingerprint: str, source: str, url: str, title: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO sent_articles (fingerprint, source, url, title) VALUES (?, ?, ?, ?)",
            (fingerprint, source, url, title),
        )
        self._conn.commit()

    # ── fetch log ────────────────────────────────────────────────

    def log_fetch(self, source: str, fetched_count: int, new_count: int, error: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO fetch_log (source, fetched_count, new_count, error) VALUES (?, ?, ?, ?)",
            (source, fetched_count, new_count, error),
        )
        self._conn.commit()

    # ── stats ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        stats: dict = {"sources": {}, "total": 0, "last_fetch": None}

        # Count per source
        rows = self._conn.execute(
            "SELECT source, COUNT(*) as cnt FROM sent_articles GROUP BY source"
        ).fetchall()
        for row in rows:
            stats["sources"][row["source"]] = row["cnt"]
            stats["total"] += row["cnt"]

        # Last fetch time
        row = self._conn.execute(
            "SELECT MAX(fetched_at) as last_fetch FROM fetch_log"
        ).fetchone()
        if row and row["last_fetch"]:
            stats["last_fetch"] = row["last_fetch"]

        return stats

    # ── cleanup ──────────────────────────────────────────────────

    def cleanup(self, retention_days: int = 90) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM sent_articles WHERE sent_at < ?", (cutoff,)
        )
        deleted = cur.rowcount
        self._conn.execute(
            "DELETE FROM fetch_log WHERE fetched_at < ?", (cutoff,)
        )
        self._conn.commit()
        return deleted

    # ── lifecycle ────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
