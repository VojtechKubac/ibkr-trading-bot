from __future__ import annotations

from decimal import Decimal
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
    """Return a deterministic IBKRConfig for broker unit tests."""
    return IBKRConfig(
        host="127.0.0.1",
        port=7497,
        client_id=1,
        kill_switch=False,
        max_orders_per_day=5,
        max_position_size=1_000_000,
        max_daily_notional=None,
    )


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


def _patched_client(
    current_pos: int,
    *,
    orders_today: int | None = 0,
    daily_notional: Decimal | None = Decimal("0"),
):
    """Return a context-manager mock for IBKRClient that reports *current_pos*."""
    mock_client = MagicMock(spec=IBKRClient)
    mock_client.get_today_order_count.return_value = orders_today
    mock_client.get_today_filled_notional.return_value = daily_notional
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

    def test_kill_switch_blocks_before_client_connect(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("DRYRUN", "false")
        cfg = _make_cfg()
        cfg.kill_switch = True
        ctx, _mock_client = _patched_client(current_pos=0)
        with caplog.at_level(logging.ERROR):
            with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
                result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=cfg)
        assert isinstance(result, OrderSkipped)
        assert result.reason == "kill_switch_enabled"
        assert "Kill switch enabled" in caplog.text
        ctx.assert_not_called()

    def test_max_orders_per_day_blocks_order(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("DRYRUN", "false")
        cfg = _make_cfg()
        cfg.max_orders_per_day = 1
        ctx, mock_client = _patched_client(current_pos=0, orders_today=1)
        with caplog.at_level(logging.WARNING):
            with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
                result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=cfg)
        assert isinstance(result, OrderSkipped)
        assert result.reason == "max_orders_per_day_reached"
        assert "max orders/day reached" in caplog.text
        mock_client.place_market_order.assert_not_called()

    def test_orders_per_day_unavailable_blocks_order(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        ctx, mock_client = _patched_client(current_pos=0, orders_today=None)
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=_make_cfg())
        assert isinstance(result, OrderSkipped)
        assert result.reason == "orders_today_unavailable"
        mock_client.place_market_order.assert_not_called()

    def test_max_position_size_blocks_buy(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        cfg = _make_cfg()
        cfg.max_position_size = 10
        ctx, mock_client = _patched_client(current_pos=10)
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=cfg)
        assert isinstance(result, OrderSkipped)
        assert result.reason == "max_position_size_exceeded"
        mock_client.place_market_order.assert_not_called()

    def test_max_daily_notional_blocks_order(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        cfg = _make_cfg()
        cfg.max_daily_notional = Decimal("500")
        ctx, mock_client = _patched_client(current_pos=0, daily_notional=Decimal("450"))
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order(
                "BUY",
                ib_symbol="VWCE",
                quantity=1,
                reference_price=100.0,
                cfg=cfg,
            )
        assert isinstance(result, OrderSkipped)
        assert result.reason == "max_daily_notional_exceeded"
        mock_client.place_market_order.assert_not_called()

    def test_missing_reference_price_blocks_notional_guardrail(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        cfg = _make_cfg()
        cfg.max_daily_notional = Decimal("500")
        ctx, mock_client = _patched_client(current_pos=0, daily_notional=Decimal("100"))
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=cfg)
        assert isinstance(result, OrderSkipped)
        assert result.reason == "missing_price_for_notional_cap"
        mock_client.place_market_order.assert_not_called()

    def test_daily_notional_unavailable_blocks_order(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        cfg = _make_cfg()
        cfg.max_daily_notional = Decimal("500")
        ctx, mock_client = _patched_client(current_pos=0, daily_notional=None)
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order(
                "BUY",
                ib_symbol="VWCE",
                quantity=1,
                reference_price=100.0,
                cfg=cfg,
            )
        assert isinstance(result, OrderSkipped)
        assert result.reason == "daily_notional_unavailable"
        mock_client.place_market_order.assert_not_called()

    def test_nan_reference_price_blocks_notional_guardrail(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        cfg = _make_cfg()
        cfg.max_daily_notional = Decimal("500")
        ctx, mock_client = _patched_client(current_pos=0, daily_notional=Decimal("100"))
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order(
                "BUY",
                ib_symbol="VWCE",
                quantity=1,
                reference_price=float("nan"),
                cfg=cfg,
            )
        assert isinstance(result, OrderSkipped)
        assert result.reason == "missing_price_for_notional_cap"
        mock_client.place_market_order.assert_not_called()

    def test_order_submission_failure_returns_skipped_reason(self, monkeypatch):
        monkeypatch.setenv("DRYRUN", "false")
        ctx, mock_client = _patched_client(current_pos=0)
        mock_client.place_market_order.return_value = None
        with patch("trading_bot.broker_ibkr.IBKRClient", ctx):
            result = execute_signal_as_market_order("BUY", ib_symbol="VWCE", quantity=1, cfg=_make_cfg())
        assert isinstance(result, OrderSkipped)
        assert result.reason == "order_submission_failed"
