# FINM3422 — A3: Risk & Derivatives Platform

**Team T7 · Group 1 · Derivatives Platform**
University of Queensland · FINM3422 Financial Modelling · Semester 1, 2026

**Authors:** Elizabeth Kvyatkovska: s48426983, Matham Al-Abudi: s4890323, Jordan Westerberg: s48917258, Indigo Hill: s47057465

The Python platform is a modelling prototype for pricing equity options, aggregating them into a portfolio with equity underlyings, and analysing the resulting risk profile under VaR, scenario, and stress-test conditions. 
---

## 1. Project Overview

This platform implements the four core capabilities of a desk-level risk system, separated cleanly into source modules:

1. **Yield curve construction** from RBA F17 zero-coupon rates, with linear or cubic-spline interpolation and continuous or annual compounding.
2. **Option pricing** for European (Black-Scholes with Merton dividend extension) and American (Cox-Ross-Rubinstein binomial tree) options, with Monte Carlo cross-validation and closed-form Greeks.
3. **Portfolio aggregation** that combines equity and option positions polymorphically and reports value, delta, dollar-delta exposure, per-position Greeks, and scenario P&L.
4. **Risk analytics** providing historical VaR, parametric VaR, Expected Shortfall, maximum drawdown, and full-revaluation Monte Carlo VaR — decoupled from the Portfolio class so they remain reusable.

---

## 2. Repository Structure

```
FINM3422_A3_T7_G1_DP/
├── README.md                       ← this file
├── AI_USAGE.md                     ← AI tooling acknowledgement
│
├── data/                           ← cached data for offline reproducibility
│   ├── F17_DATA_RAW.xlsx           ← raw RBA F17 download
│   ├── F17_DATA_CLEAN.csv          ← cleaned yield curve, generated on first run
│   ├── equity_data.csv             ← spot, volatility, dividend yield per ticker (yfinance cache)
│   └── equity_returns.csv          ← 2y daily log returns per ticker
│
├── docs/
│   └── data_selection.md           ← justifications for ASX equity universe and strategy choices
│
├── notebooks/                      ← analysis notebooks (run in order)
│   ├── 01_yield_curve.ipynb        ← curve construction, interpolation comparison
│   ├── 02_derivative.ipynb         ← option pricing engine and Greeks across the universe
│   ├── 03_portfolio.ipynb          ← portfolio construction and position aggregation
│   └── 04_trading_desk_analysis.ipynb  ← final integrated dashboard with positions, scenarios, risk analytics
│
└── src/                            ← reusable Python modules
    ├── data_loader_yieldcurve.py   ← RBA F17 ingestion and CSV caching
    ├── data_loader_market.py       ← yfinance ingestion and CSV caching
    ├── yield_curve.py              ← YieldCurve class
    ├── derivative.py               ← Derivative base + EuropeanCall/Put, BinomialEuropean*, American*
    ├── portfolio.py                ← EquityPosition, Portfolio
    └── risk.py                     ← standalone risk-metric functions
```

---

## 3. Installation

### 3.1 Prerequisites

- Python 3.11 or later (developed against 3.14.4)
- A working internet connection for the first run only (subsequent runs use cached data)

### 3.2 Requirements

# Core numerical and data stack
numpy==2.4.4
pandas==3.0.3
scipy==1.17.1

# Market data
yfinance==1.3.0

# Visualisation
matplotlib==3.10.9
seaborn==0.13.2

### 3.3 Dependencies


| Package | Purpose |
|---|---|
| `numpy` | Numerical arrays and linear algebra |
| `pandas` | Tabular data, time series, return aggregation |
| `scipy` | Statistical functions (norm.cdf for Black-Scholes), cubic spline interpolation |
| `matplotlib` | Plotting — charts and figures |
| `seaborn` | Statistical visualisation and plot styling |
| `yfinance` | Equity market data (spot, returns, dividend yield) |
| `openpyxl` | Reading the RBA F17 .xlsx file (via pandas) |
| `jupyter`, `ipykernel` | Notebook environment |

---

## 4. How to Run

Open and run the notebooks **in order**. Each notebook imports from `src/` via the project-root path added at the top of every notebook (`sys.path.append(os.path.abspath('..'))`), so they will work from any machine without configuration as long as the directory structure is preserved.

| Notebook | Run time (cached) | Run time (first run, no cache) |
|---|---|---|
| `01_yield_curve.ipynb` | < 5 s | < 5 s |
| `02_derivative.ipynb` | ~ 30 s | ~ 60 s |
| `03_portfolio.ipynb` | ~ 30 s | ~ 60 s |
| `04_trading_desk_analysis.ipynb` | ~ 60 s | ~ 90 s |

To force fresh data downloads, delete the relevant file in `data/` and re-run, or pass `use_cache=False` to `load_equity_data()` / `from_rba()`.

---

## 5. Module Overview (`src/`)

### `data_loader_yieldcurve.py`
Ingests the RBA F17 raw Excel file, cleans it, caches the result to `data/F17_DATA_CLEAN.csv`, and exposes `get_latest_yields()` returning the most recent observation date and a `{maturity: zero_rate}` dictionary across 41 maturities (0–10 years in 0.25-year increments).

### `data_loader_market.py`
Downloads ASX equity data via `yfinance` for the universe (CBA, BHP, CSL), computes annualised historical volatility from 2-year daily log returns, retrieves trailing 12-month dividend yields, and caches the result to `data/equity_data.csv`. Also provides `get_rolling_volatility()` for time-varying σ analysis.

### `yield_curve.py` — `YieldCurve`
Stores zero-coupon rates and computes interpolated rates and discount factors. Supports linear (default) and cubic-spline interpolation, continuous or annual compounding. Built either by direct construction or via the `from_rba()` classmethod. Exposes `get_zero_rate(T)` and `get_discount_factor(T)`, both consumed by `derivative.py` for maturity-matched discounting.

### `derivative.py` — `Derivative` and subclasses
Object-oriented option pricing engine:

- `Derivative` (abstract base): stores S₀, K, T, σ, yield curve reference, dividend yield; provides shared finite-difference Greeks and Monte Carlo machinery.
- `EuropeanCall`, `EuropeanPut`: Black-Scholes closed form with Merton dividend extension; closed-form delta, gamma, vega, theta, rho via `all_greeks()`.
- `BinomialEuropeanCall`, `BinomialEuropeanPut`: CRR tree (default N=2000 steps), used for convergence validation against BS.
- `AmericanCall`, `AmericanPut`: CRR tree with early-exercise check.

The polymorphic design means Portfolio aggregation works against any subclass without code changes.

### `portfolio.py` — `EquityPosition` and `Portfolio`
- `EquityPosition`: minimal equity wrapper exposing `price()` and `delta()`; delta is fixed at 1.0.
- `Portfolio`: holds a list of position dicts (`instrument`, `quantity`, `label`) and computes `value()`, `delta()`, `position_table()`, `scenario_analysis()` via full revaluation, plus risk-method wrappers (`historical_var`, `parametric_var`, `expected_shortfall`, `max_drawdown`, `monte_carlo_var`) that delegate to `risk.py`. Caches return series via `load_equity_returns(ticker)`.

### `risk.py`
Standalone, stateless functions for risk metrics. Decoupled from the Portfolio class so they can be reused on any return series or revaluation function:

- `historical_var(returns, alpha, horizon_days, portfolio_value)`
- `parametric_var(...)` — Gaussian, z-score × σ × value
- `expected_shortfall(...)` — mean loss in the worst (1−α) tail
- `max_drawdown(value_series)` — peak-to-trough percentage
- `monte_carlo_var(revaluation_fn, ...)` — full-revaluation MC with antithetic variates

---

## 6. Data Sources

| Source | Type | Detail | Cache |
|---|---|---|---|
| **RBA F17** | Interest rates | Reserve Bank of Australia, Statistical Table F17 — Zero-Coupon Interest Rates, Analytical Series. 41 maturities (0–10y, 0.25y steps). Manually downloaded as `data/F17_DATA_RAW.xlsx`. | `data/F17_DATA_CLEAN.csv` |
| **Yahoo Finance** (via `yfinance`) | Equity market data | 2-year daily adjusted close for CBA.AX, BHP.AX, CSL.AX, WES.AX, TLS.AX. Derives spot (S₀), annualised volatility (σ), trailing dividend yield (q). | `data/equity_data.csv`, `data/equity_returns.csv` |

**Observation date for yield curve**: 30-04-2026 (printed by `YieldCurve.from_rba()` at construction).
**Equity universe rationale**: documented in `docs/data_selection.md`. All AUD-denominated for currency consistency with the RBA risk-free curve, ensuring Black-Scholes validity.


---

## 7. Key Design Decisions

- **Object-oriented pricing engine.** Every pricing model is a subclass of `Derivative`, so `Portfolio.value()` and `Portfolio.delta()` work polymorphically on any combination of vanilla European and American options without code changes.
- **Decoupled risk module.** `risk.py` exposes pure functions independent of the Portfolio class. This means any risk function can be validated in isolation, and the same functions can be reused outside of this project.
- **Maturity-matched discounting.** Every option leg calls its risk-free rate from the YieldCurve at its own maturity. No hardcoded flat rate.
- **Full revaluation for scenarios and MC VaR.** Spot, vol, and rate shocks reprice every position from scratch via deep copy. This captures option convexity (gamma) correctly — a delta-based linear approximation underestimates risk for long-gamma positions and overestimates for short-gamma positions.
- **Reproducibility-first data flow.** Every external API call writes a CSV cache on first run. Subsequent runs work offline. The cached CSVs ensure the notebooks produce identical results on any machine.
- **Linear interpolation as default.** The RBA provides 41 zero-coupon rates at 0.25-year increments; the difference between linear and cubic-spline interpolated rates is < 1 basis point across all maturities (validated in `01_yield_curve.ipynb`), so linear is sufficient. If one method is preferred, this can be selected when the `YieldCurve ` is called upon.

---

## 9. Known Limitations

These are documented in detail in `04_trading_desk_analysis.ipynb`, but a brief summary:

- **Static market data.** All inputs (spot, σ, dividend yield, yield curve) are snapshots, not live feeds.
- **Historical volatility, not implied.** σ is estimated from 2-year daily log returns; implied volatility (e.g. from option-chain data) would be more forward-looking but is out of scope.
- **Equity universe is AUD-only.** Cross-currency portfolios would require currency-matched yield curves.
- **VaR assumptions.** Historical VaR assumes the past resembles the future; parametric VaR assumes Gaussian returns and typically underestimates tail risk; Monte Carlo VaR assumes GBM. All three are reported precisely so the methodology gap is visible.
- **Sqrt-of-time horizon scaling.** Assumes i.i.d. returns; can underestimate multi-day VaR under volatility clustering.

---

## 10. Acknowledgements

This platform was built for FINM3422 Assessment 3 at the University of Queensland, Semester 1 2026. Theoretical references: *Investments* (Bodie, Kane & Marcus) Ch. 20–21; *Options, Futures, and Other Derivatives* (Hull) Ch. 13, 22. AI-tool usage is documented in `AI_USAGE.md` per task sheet §3.5.
