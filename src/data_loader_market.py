"""
market_data.py: Equity Market Data Module
------------------------------------------
Purpose: Provides equity market data sourcing and caching for the platform, including:
- Spot prices (S0) from the most recent closing price.
- Annualised historical volatility (sigma) computed from 2-year daily log returns.
- Trailing dividend yield (q) sourced directly from yfinance ticker info.
- Rolling volatility time series computed from 5-year daily log returns.
- CSV caching for reproducibility — avoids repeated API calls and internet dependency.

Note on history periods:
- load_equity_data() uses 2 years — sufficient for a stable static sigma estimate.
- get_rolling_volatility() uses 5 years — longer history gives more observations
  for the rolling window and captures a fuller range of market conditions.

This module is the equity data equivalent of data_loader.py (which handles RBA yield
curve data). All equity data sourcing logic lives here and is reused by both the
derivatives and portfolio notebooks.
"""

import os
import numpy as np
import pandas as pd
import yfinance as yf

# --------------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------------

# Path to the cached equity data CSV — relative to this file's location.
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CACHE_PATH = os.path.join(DATA_DIR, "equity_data.csv")

# Historical period used to estimate volatility.
HISTORY = "2y"

# Number of trading days used to annualise daily volatility.
TRADING_DAYS = 252

# --------------------------------------------------------------------------------------------------
# Stock Universe
# --------------------------------------------------------------------------------------------------

# Five ASX-listed equities selected for the portfolio.
STOCKS = {
    "CBA": {"ticker": "CBA.AX", "sector": "Banking"},
    "BHP": {"ticker": "BHP.AX", "sector": "Materials"},
    "CSL": {"ticker": "CSL.AX", "sector": "Healthcare"},
}


# --------------------------------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------------------------------


def _download_single(name, info):
    """
    Download spot price, volatility, and dividend yield for a single stock.

    Parameters
    --------------------------
    name: str
    - Stock name key (e.g. 'CBA').
    info: dict
    - Dictionary containing at least 'ticker' key.

    Returns
    --------------------------
    dict
    - Updated info dictionary with S0, sigma, and div_yield populated.
    """
    # Download historical price data from yfinance.
    data = yf.download(info["ticker"], period=HISTORY, auto_adjust=True, progress=False)

    if data.empty:
        raise ValueError(
            f"No data returned for {name} ({info['ticker']}). "
            "Check the ticker and your internet connection."
        )

    # Most recent closing price as the spot price.
    info["S0"] = float(data["Close"].iloc[-1].squeeze())

    # Annualised volatility from daily log returns.
    log_returns = np.log(data["Close"] / data["Close"].shift(1)).dropna().squeeze()
    info["sigma"] = float(log_returns.std() * np.sqrt(TRADING_DAYS))

    # Trailing 12-month dividend yield sourced directly from yfinance ticker info.
    # Falls back to 0.0 if not available (e.g. non-dividend paying stocks).
    ticker_info = yf.Ticker(info["ticker"]).info
    div_yield = float(ticker_info.get("dividendYield", 0.0) or 0.0)
    # yfinance sometimes returns dividend yield with unusual scaling
    # If value > 1, assume it's been scaled (e.g., 3.01 for 3.01%) and normalize to decimal
    if div_yield > 1.0:
        div_yield = div_yield / 100
    info["div_yield"] = div_yield

    return info


def _sanity_check(data):
    """
    Run basic sanity checks on the downloaded equity data.

    Parameters
    --------------------------
    data: dict
    - Dictionary of stock data with S0, sigma, div_yield populated.
    """
    for name, d in data.items():
        assert d["S0"] > 0, f"{name}: S0 must be positive."
        assert d["sigma"] > 0, f"{name}: sigma must be positive."
        assert d["sigma"] < 2.0, f"{name}: sigma > 200% — likely a data error."
        assert 0 <= d["div_yield"] < 0.20, f"{name}: div_yield implausibly high."

    print(f"[market_data] Sanity checks passed for {list(data.keys())}.")


# --------------------------------------------------------------------------------------------------
# Public Interface
# --------------------------------------------------------------------------------------------------


def load_equity_data(stocks=None, use_cache=True):
    """
    Description
    --------------------------
    Load equity market data for the portfolio stocks.

    On first run, downloads data from yfinance and saves to CSV cache.
    On subsequent runs, loads from the CSV cache for reproducibility.
    Set use_cache = False to force a fresh download.

    Parameters
    --------------------------
    stocks: dict or None
    - Defaults to the module-level STOCKS dictionary.
    use_cache: bool
    - If True (default), load from the cached CSV when available.
    - If False, force a fresh download from yfinance.

    Returns
    --------------------------
    dict
    - Dictionary keyed by stock name, each containing:
        ticker    : str   — ASX ticker (e.g. 'CBA.AX')
        sector    : str   — sector label
        S0        : float — most recent closing price ($)
        sigma     : float — annualised historical volatility (decimal)
        div_yield : float — trailing dividend yield (decimal)
    """
    if stocks is None:
        stocks = {k: dict(v) for k, v in STOCKS.items()}

    # Load from cache if available and requested.
    if use_cache and os.path.exists(CACHE_PATH):
        cached = pd.read_csv(CACHE_PATH, index_col=0)
        for name in stocks:
            if name in cached.index:
                stocks[name]["S0"] = float(cached.loc[name, "S0"])
                stocks[name]["sigma"] = float(cached.loc[name, "sigma"])
                stocks[name]["div_yield"] = float(cached.loc[name, "div_yield"])
            else:
                raise ValueError(
                    f"{name} not found in cache. Run with use_cache=False."
                )
        print(f"[market_data] Loaded from cache: {CACHE_PATH}")
        return stocks

    # Download fresh data from yfinance.
    print(f"[market_data] Downloading equity data from yfinance ({HISTORY} history)...")
    for name, info in stocks.items():
        stocks[name] = _download_single(name, info)
        print(
            f"  {name}: S0=${stocks[name]['S0']:.2f} | "
            f"σ={stocks[name]['sigma']*100:.2f}% | "
            f"q={stocks[name]['div_yield']*100:.2f}%"
        )

    # Run sanity checks before caching.
    _sanity_check(stocks)

    # Cache to CSV for reproducibility.
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_df = pd.DataFrame(
        {
            name: {
                "S0": d["S0"],
                "sigma": d["sigma"],
                "div_yield": d["div_yield"],
            }
            for name, d in stocks.items()
        }
    ).T
    cache_df.to_csv(CACHE_PATH)
    print(f"[market_data] Cached equity data to: {CACHE_PATH}")

    return stocks


def get_equity_summary(stocks=None):
    """
    Description
    --------------------------
    Return a formatted summary table of equity market data.

    Parameters
    --------------------------
    stocks: dict or None
    - Stock data dictionary. If None, loads via load_equity_data().

    Returns
    --------------------------
    pd.DataFrame
    - Summary table with spot price, volatility, and dividend yield.
    """
    if stocks is None:
        stocks = load_equity_data()

    rows = []
    for name, d in stocks.items():
        rows.append(
            {
                "Stock": name,
                "Sector": d["sector"],
                "Spot Price ($)": round(d["S0"], 2),
                "Volatility (% p.a.)": round(d["sigma"] * 100, 2),
                "Div Yield (%)": round(d["div_yield"] * 100, 2),
            }
        )

    result = pd.DataFrame(rows)
    result.index = [""] * len(result)
    return result


def get_rolling_volatility(ticker, window=30, period="5y", cache_dir=None):
    """
    Description
    --------------------------
    Compute rolling annualised volatility for a given ticker.

    Uses a sliding window of N trading days — each day the oldest
    observation is removed and the newest one is added in its place. The result is
    a time series of volatility rather than a single number, showing
    how risk has evolved over time.

    Used by both the derivatives notebook (pricing sensitivity) and the
    portfolio notebook (risk monitoring) so it lives here in market_data.py
    rather than being duplicated across modules.

    Parameters
    --------------------------
    ticker: str
    - Yahoo Finance ticker (e.g. 'CBA.AX').
    window: int
    - Rolling window in trading days (default 30).
    period: str
    - Historical period to download (default '5y').
    cache_dir: str or None
    - Directory to cache the return series CSV. If None, no caching is done.

    Returns
    --------------------------
    pd.Series
    - Rolling annualised volatility as a decimal time series.
      NaN for the first (window - 1) observations.
    """
    # Build cache path for the return series if a cache directory is provided.
    if cache_dir is not None:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{ticker}_returns.csv")
        if os.path.exists(cache_path):
            # Load from cache — avoids repeated API calls on subsequent runs.
            print(f"[market_data] Loading cached returns: {cache_path}")
            returns = pd.read_csv(cache_path, index_col=0, parse_dates=True).squeeze()
        else:
            # Download and cache the return series.
            print(f"[market_data] Downloading {ticker} returns ({period})...")
            data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
            prices = data["Close"].squeeze()
            # Log returns: ln(P_t / P_{t-1}) — consistent with GBM assumption.
            returns = np.log(prices / prices.shift(1)).dropna()
            returns.to_csv(cache_path)
            print(f"[market_data] Cached returns to: {cache_path}")
    else:
        # No cache — download directly.
        print(f"[market_data] Downloading {ticker} returns ({period})...")
        data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        prices = data["Close"].squeeze()
        returns = np.log(prices / prices.shift(1)).dropna()

    # Rolling std over the window, scaled to annual using sqrt(252).
    rolling_vol = returns.rolling(window).std() * np.sqrt(TRADING_DAYS)
    print(
        f"[market_data] Rolling volatility computed "
        f"(window={window}d, {len(rolling_vol.dropna())} observations)."
    )
    return rolling_vol


# --------------------------------------------------------------------------------------------------
# Quick Test
# --------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    # Force a fresh download and display the summary table.
    data = load_equity_data(use_cache=False)
    print()
    print(get_equity_summary(data).to_string())
