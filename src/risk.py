"""
risk.py — Portfolio risk metrics for the FINM3422 A3 platform.

Provides standalone pure functions for computing risk metrics on return
series and portfolios. Functions are decoupled from the Portfolio class
to keep risk analytics reusable across different valuation contexts.

Reference: Reader §6.5 (VaR), §6.5.4 (Limitations), §6.6 (Scenarios);
Hull Ch. 22 (VaR); Acerbi & Tasche (2002) on Expected Shortfall coherence.
"""

import numpy as np
import pandas as pd
from scipy.stats import norm


def _validate_alpha(alpha):
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1 (exclusive).")


def _validate_horizon(horizon_days):
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive.")


def historical_var(returns, alpha=0.95, horizon_days=1, portfolio_value=1.0):
    """
    Compute historical Value-at-Risk from a return series.

    VaR_alpha = -quantile(returns, 1-alpha) * portfolio_value, scaled by
    sqrt(horizon_days) per the i.i.d. square-root-of-time rule.

    Parameters
    ----------
    returns : array-like
        Historical (typically daily) return series. NaNs are dropped.
    alpha : float
        Confidence level. 0.95 means "95% confident loss won't exceed VaR."
    horizon_days : int
        VaR horizon in days. Scaled via sqrt-of-time rule.
    portfolio_value : float
        Current portfolio value in dollars.

    Returns
    -------
    float
        VaR in dollars. Floor at zero (a non-positive raw value means the
        historical series lacks downside at this confidence level).

    Notes
    -----
    Sqrt-of-time scaling assumes i.i.d. returns. This can underestimate
    multi-day VaR when returns exhibit volatility clustering or
    autocorrelation. See Reader §6.5.4.
    """
    _validate_alpha(alpha)
    _validate_horizon(horizon_days)

    returns = pd.Series(returns).dropna()
    if len(returns) == 0:
        raise ValueError("Return series is empty.")

    scaled = returns * np.sqrt(horizon_days)
    q = scaled.quantile(1 - alpha)
    var = -q * portfolio_value
    return max(float(var), 0.0)


def parametric_var(returns, alpha=0.95, horizon_days=1, portfolio_value=1.0):
    """
    Compute parametric (Gaussian) Value-at-Risk from a return series.

    VaR_alpha = z_alpha * sigma * portfolio_value, with sigma scaled
    by sqrt(horizon_days). Assumes returns are normally distributed.

    Parameters
    ----------
    returns : array-like
        Historical return series. NaNs are dropped.
    alpha : float
        Confidence level.
    horizon_days : int
        VaR horizon in days.
    portfolio_value : float
        Current portfolio value in dollars.

    Returns
    -------
    float
        Parametric VaR in dollars.

    Notes
    -----
    The normality assumption typically underestimates tail risk for
    equity returns, which exhibit fat tails. See Reader §6.5.4.
    """
    _validate_alpha(alpha)
    _validate_horizon(horizon_days)

    returns = pd.Series(returns).dropna()
    if len(returns) == 0:
        raise ValueError("Return series is empty.")

    sigma = returns.std(ddof=1)
    sigma_scaled = sigma * np.sqrt(horizon_days)
    z = norm.ppf(alpha)
    var = z * sigma_scaled * portfolio_value
    return float(var)


def expected_shortfall(returns, alpha=0.95, horizon_days=1, portfolio_value=1.0):
    """
    Compute Expected Shortfall (a.k.a. Conditional VaR, ES_alpha).

    ES = expected loss given that loss exceeds VaR_alpha. Computed as
    the mean of returns in the worst (1-alpha) tail, multiplied by
    portfolio_value and scaled by sqrt(horizon_days).

    Parameters
    ----------
    returns : array-like
        Historical return series. NaNs are dropped.
    alpha : float
        Confidence level.
    horizon_days : int
        VaR horizon in days.
    portfolio_value : float
        Current portfolio value in dollars.

    Returns
    -------
    float
        Expected shortfall in dollars. Always >= historical VaR by
        construction (mean of tail >= threshold of tail).

    Notes
    -----
    ES is a "coherent" risk measure (Artzner et al. 1999) — it satisfies
    subadditivity, which VaR does not. This makes ES preferable for
    portfolio risk aggregation. See Reader §6.5.4 on VaR's non-coherence.
    """
    _validate_alpha(alpha)
    _validate_horizon(horizon_days)

    returns = pd.Series(returns).dropna()
    if len(returns) == 0:
        raise ValueError("Return series is empty.")

    scaled = returns * np.sqrt(horizon_days)
    threshold = scaled.quantile(1 - alpha)
    tail = scaled[scaled <= threshold]
    if len(tail) == 0:
        return 0.0
    es = -tail.mean() * portfolio_value
    return max(float(es), 0.0)


def max_drawdown(value_series):
    """
    Compute maximum drawdown of a portfolio or asset value series.

    MDD = max over time of (peak - trough) / peak, where peak is the
    running maximum up to that time.

    Parameters
    ----------
    value_series : array-like
        Time series of portfolio or asset values.

    Returns
    -------
    float
        Maximum drawdown as a positive decimal (e.g., 0.25 = 25% loss).
        Returns 0.0 if the series is monotonically non-decreasing.

    Notes
    -----
    MDD is a path-dependent risk measure that captures the worst
    realised loss from a peak. Unlike VaR, it requires no distributional
    assumption and reflects historical drawdown experience directly.
    """
    values = pd.Series(value_series, dtype=float)
    if len(values) == 0:
        raise ValueError("Value series is empty.")
    running_max = values.cummax()
    drawdown = (running_max - values) / running_max
    return float(drawdown.max())


def monte_carlo_var(
    revaluation_fn,
    initial_value,
    spot,
    sigma,
    horizon_days=1,
    alpha=0.95,
    n_sims=10_000,
    seed=42,
    risk_free_rate=0.045,
    dividend_yield=0.0,
):
    """
    Compute Monte Carlo Value-at-Risk via full portfolio revaluation.

    Simulates spot paths under risk-neutral GBM, revalues the portfolio
    at each terminal spot, computes P&L distribution, and returns the
    (1-alpha) quantile of losses.

    Parameters
    ----------
    revaluation_fn : callable
        Function `revaluation_fn(new_spot) -> portfolio_value` that
        computes total portfolio value at a given spot price. The
        caller is responsible for closing over portfolio state.
    initial_value : float
        Current portfolio value at current spot.
    spot : float
        Current spot price of the underlying.
    sigma : float
        Annualised volatility of the underlying.
    horizon_days : int
        VaR horizon in days. Converted to years internally (T = days/252).
    alpha : float
        Confidence level.
    n_sims : int
        Number of Monte Carlo paths. Must be even (antithetic variates).
    seed : int
        Random seed for reproducibility.
    risk_free_rate : float
        Drift rate for spot simulation (typically risk-free rate).
    dividend_yield : float
        Continuous dividend yield. Drift becomes (r - q).

    Returns
    -------
    dict
        {
            'var': MC VaR in dollars (positive),
            'es':  MC Expected Shortfall in dollars (positive, >= VaR),
            'n_sims': number of paths used,
        }

    Notes
    -----
    Antithetic variates: for every random draw Z, the path -Z is also
    used. Halves variance for free under symmetric models.

    Full revaluation (vs delta linearisation) captures non-linear
    payoff convexity correctly, which matters for portfolios containing
    options. Delta-based VaR underestimates risk for long-gamma
    positions and overestimates for short-gamma positions.
    """
    _validate_alpha(alpha)
    _validate_horizon(horizon_days)
    if n_sims < 2 or n_sims % 2 != 0:
        raise ValueError("n_sims must be a positive even integer.")

    rng = np.random.default_rng(seed)
    half = n_sims // 2
    Z = rng.standard_normal(half)
    Z = np.concatenate([Z, -Z])

    T = horizon_days / 252.0
    drift = (risk_free_rate - dividend_yield - 0.5 * sigma ** 2) * T
    diffusion = sigma * np.sqrt(T) * Z
    S_terminal = spot * np.exp(drift + diffusion)

    # Revalue portfolio at each terminal spot
    pnl = np.array([revaluation_fn(s) - initial_value for s in S_terminal])

    losses = -pnl
    var = float(np.quantile(losses, alpha))
    tail = losses[losses >= var]
    es = float(tail.mean()) if len(tail) > 0 else var

    return {
        "var": max(var, 0.0),
        "es": max(es, 0.0),
        "n_sims": n_sims,
    }