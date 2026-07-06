"""
GEX-over-time persistence (section 23 of the v0.1.1 hardening spec).

Implemented on SQLite. The GexHistoryRepository interface is deliberately
narrow so a future PostgreSQL/TimescaleDB implementation is a drop-in
replacement — no caller depends on SQLite specifics.

v0.1.1 changes:
  - snapshot_id, provider, source_data_timestamp columns added
  - UNIQUE constraint on snapshot_id prevents duplicate inserts for the
    same completed analysis snapshot
  - indexes on symbol, timestamp_utc, and (symbol, timestamp_utc)
  - configurable retention (EGE_HISTORY_RETENTION_DAYS)
"""
from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.core.config import settings


@dataclass
class GexHistoryRecord:
    timestamp_utc: str
    symbol: str
    spot: float
    net_gex: float
    absolute_gex: float
    gamma_gauge: float
    gamma_flip: Optional[float]
    positive_wall: Optional[float]
    negative_pit: Optional[float]
    confidence_score: float
    sign_model: str
    snapshot_id: Optional[str] = None
    provider: Optional[str] = None
    source_data_timestamp: Optional[str] = None


class GexHistoryRepository(ABC):
    @abstractmethod
    def append(self, record: GexHistoryRecord) -> bool:
        """Returns True if a new row was inserted, False if it was a
        no-op due to a duplicate snapshot_id."""
        raise NotImplementedError

    @abstractmethod
    def query(self, symbol: str, limit: int = 500) -> List[GexHistoryRecord]:
        raise NotImplementedError


class SQLiteGexHistoryRepository(GexHistoryRepository):
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.sqlite_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gex_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id TEXT UNIQUE,
                    timestamp_utc TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    spot REAL,
                    net_gex REAL,
                    absolute_gex REAL,
                    gamma_gauge REAL,
                    gamma_flip REAL,
                    positive_wall REAL,
                    negative_pit REAL,
                    confidence_score REAL,
                    sign_model TEXT,
                    provider TEXT,
                    source_data_timestamp TEXT
                )
                """
            )
            # Backfill columns for any pre-v0.1.1 database file.
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(gex_history)").fetchall()}
            for col, coltype in (
                ("snapshot_id", "TEXT"),
                ("provider", "TEXT"),
                ("source_data_timestamp", "TEXT"),
            ):
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE gex_history ADD COLUMN {col} {coltype}")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_gex_history_symbol ON gex_history(symbol)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gex_history_timestamp ON gex_history(timestamp_utc)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gex_history_symbol_ts ON gex_history(symbol, timestamp_utc)"
            )
            conn.commit()

    def append(self, record: GexHistoryRecord) -> bool:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO gex_history
                    (snapshot_id, timestamp_utc, symbol, spot, net_gex, absolute_gex, gamma_gauge,
                     gamma_flip, positive_wall, negative_pit, confidence_score, sign_model,
                     provider, source_data_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.snapshot_id,
                        record.timestamp_utc,
                        record.symbol,
                        record.spot,
                        record.net_gex,
                        record.absolute_gex,
                        record.gamma_gauge,
                        record.gamma_flip,
                        record.positive_wall,
                        record.negative_pit,
                        record.confidence_score,
                        record.sign_model,
                        record.provider,
                        record.source_data_timestamp,
                    ),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Duplicate snapshot_id: this exact analysis snapshot was
                # already recorded. Deliberate no-op, not an error.
                return False

    def query(self, symbol: str, limit: int = 500) -> List[GexHistoryRecord]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT timestamp_utc, symbol, spot, net_gex, absolute_gex, gamma_gauge,
                       gamma_flip, positive_wall, negative_pit, confidence_score, sign_model,
                       snapshot_id, provider, source_data_timestamp
                FROM gex_history
                WHERE symbol = ?
                ORDER BY timestamp_utc DESC
                LIMIT ?
                """,
                (symbol, limit),
            )
            rows = cur.fetchall()
        return [
            GexHistoryRecord(
                timestamp_utc=r[0],
                symbol=r[1],
                spot=r[2],
                net_gex=r[3],
                absolute_gex=r[4],
                gamma_gauge=r[5],
                gamma_flip=r[6],
                positive_wall=r[7],
                negative_pit=r[8],
                confidence_score=r[9],
                sign_model=r[10],
                snapshot_id=r[11],
                provider=r[12],
                source_data_timestamp=r[13],
            )
            for r in rows
        ]

    def purge_expired(self, retention_days: Optional[int] = None) -> int:
        """Deletes rows older than the retention window. Returns the
        number of rows deleted."""
        days = retention_days if retention_days is not None else settings.history_retention_days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM gex_history WHERE timestamp_utc < ?", (cutoff,))
            conn.commit()
            return cur.rowcount
