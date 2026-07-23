import os
import sqlite3
import tempfile

from app.repositories.gex_history import GexHistoryRecord, SQLiteGexHistoryRepository


def test_sqlite_repository_append_and_query():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_history.db")
        repo = SQLiteGexHistoryRepository(db_path=db_path)

        record = GexHistoryRecord(
            timestamp_utc="2026-07-05T12:00:00+00:00",
            symbol="SPX",
            spot=5425.35,
            net_gex=-100.0,
            absolute_gex=1000.0,
            gamma_gauge=-10.0,
            gamma_flip=5400.0,
            positive_wall=5450.0,
            negative_pit=5400.0,
            confidence_score=80.0,
            sign_model="NAIVE_CONVENTION",
        )
        repo.append(record)

        results = repo.query("SPX", limit=10)
        assert len(results) == 1
        assert results[0].symbol == "SPX"
        assert results[0].spot == 5425.35


def test_sqlite_repository_query_empty_symbol_returns_empty_list():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_history2.db")
        repo = SQLiteGexHistoryRepository(db_path=db_path)
        results = repo.query("NONEXISTENT", limit=10)
        assert results == []


def test_sqlite_repository_prevents_duplicate_snapshot_insert():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_history3.db")
        repo = SQLiteGexHistoryRepository(db_path=db_path)
        record = GexHistoryRecord(
            snapshot_id="fixed-snapshot-id-123",
            timestamp_utc="2026-07-05T12:00:00+00:00",
            symbol="SPX",
            spot=5425.35,
            net_gex=-100.0,
            absolute_gex=1000.0,
            gamma_gauge=-10.0,
            gamma_flip=5400.0,
            positive_wall=5450.0,
            negative_pit=5400.0,
            confidence_score=80.0,
            sign_model="NAIVE_CONVENTION",
            provider="mock",
            source_data_timestamp="2026-07-05T11:59:00+00:00",
        )
        inserted_first = repo.append(record)
        inserted_second = repo.append(record)  # exact duplicate snapshot_id

        assert inserted_first is True
        assert inserted_second is False
        results = repo.query("SPX", limit=10)
        assert len(results) == 1


def test_sqlite_repository_has_indexes_on_symbol_and_timestamp():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_history4.db")
        repo = SQLiteGexHistoryRepository(db_path=db_path)
        with sqlite3.connect(db_path) as conn:
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(gex_history)").fetchall()}
        assert "idx_gex_history_symbol" in indexes
        assert "idx_gex_history_timestamp" in indexes
        assert "idx_gex_history_symbol_ts" in indexes


def test_sqlite_repository_purge_expired_removes_old_rows():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_history5.db")
        repo = SQLiteGexHistoryRepository(db_path=db_path)
        old_record = GexHistoryRecord(
            snapshot_id="old-1",
            timestamp_utc="2000-01-01T00:00:00+00:00",
            symbol="SPX",
            spot=1.0,
            net_gex=0.0,
            absolute_gex=0.0,
            gamma_gauge=0.0,
            gamma_flip=None,
            positive_wall=None,
            negative_pit=None,
            confidence_score=0.0,
            sign_model="NAIVE_CONVENTION",
        )
        repo.append(old_record)
        deleted = repo.purge_expired(retention_days=1)
        assert deleted == 1
        assert repo.query("SPX") == []
