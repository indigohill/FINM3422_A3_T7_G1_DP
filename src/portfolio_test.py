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
    """
    def __init__(self, ticker, spot):
        self.ticker = ticker
        self.spot = spot

    def get_ticker(self):
        return self.ticker

    def price(self):
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