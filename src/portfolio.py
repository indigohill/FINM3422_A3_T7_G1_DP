"""
portfolio.py: Portfolio Risk Module
-------------------------------------
Purpose: Provides the portfolio risk layer for the platform, including:
- EquityPosition: A simple equity instrument compatible with the Portfolio class.
- Portfolio: Holds positions, computes portfolio value, delta, risk metrics,
  rolling volatility, scenario analysis, and visualisations.

Risk functions (historical VaR, parametric VaR, expected shortfall, max drawdown,
Monte Carlo VaR) are imported from risk.py, keeping analytics decoupled from the
Portfolio class and reusable across different valuation contexts.

Scenario analysis reprices the full portfolio under multiplicative spot and
volatility shocks, producing a P&L table and bar chart for each scenario.
"""

import copy
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# Import standalone risk functions from risk.py.
# Decoupling risk analytics from the Portfolio class keeps them
# reusable across different valuation contexts.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from risk import (
    historical_var,
    parametric_var,
    monte_carlo_var,
    expected_shortfall,
    max_drawdown,
)

# --------------------------------------------------------------------------------------------------
# EquityPosition
# --------------------------------------------------------------------------------------------------


class EquityPosition:
    """
    Description
    ------------------------------------------------------
    A simple equity instrument for use in the portfolio layer.

    Equity positions move one-to-one with the underlying spot price,
    so delta is always 1.0. This makes them compatible with the Portfolio
    class which calls price() and delta() polymorphically on all instruments,
    including derivative subclasses.

    Parameters
    ------------------------------------------------------
    ticker: str
    - Ticker symbol of the underlying stock (e.g. 'CBA.AX').
    spot: float
    - Current spot price of the stock in dollars.
    """

    def __init__(self, ticker, spot):
        # Store the ticker symbol for identification in position tables.
        self.ticker = ticker
        # Store the current spot price — used by price() and portfolio valuation.
        self.spot = spot

    def get_ticker(self):
        """Return the ticker symbol."""
        return self.ticker

    def price(self):
        """Return the current spot price of the equity."""
        return self.spot

    def delta(self):
        """
        Return delta of the equity position.
        Equity moves one-to-one with the underlying — delta is always 1.0.
        """
        return 1.0


# --------------------------------------------------------------------------------------------------
# Portfolio Class
# --------------------------------------------------------------------------------------------------


class Portfolio:
    """
    Description
    ------------------------------------------------------
    Holds a collection of positions and computes portfolio-level risk metrics.

    Supports any instrument that exposes price() and delta() methods,
    including EquityPosition and all derivative subclasses. This polymorphic
    design means the portfolio works correctly without knowing the specific
    instrument type held in each position.

    Risk metrics are delegated to standalone functions in risk.py to keep
    analytics decoupled and reusable outside this class.

    Scenario analysis reprices every position under multiplicative spot and
    volatility shocks to show how portfolio value changes under stress.
    """

    def __init__(self):
        # List of position dicts — each has keys: instrument, quantity, label.
        self.positions = []
        # Cached return series — populated by load_equity_returns().
        # Avoids repeated API calls once the series has been downloaded.
        self._returns = None

    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------

    def add_position(self, instrument, quantity, label=None):
        """
        Description
        --------------------------
        Add an instrument position to the portfolio.

        Parameters
        --------------------------
        instrument: object
        - Any object exposing price() and delta() methods.
          Compatible with EquityPosition and all derivative subclasses.
        quantity: float
        - Number of units held. Positive = long, negative = short.
        label: str or None
        - Optional display name for the position in tables (default: None).
          If None, the ticker or class name is used automatically.
        """
        self.positions.append(
            {
                "instrument": instrument,
                "quantity": quantity,
                "label": label,
            }
        )

    # ------------------------------------------------------------------
    # Core Metrics
    # ------------------------------------------------------------------

    def value(self):
        """
        Description
        --------------------------
        Compute the total mark-to-market value of the portfolio.

        Sums quantity * price across all positions. Long positions
        contribute positively; short positions (negative quantity) reduce
        the total value.

        Formula: V = sum(q_i * price_i)

        Returns
        --------------------------
        float
        - Total portfolio value in dollars.
        """
        total_value = 0.0
        for position in self.positions:
            instrument = position["instrument"]
            quantity = position["quantity"]
            # Accumulate each position's dollar value contribution.
            total_value += quantity * instrument.price()
        return total_value

    def delta(self):
        """
        Description
        --------------------------
        Compute the total delta of the portfolio.

        Aggregates position-level deltas weighted by quantity.
        Delta explains why the portfolio moves — not just how much.

        Formula: delta_portfolio = sum(q_i * delta_i)

        A portfolio delta of 500 means the portfolio gains approximately
        $500 for a $1 increase in the underlying price.

        Returns
        --------------------------
        float
        - Total portfolio delta.
        """
        total_delta = 0.0
        for position in self.positions:
            instrument = position["instrument"]
            quantity = position["quantity"]
            # Accumulate each position's delta contribution.
            total_delta += quantity * instrument.delta()
        return total_delta

    # ------------------------------------------------------------------
    # Position Table
    # ------------------------------------------------------------------

    def position_table(self):
        """
        Description
        --------------------------
        Return a table showing each position's contribution to
        portfolio value and delta.

        Determines the display name for each position in order of
        preference: custom label > ticker attribute > class name.
        A TOTAL row is appended summarising the full portfolio.

        Returns
        --------------------------
        pd.DataFrame
        - Columns: Position, Quantity, Unit Value, Position Value,
          Unit Delta, Position Delta.
        """
        rows = []

        for position in self.positions:
            instrument = position["instrument"]
            quantity = position["quantity"]

            # Determine the display name for this position.
            if position["label"] is not None:
                # Use the custom label if one was provided on add_position().
                name = position["label"]
            elif hasattr(instrument, "ticker"):
                # Fall back to the ticker symbol for equity positions.
                name = instrument.get_ticker()
            else:
                # Fall back to the class name for unnamed derivative positions.
                name = instrument.__class__.__name__

            unit_value = instrument.price()
            unit_delta = instrument.delta()

            rows.append(
                {
                    "Position": name,
                    "Quantity": quantity,
                    "Unit Value": unit_value,
                    "Position Value": unit_value * quantity,
                    "Unit Delta": unit_delta,
                    "Position Delta": unit_delta * quantity,
                }
            )

        df = pd.DataFrame(rows)

        if len(df) > 0:
            # Append a TOTAL row summarising value and delta across all positions.
            total_row = pd.DataFrame(
                [
                    {
                        "Position": "TOTAL",
                        "Quantity": np.nan,
                        "Unit Value": np.nan,
                        "Position Value": df["Position Value"].sum(),
                        "Unit Delta": np.nan,
                        "Position Delta": df["Position Delta"].sum(),
                    }
                ]
            )
            df = pd.concat([df, total_row], ignore_index=True)

        return df

    # ------------------------------------------------------------------
    # Equity Return Data
    # ------------------------------------------------------------------

    def load_equity_returns(self, ticker, period="5y", cache_dir=None):
        """
        Description
        --------------------------
        Load historical log returns for a given equity ticker using yfinance.

        Log returns are used (rather than simple returns) because they are
        additive over time and consistent with the GBM assumption underlying
        Black-Scholes. Computed as: r_t = ln(P_t / P_{t-1}).

        Results are cached to a CSV so that subsequent runs work offline
        without repeated API calls.

        Parameters
        --------------------------
        ticker: str
        - Yahoo Finance ticker (e.g. 'CBA.AX').
        period: str
        - Data period to fetch (e.g. '1y', '5y').
        cache_dir: str or None
        - Directory to cache downloaded data. If None, no caching is done.

        Returns
        --------------------------
        pd.Series
        - Series of historical log returns.
        """
        if cache_dir is not None:
            cache_path = os.path.join(cache_dir, f"{ticker}_returns.csv")
            if os.path.exists(cache_path):
                # Load from cache — avoids repeated API calls on subsequent runs.
                print(f"[portfolio] Loading cached returns: {cache_path}")
                returns = pd.read_csv(
                    cache_path, index_col=0, parse_dates=True
                ).squeeze()
                self._returns = returns
                print(
                    f"[portfolio] {len(returns)} daily returns loaded "
                    f"({returns.index[0].date()} to {returns.index[-1].date()})"
                )
                return returns

        # Download from yfinance if no cache exists.
        print(f"[portfolio] Downloading {ticker} ({period})...")
        data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        prices = data["Close"].squeeze()
        # Compute log returns: ln(P_t / P_{t-1}) — consistent with GBM.
        returns = np.log(prices / prices.shift(1)).dropna()

        # Save to cache for reproducibility.
        if cache_dir is not None:
            os.makedirs(cache_dir, exist_ok=True)
            returns.to_csv(cache_path)
            print(f"[portfolio] Cached to {cache_path}")

        self._returns = returns
        print(
            f"[portfolio] {len(returns)} daily returns loaded "
            f"({returns.index[0].date()} to {returns.index[-1].date()})"
        )
        return returns

    def _get_returns(self):
        """
        Internal helper — returns the cached return series or raises a
        clear error if load_equity_returns() has not been called yet.
        """
        if self._returns is None:
            raise RuntimeError(
                "No return data loaded. Call load_equity_returns() first."
            )
        return self._returns

    # ------------------------------------------------------------------
    # Risk Metrics
    # ------------------------------------------------------------------

    def historical_var(self, alpha=0.95, horizon_days=1):
        """
        Description
        --------------------------
        Compute historical VaR using the empirical return distribution.

        Makes no distributional assumption — uses the observed return
        history directly. The (1-alpha) quantile of scaled returns gives
        the loss threshold.

        Parameters
        --------------------------
        alpha: float
        - Confidence level (default 0.95 = 95%).
        horizon_days: int
        - VaR horizon in days (default 1 = 1-day VaR).

        Returns
        --------------------------
        float
        - Historical VaR in dollars (always non-negative).
        """
        returns = self._get_returns()
        # Delegate to the standalone historical_var function in risk.py.
        return historical_var(
            returns,
            alpha=alpha,
            horizon_days=horizon_days,
            portfolio_value=self.value(),
        )

    def parametric_var(self, alpha=0.95, horizon_days=1):
        """
        Description
        --------------------------
        Compute parametric (Gaussian) VaR assuming normally distributed returns.

        Formula: VaR = z_alpha * sigma * portfolio_value

        Typically underestimates tail risk because real equity returns are
        leptokurtic (fat-tailed). Compare with historical_var() to quantify
        the impact of the normality assumption.

        Parameters
        --------------------------
        alpha: float
        - Confidence level (default 0.95).
        horizon_days: int
        - Holding period in days (default 1).

        Returns
        --------------------------
        float
        - Parametric VaR in dollars (always non-negative).
        """
        returns = self._get_returns()
        # Delegate to the standalone parametric_var function in risk.py.
        return parametric_var(
            returns,
            alpha=alpha,
            horizon_days=horizon_days,
            portfolio_value=self.value(),
        )

    def expected_shortfall(self, alpha=0.95, horizon_days=1):
        """
        Description
        --------------------------
        Compute Expected Shortfall (CVaR) — the average loss in the worst
        (1-alpha)% of cases.

        A coherent risk measure that provides a more complete picture of
        tail risk than VaR. Always >= historical VaR by construction since
        it is the mean of the tail beyond the VaR threshold.

        Parameters
        --------------------------
        alpha: float
        - Confidence level (default 0.95).
        horizon_days: int
        - Holding period in days (default 1).

        Returns
        --------------------------
        float
        - Expected shortfall in dollars (always non-negative).
        """
        returns = self._get_returns()
        # Delegate to the standalone expected_shortfall function in risk.py.
        return expected_shortfall(
            returns,
            alpha=alpha,
            horizon_days=horizon_days,
            portfolio_value=self.value(),
        )

    def max_drawdown(self):
        """
        Description
        --------------------------
        Compute the maximum peak-to-trough drawdown of the portfolio's
        cumulative returns.

        Builds a cumulative wealth index from the return series, then finds
        the largest percentage decline from any running peak. A path-dependent
        measure requiring no distributional assumption.

        Returns
        --------------------------
        float
        - Maximum drawdown as a positive decimal (e.g. 0.25 = 25% loss).
        """
        returns = self._get_returns()
        # Build a cumulative wealth index starting at $1.
        # (1 + r_t).cumprod() gives the growth of $1 invested over time.
        wealth = (1 + returns).cumprod()
        # Delegate to the standalone max_drawdown function in risk.py.
        return max_drawdown(wealth)

    def monte_carlo_var(
        self,
        spot,
        sigma,
        yield_curve,
        alpha=0.95,
        horizon_days=1,
        n_sims=10_000,
        seed=42,
        dividend_yield=0.0,
    ):
        """
        Description
        --------------------------
        Compute Monte Carlo VaR via full portfolio revaluation under GBM.

        Simulates spot price paths, revalues each position at the new spot,
        and computes the P&L distribution. Correctly captures non-linear
        payoff convexity (gamma effects) that delta-based VaR misses.

        The risk-free rate is retrieved from the yield curve at the VaR
        horizon maturity — consistent with the rest of the platform.

        Parameters
        --------------------------
        spot: float
        - Current underlying spot price.
        sigma: float
        - Annualised volatility.
        yield_curve: YieldCurve
        - Yield curve object exposing get_zero_rate(T). Used to retrieve
          the risk-free rate — no hardcoded flat rate.
        alpha: float
        - Confidence level (default 0.95).
        horizon_days: int
        - VaR horizon in days (default 1).
        n_sims: int
        - Number of Monte Carlo paths (must be even for antithetic variates).
        seed: int
        - Random seed for reproducibility (default 42).
        dividend_yield: float
        - Continuous dividend yield for GBM drift (default 0.0).

        Returns
        --------------------------
        dict
        - {'var': float, 'es': float, 'n_sims': int}
        """
        initial_value = self.value()

        # Retrieve the risk-free rate from the yield curve at the VaR horizon.
        # Converts horizon_days to years for the yield curve lookup.
        T = horizon_days / 252.0
        risk_free_rate = yield_curve.get_zero_rate(T)

        def revalue(new_spot):
            """Revalue the full portfolio at a shocked spot price."""
            total = 0.0
            for p in self.positions:
                # Deep copy to avoid mutating the original instrument.
                repriced = copy.deepcopy(p["instrument"])
                # Update the spot price on whichever attribute the instrument uses.
                if hasattr(repriced, "S0"):
                    repriced.S0 = new_spot  # Derivative instruments use S0.
                elif hasattr(repriced, "spot"):
                    repriced.spot = new_spot  # EquityPosition uses spot.
                total += repriced.price() * p["quantity"]
            return total

        # Delegate to the standalone monte_carlo_var function in risk.py.
        return monte_carlo_var(
            revaluation_fn=revalue,
            initial_value=initial_value,
            spot=spot,
            sigma=sigma,
            horizon_days=horizon_days,
            alpha=alpha,
            n_sims=n_sims,
            seed=seed,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )

    def risk_summary(self, alpha=0.95, horizon_days=1):
        """
        Description
        --------------------------
        Return a summary table of all portfolio risk metrics at a single
        confidence level and horizon.

        Parameters
        --------------------------
        alpha: float
        - Confidence level (default 0.95).
        horizon_days: int
        - VaR horizon in days (default 1).

        Returns
        --------------------------
        pd.DataFrame
        - Indexed by metric name with a single Value ($) column.
        """
        # Compute all metrics once and store — avoids repeated calls.
        h_var = self.historical_var(alpha=alpha, horizon_days=horizon_days)
        p_var = self.parametric_var(alpha=alpha, horizon_days=horizon_days)
        es = self.expected_shortfall(alpha=alpha, horizon_days=horizon_days)
        mdd = self.max_drawdown()

        rows = [
            {
                "Metric": f"Historical VaR ({alpha:.0%}, {horizon_days}d)",
                "Value ($)": round(h_var, 4),
            },
            {
                "Metric": f"Parametric VaR ({alpha:.0%}, {horizon_days}d)",
                "Value ($)": round(p_var, 4),
            },
            {
                "Metric": f"Expected Shortfall ({alpha:.0%}, {horizon_days}d)",
                "Value ($)": round(es, 4),
            },
            {"Metric": "Max Drawdown (underlying)", "Value ($)": f"{mdd:.2%}"},
            {"Metric": "Portfolio Value ($)", "Value ($)": round(self.value(), 4)},
            {"Metric": "Portfolio Delta", "Value ($)": round(self.delta(), 4)},
        ]
        return pd.DataFrame(rows).set_index("Metric")

    # ------------------------------------------------------------------
    # Distribution Statistics
    # ------------------------------------------------------------------

    def return_distribution_stats(self):
        """
        Description
        --------------------------
        Compute descriptive statistics of the underlying return distribution.

        Includes skewness and excess kurtosis to characterise asymmetry
        and leptokurtosis — the key features that cause parametric VaR
        to underestimate tail risk. Equity returns are typically fat-tailed
        (excess kurtosis > 0) and negatively skewed.

        Returns
        --------------------------
        dict
        - Mean, std, skewness, total kurtosis, excess kurtosis, leptokurtic flag.
        """
        returns = self._get_returns()
        return {
            "Mean (daily)": round(float(returns.mean()), 6),
            "Std Dev (daily)": round(float(returns.std()), 6),
            "Skewness": round(float(returns.skew()), 4),
            # Total (Pearson) kurtosis: pandas kurtosis() returns excess (vs normal=0),
            # so add 3 to recover the total kurtosis (normal distribution = 3).
            "Kurtosis": round(float(returns.kurtosis() + 3), 4),
            # Excess kurtosis: > 0 means fatter tails than normal (leptokurtic).
            "Excess Kurtosis": round(float(returns.kurtosis()), 4),
            "Is Leptokurtic": bool(returns.kurtosis() > 0),
        }

    # ------------------------------------------------------------------
    # Scenario Analysis
    # ------------------------------------------------------------------

    def scenario_analysis(self, scenarios):
        """
        Description
        --------------------------
        Reprice the portfolio under user-defined market shock scenarios.

        For each scenario, every option's S0 and sigma are shocked by the
        specified multiplicative factors and the portfolio is repriced from
        scratch. P&L is the change in total portfolio value vs base.

        Parameters
        --------------------------
        scenarios: list of dict
        - Each dict must contain:
            'name'       : str   — scenario label.
            'spot_shock' : float — multiplicative spot shock (e.g. 0.80 = -20%).
            'vol_shock'  : float — multiplicative vol shock  (e.g. 1.30 = +30%).

        Returns
        --------------------------
        pd.DataFrame
        - Indexed by scenario name.
          Columns: Spot Shock, Vol Shock, Shocked Value ($), P&L ($).
        """
        # Record the current portfolio value as the base for P&L calculation.
        base_value = self.value()
        rows = []

        for scenario in scenarios:
            name = scenario["name"]
            # Default shocks of 1.0 (no change) if not specified.
            spot_shock = scenario.get("spot_shock", 1.0)
            vol_shock = scenario.get("vol_shock", 1.0)

            shocked_value = 0.0
            for p in self.positions:
                # Deep copy to avoid mutating the original instrument state.
                repriced = copy.deepcopy(p["instrument"])

                # Apply spot shock to whichever attribute the instrument uses.
                if hasattr(repriced, "S0"):
                    repriced.S0 = p["instrument"].S0 * spot_shock
                elif hasattr(repriced, "spot"):
                    repriced.spot = p["instrument"].spot * spot_shock

                # Apply volatility shock if the instrument has a sigma attribute.
                # EquityPosition has no sigma so this only affects derivatives.
                if hasattr(repriced, "sigma"):
                    repriced.sigma = p["instrument"].sigma * vol_shock

                shocked_value += repriced.price() * p["quantity"]

            rows.append(
                {
                    "Scenario": name,
                    # Format shocks as percentage strings for readability.
                    "Spot Shock": f"{(spot_shock - 1) * 100:+.0f}%",
                    "Vol Shock": f"{(vol_shock  - 1) * 100:+.0f}%",
                    "Shocked Value ($)": round(shocked_value, 4),
                    "P&L ($)": round(shocked_value - base_value, 4),
                }
            )

        return pd.DataFrame(rows).set_index("Scenario")

    # ------------------------------------------------------------------
    # Visualisation
    # ------------------------------------------------------------------

    def plot_return_distribution(self, alpha=0.95, show=True):
        """
        Description
        --------------------------
        Plot the daily P&L distribution with historical VaR, parametric VaR,
        and expected shortfall overlay lines.

        The empirical histogram is shown alongside a fitted normal curve to
        visually demonstrate where the normality assumption breaks down —
        the key motivation for preferring historical over parametric VaR.

        Parameters
        --------------------------
        alpha: float
        - Confidence level for VaR and ES lines (default 0.95).
        show: bool
        - If True, calls plt.show() (default True).

        Returns
        --------------------------
        matplotlib.axes.Axes
        """
        from scipy.stats import norm as scipy_norm

        returns = self._get_returns()
        port_val = self.value()
        # Approximate daily P&L: return * portfolio_value.
        pnl = returns * port_val

        fig, ax = plt.subplots(figsize=(11, 5))

        # Empirical P&L histogram — density=True for comparability with normal curve.
        ax.hist(
            pnl,
            bins=60,
            density=True,
            color="steelblue",
            alpha=0.55,
            label="Historical P&L distribution",
        )

        # Fitted normal curve — shows where the normality assumption diverges.
        x_grid = np.linspace(pnl.min(), pnl.max(), 300)
        ax.plot(
            x_grid,
            scipy_norm.pdf(x_grid, pnl.mean(), pnl.std()),
            color="coral",
            linewidth=2,
            label="Fitted normal distribution",
        )

        # Historical VaR vertical line — empirical loss threshold.
        h_var = self.historical_var(alpha=alpha)
        ax.axvline(
            -h_var,
            color="red",
            linewidth=2,
            linestyle="--",
            label=f"Historical VaR ({alpha:.0%}) = ${h_var:,.2f}",
        )

        # Parametric VaR vertical line — normal distribution loss threshold.
        p_var = self.parametric_var(alpha=alpha)
        ax.axvline(
            -p_var,
            color="orange",
            linewidth=2,
            linestyle=":",
            label=f"Parametric VaR ({alpha:.0%}) = ${p_var:,.2f}",
        )

        # Expected Shortfall vertical line — average loss in the worst tail.
        es = self.expected_shortfall(alpha=alpha)
        ax.axvline(
            -es,
            color="darkred",
            linewidth=1.5,
            linestyle="-.",
            label=f"Expected Shortfall ({alpha:.0%}) = ${es:,.2f}",
        )

        ax.set_title(
            f"Portfolio Daily P&L Distribution\n"
            f"Historical vs Parametric VaR at {alpha:.0%} confidence",
            fontsize=13,
            fontweight="bold",
        )
        ax.set_xlabel("Daily P&L ($)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=9)
        ax.grid(True, linestyle="--", alpha=0.4)
        plt.tight_layout()

        if show:
            plt.show()

        return ax

    def plot_scenario_analysis(self, scenarios, show=True):
        """
        Description
        --------------------------
        Plot portfolio P&L under user-defined shock scenarios as a bar chart.

        Blue bars indicate gains, coral bars indicate losses. A horizontal
        line at zero separates gains from losses for clarity.

        Parameters
        --------------------------
        scenarios: list of dict
        - Same format as scenario_analysis().
        show: bool
        - If True, calls plt.show() (default True).

        Returns
        --------------------------
        matplotlib.axes.Axes
        """
        results = self.scenario_analysis(scenarios)

        fig, ax = plt.subplots(figsize=(10, 5))

        # Blue for gains, coral for losses.
        colors = ["steelblue" if v >= 0 else "coral" for v in results["P&L ($)"]]
        results["P&L ($)"].plot(kind="bar", ax=ax, color=colors, edgecolor="white")

        # Zero line separating gains from losses.
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(
            "Portfolio P&L Under Stress Scenarios", fontsize=13, fontweight="bold"
        )
        ax.set_xlabel("Scenario")
        ax.set_ylabel("P&L ($)")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(True, linestyle="--", alpha=0.4, axis="y")
        plt.tight_layout()

        if show:
            plt.show()

        return ax
