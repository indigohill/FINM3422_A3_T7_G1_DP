# Packages
import numpy as np
import matplotlib.pyplot as plt

class YieldCurve:
    """
    Yield Curve represents a term structure of zero rate and provides discount factors for valuation.

    This class is infrastructure: all interest-rate logic should live here and be reused by other models.

    """
    def __init__(self, maturities, zero_rates, compounding = "continuous"): # Maturities, Rates - Lists & Compounding - String
        """
        DEFINE ALL PARAMETERS.
        
        Compounding can either be continuous or annual.

        """
        self.maturities = np.array (maturities, dtype = float) # Lists
        self.zero_rates = np.array (zero_rates, dtype = float) # Lists - you need to make sure that you have one maturitiy for one zero rates. 
        self.compounding = compounding # Keeping this one as a string. 

        if len(self.maturities) != len(self.zero_rates):
            raise ValueError ("Maturities and zero-rates should be the same length.")
        
        order = np.argsort (self.maturities) # Ensure that the maturities and zero-rates are in ascending order.
        self.maturities = self.maturities [order]
        self.zero_rates = self.zero_rates [order]

    def get_zero_rate (self, T):
        """
        Return the interpolated zero-rate for maturity T (years).

        """
        T = float (T)                                                          
        return float(np.interp(T, self.maturities, self.zero_rates))           
        
    def get_discount_factor (self, T):
        """
        Return the discount factor D(T) using the yield curve.
        
        """
        z = self.get_zero_rate(T)

        if self.compounding == "continuous":                                    
            return np.exp(-z * T) # Continuous 
        
        elif self.compounding == "annual":
            return 1.0 / (1.0 + z) **T # Annual
        
        else: # Should probably be raised in __init__. It isn't the best practice to be raising the error message here.
            raise ValueError ("Compounding should be continuous or annual.")
            
    def plot(self, max_maturity = None):                                        
        """Plot the yield curve."""

        if max_maturity is None:
            T_grid = self.maturities
        
        else: 
            T_grid = np.linspace(
                self.maturities.min (),
                max_maturity,
                100
            )
        
        z_grid = [self.get_zero_rate(T) for T in T_grid]

        plt.figure ()
        plt.plot (T_grid, z_grid)
        plt.xlabel ("Maturity (Years)")
        plt.ylabel ("Zero Rates")
        plt.title ("Yield Curve")
        plt.grid (True)
        plt.tight_layout()
        plt.show()
