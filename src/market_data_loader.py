"""
market_data.py: Equity Market Data Module
------------------------------------------
Purpose: Provides equity market data sourcing and caching for the platform, including:
- Spot prices (S0) from the most recent closing price.
- Annualised historical volatility (sigma) computed from 2-year daily log returns.
- Trailing dividend yield (q) sourced directly from yfinance ticker info.
- CSV caching for reproducibility — avoids repeated API calls.
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
history = "2y"

# Number of trading days used to annualise daily volatility.
trading_days = 252

# --------------------------------------------------------------------------------------------------
# Default Stock Universe
# --------------------------------------------------------------------------------------------------

# Five ASX-listed equities selected for the portfolio.
default_stocks = {
    "CBA" : {"ticker": "CBA.AX", "sector": "Banking"},
    "BHP" : {"ticker": "BHP.AX", "sector": "Materials"},
    "CSL" : {"ticker": "CSL.AX", "sector": "Healthcare"},
    "WES" : {"ticker": "WES.AX", "sector": "Retail"},
    "TLS" : {"ticker": "TLS.AX", "sector": "Telecommunications"},
}


# --------------------------------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------------------------------

def _download_single(name, info):
    """
    Description
    --------------------------
    Download spot price, volatility, and dividend yield for a single stock.

    Parameters
    --------------------------
    name: str
    - Stock name key (e.g. 'CBA').
    info: dict
    - Dictionary containing S0, sigma, and div_yield populated.
    """
    # Download historical price data from yfinance.
    data = yf.download(info["ticker"], period=history, auto_adjust=True, progress=False)

    if data.empty:
        raise ValueError(f"No data returned for {name} ({info['ticker']}). ")

    # Most recent closing price as the spot price.
    # .squeeze() handles newer yfinance versions that return a multi-level DataFrame.
    close = data["Close"].squeeze()
    info["S0"] = float(close.iloc[-1])

    # Annualised volatility from daily log returns.
    log_returns = np.log(close / close.shift(1)).dropna()
    info["sigma"] = float(log_returns.std() * np.sqrt(trading_days))

    # Trailing 12-month dividend yield sourced directly from yfinance ticker info.
    # Falls back to 0.0 if not available (e.g. non-dividend paying stocks).
    ticker_info = yf.Ticker(info["ticker"]).info
    raw_yield = float(ticker_info.get("dividendYield", 0.0) or 0.0)
    # Newer yfinance versions return dividendYield as a percentage (e.g. 3.5) rather than
    # a decimal (0.035). Normalise to decimal regardless of which form is returned.
    info["div_yield"] = raw_yield / 100 if raw_yield > 1.0 else raw_yield

    return info


def _sanity_check(data):
    """
    Description
    --------------------------
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
    Set use_cache=False to force a fresh download.

    Parameters
    --------------------------
    stocks: dict or None
    - Stock universe to use. Defaults to the module-level default_stocks dictionary.
    use_cache: bool
    - If True (default), load from the cached CSV when available.
    - Set to False to force a fresh download from yfinance.

    Returns
    --------------------------
    dict
    - Dictionary keyed by stock name, each containing:
        ticker : str
        — ASX ticker (e.g. 'CBA.AX')
        sector : str
        — sector label
        S0 : float
        — most recent closing price ($)
        sigma : float 
        — annualised historical volatility (decimal)
        div_yield : float
        — trailing dividend yield (decimal)
    """
    if stocks is None:
        stocks = {k: dict(v) for k, v in default_stocks.items()}

    # Load from cache if available and requested.
    if use_cache and os.path.exists(CACHE_PATH):
        cached = pd.read_csv(CACHE_PATH, index_col=0)
        for name in stocks:
            if name in cached.index:
                stocks[name]["S0"] = float(cached.loc[name, "S0"])
                stocks[name]["sigma"] = float(cached.loc[name, "sigma"])
                stocks[name]["div_yield"] = float(cached.loc[name, "div_yield"])
            else:
                raise ValueError(f"{name} not found in cache. Run with use_cache=False.")
        print(f"[market_data] Loaded from cache: {CACHE_PATH}")
        return stocks

    # Download fresh data from yfinance.
    print(f"[market_data] Downloading equity data from yfinance ({history} history)...")
    for name, info in stocks.items():
        stocks[name] = _download_single(name, info)
        print(f"  {name}: S0=${stocks[name]['S0']:.2f} | "
              f"sigma={stocks[name]['sigma']*100:.2f}% | "
              f"q={stocks[name]['div_yield']*100:.2f}%")

    # Run sanity checks before caching.
    _sanity_check(stocks)

    # Cache to CSV for reproducibility.
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_df = pd.DataFrame({
        name: {
            "S0" : d["S0"],
            "sigma" : d["sigma"],
            "div_yield" : d["div_yield"],
        }
        for name, d in stocks.items()
    }).T
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
        rows.append({
            "Stock" : name,
            "Sector" : d["sector"],
            "Spot Price ($)" : round(d["S0"], 2),
            "Volatility (% p.a.)" : round(d["sigma"] * 100, 2),
            "Div Yield (%) [yfinance]" : round(d["div_yield"] * 100, 2),
        })

    result = pd.DataFrame(rows)
    result.index = [""] * len(result)
    return result


# --------------------------------------------------------------------------------------------------
# Quick Test
# --------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    # Force a fresh download and display the summary table.
    data = load_equity_data(use_cache=False)
    print()
    print(get_equity_summary(data).to_string())