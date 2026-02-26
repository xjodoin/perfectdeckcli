"""Regional pricing tiers for PPP-based IAP pricing.

Provides deterministic calculation of regional prices from a base USD price,
using purchasing power parity tiers, currency-aware price point grids, and
snapping to valid store price points.

Live exchange rates are fetched from open.er-api.com (free, no key required)
and merged over the hardcoded fallback rates. Per-call overrides take highest
priority.
"""
from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_LIVE_RATES_URL = "https://open.er-api.com/v6/latest/USD"
_FETCH_TIMEOUT = 5.0  # seconds

PRICING_TIERS: dict[str, dict] = {
    "tier1": {
        "name": "High Income",
        "multiplier": 1.00,
        "countries": [
            "US", "CA", "GB", "DE", "FR", "AU", "NL", "SE", "NO", "CH",
            "DK", "FI", "AT", "BE", "IE", "LU", "SG", "NZ", "IL", "AE",
            "QA", "KW", "BH", "IS",
            # Small wealthy territories
            "BM", "KY", "LI", "MC", "SM", "VA", "GI", "MO", "BS", "VG",
            "TC", "AW", "SC", "MU",
        ],
    },
    "tier2": {
        "name": "Upper-Middle",
        "multiplier": 0.75,
        "countries": [
            "ES", "IT", "PT", "KR", "JP", "TW", "HK", "CZ", "SK", "SI",
            "EE", "LT", "LV", "HR", "MT", "CY", "SA", "OM", "CL", "UY",
            "PA", "CR",
            # Upper-middle Caribbean & others
            "TT", "AG", "DM", "GD", "KN", "LC", "BW", "NA", "FJ",
            "MV",
        ],
    },
    "tier3": {
        "name": "Middle Income",
        "multiplier": 0.50,
        "countries": [
            "PL", "HU", "RO", "BG", "GR", "MX", "BR", "AR", "CO", "PE",
            "TH", "MY", "TR", "ZA", "RU", "UA", "KZ", "RS", "BA", "MK",
            "AL", "MD", "BY", "AZ", "GE", "AM", "JO", "LB", "DO", "EC",
            "GT", "SV", "HN", "NI", "BO", "PY",
            # Middle-income additions
            "JM", "SR", "BZ", "VE", "CV", "GA", "CG", "LY", "WS", "TO",
            "VU", "FM",
        ],
    },
    "tier4": {
        "name": "Lower-Middle",
        "multiplier": 0.35,
        "countries": [
            "IN", "ID", "PH", "VN", "EG", "MA", "TN", "DZ", "NG", "KE",
            "GH", "TZ", "UG", "SN", "CI", "CM", "ZW", "ZM", "MZ", "AO",
            "LK", "BD", "NP", "MM", "KH", "LA", "MN", "UZ", "TM", "TJ",
            "KG", "IQ", "PK",
            # Lower-middle additions
            "PG", "SB", "GM", "GN", "YE", "KM",
        ],
    },
    "tier5": {
        "name": "Emerging Markets",
        "multiplier": 0.25,
        "countries": [
            "RW", "BF", "ML", "NE", "TG", "BJ", "HT",
            # Emerging additions
            "CD", "CF", "TD", "DJ", "ER", "GW", "LR", "SL", "SO",
        ],
    },
}

COUNTRY_CURRENCY: dict[str, str] = {
    # Authoritative map from monetization.convertRegionPrices API (regions version 2022/02)
    # Americas
    "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL",
    "CL": "CLP", "CO": "COP", "PE": "PEN", "PY": "PYG", "BO": "BOB", "CR": "CRC",
    # Caribbean & small Americas (USD on Play Store)
    "BM": "USD", "KY": "USD", "BS": "USD", "VG": "USD", "TC": "USD",
    "AW": "USD", "AG": "USD", "DM": "USD", "GD": "USD",
    "KN": "USD", "LC": "USD", "TT": "USD", "JM": "USD", "SR": "USD",
    "BZ": "USD", "VE": "USD", "FM": "USD",
    # Europe – EUR (incl. non-EU that use EUR on Play Store, e.g. IS, BG joined 2025)
    "DE": "EUR", "FR": "EUR", "NL": "EUR", "AT": "EUR", "BE": "EUR",
    "IE": "EUR", "LU": "EUR", "FI": "EUR", "ES": "EUR", "IT": "EUR",
    "PT": "EUR", "GR": "EUR", "CY": "EUR", "MT": "EUR", "EE": "EUR",
    "LT": "EUR", "LV": "EUR", "HR": "EUR", "SK": "EUR", "SI": "EUR",
    "IS": "EUR", "BG": "EUR", "MC": "EUR", "SM": "EUR", "VA": "EUR",
    # West/Central Africa – EUR on Play Store
    "BF": "EUR", "BJ": "EUR", "CF": "EUR", "GA": "EUR",
    "GW": "EUR", "ML": "EUR", "NE": "EUR", "TG": "EUR",
    # Central Africa
    "CG": "USD", "TD": "USD", "CD": "USD",
    # Europe – non-EUR
    "GB": "GBP", "GI": "GBP",
    "SE": "SEK", "NO": "NOK", "DK": "DKK",
    "CH": "CHF", "LI": "CHF",
    "PL": "PLN", "CZ": "CZK", "HU": "HUF", "RO": "RON", "RS": "RSD",
    # APAC
    "AU": "AUD", "NZ": "NZD", "JP": "JPY", "KR": "KRW", "HK": "HKD",
    "MO": "MOP", "TW": "TWD", "SG": "SGD", "TH": "THB", "MY": "MYR",
    "ID": "IDR", "PH": "PHP", "VN": "VND", "IN": "INR",
    "PK": "PKR", "BD": "BDT", "LK": "LKR", "MM": "MMK", "MN": "MNT",
    # APAC – small states (USD on Play Store)
    "FJ": "USD", "PG": "USD", "SB": "USD", "WS": "USD", "TO": "USD",
    "VU": "USD", "MV": "USD",
    # MENA – local currency
    "AE": "AED", "SA": "SAR", "TR": "TRY", "IL": "ILS",
    "QA": "QAR", "EG": "EGP", "JO": "JOD", "IQ": "IQD", "MA": "MAD", "DZ": "DZD",
    "LY": "USD", "YE": "USD",
    # Africa – local currency
    "ZA": "ZAR", "NG": "NGN", "KE": "KES", "GH": "GHS", "TZ": "TZS",
    "CI": "XOF", "SN": "XOF", "CM": "XAF",
    # Africa – additional
    "BW": "USD", "NA": "USD", "MU": "USD", "SC": "USD", "CV": "USD",
    "GM": "USD", "GN": "USD", "KM": "USD", "LR": "USD", "SL": "USD",
    "SO": "USD", "DJ": "USD", "ER": "USD",
    # Post-Soviet – local currency
    "RU": "RUB", "UA": "UAH", "KZ": "KZT", "GE": "GEL",
    # Rest fall back to USD (KW, BH, OM, AR, AM, AZ, BY, AL, BA, MK,
    # DO, GT, HN, NI, UY, UZ, RW, TN, ZM, UG, etc.)
}

EXCHANGE_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0, "EUR": 0.92, "GBP": 0.79, "CAD": 1.36, "AUD": 1.54,
    "INR": 83.0, "BRL": 5.0, "JPY": 148.0, "KRW": 1340.0, "MXN": 17.5,
    "SGD": 1.35, "NZD": 1.63, "HKD": 7.8, "TWD": 31.5, "THB": 35.0,
    "PLN": 4.0, "CZK": 22.5, "SEK": 10.5, "NOK": 10.7, "DKK": 6.9,
    "CHF": 0.9, "ZAR": 18.5, "TRY": 32.0, "RUB": 90.0, "SAR": 3.75,
    "AED": 3.67, "MYR": 4.7, "IDR": 15800.0, "PHP": 56.0, "VND": 24500.0,
    "HUF": 360.0, "RON": 4.55, "BGN": 1.80,
    # Additional currencies
    "ILS": 3.7, "QAR": 3.64, "KWD": 0.31, "BHD": 0.38, "OMR": 0.38,
    "JOD": 0.71, "IQD": 1310.0, "EGP": 48.0, "MAD": 10.0, "DZD": 135.0,
    "TND": 3.1,
    "ISK": 138.0, "RSD": 108.0,
    "CLP": 945.0, "COP": 4000.0, "PEN": 3.7, "ARS": 870.0, "UYU": 39.0,
    "PYG": 7500.0, "BOB": 6.9, "CRC": 515.0, "GTQ": 7.8, "HNL": 24.7,
    "NIO": 36.5, "DOP": 58.5,
    "NGN": 1550.0, "KES": 130.0, "GHS": 15.0, "TZS": 2700.0, "UGX": 3800.0,
    "ETB": 57.0, "RWF": 1300.0, "ZMW": 26.0, "MWK": 1720.0, "MGA": 4600.0,
    "XOF": 605.0, "XAF": 605.0, "AOA": 850.0,
    "UAH": 39.0, "KZT": 450.0, "GEL": 2.7, "AMD": 390.0, "AZN": 1.7,
    "BYN": 3.3, "UZS": 12700.0, "KGS": 88.0, "TJS": 10.9, "TMT": 3.5,
    "PKR": 280.0, "BDT": 110.0, "LKR": 320.0, "NPR": 133.0,
    "MMK": 2100.0, "KHR": 4100.0, "MNT": 3400.0,
}

# ISO-4217 currencies that do not support fractional minor units.
ZERO_DECIMAL_CURRENCIES: set[str] = {
    "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG",
    "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}


def _round_to_99_threshold(price: float) -> float:
    """Round to ``.99`` using a ``.50`` fractional threshold.

    Rules:
    - fractional part ``< .50``: previous ``.99`` (e.g. ``2.30 -> 1.99``)
    - fractional part ``>= .50``: next ``.99`` (e.g. ``2.54 -> 2.99``)
    """
    if price <= 0:
        return 0.99

    whole = int(math.floor(price))
    fractional = price - whole

    if fractional < 0.50:
        candidate = (whole - 1) + 0.99
    else:
        candidate = whole + 0.99

    return round(max(0.99, candidate), 2)


def fetch_live_rates(timeout: float = _FETCH_TIMEOUT) -> dict[str, float]:
    """Fetch current USD-based exchange rates from open.er-api.com.

    Returns ``{currency_code: rate}`` where rate is how many units of that
    currency equal 1 USD (same convention as ``EXCHANGE_RATES_TO_USD``).

    Raises ``RuntimeError`` on network failure or unexpected response shape.
    """
    try:
        req = urllib.request.urlopen(_LIVE_RATES_URL, timeout=timeout)  # noqa: S310
        data = json.loads(req.read().decode())
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Failed to fetch live exchange rates: {exc}") from exc

    if data.get("result") != "success" or "rates" not in data:
        raise RuntimeError(f"Unexpected response from exchange rate API: {data.get('result')}")

    rates: dict[str, float] = {}
    for currency, rate in data["rates"].items():
        try:
            rates[str(currency)] = float(rate)
        except (TypeError, ValueError):
            pass
    return rates


def _effective_rates(
    live_rates: bool,
    exchange_rate_overrides: dict[str, float] | None,
) -> dict[str, float]:
    """Build the effective exchange-rate table for a calculation run.

    Priority (highest → lowest):
    1. ``exchange_rate_overrides`` (per-call explicit values)
    2. Live rates from open.er-api.com (when ``live_rates=True``)
    3. Hardcoded ``EXCHANGE_RATES_TO_USD`` fallback
    """
    rates = dict(EXCHANGE_RATES_TO_USD)

    if live_rates:
        try:
            live = fetch_live_rates()
            rates.update(live)
        except RuntimeError as exc:
            logger.warning("Live rate fetch failed, using hardcoded fallback: %s", exc)

    if exchange_rate_overrides:
        rates.update(exchange_rate_overrides)

    return rates


PRICE_POINTS: dict[str, list[float]] = {
    "USD": [0.25, 0.49, 0.79, 0.99, 1.49, 1.99, 2.49, 2.99, 3.49, 3.99, 4.49, 4.99, 5.49, 5.99, 6.49, 6.99, 7.49, 7.99, 8.99, 9.99],
    "EUR": [0.25, 0.49, 0.79, 0.99, 1.49, 1.99, 2.29, 2.49, 2.99, 3.49, 3.99, 4.49, 4.99, 5.49, 5.99, 6.49, 6.99, 7.49, 7.99],
    "GBP": [0.25, 0.49, 0.79, 0.99, 1.49, 1.79, 1.99, 2.49, 2.99, 3.49, 3.99, 4.49, 4.99, 5.49, 5.99, 6.49, 6.99],
    "CAD": [0.29, 0.49, 0.99, 1.29, 1.49, 1.99, 2.49, 2.99, 3.49, 3.99, 4.49, 4.99, 5.99, 6.99, 7.99, 8.99, 9.99],
    "AUD": [0.49, 0.99, 1.49, 1.99, 2.49, 2.99, 3.49, 3.99, 4.49, 4.99, 5.49, 5.99, 6.99, 7.99, 8.99, 9.99],
    "INR": [10, 19, 29, 39, 49, 59, 69, 79, 89, 99, 109, 119, 129, 149, 169, 189, 199, 219, 229, 249, 299, 349, 399, 449, 499],
    "BRL": [2.9, 3.9, 4.9, 5.9, 7.9, 9.9, 11.9, 14.9, 17.9, 18.9, 21.9, 24.9, 27.9, 29.9],
    "JPY": [100, 120, 150, 160, 180, 200, 240, 250, 360, 480, 600, 720, 840, 960, 1080, 1200, 1500, 1800, 2400],
    "KRW": [1000, 1100, 1200, 1500, 1900, 2000, 2200, 2500, 3300, 3900, 4400, 4900, 5500, 6500, 6600, 7700, 8800, 9900],
    "SGD": [0.98, 1.48, 1.98, 2.48, 2.98, 3.48, 3.98, 4.48, 4.98, 5.98, 6.98, 7.98, 8.98, 9.98],
    "NZD": [0.49, 0.99, 1.49, 1.99, 2.49, 2.99, 3.49, 3.99, 4.49, 4.99, 5.99, 6.99, 7.99, 8.99, 9.99],
    "CHF": [0.99, 1.49, 1.99, 2.49, 2.99, 3.49, 3.99, 4.49, 4.99, 5.99, 6.49, 6.99],
    "SEK": [7.99, 9.99, 13.99, 17.99, 22.99, 29.99, 39.99, 49.99, 59.99, 69.99],
    "NOK": [7.99, 10.99, 14.99, 18.99, 23.99, 29.99, 39.99, 49.99, 59.99, 69.99],
    "DKK": [6.99, 9.99, 13.99, 17.99, 22.99, 29.99, 39.99, 49.99, 59.99, 69.99],
    "PLN": [3.49, 4.99, 7.49, 9.99, 12.99, 15.99, 19.99, 24.99, 29.99],
    "HKD": [7.8, 11.8, 15.8, 19.8, 27.8, 39.8, 47.8, 55.8, 63.8, 79.8],
    "TWD": [30, 45, 60, 75, 90, 120, 150, 180, 210, 240],
    "THB": [15, 25, 35, 45, 55, 75, 85, 100, 120, 150, 175],
    "MYR": [3.99, 5.99, 7.99, 9.99, 14.99, 19.99, 24.99, 29.99],
    "IDR": [15000, 25000, 35000, 45000, 55000, 65000, 75000, 85000],
    "PHP": [55, 75, 99, 119, 149, 179, 199, 249],
    "ZAR": [4.99, 9.99, 14.99, 19.99, 29.99, 39.99, 49.99, 69.99],
    "TRY": [24.99, 34.99, 49.99, 64.99, 84.99, 99.99, 119.99, 149.99],
    "RUB": [79, 99, 149, 199, 249, 299, 449, 599, 749],
    "SAR": [3.99, 7.49, 9.99, 14.99, 19.99, 27.99, 37.99, 49.99],
    "AED": [3.99, 5.99, 7.99, 9.99, 14.99, 19.99, 24.99, 29.99],
    "MXN": [13, 17, 19, 29, 39, 49, 59, 69, 79, 99, 119, 149],
    "VND": [25000, 35000, 49000, 69000, 79000, 99000, 119000, 149000],
    "CZK": [19, 29, 49, 69, 89, 99, 129, 149, 179, 199, 249],
}

APP_STORE_TERRITORY: dict[str, str] = {
    "US": "USA", "CA": "CAN", "GB": "GBR", "AU": "AUS", "DE": "DEU",
    "FR": "FRA", "NL": "NLD", "AT": "AUT", "BE": "BEL", "IE": "IRL",
    "LU": "LUX", "FI": "FIN", "ES": "ESP", "IT": "ITA", "PT": "PRT",
    "GR": "GRC", "CY": "CYP", "MT": "MLT", "EE": "EST", "LT": "LTU",
    "LV": "LVA", "HR": "HRV", "SK": "SVK", "SI": "SVN", "SE": "SWE",
    "NO": "NOR", "DK": "DNK", "CH": "CHE", "PL": "POL", "CZ": "CZE",
    "HU": "HUN", "RO": "ROU", "BG": "BGR", "JP": "JPN", "KR": "KOR",
    "HK": "HKG", "TW": "TWN", "SG": "SGP", "NZ": "NZL", "IN": "IND",
    "TH": "THA", "MY": "MYS", "ID": "IDN", "PH": "PHL", "VN": "VNM",
    "BR": "BRA", "MX": "MEX", "AR": "ARG", "ZA": "ZAF", "SA": "SAU",
    "AE": "ARE", "IL": "ISR", "TR": "TUR", "RU": "RUS", "NG": "NGA",
    "KE": "KEN", "EG": "EGY", "OM": "OMN", "QA": "QAT", "KW": "KWT",
    "BH": "BHR", "IS": "ISL", "CL": "CHL", "CO": "COL", "PE": "PER",
    "UY": "URY", "UA": "UKR", "KZ": "KAZ", "PK": "PAK", "BD": "BGD",
    "LK": "LKA", "MM": "MMR", "ET": "ETH", "RW": "RWA", "GH": "GHA",
    "TZ": "TZA", "SN": "SEN", "CI": "CIV", "KH": "KHM", "LA": "LAO",
    "MN": "MNG", "UZ": "UZB",
    # Additional territories
    "BM": "BMU", "KY": "CYM", "LI": "LIE", "MC": "MCO", "SM": "SMR",
    "VA": "VAT", "GI": "GIB", "MO": "MAC", "BS": "BHS", "VG": "VGB",
    "TC": "TCA", "AW": "ABW", "SC": "SYC", "MU": "MUS",
    "TT": "TTO", "AG": "ATG", "DM": "DMA", "GD": "GRD", "KN": "KNA",
    "LC": "LCA", "BW": "BWA", "NA": "NAM", "FJ": "FJI", "MV": "MDV",
    "JM": "JAM", "SR": "SUR", "BZ": "BLZ", "VE": "VEN", "CV": "CPV",
    "GA": "GAB", "CG": "COG", "LY": "LBY", "WS": "WSM", "TO": "TON",
    "VU": "VUT", "FM": "FSM", "PG": "PNG", "SB": "SLB", "GM": "GMB",
    "GN": "GIN", "YE": "YEM", "KM": "COM", "CD": "COD", "CF": "CAF",
    "TD": "TCD", "DJ": "DJI", "ER": "ERI", "GW": "GNB", "LR": "LBR",
    "SL": "SLE", "SO": "SOM",
}


def snap_to_price_point(price: float, currency: str) -> float:
    """Snap to an allowed store price point.

    For currencies with explicit store grids, this prefers ``.99`` endings
    using the ``.50`` threshold rule:
    - fractional ``< .50``: previous ``.99``
    - fractional ``>= .50``: next ``.99``
    """
    points = PRICE_POINTS.get(currency)
    if points:
        ordered = sorted(points)
        if price <= ordered[0]:
            return ordered[0]
        ninety_nine = sorted(
            p for p in ordered if int(round((p - int(p)) * 100)) == 99
        )
        if ninety_nine:
            target = _round_to_99_threshold(price)
            return min(ninety_nine, key=lambda p: abs(p - target))

        upward = [p for p in ordered if p >= price]
        if not upward:
            return ordered[-1]
        return upward[0]
    # For currencies without a defined price grid, avoid falling back to USD points
    # (which gives wrong magnitudes). Keep no-cent currencies whole-number only.
    if currency in ZERO_DECIMAL_CURRENCIES:
        return float(max(0, math.ceil(price)))
    return _round_to_99_threshold(price)


def calculate_regional_prices(
    base_usd: float,
    store: str,
    tiers: dict | None = None,
    include_tier5: bool = False,
    currency_overrides: dict | None = None,
    live_rates: bool = True,
    exchange_rate_overrides: dict[str, float] | None = None,
    countries: list[str] | None = None,
) -> dict[str, dict]:
    """Calculate regional prices for all tier countries.

    Args:
        base_usd: Base price in USD (tier1 / full price).
        store: ``"play"`` (2-letter country codes) or ``"app_store"`` (3-letter territory codes).
        tiers: Optional dict to override tier multipliers or country lists.
        include_tier5: Include Tier 5 emerging markets (0.25× multiplier). Off by default.
        currency_overrides: Optional ``{country_2letter: currency_code}`` overrides.
        live_rates: Fetch current exchange rates from open.er-api.com before calculating.
            Falls back to hardcoded rates on network failure. Default: True.
        exchange_rate_overrides: Optional ``{currency_code: rate}`` overrides applied on top
            of live/hardcoded rates. e.g. ``{"JPY": 155.0, "EUR": 0.88}``.
        countries: Optional list of 2-letter country codes to include. When provided, only
            these countries are priced; all others are skipped. e.g. ``["US", "GB", "CA"]``.

    Returns:
        ``{country_or_territory_code: {"currency": str, "price": float}}``
    """
    effective_tiers = {k: dict(v) for k, v in PRICING_TIERS.items()}
    if tiers:
        for k, v in tiers.items():
            if k in effective_tiers:
                effective_tiers[k] = {**effective_tiers[k], **v}
            else:
                effective_tiers[k] = dict(v)

    tier_keys = list(effective_tiers.keys())
    if not include_tier5 and "tier5" in tier_keys:
        tier_keys = [t for t in tier_keys if t != "tier5"]

    rates = _effective_rates(live_rates, exchange_rate_overrides)
    country_filter: set[str] | None = set(countries) if countries else None

    result: dict[str, dict] = {}
    for tier_name in tier_keys:
        tier = effective_tiers[tier_name]
        multiplier: float = float(tier["multiplier"])
        for country in tier["countries"]:
            if country_filter is not None and country not in country_filter:
                continue
            currency = (currency_overrides or {}).get(country) or COUNTRY_CURRENCY.get(country, "USD")
            rate = rates.get(currency, 1.0)
            local_price = base_usd * multiplier * rate
            snapped = snap_to_price_point(local_price, currency)

            if store == "app_store":
                code = APP_STORE_TERRITORY.get(country)
                if code:
                    result[code] = {"currency": currency, "price": snapped}
            else:
                result[country] = {"currency": currency, "price": snapped}

    return result
