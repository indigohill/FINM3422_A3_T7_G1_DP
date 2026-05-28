## 1. Data Sources

| Source | Type | Detail | Notes |
|---|---|---|---|
| RBA F17 | Interest rate data | Reserve Bank of Australia — Statistical Table F17 | Zero-coupon rates, 41 maturities (0–10yr, 0.25yr steps). Manually downloaded, cached to `data/F17_DATA_CLEAN.csv`. F17 chosen over F2 as it provides zero-coupon rates directly — no bootstrapping required. |
| yfinance API | Equity market data | Yahoo Finance via yfinance Python library | 2-year daily adjusted closing prices for CBA.AX, BHP.AX, CSL.AX. Derives spot price (S0), annualised volatility (σ), and trailing 12-month dividend yield (q). Cached to `data/equity_data.csv` on first run. |

---

## 2. Equity Selection

ASX equities were selected to ensure currency consistency with the RBA yield curve (AUD throughout), maintain Black-Scholes validity (same currency for risk-free rate and stock price), and provide sector diversification across the Australian economy. 

| Ticker | Company | Industry | Justification |
|---|---|---|---|
| CBA | Commonwealth Bank of Australia | Banking | Most traded ASX stock — highest liquidity. Directly tied to RBA rate decisions. Enables rate shock stress testing. |
| BHP | BHP Group | Materials / Mining | Second largest ASX company by market capitalisation. One of the most liquid ASX stocks. Active options market. High volatility — good for pricing engine validation. |
| CSL | CSL Limited | Healthcare / Pharmaceuticals | Large capitalisation, highly liquid. Growth stock — distinct risk profile to CBA and BHP. |

---

## 3. Portfolio Strategies

| Ticker | Strategy | Composition | Purpose | Greeks | Explanation |
|---|---|---|---|---|---|
| CBA | Protective Put | Long equity + Long 5% OTM put | Hedging | Positive delta (reduced by long put), Positive vega, Positive gamma, Negative theta, ≈ 0 (slightly Negative) rho | CBA equity for long-term banking exposure. Put acts as insurance against RBA rate shock. Put gains offset equity losses on downside. Full equity upside retained. |
| BHP | Covered Call | Long equity + Short 5% OTM call | Income | Positive delta (capped by short call), Negative vega, Negative gamma, Positive theta, Positive rho | BHP equity for long-term commodity exposure. Call premium generates income alongside 3.5% dividend yield. Upside capped if BHP passes strike. |
| CSL | Long Straddle | Long Equity, Long ATM call + Long ATM put | Speculation | Delta ≈ 0, Positive vega, Positive gamma, Negative theta, ≈ 0 rho | Profits if CSL moves beyond K ± total premium paid. |
