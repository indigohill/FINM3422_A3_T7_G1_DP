from datetime import date

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import CubicSpline


RBA_MATURITIES = [2,3,5,10]


class YieldCurve:
    

    def __init__(self, maturities, zero_rates, compounding="continuous",
                 date=None, par_yields=None, method="direct"):
        
        self.maturities  = np.array(maturities,  dtype=float)
        self.zero_rates  = np.array(zero_rates,   dtype=float)
        self.compounding = compounding
        self.date        = pd.Timestamp(date) if date is not None else None
        self.par_yields  = np.array(par_yields, dtype=float) if par_yields is not None else None
        self.method      = method
 
        if len(self.maturities) != len(self.zero_rates):
            raise ValueError("Maturities and zero_rates must be the same length.")
        
    
        # Ensure ascending order
        order = np.argsort(self.maturities)
        self.maturities = self.maturities[order]
        self.zero_rates = self.zero_rates[order]

        if self.par_yields is not None:
            self.par_yields = self.par_yields[order]

    

        # cubic spline
        if len(self.maturities) >=3:
            self._spline = CubicSpline(self.maturities, self.zero_rates)
        else:
            self._spline = None #use np.interp fallback

    
    def get_zero_rate(self, T):
        """ Interpolation stuff"""

        T = float(T)
        if T<=0:
            raise ValueError(f"Maturity must be positive. Got {T}.")
        if T < self.maturities.min() or T > self.maturitiees.max():
            raise ValueError(
                f"Maturity {T}yr is outside the observable range"
                f"[{self.maturities.min()}, {self.maturities.max()}]"
            )
        if self._spline is not None:
            return float(self._spline(T))/100
        else:
            return float(np.interp(T, self.maturities, self.zero_rates))/100
        

    def get_discount_factor(self, T):
         """
        Return the discount factor D(T) at maturity T years.
 
        Continuous compounding:  D(T) = exp(-z * T)
        Annual compounding:      D(T) = 1 / (1 + z)^T
        """
         z = self.get_zero_rate(T)

         if self.compounding == "continuous":
             return float(np.exp(-z * T))
         elif self.compounding == "annual":
             return float(1 / (1 + z) ** T)
         else:
             raise ValueError(f"Compounding must be 'continuous' or 'annual', fo t '{self.compounding}'.")
         


    # Plotting

    def plot(self, max_maturity=None, ax=None, show=True):
        """Plot the yield curve (zero rates vs maturity)"""

        if ax is None:
            fig, ax = plt.subplots(figsize=(10,6))
            
        if max_maturity is None:
            T_grid = np.linspace(0.1, self.maturities.min(), self.maturities.max(), 300)
            
        else:
            T_grid = np.linspace(self.maturities.min(), max_maturity, 300)

        z_grid = [self.get_zero_rate(T)*100 for T in T_grid
                  if self.maturities.min() <= T <= self.maturities.max()]
        T_grid = [T for T in T_grid
                  if self.maturities.min() <= T <= self.maturities.max()]
        
        label = {"bootstrap": "Bootstrapped zero curve",
                 "interpolate": "Interpolated curve (cubic spline)",
                 "direct": "Zero curve"}.get(self.method, "Zero curve")
        
        ax.plot(T_grid, z_grid, label=label, color="blue", linewidth=2)
        ax.scatter(self.maturities, self.zero_rates, color="red", s=80, zorder=5)

        if self.par_yields is not None:
            ax.scatter(self.maturities, self.par_yields, color="coral", zorder=5, s=60, marker="x", linewidths=2, label="Observed RBA par yields")
            for mat, yld in zip(self.maturities, self.par_yields):
                ax.annotate(f"{yld:.2f}%", xy=(mat, yld), xytext=(4,6), textcoords="offset points", fontsize=9)
        

        title = "Australian Government Bond Yield Curve"
        if self.dat is not None:
            title += f"\nDate: {self.date.strftime('%B %Y')}"
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.set_xlabel("Maturity (Years)")
        ax.set_ylabel("Zero Rate (% per annum)")
        ax.legend()
        ax.grid(True)
        plt.tight_layout()
        if show:
            plt.show()
        return ax
    

    def plot_discount_factors(self, ax=None, show=True):
        # plot discount factor curve
        if ax is None:
            fig, ax = plt.subplots(figsize=(10,6))

        
        T_grid = np.linspace(self.maturities.min(), self.maturities.max(), 300)
        df_grid = [self.get_discount_factor(T) for T in T_grid]

        ax.plot(T_grid, df_grid, color="coral", linewidth=2)
        ax.scatter(self.maturities,
                   [self.get_discount_factor(T) for T in self.maturities],
                   color="coral", zorder=5, s=80)
 
        title = "Discount Factor Curve"
        if self.date is not None:
            title += f"\nDate: {self.date.strftime('%B %Y')}"
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.set_xlabel("Maturity (Years)")
        ax.set_ylabel("Discount Factor")
        ax.grid(True)
        plt.tight_layout()
        if show:
            plt.show()
        return ax





"""
    def _bootstrap(self):
        zerp_rates = np.zeros(len(self.maturities))
        for i, (T,c) in enumerate(zip(self.maturities, self.yields)):
            coupon = c/100
            if i ==0
                zero_rates[i] = c
            else:
                known_zeros = zero_rates[:i]/100
                known_mats = self.maturities[:i]
                if len(known_mats) >= 2:
                    temp_spline = CubicSpline(known_mats, known_zeros)
                else:
                    temp_spline = lambda t: known_zeros[0]
                coupon_pv = 0.0
                for t in np.arange(1, T):
                    if t<=min(known_mats):
                        z_t = known_zeros[0]
                    elif t>=max(known_mats):
                        z_t = known_zeros[-1]
                    else: 
                        z_t = float(temp_spline(t))
                    coupon_pv += coupon *np.exp(-z_t*t)
                df_T =(1-coupon_pv) / (1+coupon)
                if df_T <=0:
                    raise ValueError(f" Bootstrap failed at tenor {T}yr-negative DF ({df_T:.4f})")
                    zero_rates[i] = -np.log(df_T)/T*100
        return zero_rates
"""