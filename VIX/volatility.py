"""
S&P 500 volatility: VIX (implied) vs what volatility actually turned out to
be over the following period (forward-looking realized volatility).

VIX(t) is a claim about the ~21 days AFTER date t, so it's scored against
realized volatility computed from the 21 days after t -- not the 21 days
before, which would compare it to the wrong time window.
"""

from pathlib import Path

import plotly.graph_objects as go
import numpy as np
import yfinance as yf
import pandas as pd

OUTPUT_PATH = Path(__file__).parent / "output" / "volatility.html"

TICKER = "^GSPC"
VIX_TICKER = "^VIX"
PERIOD = "30y"          # far enough back to cover the dot-com crash (2000-02)
TRADING_DAYS_PER_YEAR = 252
FORWARD_HORIZON = 21  # ~1 month, matching VIX's ~30-day implied window


def fetch_prices(ticker: str, period: str):
    data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    return data["Close"].squeeze()  # yfinance returns a 1-column DataFrame; squeeze to a Series


def compute_log_returns(prices):
    # Log returns are used (instead of simple % change) because they are
    # additive over time and symmetric for gains/losses, which is what
    # the annualization math below (sqrt-of-time scaling) assumes.
    return np.log(prices / prices.shift(1)).dropna()


def forward_realized_volatility(log_returns, horizon):
    # What volatility actually turned out to be over the `horizon` days
    # AFTER each date -- the fair comparison for a forward-looking measure
    # like VIX, unlike a backward rolling std dev which looks the wrong way.
    n = len(log_returns)
    dates, values = [], []
    for i in range(n - horizon):
        future_returns = log_returns.iloc[i + 1: i + 1 + horizon]
        dates.append(log_returns.index[i])
        values.append(future_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100)
    return pd.Series(values, index=pd.DatetimeIndex(dates, name="Date"))


def main():
    prices = fetch_prices(TICKER, PERIOD)
    log_returns = compute_log_returns(prices)

    vix = fetch_prices(VIX_TICKER, PERIOD)
    forward_vol = forward_realized_volatility(log_returns, FORWARD_HORIZON)

    common_dates = vix.index.intersection(forward_vol.index)
    vix_aligned = vix.loc[common_dates]
    forward_vol_aligned = forward_vol.loc[common_dates]

    bias = (vix_aligned - forward_vol_aligned).mean()
    rmse = np.sqrt(((vix_aligned - forward_vol_aligned) ** 2).mean())

    print(f"{TICKER} - last close: {prices.iloc[-1]:.2f} ({prices.index[-1].date()})")
    print(f"VIX vs what actually happened over the following {FORWARD_HORIZON} days:")
    print(f"  Average bias (VIX - realized): {bias:+.2f} percentage points "
          f"({'VIX overpriced volatility on average' if bias > 0 else 'VIX underpriced volatility on average'})")
    print(f"  RMSE:                          {rmse:.2f}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=vix_aligned.index, y=vix_aligned,
                              name="VIX (implied volatility)"))
    fig.add_trace(go.Scatter(x=forward_vol_aligned.index, y=forward_vol_aligned,
                              name=f"Realized volatility (next {FORWARD_HORIZON}d, forward-looking)"))
    fig.update_layout(
        title=f"{TICKER}: VIX vs subsequent realized volatility",
        yaxis_title="Annualized volatility (%)",
        xaxis_title="Date",
        hovermode="x unified",
    )
    fig.write_html(OUTPUT_PATH)
    print(f"Chart saved to {OUTPUT_PATH}")
    #fig.show()


if __name__ == "__main__":
    main()
