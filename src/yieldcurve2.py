import numpy as py
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import CubicSpline


RBA_MATURITIES = [2,3,5,10]


class YieldCurve:
""" Represents a yield curve at a single point in time, constructed from Aus Gov Bond yields sourced from the RBA

Attributes
date: pd.Timestampd - observation date of the curve
maturities: list [float] - tenor points in years
yields: np.ndarray - observed yields (% p.a.) at each tenor
_spline: CubicSpline - fitted cubic spline for interpolation between tenor points'

Supports the two construction methods; inetrpolation and bootstrapping
"""

    def __init__(self, date, maturities, yields, method="interpolate"):
        self.date = pd.Timestamp(date)
        self.maturities = list(maturities)
        self.yields = np.array(yields, dtype=float)
        self.method = method
        self.zero_rates = self._bootstrap() if method == "bootstrap" else self.yields.copy()
        self._spline = CubicSpline(self.maturities, self.zero_rates)

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
                    rais ValueError(f" Bootstrap failed at tenor {T}yr-negative DF ({df_T:.4f})")
                    zero_rates[i] = -np.log(df_T)/T*100
        return zero_rates