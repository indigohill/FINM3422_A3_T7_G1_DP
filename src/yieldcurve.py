# Packages
import numpy as np
import matplotlib.pyplot as plt

class YieldCurve:
    """
    Yield Curve represents a term structure of zero rate and provides discount factors for valuation.

    This class is infrastructure: all interest-rate logic should live here and be reused by other models.

    """
    def __init__(self, maturities, zero_rates, compounding = "continuous", source_date = None): # Maturities, Rates - Lists & Compounding - String
        """
        Parameters
        -------------
        Maturities: list
            Maturities in years 

        Zero-Rates: list
            Annualised zero-coupon rates (expressed as decimals)

        Both maturities and zero-rates are the same length. 

        Compounding: str NOTE: THIS CAN BE ANNUAL TOO.
            Conistency across the model is important. 
        
        source_data: str
            Date the data was sourced for use in the plot title. 

        """
        # Convert the maturities list to a numpy array of floats for numerical operations.
        self.maturities = np.array (maturities, dtype = float) # Lists

        # Convert zero_rates list to a numpy array of floats for numerical operations.
        self.zero_rates = np.array (zero_rates, dtype = float) # Lists
        
        # Store the compounding convention as a string.
        self.compounding = compounding 

        # Store the data source data to be shown in plot title.
        self.source_date = source_date

        # Ensure that each maturity has a corresponding zero rate.
        if len(self.maturities) != len(self.zero_rates):
            raise ValueError ("Maturities and zero-rates should be the same length.")
        
         # Ensure that the compounding input is either continuous or annual. If not, raise an error. 
        if compounding not in ("continuous", "annual"):
            raise ValueError ("Compounding must be continuous or annual.")

        # np.argsort returns the indices that would sort the maturities in ascending order. 
        order = np.argsort (self.maturities) # Ensure that the maturities and zero-rates are in ascending order.
        # Ensure that both maturities and zero rate arrays are aligned and sorted. 
        self.maturities = self.maturities [order]
        self.zero_rates = self.zero_rates [order]

    @classmethod
    def from_rba (cls, compounding = "continuous"):

        """
        Construct a YieldCurve from the most recent zero-coupon yield data.

        The data_loader.get_latest_yields() to retrieve the most recent observed rates and passes them directly into the YieldCurve.

        Parameters
        ----------
        compounding: str

        Returns
        ---------
        YieldCurve:
            Curve built from 41 RBA-observed maturities (0 - 10 years).
        """
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from data_loader import get_latest_yields

        date, yields = get_latest_yields()

        maturities = list (yields.keys())
        zero_rates = list (yields.values())

        return cls (maturities, zero_rates, compounding = compounding, source_date = date)

    def get_zero_rate (self, T):
        """
        Return the interpolated zero-rate for maturity T (years).

        Use linear interpolation zero-coupon rate for maturity T (years).

        Use linear interpolation between observed maturities. 

        For T outside the observed range, np.interp extrapolates using the nearest boundary value (flat extrapolation).

        Parameters
        ----------
        T: float
            Maturity in years.

        Returns
        ---------
        float
            Annualised zero rate as a decimal.

        """
        # np.interp performs linear interpolation:
        # Given a target value T, it finds wherw T sits between the known maturities and returns the proportionally weighted rate between the two nearest points.
        T = float (T)                                                          
        return float(np.interp(T, self.maturities, self.zero_rates))           
        
    def get_discount_factor (self, T):
        """
        Return the discount factor D(T) for maturity T (years) using the yield curve.

        Continuous: D(T) = exp (-z(T) * T)
        Annual: D(T) = 1/ (1 + z(T))^T

        Parameters
        ----------
        T: float
            Maturity in years.

        
        Returns
        ---------
        float
            Discount factor (between 0 and 1).
        """
        # Retrieve the interpolated zero rate for this maturiy. 
        z = self.get_zero_rate(T)

        if self.compounding == "continuous":   
            # np.exp computes the exponential function e^x.
            # A higher rate or longer maturity will result in a smaller discount factor.
            return np.exp(-z * T) # Continuous 
        
        elif self.compounding == "annual":
            # Equivalent to discounting by the annual rate over T years.
            return 1.0 / (1.0 + z) **T # Annual
        
            
    def plot(self, max_maturity = None):                                        
        """
        
        Plot the yield curve (zero rate vs maturity).
        
        Parameters
        ----------
        max_maturity = float or None
            Upper bound for the x-axis. Defaults to the longest observed maturity.
        
        """
        # If no  max_maturity, just use the observed maturity point as is.
        if max_maturity is None:
            T_grid = self.maturities
        # Otherwise, create a smooth grid of 200 evenly spaced points up to max_maturity.
        # np.linspace (start, stop, num) generates 'num' evenly spaced values. 
        else: 
            T_grid = np.linspace(
                self.maturities.min (),
                max_maturity,
                100
            )
        # Compute the zero rate at each point on the grid, converting to % for display.
        # This is a list comprehension - equivalent to a for loop building a list.
        z_grid = [self.get_zero_rate (T) * 100 for T in T_grid]

        # Build the plot title, appending the source date if available. 
        title = "RBA Zero-Coupon Yield Curve"
        if self.source_date:
            title += f" - {self.source_date}"
        plt.figure (figsize=(10,5))
        plt.plot (T_grid, z_grid, color="orange", linewidth = 2)
        plt.scatter (self.maturities, self.zero_rates * 100, color = "blue", zorder = 5, s = 20, label = "Observed rates")
        plt.xlabel ("Maturity (Years)")
        plt.ylabel ("Zero Rates (% p.a.)")
        plt.title (title)
        plt.grid (True, linestyle="--", alpha = 0.5)
        plt.tight_layout()
        plt.show()
