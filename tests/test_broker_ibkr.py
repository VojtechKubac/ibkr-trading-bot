from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from trading_bot.broker_ibkr import (
    DryRunSkipped,
    IBKRClient,
    IBKRConfig,
    OrderSkipped,
    execute_signal_as_market_order,
)


def _make_cfg() -> IBKRConfig:
    return IBKRConfig(host="127.0.0.1", port=7497, client_id=1)


def _make_position(symbol: str, shares: float) -> SimpleNamespace:
    """Minimal stand-in for an ib_insync Position object."""
    return SimpleNamespace(contract=SimpleNamespace(symbol=symbol), position=shares)


# ---------------------------------------------------------------------------
# IBKRClient.get_current_position
# ---------------------------------------------------------------------------


class TestGetCurrentPosition:
    def _client(self, positions: list) -> IBKRClient:
        client = IBKRClient(_make_cfg())
        client.ib = MagicMock()
        client.ib.positions.return_value = positions
        return client

    def test_returns_zero_when_no_positions(self):
        client = self._client([])
        assert client.get_current_position("VWCE") == 0

    def test_returns_zero_when_symbol_not_held(self):
        client = self._client([_make_position("SPY", 10)])
        assert client.get_current_position("VWCE") == 0

    def test_returns_share_count_for_held_symbol(self):
        client = self._client([_make_position("VWCE", 5)])
        assert client.get_current_position("VWCE") == 5

    def test_returns_int_not_float(self):
        client = self._client([_make_position("VWCE", 3.0)])
        result = client.get_current_position("VWCE")
        assert isinstance(result, int)
        assert result == 3

    def test_matches_by_symbol_only(self):
        """Picks the right position when multiple symbols are held."""
        client = self._client([
            _make_position("SPY", 2),
            _make_position("VWCE", 7),
        ])
        assert client.get_current_position("VWCE") == 7
        assert client.get_current_position("SPY") == 2

    def test_returns_zero_on_network_error(self):
        """Any exception from ib.positions() is caught and 0 is returned."""
        client = IBKRClient(_make_cfg())
        client.ib = MagicMock()
        client.ib.positions.side_effect = ConnectionError("lost connection")
        assert client.get_current_position("VWCE") == 0


# ---------------------------------------------------------------------------
# execute_signal_as_market_order — position-aware skipping
# ---------------------------------------------------------------------------


def _patched_client(current_pos: int):
    """Return a context-manager mock for IBKRClient that reports *current_pos*."""
    mock_client = MagicMock(spec=IBKRClient)
    mock_client.get_current_position.return_value = current_pos
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    ctx = MagicMock(return_value=mock_client)
    return ctx, mock_client


class TestExecuteSignalPositionCheck:
    """Tests that verify position-aware skipping logic (DRYRUN=false path)."""

    def test_buy_skipped_when_already_long(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        ctx, mock_client = _patched_client(current_pos=5)
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=_make_cfg())
        assert isinstance(result, OrderSkipped)
        assert result.reason == "already_long"
        assert result.signal == "BUY"
        assert result.ib_symbol == "VWCE"
        mock_client.place_market_order.assert_not_called()

    def test_sell_skipped_when_already_flat(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        ctx, mock_client = _patched_client(current_pos=0)
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("SELL", ib_symbol="VWCE", quantity=1, cfg=_make_cfg())
        assert isinstance(result, OrderSkipped)
        assert result.reason == "already_flat"
        mock_client.place_market_order.assert_not_called()

    def test_buy_placed_when_flat(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        ctx, mock_client = _patched_client(current_pos=0)
        mock_trade = MagicMock()
        mock_client.place_market_order.return_value = mock_trade
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=_make_cfg())
        assert result is mock_trade
        mock_client.place_market_order.assert_called_once_with(symbol="VWCE", quantity=1, action="BUY")

    def test_sell_placed_when_long(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        ctx, mock_client = _patched_client(current_pos=3)
        mock_trade = MagicMock()
        mock_client.place_market_order.return_value = mock_trade
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("SELL", ib_symbol="VWCE", quantity=3, cfg=_make_cfg())
        assert result is mock_trade
        mock_client.place_market_order.assert_called_once_with(symbol="VWCE", quantity=3, action="SELL")

    def test_hold_returns_none_without_connecting(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        ctx, mock_client = _patched_client(current_pos=0)
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("HOLD", ib_symbol="VWCE", quantity=1, cfg=_make_cfg())
        assert result is None
        ctx.assert_not_called()

    def test_dryrun_takes_precedence_over_position_check(self, monkeypatch):
        """DRYRUN=true must short-circuit before any IBKR connection."""
        monkeypatch.setenv("DRYRUN", "true")
        ctx, mock_client = _patched_client(current_pos=99)
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=_make_cfg())
        assert isinstance(result, DryRunSkipped)
        ctx.assert_not_called()
