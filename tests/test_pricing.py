"""Tests for regional pricing: snap_to_price_point, calculate_regional_prices,
_effective_rates, fetch_live_rates, _expand_pricing_tiers, and MCP pricing tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from perfectdeckcli import mcp_server
from perfectdeckcli import regional_pricing
from perfectdeckcli.project_router import ProjectListingRouter
from perfectdeckcli.regional_pricing import (
    COUNTRY_CURRENCY,
    EXCHANGE_RATES_TO_USD,
    PRICE_POINTS,
    PRICING_TIERS,
    APP_STORE_TERRITORY,
    ZERO_DECIMAL_CURRENCIES,
    _effective_rates,
    calculate_regional_prices,
    calculate_regional_prices_for_products,
    snap_to_price_point,
)


# ===========================================================================
# snap_to_price_point
# ===========================================================================


class TestSnapToPricePoint:
    def test_exact_match_returns_same(self):
        assert snap_to_price_point(0.99, "USD") == 0.99

    def test_rounds_up_to_next_99_when_fraction_below_half(self):
        result = snap_to_price_point(1.20, "USD")
        assert result in PRICE_POINTS["USD"]
        assert result == 1.99

    def test_rounds_to_next_99_when_fraction_above_half(self):
        result = snap_to_price_point(2.54, "USD")
        assert result in PRICE_POINTS["USD"]
        assert result == 2.99

    def test_rounds_up_to_next_99_for_mid_price_example(self):
        result = snap_to_price_point(2.30, "USD")
        assert result in PRICE_POINTS["USD"]
        assert result == 2.99

    def test_rounds_to_next_99_when_fraction_is_exactly_half(self):
        result = snap_to_price_point(2.50, "USD")
        assert result in PRICE_POINTS["USD"]
        assert result == 2.99

    def test_rounds_up_without_99_fallback(self):
        # SGD grid uses .98 endings, so we pick the next valid upward point.
        result = snap_to_price_point(1.20, "SGD")
        assert result == 1.48

    def test_below_first_point_snaps_to_first(self):
        result = snap_to_price_point(0.01, "USD")
        assert result == PRICE_POINTS["USD"][0]

    def test_above_last_point_snaps_to_last(self):
        result = snap_to_price_point(999.0, "USD")
        assert result == PRICE_POINTS["USD"][-1]

    def test_known_currencies(self):
        for currency in ["EUR", "GBP", "CAD", "AUD", "INR", "JPY", "KRW"]:
            result = snap_to_price_point(2.0, currency)
            assert result in PRICE_POINTS[currency], f"Snapped price not in {currency} grid"

    def test_unknown_fractional_currency_uses_50_cent_threshold(self):
        result = snap_to_price_point(1.20, "XYZ")
        assert result == 1.99

    def test_unknown_zero_decimal_currency_rounds_to_whole_number(self):
        result = snap_to_price_point(7.36, "XOF")
        assert result == 8.0

    def test_result_is_always_a_valid_point(self):
        for price in [0.5, 1.0, 2.5, 5.0, 9.99, 15.0]:
            result = snap_to_price_point(price, "EUR")
            assert result in PRICE_POINTS["EUR"]


# ===========================================================================
# _effective_rates
# ===========================================================================


class TestEffectiveRates:
    def test_no_overrides_returns_hardcoded(self):
        rates = _effective_rates(live_rates=False, exchange_rate_overrides=None)
        assert rates["USD"] == 1.0
        assert rates["EUR"] == EXCHANGE_RATES_TO_USD["EUR"]

    def test_exchange_rate_overrides_take_priority(self):
        rates = _effective_rates(
            live_rates=False,
            exchange_rate_overrides={"EUR": 0.50, "GBP": 0.60},
        )
        assert rates["EUR"] == 0.50
        assert rates["GBP"] == 0.60
        # Other currencies unaffected
        assert rates["USD"] == 1.0

    def test_live_rates_fetched_and_merged(self):
        fake_live = {"EUR": 0.88, "JPY": 155.0, "NEWCUR": 42.0}
        with patch.object(regional_pricing, "fetch_live_rates", return_value=fake_live):
            rates = _effective_rates(live_rates=True, exchange_rate_overrides=None)
        assert rates["EUR"] == 0.88
        assert rates["JPY"] == 155.0
        assert rates["NEWCUR"] == 42.0

    def test_overrides_beat_live_rates(self):
        fake_live = {"EUR": 0.88}
        with patch.object(regional_pricing, "fetch_live_rates", return_value=fake_live):
            rates = _effective_rates(
                live_rates=True,
                exchange_rate_overrides={"EUR": 0.75},
            )
        assert rates["EUR"] == 0.75

    def test_live_rate_failure_falls_back_to_hardcoded(self):
        with patch.object(regional_pricing, "fetch_live_rates", side_effect=RuntimeError("no network")):
            rates = _effective_rates(live_rates=True, exchange_rate_overrides=None)
        # Falls back silently; hardcoded rates still present
        assert rates["EUR"] == EXCHANGE_RATES_TO_USD["EUR"]
        assert rates["USD"] == 1.0


# ===========================================================================
# fetch_live_rates
# ===========================================================================


class TestFetchLiveRates:
    def test_successful_fetch_returns_rates(self):
        fake_response_body = json.dumps(
            {"result": "success", "rates": {"EUR": 0.92, "GBP": 0.79, "JPY": 148.0}}
        ).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response_body

        with patch("urllib.request.urlopen", return_value=mock_resp):
            rates = regional_pricing.fetch_live_rates()

        assert rates["EUR"] == 0.92
        assert rates["GBP"] == 0.79
        assert rates["JPY"] == 148.0

    def test_network_error_raises_runtime_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(RuntimeError, match="Failed to fetch live exchange rates"):
                regional_pricing.fetch_live_rates()

    def test_unexpected_response_raises_runtime_error(self):
        fake_response_body = json.dumps({"result": "error"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response_body
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="Unexpected response"):
                regional_pricing.fetch_live_rates()

    def test_bad_rate_values_are_skipped(self):
        fake_response_body = json.dumps(
            {"result": "success", "rates": {"EUR": 0.92, "BAD": "not-a-number"}}
        ).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response_body
        with patch("urllib.request.urlopen", return_value=mock_resp):
            rates = regional_pricing.fetch_live_rates()
        assert rates["EUR"] == 0.92
        assert "BAD" not in rates


# ===========================================================================
# calculate_regional_prices
# ===========================================================================


class TestCalculateRegionalPrices:
    # All tests disable live_rates to avoid network calls in CI
    def _calc(self, base_usd=1.99, store="play", **kwargs):
        return calculate_regional_prices(
            base_usd=base_usd, store=store, live_rates=False, **kwargs
        )

    # -- basic output structure --

    def test_returns_dict_of_country_codes(self):
        result = self._calc()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_play_uses_2letter_codes(self):
        result = self._calc(store="play")
        for code in result:
            assert len(code) == 2, f"Expected 2-letter code, got: {code}"

    def test_app_store_uses_3letter_codes(self):
        result = self._calc(store="app_store")
        for code in result:
            assert len(code) == 3, f"Expected 3-letter code, got: {code}"

    def test_each_entry_has_currency_and_price(self):
        result = self._calc()
        for code, entry in result.items():
            assert "currency" in entry, f"Missing currency for {code}"
            assert "price" in entry, f"Missing price for {code}"
            assert isinstance(entry["price"], (int, float))

    # -- tier1 countries (no discount) --

    def test_us_gets_base_usd_price(self):
        result = self._calc(base_usd=1.99, store="play")
        assert "US" in result
        assert result["US"]["currency"] == "USD"
        assert result["US"]["price"] == snap_to_price_point(1.99, "USD")

    def test_gb_gets_gbp_price(self):
        result = self._calc(base_usd=1.99, store="play")
        assert "GB" in result
        assert result["GB"]["currency"] == "GBP"

    def test_de_gets_eur_price(self):
        result = self._calc(base_usd=1.99, store="play")
        assert "DE" in result
        assert result["DE"]["currency"] == "EUR"

    def test_ca_preserves_099_nominal_price_near_parity(self):
        result = self._calc(base_usd=0.99, store="play", countries=["CA"])
        assert result["CA"]["currency"] == "CAD"
        assert result["CA"]["price"] == 0.99

    def test_de_preserves_099_nominal_price_near_parity(self):
        result = self._calc(base_usd=0.99, store="play", countries=["DE"])
        assert result["DE"]["currency"] == "EUR"
        assert result["DE"]["price"] == 0.99

    def test_aud_does_not_preserve_nominal_price_outside_parity_band(self):
        result = self._calc(base_usd=0.99, store="play", countries=["AU"])
        assert result["AU"]["currency"] == "AUD"
        assert result["AU"]["price"] == 1.99

    # -- tier multipliers reduce price --

    def test_tier4_price_less_than_tier1(self):
        result = self._calc(base_usd=9.99, store="play")
        # IN is tier4 (0.35×), US is tier1 (1.0×)
        in_usd_equiv = result["IN"]["price"] / EXCHANGE_RATES_TO_USD.get("INR", 1.0)
        us_price = result["US"]["price"]
        assert in_usd_equiv < us_price * 0.6  # comfortably less

    def test_tier2_price_less_than_tier1(self):
        result = self._calc(base_usd=9.99, store="play")
        # KR is tier2 (0.75×), US is tier1 (1.0×)
        kr_usd_equiv = result["KR"]["price"] / EXCHANGE_RATES_TO_USD.get("KRW", 1.0)
        us_price = result["US"]["price"]
        assert kr_usd_equiv < us_price

    # -- include_tier5 --

    def test_tier5_excluded_by_default(self):
        result = self._calc(store="play")
        tier5_countries = set(PRICING_TIERS["tier5"]["countries"])
        for c in tier5_countries:
            assert c not in result, f"Tier5 country {c} should not appear by default"

    def test_tier5_included_when_flag_set(self):
        result = self._calc(store="play", include_tier5=True)
        tier5_countries = PRICING_TIERS["tier5"]["countries"]
        found = [c for c in tier5_countries if c in result]
        assert len(found) > 0, "At least some tier5 countries should be present"

    # -- countries filter --

    def test_countries_filter_limits_output(self):
        result = self._calc(store="play", countries=["US", "GB", "CA"])
        assert set(result.keys()) == {"US", "GB", "CA"}

    def test_countries_filter_none_returns_all(self):
        # countries=None means no filter → all countries included
        result_none = self._calc(store="play", countries=None)
        result_all = self._calc(store="play")
        assert result_none == result_all

    def test_countries_filter_with_app_store_maps_to_3letter(self):
        result = self._calc(store="app_store", countries=["US", "GB"])
        assert "USA" in result
        assert "GBR" in result
        assert len(result) == 2

    # -- currency_overrides --

    def test_currency_override_applied(self):
        # Force US to use EUR instead of USD
        result = self._calc(store="play", countries=["US"], currency_overrides={"US": "EUR"})
        assert result["US"]["currency"] == "EUR"

    # -- exchange_rate_overrides --

    def test_exchange_rate_override_affects_price(self):
        # With a very high JPY rate, the JPY price should be high
        result_normal = self._calc(store="play", countries=["JP"])
        result_high = self._calc(
            store="play", countries=["JP"],
            exchange_rate_overrides={"JPY": 300.0},
        )
        # Higher rate → more JPY per USD → higher JPY price
        assert result_high["JP"]["price"] >= result_normal["JP"]["price"]

    # -- tier_overrides --

    def test_tier_override_changes_multiplier(self):
        result_normal = self._calc(store="play", countries=["US"])
        result_half = self._calc(
            store="play", countries=["US"],
            tiers={"tier1": {"multiplier": 0.5, "countries": ["US"]}},
        )
        assert result_half["US"]["price"] <= result_normal["US"]["price"]

    def test_custom_tier_adds_countries(self):
        # Add a fictional tier with a specific country
        result = self._calc(
            store="play",
            tiers={"tier_custom": {"multiplier": 0.8, "countries": ["US"]}},
            countries=["US"],
        )
        assert "US" in result

    # -- snapping --

    def test_all_prices_are_valid_price_points(self):
        result = self._calc(store="play")
        for country, entry in result.items():
            currency = entry["currency"]
            price = entry["price"]
            grid = PRICE_POINTS.get(currency)
            if grid:
                assert price in grid, f"{country}/{currency} price {price} not in grid {grid}"
            elif currency in ZERO_DECIMAL_CURRENCIES:
                assert price == round(price), f"{country}/{currency} expected whole-number fallback, got {price}"
            else:
                cents = int(round((price - int(price)) * 100))
                assert cents == 99, (
                    f"{country}/{currency} expected .99 fallback pricing, got {price}"
                )

    # -- app_store territory mapping --

    def test_app_store_territory_codes_match_table(self):
        result = self._calc(store="app_store")
        expected_codes = set(APP_STORE_TERRITORY.values())
        for code in result:
            assert code in expected_codes, f"Unknown App Store territory: {code}"

    # -- zero base price --

    def test_zero_base_price_snaps_to_lowest_point(self):
        result = self._calc(base_usd=0.0, store="play", countries=["US"])
        assert result["US"]["price"] == PRICE_POINTS["USD"][0]


# ===========================================================================
# calculate_regional_prices_for_products
# ===========================================================================


class TestCalculateRegionalPricesForProducts:
    def test_bundle_group_keeps_non_increasing_price_per_unit(self):
        products = {
            "credits_10": {"base_usd": 1.99, "units": 10, "value_group": "credits"},
            "credits_25": {"base_usd": 3.99, "units": 25, "value_group": "credits"},
            "credits_50": {"base_usd": 6.99, "units": 50, "value_group": "credits"},
        }
        result = calculate_regional_prices_for_products(
            products=products,
            store="play",
            live_rates=False,
            countries=["US", "GB", "CA", "ES", "RU"],
        )

        for country in ["US", "GB", "CA", "ES", "RU"]:
            ratios = [
                result["credits_10"][country]["price"] / 10,
                result["credits_25"][country]["price"] / 25,
                result["credits_50"][country]["price"] / 50,
            ]
            assert ratios[0] >= ratios[1] >= ratios[2], f"{country} ratios out of order: {ratios}"

    def test_products_without_units_are_priced_independently(self):
        products = {
            "one_off": {"base_usd": 1.99},
            "bundle": {"base_usd": 3.99, "units": 25, "value_group": "credits"},
        }
        result = calculate_regional_prices_for_products(
            products=products,
            store="play",
            live_rates=False,
            countries=["US"],
        )
        assert result["one_off"]["US"]["price"] == snap_to_price_point(1.99, "USD")
        assert "US" in result["bundle"]

    def test_invalid_units_raise(self):
        with pytest.raises(ValueError, match="invalid 'units'"):
            calculate_regional_prices_for_products(
                products={"bad": {"base_usd": 1.99, "units": 0}},
                store="play",
                live_rates=False,
            )


# ===========================================================================
# _expand_pricing_tiers (mcp_server helper)
# ===========================================================================


class TestExpandPricingTiers:
    def test_passthrough_when_no_pricing_tiers_key(self):
        products = {
            "com.app.pro": {"default_price": {"currency": "USD", "price": 4.99}},
        }
        result = mcp_server._expand_pricing_tiers(products, "play")
        assert result == products

    def test_pricing_tiers_replaced_with_pricing_dict(self):
        products = {
            "com.app.credits": {
                "pricing_tiers": {"base_usd": 1.99, "live_rates": False},
            }
        }
        result = mcp_server._expand_pricing_tiers(products, "play")
        assert "pricing_tiers" not in result["com.app.credits"]
        assert "pricing" in result["com.app.credits"]
        assert isinstance(result["com.app.credits"]["pricing"], dict)

    def test_pricing_dict_contains_us(self):
        products = {
            "prod": {"pricing_tiers": {"base_usd": 2.99, "live_rates": False}},
        }
        result = mcp_server._expand_pricing_tiers(products, "play")
        assert "US" in result["prod"]["pricing"]

    def test_pricing_tiers_with_countries_filter(self):
        products = {
            "prod": {
                "pricing_tiers": {
                    "base_usd": 1.99,
                    "live_rates": False,
                    "countries": ["US", "GB"],
                }
            }
        }
        result = mcp_server._expand_pricing_tiers(products, "play")
        assert set(result["prod"]["pricing"].keys()) == {"US", "GB"}

    def test_other_keys_preserved_alongside_pricing(self):
        products = {
            "prod": {
                "listings": {"en-US": {"title": "Credits"}},
                "pricing_tiers": {"base_usd": 0.99, "live_rates": False},
            }
        }
        result = mcp_server._expand_pricing_tiers(products, "play")
        assert "listings" in result["prod"]
        assert "pricing" in result["prod"]

    def test_non_dict_product_passed_through(self):
        products = {"bad": "not-a-dict"}
        result = mcp_server._expand_pricing_tiers(products, "play")
        assert result == products

    def test_missing_base_usd_defaults_to_zero(self):
        products = {"prod": {"pricing_tiers": {"live_rates": False}}}
        result = mcp_server._expand_pricing_tiers(products, "play")
        assert "pricing" in result["prod"]

    def test_app_store_store_uses_3letter_codes(self):
        products = {
            "com.app.pro": {
                "pricing_tiers": {
                    "base_usd": 1.99,
                    "live_rates": False,
                    "countries": ["US", "GB"],
                }
            }
        }
        result = mcp_server._expand_pricing_tiers(products, "app_store")
        assert "USA" in result["com.app.pro"]["pricing"]
        assert "GBR" in result["com.app.pro"]["pricing"]

    def test_bundle_shorthand_preserves_non_increasing_price_per_unit(self):
        products = {
            "credits_10": {
                "pricing_tiers": {
                    "base_usd": 1.99,
                    "units": 10,
                    "value_group": "credits",
                    "live_rates": False,
                    "countries": ["US", "CA", "GB", "ES", "RU"],
                }
            },
            "credits_25": {
                "pricing_tiers": {
                    "base_usd": 3.99,
                    "units": 25,
                    "value_group": "credits",
                    "live_rates": False,
                    "countries": ["US", "CA", "GB", "ES", "RU"],
                }
            },
            "credits_50": {
                "pricing_tiers": {
                    "base_usd": 6.99,
                    "units": 50,
                    "value_group": "credits",
                    "live_rates": False,
                    "countries": ["US", "CA", "GB", "ES", "RU"],
                }
            },
        }
        result = mcp_server._expand_pricing_tiers(products, "play")

        for country in ["US", "CA", "GB", "ES", "RU"]:
            ratios = [
                result["credits_10"]["pricing"][country]["price"] / 10,
                result["credits_25"]["pricing"][country]["price"] / 25,
                result["credits_50"]["pricing"][country]["price"] / 50,
            ]
            assert ratios[0] >= ratios[1] >= ratios[2], f"{country} ratios out of order: {ratios}"


# ===========================================================================
# MCP tool: perfectdeck_get_pricing_tiers
# ===========================================================================


class TestMcpGetPricingTiers:
    def test_returns_all_tiers(self):
        result = json.loads(mcp_server.perfectdeck_get_pricing_tiers())
        assert result["ok"] is True
        assert "tiers" in result
        for tier in ["tier1", "tier2", "tier3", "tier4", "tier5"]:
            assert tier in result["tiers"]

    def test_each_tier_has_multiplier_and_countries(self):
        result = json.loads(mcp_server.perfectdeck_get_pricing_tiers())
        for tier_name, tier_data in result["tiers"].items():
            assert "multiplier" in tier_data, f"{tier_name} missing multiplier"
            assert "countries" in tier_data, f"{tier_name} missing countries"
            assert isinstance(tier_data["countries"], list)

    def test_tier1_multiplier_is_one(self):
        result = json.loads(mcp_server.perfectdeck_get_pricing_tiers())
        assert result["tiers"]["tier1"]["multiplier"] == 1.0

    def test_hint_included(self):
        result = json.loads(mcp_server.perfectdeck_get_pricing_tiers())
        assert "hint" in result

    def test_us_in_tier1(self):
        result = json.loads(mcp_server.perfectdeck_get_pricing_tiers())
        assert "US" in result["tiers"]["tier1"]["countries"]


# ===========================================================================
# MCP tool: perfectdeck_set_iap_pricing_tiers
# ===========================================================================


def _setup_project(tmp_path: Path, app: str = "myapp") -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(
            project_path="proj",
            app=app,
            stores=["play", "app_store"],
            locales=["en-US"],
        )
    )


def _json(raw: str) -> dict:
    return json.loads(raw)


class TestMcpSetIapPricingTiers:
    def test_basic_play_pricing(self, tmp_path):
        _setup_project(tmp_path)
        result = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={"com.app.credits_10": {"base_usd": 1.99}},
                live_rates=False,
            )
        ))
        assert result["ok"] is True
        assert result["products_configured"] == 1
        assert result["countries_configured"] > 0
        assert result["store"] == "play"

    def test_basic_app_store_pricing(self, tmp_path):
        _setup_project(tmp_path)
        result = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj",
                app="myapp",
                store="app_store",
                products={"com.app.pro": {"base_usd": 4.99}},
                live_rates=False,
            )
        ))
        assert result["ok"] is True
        assert result["store"] == "app_store"

    def test_multiple_products(self, tmp_path):
        _setup_project(tmp_path)
        result = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={
                    "com.app.credits_10": {"base_usd": 1.99},
                    "com.app.credits_25": {"base_usd": 3.99},
                    "com.app.credits_50": {"base_usd": 6.99},
                },
                live_rates=False,
            )
        ))
        assert result["products_configured"] == 3

    def test_countries_filter_reduces_country_count(self, tmp_path):
        _setup_project(tmp_path)
        result_all = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={"prod": {"base_usd": 1.99}},
                live_rates=False,
            )
        ))
        result_filtered = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={"prod": {"base_usd": 1.99}},
                countries=["US", "GB", "CA"],
                live_rates=False,
            )
        ))
        assert result_filtered["countries_configured"] == 3
        assert result_filtered["countries_configured"] < result_all["countries_configured"]

    def test_include_tier5_increases_country_count(self, tmp_path):
        _setup_project(tmp_path)
        result_no_t5 = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj", app="myapp", store="play",
                products={"prod": {"base_usd": 1.99}}, live_rates=False,
            )
        ))
        result_with_t5 = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj", app="myapp", store="play",
                products={"prod": {"base_usd": 1.99}}, include_tier5=True, live_rates=False,
            )
        ))
        assert result_with_t5["countries_configured"] > result_no_t5["countries_configured"]

    def _get_products(self, tmp_path, store="play"):
        data = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(project_path="proj", app="myapp", store=store)
        ))
        return data["data"].get("products", {})

    def test_pricing_persisted_to_listing(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={"com.app.credits": {"base_usd": 1.99}},
                countries=["US", "GB"],
                live_rates=False,
            )
        )
        products = self._get_products(tmp_path)
        assert "com.app.credits" in products
        pricing = products["com.app.credits"]["pricing"]
        assert "US" in pricing
        assert "GB" in pricing

    def test_exchange_rate_overrides_applied(self, tmp_path):
        _setup_project(tmp_path)
        # Price with normal rates
        mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj", app="myapp", store="play",
                products={"prod": {"base_usd": 1.99}},
                countries=["JP"],
                live_rates=False,
            )
        )
        price_normal = self._get_products(tmp_path)["prod"]["pricing"]["JP"]["price"]

        # Price with doubled JPY rate
        mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj", app="myapp", store="play",
                products={"prod": {"base_usd": 1.99}},
                countries=["JP"],
                live_rates=False,
                exchange_rate_overrides={"JPY": EXCHANGE_RATES_TO_USD["JPY"] * 2},
            )
        )
        price_high = self._get_products(tmp_path)["prod"]["pricing"]["JP"]["price"]
        assert price_high >= price_normal

    def test_merges_with_existing_products(self, tmp_path):
        _setup_project(tmp_path)
        # First configure a product with localizations
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj", app="myapp", store="play",
                products={"prod": {"listings": {"en-US": {"title": "My Product"}}}},
            )
        )
        # Then apply pricing tiers
        mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj", app="myapp", store="play",
                products={"prod": {"base_usd": 1.99}},
                countries=["US"],
                live_rates=False,
            )
        )
        product = self._get_products(tmp_path)["prod"]
        assert "listings" in product
        assert "pricing" in product

    def test_hint_included(self, tmp_path):
        _setup_project(tmp_path)
        result = _json(mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj", app="myapp", store="play",
                products={"p": {"base_usd": 1.99}}, live_rates=False,
            )
        ))
        assert "hint" in result

    def test_bundle_group_preserves_non_increasing_price_per_unit(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_set_iap_pricing_tiers(
            mcp_server.SetIapPricingTiersInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={
                    "credits_10": {"base_usd": 1.99, "units": 10, "value_group": "credits"},
                    "credits_25": {"base_usd": 3.99, "units": 25, "value_group": "credits"},
                    "credits_50": {"base_usd": 6.99, "units": 50, "value_group": "credits"},
                },
                countries=["US", "CA", "GB", "ES", "RU"],
                live_rates=False,
            )
        )
        products = self._get_products(tmp_path)
        for country in ["US", "CA", "GB", "ES", "RU"]:
            ratios = [
                products["credits_10"]["pricing"][country]["price"] / 10,
                products["credits_25"]["pricing"][country]["price"] / 25,
                products["credits_50"]["pricing"][country]["price"] / 50,
            ]
            assert ratios[0] >= ratios[1] >= ratios[2], f"{country} ratios out of order: {ratios}"


# ===========================================================================
# MCP tool: perfectdeck_configure_iap with pricing_tiers shorthand
# ===========================================================================


class TestMcpConfigureIapPricingTiers:
    def _get_products(self, tmp_path, store="play"):
        data = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(project_path="proj", app="myapp", store=store)
        ))
        return data["data"].get("products", {})

    def test_pricing_tiers_shorthand_expanded(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={
                    "com.app.pro": {
                        "pricing_tiers": {
                            "base_usd": 2.99,
                            "live_rates": False,
                            "countries": ["US", "GB", "DE"],
                        }
                    }
                },
            )
        )
        product = self._get_products(tmp_path)["com.app.pro"]
        assert "pricing" in product
        assert "pricing_tiers" not in product
        assert set(product["pricing"].keys()) == {"US", "GB", "DE"}

    def test_us_price_snapped_to_valid_point(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={
                    "prod": {
                        "pricing_tiers": {
                            "base_usd": 1.99,
                            "live_rates": False,
                            "countries": ["US"],
                        }
                    }
                },
            )
        )
        us_price = self._get_products(tmp_path)["prod"]["pricing"]["US"]["price"]
        assert us_price in PRICE_POINTS["USD"]

    def test_bundle_ladder_shorthand_preserves_non_increasing_price_per_unit(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={
                    "credits_10": {
                        "pricing_tiers": {
                            "base_usd": 1.99,
                            "units": 10,
                            "value_group": "credits",
                            "live_rates": False,
                            "countries": ["US", "CA", "GB", "ES", "RU"],
                        }
                    },
                    "credits_25": {
                        "pricing_tiers": {
                            "base_usd": 3.99,
                            "units": 25,
                            "value_group": "credits",
                            "live_rates": False,
                            "countries": ["US", "CA", "GB", "ES", "RU"],
                        }
                    },
                    "credits_50": {
                        "pricing_tiers": {
                            "base_usd": 6.99,
                            "units": 50,
                            "value_group": "credits",
                            "live_rates": False,
                            "countries": ["US", "CA", "GB", "ES", "RU"],
                        }
                    },
                },
            )
        )
        products = self._get_products(tmp_path)
        for country in ["US", "CA", "GB", "ES", "RU"]:
            ratios = [
                products["credits_10"]["pricing"][country]["price"] / 10,
                products["credits_25"]["pricing"][country]["price"] / 25,
                products["credits_50"]["pricing"][country]["price"] / 50,
            ]
            assert ratios[0] >= ratios[1] >= ratios[2], f"{country} ratios out of order: {ratios}"

    def test_manual_pricing_preserved_as_is(self, tmp_path):
        _setup_project(tmp_path)
        manual_pricing = {"US": {"currency": "USD", "price": 1.99}}
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={"prod": {"pricing": manual_pricing}},
            )
        )
        assert self._get_products(tmp_path)["prod"]["pricing"] == manual_pricing

    def test_app_store_pricing_tiers_uses_3letter_codes(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj",
                app="myapp",
                store="app_store",
                products={
                    "com.app.pro": {
                        "pricing_tiers": {
                            "base_usd": 4.99,
                            "live_rates": False,
                            "countries": ["US", "GB"],
                        }
                    }
                },
            )
        )
        pricing = self._get_products(tmp_path, store="app_store")["com.app.pro"]["pricing"]
        assert "USA" in pricing
        assert "GBR" in pricing

    def test_mixed_products_with_and_without_pricing_tiers(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={
                    "manual_prod": {"pricing": {"US": {"currency": "USD", "price": 0.99}}},
                    "tier_prod": {
                        "pricing_tiers": {
                            "base_usd": 1.99,
                            "live_rates": False,
                            "countries": ["US"],
                        }
                    },
                },
            )
        )
        products = self._get_products(tmp_path)
        assert products["manual_prod"]["pricing"]["US"]["price"] == 0.99
        assert "pricing" in products["tier_prod"]
        assert "US" in products["tier_prod"]["pricing"]

    def test_include_tier5_in_shorthand(self, tmp_path):
        _setup_project(tmp_path)
        mcp_server.perfectdeck_configure_iap(
            mcp_server.ConfigureIapInput(
                project_path="proj",
                app="myapp",
                store="play",
                products={
                    "prod": {
                        "pricing_tiers": {
                            "base_usd": 1.99,
                            "live_rates": False,
                            "include_tier5": True,
                        }
                    }
                },
            )
        )
        pricing = self._get_products(tmp_path)["prod"]["pricing"]
        tier5_countries = PRICING_TIERS["tier5"]["countries"]
        found = [c for c in tier5_countries if c in pricing]
        assert len(found) > 0
