"""
Tests for the risk metrics module.

Verifies:
- Historical VaR on a known distribution
- Parametric VaR matches z-score * sigma on Gaussian data
- Historical and parametric VaR agree on Gaussian data
- Expected Shortfall >= VaR (coherence property)
- Sqrt-of-time scaling (T-day VaR ~= sqrt(T) * 1-day VaR)
- Max drawdown on monotonic and known peak-trough series
- Monte Carlo VaR on pure equity matches parametric VaR
- MC VaR seed reproducibility
- Input validation (alpha range, horizon, n_sims)
"""

import sys
import os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from risk import (
    historical_var,
    parametric_var,
    expected_shortfall,
    max_drawdown,
    monte_carlo_var,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def gaussian_returns():
    """Synthetic Gaussian return series: 5000 obs, daily vol 1%."""
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(0, 0.01, 5000))


# ----------------------------------------------------------------------
# Historical VaR
# ----------------------------------------------------------------------

def test_historical_var_positive(gaussian_returns):
    """Historical VaR on symmetric returns should be positive."""
    var = historical_var(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    assert var > 0


def test_historical_var_increases_with_confidence(gaussian_returns):
    """99% VaR should be larger than 95% VaR."""
    var_95 = historical_var(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    var_99 = historical_var(gaussian_returns, alpha=0.99, portfolio_value=1_000_000)
    assert var_99 > var_95


def test_historical_var_sqrt_time_scaling(gaussian_returns):
    """10-day VaR should equal 1-day VaR * sqrt(10) (linearity of quantile)."""
    var_1 = historical_var(gaussian_returns, alpha=0.95, horizon_days=1, portfolio_value=1_000_000)
    var_10 = historical_var(gaussian_returns, alpha=0.95, horizon_days=10, portfolio_value=1_000_000)
    assert abs(var_10 - var_1 * np.sqrt(10)) < 1.0  # to within $1


def test_historical_var_scales_with_portfolio_value(gaussian_returns):
    """VaR should scale linearly with portfolio value."""
    var_1m = historical_var(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    var_2m = historical_var(gaussian_returns, alpha=0.95, portfolio_value=2_000_000)
    assert abs(var_2m - 2 * var_1m) < 1.0


# ----------------------------------------------------------------------
# Parametric VaR
# ----------------------------------------------------------------------

def test_parametric_var_matches_formula(gaussian_returns):
    """Parametric VaR should equal z * sigma * V exactly on the data."""
    from scipy.stats import norm
    sigma = gaussian_returns.std(ddof=1)
    z = norm.ppf(0.95)
    expected = z * sigma * 1_000_000
    actual = parametric_var(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    assert abs(actual - expected) < 1e-6


def test_parametric_var_close_to_historical_on_gaussian(gaussian_returns):
    """For genuinely Gaussian data, historical and parametric VaR should be close."""
    hist = historical_var(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    param = parametric_var(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    # Within 10% relative difference
    assert abs(hist - param) / param < 0.10


# ----------------------------------------------------------------------
# Expected Shortfall
# ----------------------------------------------------------------------

def test_expected_shortfall_geq_var(gaussian_returns):
    """ES should always be >= historical VaR (coherence property)."""
    var = historical_var(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    es = expected_shortfall(gaussian_returns, alpha=0.95, portfolio_value=1_000_000)
    assert es >= var


def test_expected_shortfall_scales_with_horizon(gaussian_returns):
    """10-day ES should equal 1-day ES * sqrt(10)."""
    es_1 = expected_shortfall(gaussian_returns, alpha=0.95, horizon_days=1, portfolio_value=1_000_000)
    es_10 = expected_shortfall(gaussian_returns, alpha=0.95, horizon_days=10, portfolio_value=1_000_000)
    assert abs(es_10 - es_1 * np.sqrt(10)) < 1.0


# ----------------------------------------------------------------------
# Max Drawdown
# ----------------------------------------------------------------------

def test_mdd_monotonic_increasing_is_zero():
    """A monotonically increasing series has zero drawdown."""
    assert max_drawdown([100, 110, 120, 130]) == 0.0


def test_mdd_monotonic_decreasing():
    """100 -> 70 should give MDD = 30%."""
    mdd = max_drawdown([100, 90, 80, 70])
    assert abs(mdd - 0.30) < 1e-10


def test_mdd_specific_peak_trough():
    """100 -> 120 -> 80 -> 90 -> 110 should give MDD = (120-80)/120 = 1/3."""
    mdd = max_drawdown([100, 120, 80, 90, 110])
    assert abs(mdd - 1/3) < 1e-10


def test_mdd_empty_series_raises():
    """Empty series should raise ValueError."""
    with pytest.raises(ValueError):
        max_drawdown([])


# ----------------------------------------------------------------------
# Monte Carlo VaR
# ----------------------------------------------------------------------

def test_mc_var_pure_equity_matches_parametric():
    """
    MC VaR on a pure equity position should match parametric VaR
    (lognormal approximates normal for small T) within ~5%.
    """
    spot = 100
    n_shares = 10_000
    initial_value = n_shares * spot

    mc = monte_carlo_var(
        revaluation_fn=lambda S: n_shares * S,
        initial_value=initial_value,
        spot=spot,
        sigma=0.20,
        horizon_days=10,
        alpha=0.95,
        n_sims=50_000,
        seed=42,
    )

    # Expected parametric VaR for $1M of stock, 20% vol, 10-day, 95%
    from scipy.stats import norm
    T = 10 / 252
    expected = norm.ppf(0.95) * 0.20 * np.sqrt(T) * initial_value

    assert abs(mc["var"] - expected) / expected < 0.05


def test_mc_var_seed_reproducibility():
    """Same seed should give identical results."""
    args = dict(
        revaluation_fn=lambda S: 10_000 * S,
        initial_value=1_000_000,
        spot=100,
        sigma=0.20,
        horizon_days=10,
        alpha=0.95,
        n_sims=10_000,
        seed=42,
    )
    r1 = monte_carlo_var(**args)
    r2 = monte_carlo_var(**args)
    assert r1["var"] == r2["var"]
    assert r1["es"] == r2["es"]


def test_mc_var_es_geq_var():
    """MC ES should always be >= MC VaR."""
    mc = monte_carlo_var(
        revaluation_fn=lambda S: 10_000 * S,
        initial_value=1_000_000,
        spot=100,
        sigma=0.20,
        horizon_days=10,
        alpha=0.95,
        n_sims=10_000,
        seed=42,
    )
    assert mc["es"] >= mc["var"]


# ----------------------------------------------------------------------
# Input validation
# ----------------------------------------------------------------------

@pytest.mark.parametrize("alpha", [-0.1, 0, 1.0, 1.5])
def test_invalid_alpha_raises(alpha, gaussian_returns):
    """alpha outside (0, 1) should raise ValueError."""
    with pytest.raises(ValueError):
        historical_var(gaussian_returns, alpha=alpha)


@pytest.mark.parametrize("horizon", [0, -1, -10])
def test_invalid_horizon_raises(horizon, gaussian_returns):
    """Non-positive horizon should raise ValueError."""
    with pytest.raises(ValueError):
        historical_var(gaussian_returns, horizon_days=horizon)


def test_mc_var_odd_n_sims_raises():
    """Odd n_sims should raise (antithetic variates need even)."""
    with pytest.raises(ValueError):
        monte_carlo_var(
            revaluation_fn=lambda S: S,
            initial_value=100,
            spot=100,
            sigma=0.20,
            n_sims=999,  # odd
        )


def test_empty_returns_raises():
    """Empty return series should raise."""
    with pytest.raises(ValueError):
        historical_var(pd.Series([]), alpha=0.95)