"""Tests for run_weekly.py — the weekly entry point."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from run_weekly import (
    delete_position,
    get_position,
    init_db,
    is_stop_loss_triggered,
    run_symbol,
    save_position,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_df(close: float = 100.0, n: int = 5) -> pd.DataFrame:
    """Return a minimal enriched DataFrame that satisfies run_symbol's expectations."""
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "close": [close] * n,
            "adj_close": [close] * n,
            "ma_short": [close * 0.9] * n,
            "ma_long": [close * 0.8] * n,
            "rsi": [55.0] * n,
        },
        index=idx,
    )


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    """In-memory-backed connection using a temp file."""
    return init_db(str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# init_db / get_position / save_position / delete_position
# ---------------------------------------------------------------------------

class TestDbHelpers:
    """Tests for the SQLite position-tracking helper functions."""

    def test_init_creates_positions_table(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert ("positions",) in tables

    def test_get_position_returns_none_when_empty(self, conn):
        assert get_position(conn, "VWCE") is None

    def test_save_and_get_position(self, conn):
        save_position(conn, "VWCE", 95.0, 3)
        pos = get_position(conn, "VWCE")
        assert pos is not None
        assert pos["entry_price"] == pytest.approx(95.0)
        assert pos["quantity"] == 3

    def test_delete_position(self, conn):
        save_position(conn, "VWCE", 95.0, 3)
        delete_position(conn, "VWCE")
        assert get_position(conn, "VWCE") is None

    def test_save_position_upserts(self, conn):
        save_position(conn, "VWCE", 95.0, 3)
        save_position(conn, "VWCE", 110.0, 2)
        pos = get_position(conn, "VWCE")
        assert pos["entry_price"] == pytest.approx(110.0)
        assert pos["quantity"] == 2


# ---------------------------------------------------------------------------
# is_stop_loss_triggered
# ---------------------------------------------------------------------------

class TestIsStopLossTriggered:
    """Tests for the is_stop_loss_triggered boundary logic."""

    def test_not_triggered_when_price_unchanged(self):
        assert not is_stop_loss_triggered(100.0, 100.0, 0.15)

    def test_not_triggered_when_price_up(self):
        assert not is_stop_loss_triggered(110.0, 100.0, 0.15)

    def test_not_triggered_just_above_threshold(self):
        assert not is_stop_loss_triggered(86.0, 100.0, 0.15)  # -14% < -15%

    def test_triggered_at_threshold(self):
        assert is_stop_loss_triggered(85.0, 100.0, 0.15)  # exactly -15%

    def test_triggered_below_threshold(self):
        assert is_stop_loss_triggered(80.0, 100.0, 0.15)  # -20%


# ---------------------------------------------------------------------------
# run_symbol — smoke tests (DRYRUN=true)
# ---------------------------------------------------------------------------

class TestRunSymbolDryRun:
    """Smoke tests for run_symbol in DRYRUN mode — no IBKR connection made."""

    def _patch_data(self, df: pd.DataFrame):
        """Return a context-manager that patches fetch_ohlcv and enrich_with_indicators."""
        return patch.multiple(
            "run_weekly",
            fetch_ohlcv=MagicMock(return_value=df),
            enrich_with_indicators=MagicMock(return_value=df),
        )

    def test_runs_without_error(self, monkeypatch, conn):
        monkeypatch.setenv("DRYRUN", "true")
        df = _minimal_df()
        with self._patch_data(df):
            run_symbol("vwce", conn)  # must not raise

    def test_no_db_write_in_dryrun(self, monkeypatch, conn):
        monkeypatch.setenv("DRYRUN", "true")
        df = _minimal_df()
        with self._patch_data(df):
            run_symbol("vwce", conn)
        assert get_position(conn, "VWCE") is None

    def test_fetch_error_is_swallowed(self, monkeypatch, conn):
        """A data-fetch failure should log and return, not raise."""
        monkeypatch.setenv("DRYRUN", "true")
        with patch("run_weekly.fetch_ohlcv", side_effect=RuntimeError("network down")):
            run_symbol("vwce", conn)  # must not raise

    def test_stop_loss_overrides_signal_in_dryrun(self, monkeypatch, conn, caplog):
        """Stop-loss condition forces signal to SELL even in DRYRUN mode."""
        import logging
        monkeypatch.setenv("DRYRUN", "true")
        save_position(conn, "VWCE", 200.0, 1)  # entry at 200, current at 100 → -50%
        df = _minimal_df(close=100.0)
        with caplog.at_level(logging.INFO):
            with self._patch_data(df):
                run_symbol("vwce", conn)
        assert "signal=SELL" in caplog.text
