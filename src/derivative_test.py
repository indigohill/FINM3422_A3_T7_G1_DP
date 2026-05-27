"""
derivative.py: Option Pricing Module
-----------------------------------
Purpose: Provides the option pricing engine including the following classes (and sub-classes):
- Derivative: Shared inputs for all derivatives (Greeks, Volatility).
- _BinomialBase: Shared inputs for all binomial pricers.
- EuropeanCall: Black-Scholes closed-form call price with dividends.
- EuropeanPut: Black-Scholes closed-form put pricer with dividends.
- BinomialEuropeanCall: CRR tree European call (convergence cross-check).
- BinomialEuropeanPut: CRR tree European put (convergence cross-check).
- AmericanCall: CRR tree call with early exercise.
- AmericanPut: CRR tree put with early exercise.

All European pricers support a dividend yield (continuous) using the Merton (1973) extension.
Monte Carlo pricing (incorporating antithetic variates) is available on EuropeanCall and EuropeanPut.
"""

import numpy as np
from scipy.stats import norm

# --------------------------------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------------------------------


def _d1_d2(S0, K, T, sigma, r):
    """
    Description
    ---------------------------
    Compute d1 and d2 for the Black-Scholes and Merton (1973) formula.

    Note: If called with dividend yield, pass (r - q) as the r argument.
    According to Merton (1973), the drift of the stock under the risk-neutral
    measure becomes (r - q) rather than r when dividends are paid.

    Parameters
    ----------------------------
    S0: float
    - Current spot price of the underlying asset.
    K: float
    - Strike price of the option.
    T: float
    - Time to maturity (in years).
    sigma: float
    - Annualised volatility of the underlying asset (as a decimal).
    r: float
    - Risk-free rate (r - q when dividends are present).

    Returns
    ----------------------------
    d1, d2: float, float
    """
    d1 = (np.log(S0 / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def _crr_setup(S0, K, T, sigma, r, q, N, payoff_fn):
    """
    Description
    --------------------------
    Shared setup for both CRR binomial tree pricers. Computes the tree
    parameters and terminal payoffs that are identical for both European
    and American trees. Each tree function then only implements its rollback.

    Parameters
    --------------------------
    S0, K, T, sigma: float
    - Standard option parameters.
    r: float
    - Risk-free rate (continuously compounded).
    q: float
    - Continuous dividend yield.
    N: int
    - Number of time steps.
    payoff_fn: callable
    - payoff_fn(S, K) returns terminal payoffs.

    Returns
    -------------------------
    u, d, disc, p, V
    """
    dt = T / N  # Length of each time step in years.
    u = np.exp(sigma * np.sqrt(dt))  # Up factor.
    d = 1.0 / u  # Down factor.
    disc = np.exp(-r * dt)  # One-step discount factor.
    p = (np.exp((r - q) * dt) - d) / (u - d)  # Risk-neutral up probability.

    # Build all N+1 terminal stock prices and apply the payoff function.
    j = np.arange(N + 1)
    V = payoff_fn(S0 * (u**j) * (d ** (N - j)), K)

    return u, d, disc, p, V


# --------------------------------------------------------------------------------------------------
# ShiftedCurve
# --------------------------------------------------------------------------------------------------


class ShiftedCurve:
    """
    A lightweight wrapper that applies a flat parallel shift to YieldCurve.

    Used by FD rho_fd() to bump all rates up or down by a small amount (h)
    without mutating the original YieldCurve object. In effect, it isolates the
    interest rate sensitivity of the option price.
    """

    def __init__(self, base_curve, shift):
        self._base = base_curve
        # Shift amount in decimal (e.g. 0.0001 = 1 basis point).
        self._shift = shift

    def get_zero_rate(self, T):
        # Mimics the YieldCurve interface so it is a drop-in replacement.
        return self._base.get_zero_rate(T) + self._shift


# --------------------------------------------------------------------------------------------------
# Derivative Class
# --------------------------------------------------------------------------------------------------


class Derivative:
    """
    Description
    ------------------------------------------------------
    An abstract base class for all derivative instruments that stores the common
    parameters shared by all derivative contracts. It exposes a price() interface
    that every concrete sub-class must implement.

    This class should not be instantiated directly; use a sub-class such as
    EuropeanCall or EuropeanPut instead.

    Parameters
    ------------------------------------------------------
    S0 : float
    - Current spot price of the underlying asset.
    K : float
    - Strike price of the option.
    T : float
    - Time to maturity (in years).
    sigma : float
    - Annualised volatility of the underlying asset (as decimal).
    yield_curve : object
    - Yield curve object that exposes a get_zero_rate(T) method returning
      the continuously-compounded risk-free zero rate for maturity T.
    dividend_yield : float, (optional)
    - Continuous dividend yield of the underlying asset (default is 0.0).
    """

    def __init__(self, S0, K, T, sigma, yield_curve, dividend_yield=0.0):
        self.S0 = S0
        self.K = K
        self.T = T
        self.sigma = sigma
        self.yield_curve = yield_curve
        self.dividend_yield = float(dividend_yield)

        # Input validation — loop raises a clear error immediately rather than
        # producing a silently wrong price later.
        for name, val in [
            ("S0", self.S0),
            ("K", self.K),
            ("T", self.T),
            ("sigma", self.sigma),
        ]:
            if val <= 0:
                raise ValueError(f"{name} must be positive.")

    def price(self):
        """Sub-classes must implement their own pricing logic. Avoids
        Derivative from being used directly."""
        raise NotImplementedError("price() must be implemented in a sub-class.")

    # --------------------------------------------------------------------------------------------------
    # Shared Parameter Helpers
    # --------------------------------------------------------------------------------------------------

    def _rq(self):
        """
        Return the risk-free rate and dividend yield in one call. Used by
        _params() and the binomial/MC pricers which don't need d1, d2.
        """
        return self.yield_curve.get_zero_rate(self.T), self.dividend_yield

    def _params(self):
        """
        Return r, q, d1, d2 in one call.

        Every closed-form Greek needs these four values. Centralising them
        here removes repeated lines from every method.
        """
        r, q = self._rq()
        # Pass r-q as the drift — Merton adjustment for continuous dividends.
        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r - q)
        return r, q, d1, d2

    def _bump(self, **kwargs):
        """
        Return the option price with one parameter replaced.

        Used by all FD Greeks to avoid repeating cls = type(self) and the
        full constructor call in every method. Keyword arguments override
        the current parameter values (e.g. _bump(S0=self.S0+h)).
        """
        # Build a dictionary of current parameters.
        params = dict(
            S0=self.S0,
            K=self.K,
            T=self.T,
            sigma=self.sigma,
            yield_curve=self.yield_curve,
            dividend_yield=self.dividend_yield,
        )
        # Override with any bumped values passed as keyword arguments.
        params.update(kwargs)
        # Re-instantiate using type(self) so the correct subclass pricer is used.
        return type(self)(**params).price()

    # --------------------------------------------------------------------------------------------------
    # Shared Closed-Form Greeks
    # --------------------------------------------------------------------------------------------------
    # Gamma and vega are identical for calls and puts — defined once here.

    def gamma(self):
        """
        Closed-form gamma — identical for calls and puts.
        gamma = e^(-qT) * N'(d1) / (S * σ * sqrt(T)), always positive.
        Measures the rate of change of delta with respect to spot.
        """
        r, q, d1, _ = self._params()
        return float(
            np.exp(-q * self.T)
            * norm.pdf(d1)
            / (self.S0 * self.sigma * np.sqrt(self.T))
        )

    def vega(self):
        """
        Closed-form vega — identical for calls and puts.
        vega = S * e^(-qT) * N'(d1) * sqrt(T) / 100, always positive.
        Measures sensitivity to a 1% change in volatility.
        """
        r, q, d1, _ = self._params()
        # Divide by 100 to express per 1% volatility move.
        return float(
            self.S0 * np.exp(-q * self.T) * norm.pdf(d1) * np.sqrt(self.T) / 100
        )

    def all_greeks(self):
        """
        Return all closed-form Greeks as a dictionary.
        gamma and vega resolved here; delta, theta, rho come from the subclass.
        """
        return {
            "delta": self.delta(),
            "gamma": self.gamma(),
            "vega": self.vega(),
            "theta": self.theta(),
            "rho": self.rho(),
        }

    # --------------------------------------------------------------------------------------------------
    # Shared Monte Carlo
    # --------------------------------------------------------------------------------------------------

    def _mc_price(self, payoff_fn, n_sims=100_000, seed=42):
        """
        Description
        --------------------------
        Shared Monte Carlo simulation engine using GBM with antithetic variates.

        For every random draw Z, its mirror -Z is also simulated (antithetic
        variates), reducing variance and improving accuracy with the same paths.

        Parameters
        --------------------------
        payoff_fn: callable
        - payoff_fn(ST) applied at each terminal stock price.
          Call: lambda ST: np.maximum(ST - K, 0)
          Put:  lambda ST: np.maximum(K - ST, 0)
        n_sims: int
        - Number of simulated paths (default 100,000).
        seed: int
        - Random seed for reproducibility (default 42).

        Returns
        --------------------------
        float
        - Monte Carlo estimate of the option price.
        """
        np.random.seed(seed)
        r, q = self._rq()

        # Generate half the draws then concatenate with their negatives (antithetic).
        Z = np.random.standard_normal(n_sims // 2)
        Z = np.concatenate([Z, -Z])

        # Simulate final stock prices under risk-neutral GBM.
        # Drift: (r - q - 0.5*σ²)*T is the Ito correction keeping simulation risk-neutral.
        ST = self.S0 * np.exp(
            (r - q - 0.5 * self.sigma**2) * self.T + self.sigma * np.sqrt(self.T) * Z
        )

        # Apply the payoff function and discount back to today.
        return float(np.exp(-r * self.T) * np.mean(payoff_fn(ST)))

    def mc_vs_bs(self, n_sims=100_000, seed=42):
        """
        Compare Monte Carlo price to Black-Scholes price.
        Shared by calls and puts — both should agree closely.

        Returns
        --------------------------
        dict
        - BS price, MC price, and absolute difference.
        """
        bs = self.price()
        mc = self.price_mc(n_sims=n_sims, seed=seed)
        return {
            "BS Price ($)": round(bs, 4),
            "MC Price ($)": round(mc, 4),
            "Difference ($)": round(abs(mc - bs), 4),
        }

    # --------------------------------------------------------------------------------------------------
    # Finite Difference Greeks
    # --------------------------------------------------------------------------------------------------
    # These methods sit on the base class so any subclass that implements
    # price() automatically inherits a complete set of FD Greeks.
    # All use _bump() which handles type(self) internally — each Greek
    # is now a clean one-liner formula.

    def delta_fd(self, h=0.01):
        """
        Finite Difference Delta (Central Difference).
        Measures sensitivity of the option price to a $1 move in spot.

        Formula: delta = [V(S0 + h) - V(S0 - h)] / 2h
        """
        return (self._bump(S0=self.S0 + h) - self._bump(S0=self.S0 - h)) / (2 * h)

    def gamma_fd(self, h=0.01):
        """
        Finite Difference Gamma (Central Difference).
        Measures the rate of change of delta with respect to spot.

        Formula: gamma = [V(S0 + h) - 2*V(S0) + V(S0 - h)] / h^2
        """
        return (
            self._bump(S0=self.S0 + h) - 2 * self.price() + self._bump(S0=self.S0 - h)
        ) / h**2

    def vega_fd(self, h=0.001):
        """
        Finite Difference Vega (Central Difference), reported per 1% vol move.
        Measures sensitivity of the option price to a 1% change in volatility.

        Formula: vega = [V(sigma + h) - V(sigma - h)] / 2h / 100
        """
        return (
            (self._bump(sigma=self.sigma + h) - self._bump(sigma=self.sigma - h))
            / (2 * h)
            / 100
        )

    def theta_fd(self, h=1 / 365):
        """
        Finite Difference Theta (Central Difference), reported per calendar day.
        Measures sensitivity to daily time erosion as T shrinks.

        Formula: theta = [V(T - h) - V(T + h)] / (2h * 365)
        """
        # down - up because theta is negative (options lose value as T shrinks).
        return (self._bump(T=self.T - h) - self._bump(T=self.T + h)) / (2 * h) / 365

    def rho_fd(self, h=0.0001):
        """
        Finite Difference Rho, reported per 1% rate move via parallel curve shift.
        Measures sensitivity to a 1% change in the risk-free interest rate.

        Formula: rho = [V(r + h) - V(r - h)] / 2h / 100
        """
        return (
            (
                self._bump(yield_curve=ShiftedCurve(self.yield_curve, +h))
                - self._bump(yield_curve=ShiftedCurve(self.yield_curve, -h))
            )
            / (2 * h)
            / 100
        )

    def all_greeks_fd(self):
        """Return all finite-difference Greeks as a dictionary."""
        return {
            "delta": self.delta_fd(),
            "gamma": self.gamma_fd(),
            "vega": self.vega_fd(),
            "theta": self.theta_fd(),
            "rho": self.rho_fd(),
        }

    # --------------------------------------------------------------------------------------------------
    # Historical Volatility
    # --------------------------------------------------------------------------------------------------

    @staticmethod
    def historical_volatility(prices, trading_days=252):
        """
        Description
        -------------------------------------------------------------------------------
        Estimate annualised historical volatility from a closing price series.

        Computes daily log returns ln(P_t / P_{t-1}), takes their standard deviation,
        then converts to an annual value using sqrt(trading_days).

        Parameters
        --------------------------------------------------------------------------------
        prices : array-like
        - Sequence of historical closing prices.
        trading_days : int
        - Number of trading days in a year (default 252, removing weekends and holidays).

        Returns
        --------------------------------------------------------------------------------
        float
        - Annualised historical volatility (as a decimal).
        """
        prices = np.array(prices, dtype=float)
        log_returns = np.diff(np.log(prices))  # Daily log returns.
        daily_vol = np.std(log_returns, ddof=1)  # Sample standard deviation.
        return daily_vol * np.sqrt(trading_days)  # Scale to annual.


# --------------------------------------------------------------------------------------------------
# European Options - Black-Scholes with Merton Dividend Extension
# --------------------------------------------------------------------------------------------------


class EuropeanCall(Derivative):
    """
    European call option priced with the closed-form Black-Scholes formula.
    Supports continuous dividend yield via the Merton (1973) extension:
        C = S * e^(-qT) * N(d1) - K * e^(-rT) * N(d2)
    where q is the continuous dividend yield.

    Inherits from base class: gamma, vega, all_greeks, mc_vs_bs, all FD Greeks.
    Only implements what is call-specific: price, delta, theta, rho, price_mc.
    """

    def price(self):
        """
        Return the Black-Scholes price of the European call option.

        Returns
        -------
        float
            Theoretical call price.
        """
        r, q, d1, d2 = self._params()
        return float(
            self.S0 * np.exp(-q * self.T) * norm.cdf(d1)
            - self.K * np.exp(-r * self.T) * norm.cdf(d2)
        )

    def delta(self):
        """
        Sensitivity of price to spot price (dV/dS).
        For a call: delta = e^(-qT) * N(d1), range 0 to 1.
        """
        _, q, d1, _ = self._params()
        return float(np.exp(-q * self.T) * norm.cdf(d1))

    def theta(self):
        """
        Sensitivity of price to time erosion (dV/dT).
        For a call: three terms — time decay, interest on strike, dividend effect.
        Reported per calendar day, so divide by 365.
        """
        r, q, d1, d2 = self._params()
        term1 = (
            -self.S0
            * np.exp(-q * self.T)
            * norm.pdf(d1)
            * self.sigma
            / (2 * np.sqrt(self.T))
        )
        term2 = -r * self.K * np.exp(-r * self.T) * norm.cdf(d2)  # Negative for calls.
        term3 = q * self.S0 * np.exp(-q * self.T) * norm.cdf(d1)  # Positive for calls.
        return float((term1 + term2 + term3) / 365)

    def rho(self):
        """
        Sensitivity of price to interest rate (dV/dr).
        For a call: rho = K*T*e^(-rT)*N(d2), always positive.
        Reported per 1% move in rate, so divide by 100.
        """
        r, _, _, d2 = self._params()
        return float(self.K * self.T * np.exp(-r * self.T) * norm.cdf(d2) / 100)

    def price_mc(self, n_sims=100_000, seed=42):
        """Price the call via Monte Carlo — delegates to shared _mc_price."""
        # Call payoff: max(ST - K, 0).
        return self._mc_price(lambda ST: np.maximum(ST - self.K, 0), n_sims, seed)


# --------------------------------------------------------------------------------------------------


class EuropeanPut(Derivative):
    """
    European put option priced with the closed-form Black-Scholes formula.
    Supports continuous dividend yield via the Merton (1973) extension:
        P = K * e^(-rT) * N(-d2) - S * e^(-qT) * N(-d1)
    where q is the continuous dividend yield.

    Inherits from base class: gamma, vega, all_greeks, mc_vs_bs, all FD Greeks.
    Only implements what is put-specific: price, delta, theta, rho, price_mc.
    """

    def price(self):
        """
        Return the Black-Scholes price of the European put option.

        Returns
        -------
        float
            Theoretical put price.
        """
        r, q, d1, d2 = self._params()
        return float(
            self.K * np.exp(-r * self.T) * norm.cdf(-d2)
            - self.S0 * np.exp(-q * self.T) * norm.cdf(-d1)
        )

    def delta(self):
        """
        Sensitivity of price to spot price (dV/dS).
        For a put: delta = e^(-qT) * (N(d1) - 1), range -1 to 0.
        """
        _, q, d1, _ = self._params()
        return float(np.exp(-q * self.T) * (norm.cdf(d1) - 1))

    def theta(self):
        """
        Sensitivity of price to time erosion (dV/dT).
        For a put: three terms — time decay, interest on strike, dividend effect.
        Reported per calendar day, so divide by 365.
        """
        r, q, d1, d2 = self._params()
        term1 = -(self.S0 * np.exp(-q * self.T) * norm.pdf(d1) * self.sigma) / (
            2 * np.sqrt(self.T)
        )
        term2 = +r * self.K * np.exp(-r * self.T) * norm.cdf(-d2)  # Positive for puts.
        term3 = -q * self.S0 * np.exp(-q * self.T) * norm.cdf(-d1)  # Negative for puts.
        return float((term1 + term2 + term3) / 365)

    def rho(self):
        """
        Sensitivity of price to interest rate (dV/dr).
        For a put: rho = -K*T*e^(-rT)*N(-d2), always negative.
        Reported per 1% move in rate, so divide by 100.
        """
        r, _, _, d2 = self._params()
        return float(-self.K * self.T * np.exp(-r * self.T) * norm.cdf(-d2) / 100)

    def price_mc(self, n_sims=100_000, seed=42):
        """Price the put via Monte Carlo — delegates to shared _mc_price."""
        # Put payoff: max(K - ST, 0).
        return self._mc_price(lambda ST: np.maximum(self.K - ST, 0), n_sims, seed)


# ======================================================================
# Binomial (Cox-Ross-Rubinstein) Pricers — European and American
# ======================================================================
# These subclasses price European- and American-style options using a
# recombining CRR binomial tree. They share the same Derivative base class
# as the Black-Scholes pricers, which means Portfolio.value() and
# Portfolio.delta() work polymorphically on all pricer types without any
# code change.
#
# FD Greeks inherited from the base class work correctly via _bump().
#
# NOTE on gamma_fd: the inherited finite-difference gamma is noise-dominated
# on binomial trees due to discretisation. Use the closed-form gamma from
# EuropeanCall / EuropeanPut for risk metrics. Binomial is used here
# for pricing cross-validation, not for production gamma.
#
# Reference: Cox, Ross, Rubinstein (1979); Hull, Ch. 13.
# ======================================================================


def _crr_tree_price_european(S0, K, T, sigma, r, q, N, payoff_fn):
    """
    CRR binomial tree for European options — no early exercise.

    Setup is shared via _crr_setup(). This function only implements
    the European rollback: pure discounted expectation at each step.

    Parameters
    ----------
    Same as _crr_setup.
    """
    u, d, disc, p, V = _crr_setup(S0, K, T, sigma, r, q, N, payoff_fn)

    # European rollback: pure discounted expectation — no early exercise check.
    for i in range(N, 0, -1):
        V = disc * (p * V[1 : i + 1] + (1 - p) * V[0:i])

    return float(V[0])


def _crr_tree_price_american(S0, K, T, sigma, r, q, N, payoff_fn):
    """
    CRR binomial tree for American options — with early exercise check.

    Setup is shared via _crr_setup(). This function only implements the
    American rollback: max(continuation, intrinsic) at each node.

    Key theoretical results validated by this implementation:
    - American calls on non-dividend stocks equal European calls; confirms Merton (1973).
    - American calls on dividend-paying stocks can exceed European calls.
    - American puts are always >= European puts.

    Reference: Hull, Ch. 13.

    Parameters
    ----------
    Same as _crr_setup.
    """
    u, d, disc, p, V = _crr_setup(S0, K, T, sigma, r, q, N, payoff_fn)

    for i in range(N, 0, -1):
        # Continuation value: discounted expected value of holding.
        continuation = disc * (p * V[1 : i + 1] + (1 - p) * V[0:i])

        # Stock prices at this level of the tree.
        j_step = np.arange(i)
        S_step = S0 * (u**j_step) * (d ** (i - 1 - j_step))
        intrinsic = payoff_fn(S_step, K)

        # American rule: exercise early if intrinsic value > continuation.
        V = np.maximum(continuation, intrinsic)

    return float(V[0])


# --------------------------------------------------------------------------------------------------
# Shared Binomial Base Class
# --------------------------------------------------------------------------------------------------


class _BinomialBase(Derivative):
    """
    Shared __init__ and price() for all four binomial pricing classes.

    Each subclass declares two class-level attributes:
        _tree_fn : which tree function to use (European or American).
        _payoff  : which payoff function to use (call or put).

    price() is then fully shared — each binomial class is just two lines.
    DEFAULT_N = 2000 gives error
    """

    DEFAULT_N = 2000  # Default number of tree steps.
    _tree_fn = None  # Set by each subclass: European or American tree function.
    _payoff = None  # Set by each subclass: call or put payoff function.

    def __init__(self, S0, K, T, sigma, yield_curve, dividend_yield=0.0, N=None):
        super().__init__(S0, K, T, sigma, yield_curve, dividend_yield)
        # Use the provided N or fall back to DEFAULT_N.
        self.N = N if N is not None else self.DEFAULT_N

    def price(self):
        """Shared price() — delegates to _tree_fn with _payoff."""
        r, q = self._rq()
        return self._tree_fn(
            self.S0, self.K, self.T, self.sigma, r, q, self.N, payoff_fn=self._payoff
        )


# --------------------------------------------------------------------------------------------------
# Binomial European Pricers
# --------------------------------------------------------------------------------------------------


class BinomialEuropeanCall(_BinomialBase):
    """
    European call option priced via the Cox-Ross-Rubinstein binomial tree.

    Converges to the Black-Scholes price as N -> infinity with error of
    order O(1/N). Supports continuous dividend yield via Merton drift.
    """

    _tree_fn = staticmethod(_crr_tree_price_european)
    _payoff = staticmethod(lambda S, K: np.maximum(S - K, 0.0))


class BinomialEuropeanPut(_BinomialBase):
    """
    European put option priced via the Cox-Ross-Rubinstein binomial tree.

    Converges to the Black-Scholes price as N -> infinity. Put-call parity
    holds exactly in the tree (to machine precision).
    """

    _tree_fn = staticmethod(_crr_tree_price_european)
    _payoff = staticmethod(lambda S, K: np.maximum(K - S, 0.0))


# --------------------------------------------------------------------------------------------------
# American Pricers
# --------------------------------------------------------------------------------------------------


class AmericanCall(_BinomialBase):
    """
    American call option priced via the Cox-Ross-Rubinstein binomial tree
    with early-exercise checking at each node.

    Behaviour:
    - For non-dividend-paying underlyings (q=0), price equals the European
      call (Merton's theorem: never optimal to exercise early without dividends).
    - For dividend-paying underlyings (q > 0), price may exceed European,
      reflecting the right to exercise just before a dividend.
    """

    _tree_fn = staticmethod(_crr_tree_price_american)
    _payoff = staticmethod(lambda S, K: np.maximum(S - K, 0.0))


class AmericanPut(_BinomialBase):
    """
    American put option priced via the Cox-Ross-Rubinstein binomial tree
    with early-exercise checking at each node.

    Always greater than or equal to the equivalent European put. The
    premium reflects the value of the right to exercise early, which can
    be optimal when the put is deeply in-the-money.
    """

    _tree_fn = staticmethod(_crr_tree_price_american)
    _payoff = staticmethod(lambda S, K: np.maximum(K - S, 0.0))
