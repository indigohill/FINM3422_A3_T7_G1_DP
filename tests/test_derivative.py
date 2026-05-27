"""
Tests for the derivative pricing module.

Verifies:
- Black-Scholes pricing against textbook reference values
- Put-call parity (BS and binomial, with and without dividends)
- Finite-difference Greeks agreement with closed-form Greeks
- Binomial CRR convergence to Black-Scholes
- Binomial with dividend yield (Merton extension)
- American option early-exercise behaviour
- Monte Carlo cross-validation against Black-Scholes
- Input validation
- Historical volatility recovery

Note: Binomial gamma is NOT tested because finite-difference gamma on
binomial trees is dominated by tree discretisation noise rather than
true curvature. Use closed-form BS gamma for risk metrics.
"""

import sys
import os
import numpy as np
import pytest

# Add src to path so we can import the derivatives module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from derivative_test import (
    EuropeanCall,
    EuropeanPut,
    BinomialEuropeanCall,
    BinomialEuropeanPut,
    AmericanCall,
    AmericanPut,
    Derivative,
)


class FlatCurve:
    """Stub yield curve returning a constant zero rate."""

    def __init__(self, rate=0.045):
        self.rate = rate

    def get_zero_rate(self, T):
        return self.rate


# Standard test parameters
S0 = 100.0
K = 100.0
T = 1.0
SIGMA = 0.20
R = 0.045

BS_CALL_REF = 10.186111
BS_PUT_REF = 5.785859


# ----------------------------------------------------------------------
# Black-Scholes pricing
# ----------------------------------------------------------------------

def test_bs_call_price():
    """BS call should match textbook reference."""
    call = EuropeanCall(S0, K, T, SIGMA, FlatCurve())
    assert abs(call.price() - BS_CALL_REF) < 1e-6


def test_bs_put_price():
    """BS put should match textbook reference."""
    put = EuropeanPut(S0, K, T, SIGMA, FlatCurve())
    assert abs(put.price() - BS_PUT_REF) < 1e-6


def test_bs_put_call_parity():
    """Put-call parity: C - P = S0 - K*exp(-rT)."""
    call = EuropeanCall(S0, K, T, SIGMA, FlatCurve())
    put = EuropeanPut(S0, K, T, SIGMA, FlatCurve())
    lhs = call.price() - put.price()
    rhs = S0 - K * np.exp(-R * T)
    assert abs(lhs - rhs) < 1e-10


def test_bs_put_call_parity_with_dividends():
    """Generalised parity: C - P = S0*exp(-qT) - K*exp(-rT)."""
    q = 0.03
    call = EuropeanCall(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q)
    put = EuropeanPut(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q)
    lhs = call.price() - put.price()
    rhs = S0 * np.exp(-q * T) - K * np.exp(-R * T)
    assert abs(lhs - rhs) < 1e-10


# ----------------------------------------------------------------------
# Greeks: FD vs closed-form
# ----------------------------------------------------------------------

@pytest.mark.parametrize("greek_name", ["delta", "gamma", "vega", "theta", "rho"])
def test_call_fd_vs_cf_greeks(greek_name):
    """FD and closed-form Greeks should agree for the call."""
    call = EuropeanCall(S0, K, T, SIGMA, FlatCurve())
    fd = getattr(call, f"{greek_name}_fd")()
    cf = getattr(call, greek_name)()
    assert abs(fd - cf) < 1e-4


@pytest.mark.parametrize("greek_name", ["delta", "gamma", "vega", "theta", "rho"])
def test_put_fd_vs_cf_greeks(greek_name):
    """FD and closed-form Greeks should agree for the put."""
    put = EuropeanPut(S0, K, T, SIGMA, FlatCurve())
    fd = getattr(put, f"{greek_name}_fd")()
    cf = getattr(put, greek_name)()
    assert abs(fd - cf) < 1e-4


# ----------------------------------------------------------------------
# Binomial CRR (European) convergence
# ----------------------------------------------------------------------

@pytest.mark.parametrize("N,tol", [
    (100, 0.02),
    (500, 0.005),
    (1000, 0.003),
    (5000, 0.001),
])
def test_binomial_call_converges_to_bs(N, tol):
    """Binomial call converges to BS as N grows."""
    bin_call = BinomialEuropeanCall(S0, K, T, SIGMA, FlatCurve(), N=N)
    assert abs(bin_call.price() - BS_CALL_REF) < tol


@pytest.mark.parametrize("N,tol", [
    (100, 0.02),
    (500, 0.005),
    (1000, 0.003),
    (5000, 0.001),
])
def test_binomial_put_converges_to_bs(N, tol):
    """Binomial put converges to BS as N grows."""
    bin_put = BinomialEuropeanPut(S0, K, T, SIGMA, FlatCurve(), N=N)
    assert abs(bin_put.price() - BS_PUT_REF) < tol


def test_binomial_put_call_parity():
    """Put-call parity holds exactly in the binomial tree."""
    bc = BinomialEuropeanCall(S0, K, T, SIGMA, FlatCurve()).price()
    bp = BinomialEuropeanPut(S0, K, T, SIGMA, FlatCurve()).price()
    lhs = bc - bp
    rhs = S0 - K * np.exp(-R * T)
    assert abs(lhs - rhs) < 1e-10


def test_binomial_with_dividends_converges_to_bs():
    """Binomial pricer with q=0.03 converges to BS-with-dividends."""
    q = 0.03
    bs_call = EuropeanCall(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q).price()
    bs_put = EuropeanPut(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q).price()
    bin_call = BinomialEuropeanCall(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q, N=1000).price()
    bin_put = BinomialEuropeanPut(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q, N=1000).price()
    assert abs(bin_call - bs_call) < 0.005
    assert abs(bin_put - bs_put) < 0.005


def test_binomial_delta_via_inherited_fd():
    """Binomial FD delta inherits correctly via type(self)."""
    bs_call = EuropeanCall(S0, K, T, SIGMA, FlatCurve())
    bin_call = BinomialEuropeanCall(S0, K, T, SIGMA, FlatCurve())
    assert abs(bin_call.delta_fd() - bs_call.delta()) < 1e-3


# ----------------------------------------------------------------------
# American option behaviour
# ----------------------------------------------------------------------

def test_american_call_equals_european_when_no_dividends():
    """
    Merton's theorem: American call on a non-dividend stock should never
    be exercised early, so its price equals the European call.
    """
    am_call = AmericanCall(S0, K, T, SIGMA, FlatCurve(), N=1000).price()
    eu_call = EuropeanCall(S0, K, T, SIGMA, FlatCurve()).price()
    assert abs(am_call - eu_call) < 0.005


def test_american_call_exceeds_european_with_dividends():
    """
    American call on a dividend-paying stock can exceed European because
    early exercise just before a dividend can be optimal.
    """
    q = 0.05
    am_call = AmericanCall(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q, N=1000).price()
    eu_call = EuropeanCall(S0, K, T, SIGMA, FlatCurve(), dividend_yield=q).price()
    assert am_call > eu_call


def test_american_put_at_least_european():
    """American put always >= European put (early-exercise premium)."""
    am_put = AmericanPut(S0, K, T, SIGMA, FlatCurve(), N=1000).price()
    eu_put = EuropeanPut(S0, K, T, SIGMA, FlatCurve()).price()
    assert am_put >= eu_put


def test_american_put_deep_itm_premium_is_substantial():
    """Deep ITM American put has noticeable early-exercise premium."""
    am_put = AmericanPut(50, 100, 1.0, 0.20, FlatCurve(), N=1000).price()
    eu_put = EuropeanPut(50, 100, 1.0, 0.20, FlatCurve()).price()
    # At least $1 of early-exercise premium
    assert am_put - eu_put > 1.0


# ----------------------------------------------------------------------
# Monte Carlo cross-validation
# ----------------------------------------------------------------------

def test_mc_call_vs_bs():
    """MC call price within tolerance of BS at high path count."""
    call = EuropeanCall(S0, K, T, SIGMA, FlatCurve())
    mc_price = call.price_mc(n_sims=200_000, seed=42)
    assert abs(mc_price - BS_CALL_REF) < 0.05


def test_mc_put_vs_bs():
    """MC put price within tolerance of BS at high path count."""
    put = EuropeanPut(S0, K, T, SIGMA, FlatCurve())
    mc_price = put.price_mc(n_sims=200_000, seed=42)
    assert abs(mc_price - BS_PUT_REF) < 0.05


# ----------------------------------------------------------------------
# Input validation
# ----------------------------------------------------------------------

@pytest.mark.parametrize("S0_val,K_val,T_val,sigma_val", [
    (0, 100, 1.0, 0.20),
    (-1, 100, 1.0, 0.20),
    (100, 0, 1.0, 0.20),
    (100, 100, 0, 0.20),
    (100, 100, -1, 0.20),
    (100, 100, 1.0, 0),
    (100, 100, 1.0, -0.1),
])
def test_invalid_inputs_raise(S0_val, K_val, T_val, sigma_val):
    """Invalid inputs should raise ValueError on construction."""
    with pytest.raises(ValueError):
        EuropeanCall(S0_val, K_val, T_val, sigma_val, FlatCurve())


# ----------------------------------------------------------------------
# Historical volatility helper
# ----------------------------------------------------------------------

def test_historical_volatility_recovers_known_sigma():
    """historical_volatility() recovers a known synthetic vol within ~10%."""
    np.random.seed(42)
    true_daily_vol = 0.01
    n_days = 500
    prices = [100.0]
    for _ in range(n_days):
        prices.append(prices[-1] * np.exp(np.random.normal(0, true_daily_vol)))
    sigma_est = Derivative.historical_volatility(prices)
    true_annual = true_daily_vol * np.sqrt(252)
    assert abs(sigma_est - true_annual) / true_annual < 0.10