import numpy as np                        
from scipy.stats import norm              


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

        d1 = (
            np.log(self.S0 / self.K)
            + (r + 0.5 * self.sigma ** 2) * self.T
        ) / (self.sigma * np.sqrt(self.T))

        d2 = d1 - self.sigma * np.sqrt(self.T)

        call_price = (
            self.S0 * norm.cdf(d1)
            - self.K * np.exp(-r * self.T) * norm.cdf(d2)
        )
        return call_price


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

        d1 = (
            np.log(self.S0 / self.K)
            + (r + 0.5 * self.sigma ** 2) * self.T
        ) / (self.sigma * np.sqrt(self.T))

        d2 = d1 - self.sigma * np.sqrt(self.T)

        put_price = (                    
            self.K * np.exp(-r * self.T) * norm.cdf(-d2)
            - self.S0 * norm.cdf(-d1)
        )
        return put_price