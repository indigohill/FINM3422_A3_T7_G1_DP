"""

yieldcurve.py: Yield Curve and Discounting Module

Purpose: Provides the YieldCurve class which:
- Stores zero-coupon rates for various maturities.
- Interpolates rates at arbitrary maturities using two methods (linear, cubic spline).
- Computes discount factors using continuous or annual compounding.
- Integrates directly with `data_loader` for construction from RBA data.

"""

# Download the required packages.
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# scipy CubicSpline: used for cubic spline interpolation.
from scipy.interpolate import CubicSpline

class YieldCurve:
    """
    Description
    ---------------------------
    Yield Curve constructs a term-structure of zero-coupon interest rates and provides discount factors for use across all valuation models.

    This class is the interest-rate infrastructure layer for the platform. It is reused by `derivative.py` and `portfolio.py` whereveer discounting is required.

    """
    def __init__(self, maturities, zero_rates, compounding = "continuous", interpolation = "linear"): # Maturities, Rates - Lists & Compounding - String
        """
        Parameters
        -------------------------
        maturities: list or array,
        - Maturities in years (denoted by yrs).

        zero_rates: list or array,
        - Annualised zero-coupon rates (expressed as decimals).

        NOTE: Both maturities and zero-rates are required to be the same length.

        compounding: str
        - 'continuous' (default) or 'annual'

        interpolation: str
        - 'linear' (default) or 'cubic'
        - Determines the method rates are interpolated between observed maturities.

        """
        # Convert the maturities list to a numpy array of floats for numerical operations.
        self.maturities = np.array (maturities, dtype = float)

        # Convert zero_rates list to a numpy array of floats for numerical operations.
        self.zero_rates = np.array (zero_rates, dtype = float)

        # Store the compounding convention as a string.
        self.compounding = compounding

        # Store the interpolation method as a string.
        self.interpolation = interpolation

        # Validate each maturity has a corresponding zero rate.
        if len(self.maturities) != len(self.zero_rates):
            raise ValueError ("maturities and zero_rates must be the same length.")

        # Validate that the compounding input is either continuous or annual. If not, raise an error.
        if compounding not in ("continuous", "annual"):
            raise ValueError ("compounding must be continuous or annual.")

        #  Validate that the interpolation method is either linear or cubic. If not, raise an error.
        if interpolation not in ("linear", "cubic"):
            raise ValueError ("interpolation must be linear or cubic.")

        order = np.argsort (self.maturities) # Ensure that the maturities are in ascending order.
        self.maturities = self.maturities [order]
        self.zero_rates = self.zero_rates [order]

        # If cubic interpolation is selected, fit it once at initialisation and reuse.
        if self.interpolation == "cubic":
            self._cubic_spline = CubicSpline (self.maturities, self.zero_rates)

    @classmethod
    def from_rba (cls, compounding = "continuous", interpolation = "linear"):

        """
        Description
        --------------------------
        Construct a YieldCurve from the most recent RBA zero-coupon yield data.

        Calls data_loader.get_latest_yields() to retrieve the most recent observed rates and passes them directly into the YieldCurve.

        Parameters
        --------------------------
        compounding: str
        - 'continuous' (default) or 'annual'.

        interpolation: str
        - 'linear' (default) or 'cubic'.

        Returns
        -------------------------
        YieldCurve:
        - Curve built from 41 RBA-observed maturities (0 - 10yrs).
        """
        """ Import data here (instead of at the top) so that yield.curve.py can be used independently without data_loader.py present."""
        try:
            from yield_data_loader import get_latest_yields
        except ModuleNotFoundError:
            from src.yield_data_loader import get_latest_yields

        date, yields = get_latest_yields()

        maturities = list (yields.keys())
        zero_rates = list (yields.values())

        # Print a confirmation message so that the user knows what data was loaded.
        print (f" [YieldCurve] Built from RBA F17 data as of {date}.")
        print (f" Maturtites: {len(maturities)} points (0yr to 10yr in 0.25yr increments.)")
        print (f" Compounding: {compounding}")
        print (f" Interpolation: {interpolation}")

        return cls (maturities, zero_rates, compounding = compounding, interpolation=interpolation)

# Core Functions
# ----------------------------------------------------------------------------------------------------------------
    def get_zero_rate (self, T):
        """
        Description
        ----------------------------------
        Return the interpolated zero-rate for maturity T (years) using either linear or cubic spline interpolation.

        Parameters
        ----------------------------------
        T: float
            Maturity in years.

        Returns
        ----------------------------------
        float
            Annualised zero rate as a decimal.

        """
        # np.interp performs linear interpolation:
        # Given a target value T, it finds wherw T sits between the known maturities and returns the proportionally weighted rate between the two nearest points.
        if self.interpolation == "linear":
            return float(np.interp(float(T), self.maturities, self.zero_rates)) #   Linear
        else:
            return float (self._cubic_spline(float(T))) # Cubic

    def get_discount_factor (self, T):
        """
        Description
        --------------------------------
        Return the discount factor D(T) for maturity T (years).

        Continuous: D(T) = exp (-z(T) * T)
        Annual: D(T) = 1/ (1 + z(T))^T

        Parameters
        --------------------------------
        T: float
            Maturity in years.

        Returns
        --------------------------------
        float
            Discount factor (between 0 and 1).
        """
        # Retrieve the interpolated zero rate for this maturiy.
        z = self.get_zero_rate(T)

        if self.compounding == "continuous":
            # A higher rate or longer maturity will result in a smaller discount factor.
            return np.exp(-z * T) # Continuous
        else:
            return 1.0 / (1.0 + z) **T # Annual

# Plotting
# -------------------------------------------------------------------------------------------------------

    def plot(self, max_maturity = None, compare = False):
        """
        Description
        ----------------------------------
        Plot the yield curve (zero rate vs maturity).

        Parameters
        ----------------------------------
        max_maturity: float or None
        - Upper bound for the x-axis. Defaults to the longest observed maturity.

        compare: bool
        - If True, plots both linear and cubic spline on the same chart.
        - If False, plots only default (linear).
        """
        # If no  max_maturity, just use the observed maturity point as is.
        if max_maturity is None:
            T_grid = np.linspace (self.maturities.min(), self.maturities.max(), 200)
        # Otherwise, create a smooth grid of 200 evenly spaced points up to max_maturity.
        # np.linspace (start, stop, num) generates 'num' evenly spaced values.
        else:
            T_grid = np.linspace(self.maturities.min (), max_maturity, 200)

        # Build the plot title, appending the source date if available.
        title = "RBA Zero-Coupon Yield Curve"

        # Create two side-by side plots - one for zero rates, one for discount factors.
        fig, (ax1, ax2) = plt.subplots (1, 2, figsize = (16,5))
        fig.suptitle (title, fontsize = 13)

        # Left Panel: Zero Rates
        if compare:
            z_linear = [float(np.interp(T, self.maturities, self.zero_rates))* 100 for T in T_grid]
            cs = CubicSpline (self.maturities, self.zero_rates)
            z_cubic = [float(cs(T)) * 100 for T in T_grid]
            ax1.plot (T_grid, z_linear, color = "#2196F3", linewidth = 2, label = "Linear")
            ax1.plot (T_grid, z_cubic, color = "#F44336", linewidth = 2, linestyle = "--", label = "Cubic Spline")
            ax1.legend()

        else:
            z_grid = [self.get_zero_rate(T) * 100 for T in T_grid]
            label = "Cubic Spline" if self.interpolation == "Cubic" else "Linear"
            ax1.plot (T_grid, z_grid, color = "#2196F3", linewidth = 2, label=label)

        ax1.scatter (self.maturities, self.zero_rates * 100, color = "#000000", zorder = 5, s = 5, label = "Observed Rates")
        ax1.set_xlabel ("Maturity (Years)")
        ax1.set_ylabel ("Zero Rates (% p.a.)")
        ax1.set_title ("Zero Rates")
        ax1.grid (True, linestyle="--", alpha = 0.5)

         # Right Panel: Discount Rates
        d_grid = [self.get_discount_factor(T) for T in T_grid]
        ax2.plot (T_grid, d_grid, color = "#4CAF50", linewidth = 2)
        ax2.scatter (self.maturities, [self.get_discount_factor(T) for T in self.maturities], color = "#000000", zorder = 5, s = 5)
        ax2.set_xlabel ("Maturity (Years)")
        ax2.set_ylabel ("Discount Factor D(T)")
        ax2.set_title ("Discount Factors")
        ax2.grid (True, linestyle = "--", alpha = 0.5)

        plt.tight_layout()
        plt.show()

    def compare_interpolation (self, test_maturities = None):
        """
        Description:
        ---------------------------------------------------
        Compare linear and cubic spline interpolation at a set of maturities.

        Parameters
        --------------------------------------------------
        test_maturities: List or None
        - Maturities to compare, where the default is non-observed maturities.

        Returns
        ---------------------------------------------------
        pd.DataFrame
        - Table comparing linear and cubic spline zero rates.

        """

        if test_maturities is None:
            test_maturities = [0.6, 1.3, 2.8, 4.2, 6.3, 8.5, 9.1]

        curve_linear = YieldCurve(self.maturities, self.zero_rates, self.compounding, interpolation="linear")
        curve_cubic  = YieldCurve(self.maturities, self.zero_rates, self.compounding, interpolation="cubic")

        rows = []
        for T in test_maturities:
            z_l = curve_linear.get_zero_rate (T)
            d_l = curve_linear.get_discount_factor (T)
            z_c = curve_cubic.get_zero_rate (T)
            d_c = curve_cubic.get_discount_factor (T)
            diff = (z_c - z_l) * 10000
            rows.append({
                "Maturity (Years)" : T,
                "Linear Zero Rates (% p.a.)" : round(z_l * 100, 4),
                "Linear Discount Factor" : round (d_l, 6),
                "Cubic Spline Zero Rates (% p.a.)"  : round (z_c * 100, 4),
                "Cubic Spline Discount Factor" : round (d_c, 6),
                "Difference (bps)" : round (diff, 4)
            })

        results = pd.DataFrame(rows)
        results.index = [""] * len(results)
        return results

# Tests
# -------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    curve = YieldCurve.from_rba()
    print(curve.compare_interpolation().to_string())
