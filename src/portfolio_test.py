import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import yfinance as yf

#Import the standalone risk functions from risk.py
#These are kept separate so they can be resused outside the Portfolio class
import sys
sys.path.insert (0, os.path.dirname(os.path.abspath(__file__)))

from risk import (
    historical_var,
    parametric_var,
    monte_carlo_var,
    expected_shortfall,
    max_drawdown
)


class EquityPosition:
    """
    Simple equity object for this portfolio layer.
    An equity position has delt = 1 because the position value moves
    dollar-for-dollar with the underlying stock price.
    """
    def __init__(self, ticker, spot):
        self.ticker = ticker
        self.spot = spot

    def get_ticker(self):
        return self.ticker

    def price(self):
        """ Return the current spot price of the equity."""
        return self.spot

    def delta(self):
        # Equity moves 1 to 1 with itself (need to define in derivatives as well)
        return 1.0


class Portfolio:
    """
    Simple portfolio object to hold positions, calculates portfolio value,
    computes delta of total portfolio, computes basic historical VaR,
    and creates a simple position table.
    Scenario analysis should be done in the notebook.
    """

    def __init__(self):
        self.positions = []
        self._returns = None #cached return series after load equity returns

    def add_position(self, instrument, quantity, label=None):
        """Add an instrument position into the portfolio."""

        # Potentially set this up so you can't append two of the same instruments
        # if you don't have a dictionary, do this. If there is, alter the qty...

        self.positions.append({
            "instrument" : instrument,
            "quantity"   : quantity,
            "label"      : label
        })

    def value(self):
        """Compute the total value of the portfolio."""
        total_value = 0.0

        for position in self.positions:
            instrument = position["instrument"]
            quantity   = position["quantity"]

            total_value += quantity * instrument.price()

        return total_value

    def delta(self):
        """Compute the total delta of the portfolio."""
        total_delta = 0.0

        for position in self.positions:
            instrument = position["instrument"]
            quantity   = position["quantity"]

            total_delta += quantity * instrument.delta()

        return total_delta

    def position_table(self):
        """Return a table showing each position's contribution to both value and delta."""
        rows = []

        for position in self.positions:
            instrument = position["instrument"]
            quantity   = position["quantity"]

            if position["label"] is not None:
                name = position["label"]
            elif hasattr(instrument, "ticker"):
                name = instrument.get_ticker()
            else:
                name = instrument.__class__.__name__

            unit_value = instrument.price()
            unit_delta = instrument.delta()

            rows.append({
                "Position"       : name,
                "Quantity"       : quantity,
                "Unit Value"     : unit_value,
                "Position Value" : unit_value * quantity,
                "Unit Delta"     : unit_delta,
                "Position Delta" : unit_delta * quantity
            })

        df = pd.DataFrame(rows)

        if len(df) > 0:
            total_row = pd.DataFrame([{
                "Position"       : "TOTAL",
                "Quantity"       : np.nan,
                "Unit Value"     : np.nan,
                "Position Value" : df["Position Value"].sum(),
                "Unit Delta"     : np.nan,
                "Position Delta" : df["Position Delta"].sum()
            }])

            df = pd.concat([df, total_row], ignore_index=True)
        return df
    

    #Equity Return Data

    def load_equity_returns (self, ticker, period ="5y", cache_dir =None):
        """
        Load historical returns for a given equity ticker using yfinance.
        Log returns are used (rather than simple returns) because they are additive over time,
        and consisitent with the GBM assumption underlying Black-Scholes.

        Computed as: r_t = ln(Pt / Pt-1)

        Results are cached to a CSV so that subsequent runs can be done offline.

        Parameters
        ----------
        ticker : str
            Yahoo Finance ticker.
        period : str
            Data period to fetch (e.g., '1y', '5y').
        cache_dir : str or None
            Directory to cache downloaded data. If None, no caching is done.

        Returns
        -------
        pd.Series
            Series of historical returns.
        """
        if cache_dir is not None:
            cache_path = os.path.join (cache_dir, f"{ticker}_returns.csv")
            if os.path.exists (cache_path):
                print (f"[portfolio] Loading cached returns: {cache_path}")
                returns = pd.read_csv (cache_path, index_col=0, parse_dates = True).squeeze ()
                self._returns = returns
                print (f"[portfolio] {len (returns)} daily returns loaded "
                       f"({returns.index [0].date()} to {returns.index [-1].date()})")
                return returns
            
        #Download data using yfinance
        print (f"[portfolio] Downloading {ticker} ({period})...")
        data   = yf.download (ticker, period = period, auto_adjust = True, progress = False)
        prices = data ["Close"].squeeze ()
        returns = np.log (prices / prices.shift (1)).dropna ()
 
        # Save to cache.
        if cache_dir is not None:
            os.makedirs (cache_dir, exist_ok = True)
            returns.to_csv (cache_path)
            print (f"[portfolio] Cached to {cache_path}")
 
        self._returns = returns
        print (f"[portfolio] {len (returns)} daily returns loaded "
               f"({returns.index [0].date()} to {returns.index [-1].date()})")
        return returns
 
    def _get_returns (self):
        """Internal helper — returns cached series or raises if not loaded."""
        if self._returns is None:
            raise RuntimeError (
                "No return data loaded. Call load_equity_returns() first."
            )
        return self._returns





    #Risk Metrics

    def historical_var(self, returns, alpha=0.95, horizon_days=1):
        """
        Compute a basic historical VaR.

        Parameters
        ----------
        returns : array
            Historical return series.
        alpha : float
            Confidence level (typically 0.95 or 0.99).
        horizon_days : int
            Length of VaR period.

        Returns
        -------
        float
            Historical VaR in $.
        """
        returns = pd.Series(returns).dropna()

        if len(returns) == 0:
            raise ValueError("Return series is empty.")
        if horizon_days <= 0:
            raise ValueError("horizon_days must be positive.")

        # Scale daily returns to the desired horizon using square root of time rule
        scaled_returns = returns * np.sqrt(horizon_days)

        q       = scaled_returns.quantile(1 - alpha)
        var     = -q * self.value()
        return max(var, 0)
    

    def parametric_var (self, alpha=0.95, horizon_days=1):
        """
        Gaussian assumption using historical mean and std.

        Usually underestimates tail risk because real equity returns
        are leptokurtic (fat-tailed). Compare with historical_var() to
        quantify the impact of the normality assumption.

        Parameters
        ----------
        alpha : float
            Confidence level.
        horizon_days : int
            Holding period in days.
 
        Returns
        -------
        float
            VaR in dollars (positive).

        """
        
        returns = self._get_returns ()
        return parametric_var (
            returns,
            alpha           = alpha,
            horizon_days    = horizon_days,
            portfolio_value = self.value (),
        )
    


    def expected_shortfall (self, alpha=0.95, horizon_days=1):
        """
        Expected shortfall (CVaR) is the average loss in the worst (1-alpha)% of cases.
        Provides a more complete picture of tail risk than VaR.
        It helps calculate the expected loss given that loss exceeds VaR

        Parameters
        ----------
        alpha : float
            Confidence level.
        horizon_days : int
            Holding period in days.

        Returns
        -------
        float
            Expected shortfall in dollars (positive).
        """
        
        returns = self._get_returns ()
        return expected_shortfall (
            returns,
            alpha           = alpha,
            horizon_days    = horizon_days,
            portfolio_value = self.value (),
        )