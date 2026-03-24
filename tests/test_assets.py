from __future__ import annotations

import pytest

from trading_bot.assets import ASSETS, get_asset


class TestGetAsset:
    def test_returns_correct_asset_for_known_key(self):
        """get_asset('vwce') returns the VWCE asset with correct symbols."""
        asset = get_asset("vwce")
        assert asset.yahoo_symbol == "VWCE.DE"
        assert asset.ib_symbol == "VWCE"
        assert asset.currency == "EUR"

    def test_case_insensitive(self):
        """'VWCE' and 'vwce' resolve to the same Asset instance."""
        assert get_asset("VWCE") == get_asset("vwce")

    def test_mixed_case(self):
        """Mixed-case keys are also normalised to lowercase."""
        assert get_asset("VwCe") == get_asset("vwce")

    def test_unknown_key_raises_key_error(self):
        """An unrecognised key raises KeyError."""
        with pytest.raises(KeyError, match="unknown_ticker"):
            get_asset("unknown_ticker")


class TestAssetsRegistry:
    def test_all_assets_have_nonempty_yahoo_symbol(self):
        """Every entry in ASSETS has a non-empty yahoo_symbol."""
        for key, asset in ASSETS.items():
            assert asset.yahoo_symbol, f"{key}: yahoo_symbol is empty"

    def test_all_assets_have_nonempty_ib_symbol(self):
        """Every entry in ASSETS has a non-empty ib_symbol."""
        for key, asset in ASSETS.items():
            assert asset.ib_symbol, f"{key}: ib_symbol is empty"

    def test_all_assets_have_nonempty_currency(self):
        """Every entry in ASSETS has a non-empty currency code."""
        for key, asset in ASSETS.items():
            assert asset.currency, f"{key}: currency is empty"
