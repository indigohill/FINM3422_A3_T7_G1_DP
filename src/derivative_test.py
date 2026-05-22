import numpy as np                        
from scipy.stats import norm              


def _d1_d2(S0, K, T, sigma, r):
    """
    Helper function to calculate d1 and d2 for the Black-Scholes formula.
    """
    d1 = (
        np.log(S0 / K)
        + (r + 0.5 * sigma ** 2) * T
    ) / (sigma * np.sqrt(T))

    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2

class ShiftedCurve:
    """
    Lightweight wrapper that applies a flat parallel shift to a yield curve.

    Used by finite-difference rho calculations to bump the curve up or down
    by a small amount without mutating the underlying YieldCurve object.
    """

    def __init__(self, base_curve, shift):
        self._base = base_curve
        self._shift = shift

    def get_zero_rate(self, T):
        return self._base.get_zero_rate(T) + self._shift

class Derivative:
    """
    Abstract base class for derivative instruments.

    Stores the common parameters shared by all derivative contracts and
    exposes a price() interface that every concrete sub-class must implement.
    This class should never be instantiated directly; use a sub-class such as
    EuropeanCall or EuropeanPut instead.
    """                                   

    def __init__(self, S0, K, T, sigma, yield_curve, dividend_yield=0.0):
        """
        Initialise common derivative parameters.

        Parameters
        ----------
        S0 : float
            Current spot price of the underlying asset.
        K : float
            Strike price of the option.
        T : float
            Time to maturity, expressed in years.
        sigma : float
            Annualised volatility of the underlying asset (e.g. 0.20 for 20%).
        yield_curve : object
            Yield-curve object that exposes a get_zero_rate(T) method returning
            the continuously-compounded risk-free zero rate for maturity T.
        dividend_yield : float, optional
            Continuous dividend yield of the underlying asset (default is 0.0).
        """                               
        self.S0 = S0
        self.K = K
        self.T = T
        self.sigma = sigma
        self.yield_curve = yield_curve
        self.dividend_yield = float(dividend_yield)

        #input validation
        if self.S0 <= 0: raise ValueError("S0 must be positive.")
        if self.K <= 0: raise ValueError("K must be positive.")
        if self.T <= 0: raise ValueError("T must be positive.")
        if self.sigma <= 0: raise ValueError("sigma cannot be negative.")


    def price(self):
        """Sub-classes must implement their own pricing logic."""
        raise NotImplementedError(        
            "price() must be implemented in a sub-class."
        )


    # ------------------------------------------------------------------
    # Finite-difference Greeks
    # ------------------------------------------------------------------
    # These methods sit on the base class so any subclass that implements
    # price() automatically inherits a complete set of FD Greeks. They use
    # type(self) rather than a hardcoded class name so subclasses (binomial,
    # Monte Carlo, etc.) get re-instantiated through their own pricer.
    # ------------------------------------------------------------------

    def delta_fd(self, h=0.01):
        """
        Finite-difference delta (central difference).
        delta = [V(S+h) - V(S-h)] / 2h
        """
        cls = type(self)
        up = cls(self.S0 + h, self.K, self.T, self.sigma, self.yield_curve, self.dividend_yield).price()
        down = cls(self.S0 - h, self.K, self.T, self.sigma, self.yield_curve, self.dividend_yield).price()
        return (up - down) / (2 * h)

    def gamma_fd(self, h=0.01):
        """
        Finite-difference gamma (central difference).
        gamma = [V(S+h) - 2*V(S) + V(S-h)] / h^2
        """
        cls = type(self)
        up = cls(self.S0 + h, self.K, self.T, self.sigma, self.yield_curve, self.dividend_yield).price()
        mid = self.price()
        down = cls(self.S0 - h, self.K, self.T, self.sigma, self.yield_curve, self.dividend_yield).price()
        return (up - 2 * mid + down) / (h ** 2)

    def vega_fd(self, h=0.001):
        """
        Finite-difference vega (central difference), reported per 1% vol move.
        vega = [V(sigma+h) - V(sigma-h)] / 2h, then divided by 100.
        """
        cls = type(self)
        up = cls(self.S0, self.K, self.T, self.sigma + h, self.yield_curve, self.dividend_yield).price()
        down = cls(self.S0, self.K, self.T, self.sigma - h, self.yield_curve, self.dividend_yield).price()
        return (up - down) / (2 * h) / 100

    def theta_fd(self, h=1 / 365):
        """
        Finite-difference theta (central difference), reported per calendar day.

        Theta measures sensitivity to time decay. As time passes, T shrinks.
        We use a central difference around T to be consistent with the other
        FD Greeks: theta = [V(T-h) - V(T+h)] / (2h * 365).
        """
        cls = type(self)
        up = cls(self.S0, self.K, self.T + h, self.sigma, self.yield_curve, self.dividend_yield).price()
        down = cls(self.S0, self.K, self.T - h, self.sigma, self.yield_curve, self.dividend_yield).price()
        return (down - up) / (2 * h) / 365

    def rho_fd(self, h=0.0001):
        """
        Finite-difference rho via flat parallel rate shift, reported per 1%
        rate move.
        rho = [V(r+h) - V(r-h)] / 2h, then divided by 100.
        """
        cls = type(self)
        up = cls(self.S0, self.K, self.T, self.sigma,
                 ShiftedCurve(self.yield_curve, +h), self.dividend_yield).price()
        down = cls(self.S0, self.K, self.T, self.sigma,
                   ShiftedCurve(self.yield_curve, -h), self.dividend_yield).price()
        return (up - down) / (2 * h) / 100

    def all_greeks_fd(self):
        """Return all finite-difference Greeks as a dictionary."""
        return {
            "delta": self.delta_fd(),
            "gamma": self.gamma_fd(),
            "vega": self.vega_fd(),
            "theta": self.theta_fd(),
            "rho": self.rho_fd(),
        }

    @staticmethod
    def historical_volatility(prices,trading_days=252):
        """
        Estimate annualised historical volatility from a price series
        Computes daily log returns, takes their standard deviation then scale to annual


        Parameters:
        prices : array-like
            Sequence of historical closing prices
        trading_days : int
            Number of trading days in a year (default is 252).

        Returns:
        float
            Annualised historical volatility.
        """
        prices = np.array(prices, dtype=float)
        log_returns = np.diff(np.log(prices))
        daily_vol = np.std(log_returns, ddof=1)
        annualised_vol = daily_vol * np.sqrt(trading_days)
        return annualised_vol



class EuropeanCall(Derivative):          
    """
    European call option priced with the closed-form Black-Scholes formula.
    Supports continuous dividend yield via the Merton (1973) extension:
        C = S * e^(-qT) * N(d1) - K * e^(-rT) * N(d2)
    where q is the continuous dividend yield.
    """

    def price(self):
        """
        Return the Black-Scholes price of the European call option.

        Returns
        -------
        float
            Theoretical call price.
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield

        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r-q)

        call_price = (
            self.S0 * np.exp(-q*self.T) * norm.cdf(d1)
            - self.K * np.exp(-r * self.T) * norm.cdf(d2)
        )
        return float(call_price)

    def delta(self):
        """
        sensitivity of price to spot price (dv/dS)
        for a call: change = N(d1) (range: 0 to 1)
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r-q)
        return float(np.exp(-q*self.T)*norm.cdf(d1))
    
    def gamma(self):
        """
        sensitivity of delta to spot price (dV/dS)^2
        same formula for call and puts: r=N'(d1)/(S*σ*sqrt(T))
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r-q)
        return float(np.exp(-q*self.T)*norm.pdf(d1) / (self.S0 * self.sigma * np.sqrt(self.T)))
    
    def vega(self):
        """
        sensitivity of price to volatility (dV/dσ)
        same formula for call and puts: v = S*N'(d1)*sqrt(T)
        > reported per 1% move in volatility, so divide by 100
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r-q)
        return float(self.S0 *np.exp(-q*self.T)* norm.pdf(d1) * np.sqrt(self.T) / 100)
    
    def theta(self):
        """
        sensitivity of price to time decay (dV/dT)
        for a call: o = [-S*N'(d1)*σ/(2*sqrt(T))] - r*K*e^(-r*T)*N(d2)
        reported per day, so divide by 365
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r-q)
        #time decay: always negative
        term1 = -self.S0 * np.exp(-q*self.T) * norm.pdf(d1) * self.sigma / (2 * np.sqrt(self.T))
        #interest rate effect; negative for calls
        term2 = -r*self.K*np.exp(-r*self.T)*norm.cdf(d2)
        #dividend effect: positive for calls, as dividends reduce the underlying price
        term3 = q*self.S0*np.exp(-q*self.T)*norm.cdf(d1)
        
        return float((term1 + term2 + term3) / 365)

    def rho(self):
        """
        sensitivity of price to interest rate (dV/dr)
        for a call: p = K*T*e^(-r*T)*N(d2)
        reported per 1% move in rate, so divide by 100
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        _, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r-q)
        return float(self.K * self.T * np.exp(-r * self.T) * norm.cdf(d2) / 100)

    def all_greeks(self):
        """
        Return all the Greeks in a dictionary.
        """
        return {
            "delta": self.delta(),
            "gamma": self.gamma(),
            "vega": self.vega(),
            "theta": self.theta(),
            "rho": self.rho()
        }



    # Monte Carlo Pricing

    def price_mc(self, n_sims=100_000, seed = 42):
        """
        Price the call via Monte Carlo simulation using Geometric Brownian Motion.
 
        Uses antithetic variates to reduce simulation variance:
        for every random draw Z, its mirror -Z is also used.
        This gives more accurate results with the same number of paths.

        Steps:
         1. Draw n_sims/2 random numbers Z, pair with -Z (antithetic variates).
        2. Simulate final stock price:
               S_T = S0 * exp((r - q - sigma^2/2)*T + sigma*sqrt(T)*Z)
        3. Calculate call payoff: max(S_T - K, 0).
        4. Average payoffs and discount: price = e^(-rT) * mean(payoffs).
 
        Parameters:       
        n_sims : int
            Number of simulated paths (must be even).
        seed : int
            Random seed for reproducibility.
 
        Returns
        float
            Monte Carlo estimate of the call price.
        """

        np.random.seed(seed)
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield

        #antithetic variates: pair each Z with -Z to reduce variance
        half = n_sims // 2
        Z = np.random.standard_normal(half)
        Z = np.concatenate([Z, -Z])  # antithetic pairing

        #simulate final stock prices under risk-neutral GBM
        ST = self.S0 * np.exp((r - q - 0.5 * self.sigma ** 2) * self.T + self.sigma * np.sqrt(self.T) * Z)

        #call payoff: max(ST - K, 0)
        payoffs = np.maximum(ST - self.K, 0)
        return float(np.exp(-r * self.T) * np.mean(payoffs))
    
    def mc_vs_bs(self, n_sims=100_000, seed=42):
        """
        Compare Monte Carlo price to Black-Scholes price and return the difference.
        Useful as a validation step since they should be very close
        Returns
        float
            Difference between Monte Carlo price and Black-Scholes price.
        """
        bs = self.price()
        mc = self.price_mc(n_sims=n_sims, seed=seed)
        return {
            "BS Price ($)": round(bs, 4),
            "MC Price ($)": round(mc, 4),
            "Difference ($)": round(abs(mc - bs), 4)
        }





class EuropeanPut(Derivative):           
    """
    European put option priced with the closed-form Black-Scholes formula.
    """

    def price(self):                    
        """
        Return the Black-Scholes price of the European put option.

        Returns
        -------
        float
            Theoretical put price.
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield

        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r-q)

        put_price = (                    
            self.K * np.exp(-r * self.T) * norm.cdf(-d2)
            - self.S0 * np.exp(-q * self.T) * norm.cdf(-d1)
        )
        return float(put_price)
    

    #closed-form greeks


    def delta(self):
        """
        for a put:
        change = N(d1) - 1 (range: -1 to 0)
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r - q)
        return float(np.exp(-q*self.T) * (norm.cdf(d1) - 1))
    

    def gamma(self):
        """
        for a put:
        (same as call)
        r = N'(d1)/(S*σ*sqrt(T)) -> always positive
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r - q)
        return float(np.exp(-q*self.T)*norm.pdf(d1) / (self.S0 * self.sigma * np.sqrt(self.T)))
    
    def vega(self):
        """
        for a put:
        (same as call)
        v = S*N'(d1)*sqrt(T) -> always positive
        """
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r - q)
        return float(self.S0 * np.exp(-q*self.T)*norm.pdf(d1) * np.sqrt(self.T) / 100)
    
    def theta(self):
        """
        for a put:
        o = [-S*N'(d1)*σ/(2*sqrt(T))] + r*K*e^(-r*T)*N(-d2)
        reported per day
        """
        r       = self.yield_curve.get_zero_rate(self.T)
        q       = self.dividend_yield
        d1, d2  = _d1_d2(self.S0, self.K, self.T, self.sigma, r - q)
 
        term1   = -(self.S0 * np.exp(-q * self.T) * norm.pdf(d1) * self.sigma) / (2 * np.sqrt(self.T))
        term2   = +r * self.K * np.exp(-r * self.T) * norm.cdf(-d2)
        term3   = -q * self.S0 * np.exp(-q * self.T) * norm.cdf(-d1)
 
        return float((term1 + term2 + term3) / 365)
    
    def rho(self):
        """
        for a put:
        p = -K*T*e^(-r*T)*N(-d2)
        reported per 1% move in rate, so divide by 100
        """
        r      = self.yield_curve.get_zero_rate(self.T)
        q      = self.dividend_yield
        _, d2  = _d1_d2(self.S0, self.K, self.T, self.sigma, r - q)
        return float(-self.K * self.T * np.exp(-r * self.T) * norm.cdf(-d2) / 100)
    
    
    def all_greeks(self):
        """
        Return all the Greeks in a dictionary.
        """
        return {
            "delta": self.delta(),
            "gamma": self.gamma(),
            "vega": self.vega(),
            "theta": self.theta(),
            "rho": self.rho()
        }
    

    #Monte Carlo Pricing

    def price_mc(self, n_sims=100_000, seed=42):
        """
        Price the put via Monte Carlo using GBM with antithetic variates.
 
        """
        np.random.seed(seed)
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
 
       
        half = n_sims // 2
        Z    = np.random.standard_normal(half)
        Z    = np.concatenate([Z, -Z])
 
        ST = self.S0 * np.exp(
            (r - q - 0.5 * self.sigma ** 2) * self.T
            + self.sigma * np.sqrt(self.T) * Z
        )
 
        
        payoffs = np.maximum(self.K - ST, 0)
        return float(np.exp(-r * self.T) * np.mean(payoffs))
 
    def mc_vs_bs(self, n_sims=100_000, seed=42):
        """
        Compare the Monte Carlo price to the Black-Scholes price.
 
        """
        bs = self.price()
        mc = self.price_mc(n_sims=n_sims, seed=seed)
        return {
            "BS Price ($)":    round(bs, 4),
            "MC Price ($)":    round(mc, 4),
            "Difference ($)":  round(abs(bs - mc), 4),
        }
    
# ======================================================================
# Binomial (Cox-Ross-Rubinstein) pricers — European and American
# ======================================================================
# These subclasses price European- and American-style options using a
# recombining CRR binomial tree. They share the same Derivative base class
# as the Black-Scholes pricers, which means Portfolio.value() and
# Portfolio.delta() work polymorphically on all pricer types without any
# code change.
#
# FD Greeks inherited from the base class work correctly via type(self).
#
# NOTE on gamma_fd: the inherited finite-difference gamma is noise-dominated
# on binomial trees due to discretisation. The tree's price function is
# piecewise smooth with small jumps as nodes cross the strike, which the
# second-derivative finite difference amplifies. Use the closed-form gamma
# from EuropeanCall / EuropeanPut for risk metrics. Binomial is used here
# for pricing cross-validation, not for production gamma.
#
# Reference: Cox, Ross, Rubinstein (1979); Hull, Ch. 13.
# ======================================================================


def _crr_tree_price_european(S0, K, T, sigma, r, q, N, payoff_fn):
    """
    Cox-Ross-Rubinstein binomial tree pricer for European-style options.

    Builds a recombining tree of N steps, computes terminal payoffs at
    expiry, then discounts backward through the tree using the risk-neutral
    probability. Vectorised across nodes at each time step for efficiency.

    Supports continuous dividend yield via Merton's drift adjustment:
    the risk-neutral probability uses (r - q) as the drift while
    discounting still uses r.

    Parameters
    ----------
    S0 : float
        Current spot price of the underlying.
    K : float
        Strike price.
    T : float
        Time to maturity in years.
    sigma : float
        Volatility of the underlying (annualised, as a decimal).
    r : float
        Risk-free rate, continuously compounded, assumed flat over [0, T].
    q : float
        Continuous dividend yield.
    N : int
        Number of time steps in the tree. Error decays as O(1/N).
    payoff_fn : callable
        Intrinsic-value function payoff_fn(S, K) called at expiry.

    Returns
    -------
    float
        Present value of the option.
    """
    dt = T / N
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    disc = np.exp(-r * dt)
    p = (np.exp((r - q) * dt) - d) / (u - d)

    j = np.arange(N + 1)
    S_terminal = S0 * (u ** j) * (d ** (N - j))
    V = payoff_fn(S_terminal, K)

    # European rollback: pure discounted expectation, no early exercise
    for i in range(N, 0, -1):
        V = disc * (p * V[1:i+1] + (1 - p) * V[0:i])

    return float(V[0])


def _crr_tree_price_american(S0, K, T, sigma, r, q, N, payoff_fn):
    """
    Cox-Ross-Rubinstein binomial tree pricer for American-style options.

    Identical to the European tree pricer except for the rollback step,
    which takes max(continuation_value, intrinsic_value) at each node.
    This embeds the holder's right to exercise early.

    Key theoretical results validated by this implementation:
    - American calls on non-dividend stocks equal European calls (no
      early-exercise premium); confirms Merton (1973).
    - American calls on dividend-paying stocks can exceed European calls,
      with the premium growing with dividend yield.
    - American puts are always >= European puts; the premium grows as
      the put moves deeper in-the-money.

    Reference: Hull, Ch. 13.

    Parameters
    ----------
    Same as _crr_tree_price_european.

    Returns
    -------
    float
        Present value of the American option.
    """
    dt = T / N
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    disc = np.exp(-r * dt)
    p = (np.exp((r - q) * dt) - d) / (u - d)

    j = np.arange(N + 1)
    S_terminal = S0 * (u ** j) * (d ** (N - j))
    V = payoff_fn(S_terminal, K)

    for i in range(N, 0, -1):
        # Continuation value: discounted expected value of holding
        continuation = disc * (p * V[1:i+1] + (1 - p) * V[0:i])

        # Spot prices at step i-1 (after rollback)
        j_step = np.arange(i)
        S_step = S0 * (u ** j_step) * (d ** (i - 1 - j_step))
        intrinsic = payoff_fn(S_step, K)

        # American optionality: max of holding vs exercising now
        V = np.maximum(continuation, intrinsic)

    return float(V[0])


class BinomialEuropeanCall(Derivative):
    """
    European call option priced via the Cox-Ross-Rubinstein binomial tree.

    Converges to the Black-Scholes price as N -> infinity with error of
    order O(1/N). Supports continuous dividend yield via Merton drift.
    """

    DEFAULT_N = 500

    def __init__(self, S0, K, T, sigma, yield_curve, dividend_yield=0.0, N=None):
        super().__init__(S0, K, T, sigma, yield_curve, dividend_yield)
        self.N = N if N is not None else self.DEFAULT_N

    def price(self):
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        return _crr_tree_price_european(
            self.S0, self.K, self.T, self.sigma, r, q, self.N,
            payoff_fn=lambda S, K: np.maximum(S - K, 0.0)
        )


class BinomialEuropeanPut(Derivative):
    """
    European put option priced via the Cox-Ross-Rubinstein binomial tree.

    Converges to the Black-Scholes price as N -> infinity. Put-call parity
    holds exactly in the tree (to machine precision), making this a strong
    cross-check on the binomial pricing logic.
    """

    DEFAULT_N = 500

    def __init__(self, S0, K, T, sigma, yield_curve, dividend_yield=0.0, N=None):
        super().__init__(S0, K, T, sigma, yield_curve, dividend_yield)
        self.N = N if N is not None else self.DEFAULT_N

    def price(self):
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        return _crr_tree_price_european(
            self.S0, self.K, self.T, self.sigma, r, q, self.N,
            payoff_fn=lambda S, K: np.maximum(K - S, 0.0)
        )


class AmericanCall(Derivative):
    """
    American call option priced via the Cox-Ross-Rubinstein binomial tree
    with early-exercise checking at each node.

    Behaviour:
    - For non-dividend-paying underlyings (q=0), price equals the European
      call (Merton's theorem: never optimal to exercise early without
      dividends).
    - For dividend-paying underlyings (q > 0), price may exceed European,
      reflecting the right to exercise just before a dividend.
    """

    DEFAULT_N = 500

    def __init__(self, S0, K, T, sigma, yield_curve, dividend_yield=0.0, N=None):
        super().__init__(S0, K, T, sigma, yield_curve, dividend_yield)
        self.N = N if N is not None else self.DEFAULT_N

    def price(self):
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        return _crr_tree_price_american(
            self.S0, self.K, self.T, self.sigma, r, q, self.N,
            payoff_fn=lambda S, K: np.maximum(S - K, 0.0)
        )


class AmericanPut(Derivative):
    """
    American put option priced via the Cox-Ross-Rubinstein binomial tree
    with early-exercise checking at each node.

    Always greater than or equal to the equivalent European put. The
    premium reflects the value of the right to exercise early, which can
    be optimal when the put is deeply in-the-money — the present value of
    receiving K now (which earns interest) exceeds the option value of
    waiting.
    """

    DEFAULT_N = 500

    def __init__(self, S0, K, T, sigma, yield_curve, dividend_yield=0.0, N=None):
        super().__init__(S0, K, T, sigma, yield_curve, dividend_yield)
        self.N = N if N is not None else self.DEFAULT_N

    def price(self):
        r = self.yield_curve.get_zero_rate(self.T)
        q = self.dividend_yield
        return _crr_tree_price_american(
            self.S0, self.K, self.T, self.sigma, r, q, self.N,
            payoff_fn=lambda S, K: np.maximum(K - S, 0.0)
        )


    