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

    def __init__(self, S0, K, T, sigma, yield_curve):
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
        """                               
        self.S0 = S0
        self.K = K
        self.T = T
        self.sigma = sigma
        self.yield_curve = yield_curve

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
        up = cls(self.S0 + h, self.K, self.T, self.sigma, self.yield_curve).price()
        down = cls(self.S0 - h, self.K, self.T, self.sigma, self.yield_curve).price()
        return (up - down) / (2 * h)

    def gamma_fd(self, h=0.01):
        """
        Finite-difference gamma (central difference).
        gamma = [V(S+h) - 2*V(S) + V(S-h)] / h^2
        """
        cls = type(self)
        up = cls(self.S0 + h, self.K, self.T, self.sigma, self.yield_curve).price()
        mid = self.price()
        down = cls(self.S0 - h, self.K, self.T, self.sigma, self.yield_curve).price()
        return (up - 2 * mid + down) / (h ** 2)

    def vega_fd(self, h=0.001):
        """
        Finite-difference vega (central difference), reported per 1% vol move.
        vega = [V(sigma+h) - V(sigma-h)] / 2h, then divided by 100.
        """
        cls = type(self)
        up = cls(self.S0, self.K, self.T, self.sigma + h, self.yield_curve).price()
        down = cls(self.S0, self.K, self.T, self.sigma - h, self.yield_curve).price()
        return (up - down) / (2 * h) / 100

    def theta_fd(self, h=1 / 365):
        """
        Finite-difference theta (central difference), reported per calendar day.

        Theta measures sensitivity to time decay. As time passes, T shrinks.
        We use a central difference around T to be consistent with the other
        FD Greeks: theta = [V(T-h) - V(T+h)] / (2h * 365).
        """
        cls = type(self)
        up = cls(self.S0, self.K, self.T + h, self.sigma, self.yield_curve).price()
        down = cls(self.S0, self.K, self.T - h, self.sigma, self.yield_curve).price()
        return (down - up) / (2 * h) / 365

    def rho_fd(self, h=0.0001):
        """
        Finite-difference rho via flat parallel rate shift, reported per 1%
        rate move.
        rho = [V(r+h) - V(r-h)] / 2h, then divided by 100.
        """
        cls = type(self)
        up = cls(self.S0, self.K, self.T, self.sigma,
                 ShiftedCurve(self.yield_curve, +h)).price()
        down = cls(self.S0, self.K, self.T, self.sigma,
                   ShiftedCurve(self.yield_curve, -h)).price()
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

class EuropeanCall(Derivative):          
    """
    European call option priced with the closed-form Black-Scholes formula.
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

        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r)

        call_price = (
            self.S0 * norm.cdf(d1)
            - self.K * np.exp(-r * self.T) * norm.cdf(d2)
        )
        return call_price

    def delta(self):
        """
        sensitivity of price to spot price (dv/dS)
        for a call: change = N(d1) (range: 0 to 1)
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        return float(norm.cdf(d1))
    
    def gamma(self):
        """
        sensitivity of delta to spot price (dV/dS)^2
        same formula for call and puts: r=N'(d1)/(S*σ*sqrt(T))
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        return float(norm.pdf(d1) / (self.S0 * self.sigma * np.sqrt(self.T)))
    
    def vega(self):
        """
        sensitivity of price to volatility (dV/dσ)
        same formula for call and puts: v = S*N'(d1)*sqrt(T)
        > reported per 1% move in volatility, so divide by 100
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        return float(self.S0 * norm.pdf(d1) * np.sqrt(self.T) / 100)
    
    def theta(self):
        """
        sensitivity of price to time decay (dV/dT)
        for a call: o = [-S*N'(d1)*σ/(2*sqrt(T))] - r*K*e^(-r*T)*N(d2)
        reported per day, so divide by 365
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        term1 = -self.S0 * norm.pdf(d1) * self.sigma / (2 * np.sqrt(self.T))
        term2 = -r*self.K*np.exp(-r*self.T)*norm.cdf(d2)
        return float((term1 + term2) / 365)
    
    def rho(self):
        """
        sensitivity of price to interest rate (dV/dr)
        for a call: p = K*T*e^(-r*T)*N(d2)
        reported per 1% move in rate, so divide by 100
        """
        r = self.yield_curve.get_zero_rate(self.T)
        _, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
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

        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r)

        put_price = (                    
            self.K * np.exp(-r * self.T) * norm.cdf(-d2)
            - self.S0 * norm.cdf(-d1)
        )
        return put_price
    

    #closed-form greeks


    def delta(self):
        """
        for a put:
        change = N(d1) - 1 (range: -1 to 0)
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        return float(norm.cdf(d1) - 1)
    

    def gamma(self):
        """
        for a put:
        (same as call)
        r = N'(d1)/(S*σ*sqrt(T)) -> always positive
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        return float(norm.pdf(d1) / (self.S0 * self.sigma * np.sqrt(self.T)))
    
    def vega(self):
        """
        for a put:
        (same as call)
        v = S*N'(d1)*sqrt(T) -> always positive
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, _ = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        return float(self.S0 * norm.pdf(d1) * np.sqrt(self.T) / 100)
    
    def theta(self):
        """
        for a put:
        o = [-S*N'(d1)*σ/(2*sqrt(T))] + r*K*e^(-r*T)*N(-d2)
        reported per day
        """
        r = self.yield_curve.get_zero_rate(self.T)
        d1, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
        term1 = -self.S0 * norm.pdf(d1) * self.sigma / (2 * np.sqrt(self.T))
        term2 = +r*self.K*np.exp(-r*self.T)*norm.cdf(-d2)
        return float((term1 + term2) / 365)
    
    def rho(self):
        """
        for a put:
        p = -K*T*e^(-r*T)*N(-d2)
        reported per 1% move in rate, so divide by 100
        """
        r = self.yield_curve.get_zero_rate(self.T)
        _, d2 = _d1_d2(self.S0, self.K, self.T, self.sigma, r)
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
    


    