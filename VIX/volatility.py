"""
S&P 500 volatility: VIX (implied) vs what volatility actually turned out to
be over the following period (forward-looking realized volatility).

VIX(t) is a claim about the ~21 days AFTER date t, so it's scored against
realized volatility computed from the 21 days after t -- not the 21 days
before, which would compare it to the wrong time window.

Layout of this file (see CLAUDE.md):
    1. python / data code  -> download, calculate, print, and def main()
    2. html / chart code   -> draws the Plotly chart and saves the .html file
"""

from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import numpy as np                        # number tools: log, sqrt, mean
import pandas as pd                       # tables and time series (Series / DataFrame)
import plotly.graph_objects as go         # chart library (only used by the html / chart code below)
import yfinance as yf                     # downloads market prices from Yahoo Finance


# ===========================================================================
# python / data code
# ===========================================================================

OUTPUT_PATH = Path(__file__).parent / "output" / "volatility.html"  # where the chart is saved: VIX/output/volatility.html

TICKER = "^GSPC"                          # Yahoo Finance symbol for the S&P 500 index
VIX_TICKER = "^VIX"                       # Yahoo Finance symbol for the VIX index
PERIOD = "30y"                            # how far back to download; far enough to cover the dot-com crash (2000-02)
TRADING_DAYS_PER_YEAR = 252               # trading days in a year, used to annualize daily volatility
FORWARD_HORIZON = 21                      # ~1 month of trading days, matching VIX's ~30-day implied window


def fetch_prices(ticker: str, period: str):
    """Download the daily closing prices of one ticker."""
    data = yf.download(ticker, period=period, auto_adjust=True, progress=False)  # daily prices table; auto_adjust corrects for dividends/splits; progress=False hides the progress bar
    prices = data["Close"].squeeze()      # keep only the closing prices; yfinance gives a 1-column table, squeeze() turns it into a Series

    # RETURNS a pandas Series: 7,547 values (one per trading day), index = Date, values = closing price (float64).
    # fetch_prices("^GSPC", "30y") prints as:
    # Date
    # 1996-10-03     692.780029
    # 1996-10-04     701.460022
    # 1996-10-07     703.340027
    #                   ...
    # 2026-10-01    7666.450195
    # 2026-10-02    7722.720215
    # Name: ^GSPC, Length: 7547, dtype: float64
    return prices


def compute_log_returns(prices):
    """Turn prices into daily log returns."""
    # Log returns are used (instead of simple % change) because they are
    # additive over time and symmetric for gains/losses, which is what
    # the annualization math (sqrt-of-time scaling) assumes.
    shifted = prices.shift(1)             # yesterday's price lined up against today's (everything moves down one row)
    log_returns = np.log(prices / shifted)  # ln(today / yesterday), one value per day
    log_returns = log_returns.dropna()    # the first day has no "yesterday", so its value is empty; remove it

    # RETURNS a pandas Series: 7,546 values (one fewer than prices: the first day has no "yesterday"),
    # index = Date, values = daily log return (float64). Prints as:
    # Date
    # 1996-10-04    0.012451       <- ln(701.46 / 692.78): the S&P rose about 1.25% that day
    # 1996-10-07    0.002677
    # 1996-10-08   -0.003846
    #                 ...
    # 2026-10-01    0.001947
    # 2026-10-02    0.007313
    # Name: ^GSPC, Length: 7546, dtype: float64
    return log_returns


def forward_realized_volatility(log_returns, horizon):
    """Volatility that actually followed each date, over the next `horizon` days."""
    # What volatility actually turned out to be over the `horizon` days
    # AFTER each date -- the fair comparison for a forward-looking measure
    # like VIX, unlike a backward rolling std dev which looks the wrong way.
    n = len(log_returns)                  # number of daily returns we have
    dates, values = [], []                # two empty lists: one date and one volatility per loop
    for i in range(n - horizon):          # stop `horizon` days early: the last days have no complete future yet
        future_returns = log_returns.iloc[i + 1: i + 1 + horizon]  # the NEXT 21 returns (day i itself is excluded: it is already known)
        dates.append(log_returns.index[i])  # remember the date we are scoring
        values.append(future_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100)  # std of daily returns -> annualized (x sqrt(252)) -> in percent (x100), comparable with the VIX
    realized = pd.Series(values, index=pd.DatetimeIndex(dates, name="Date"))  # list of numbers + their dates -> one Series

    # RETURNS a pandas Series: 7,525 values (21 fewer than log_returns: the last 21 dates have no complete future),
    # index = Date, values = annualized volatility in % (float64; shown here rounded to 2 decimals). Prints as:
    # Date
    # 1996-10-04     7.16          <- volatility of the 21 returns AFTER 1996-10-04, annualized
    # 1996-10-07     7.94
    # 1996-10-08     9.07
    #               ...
    # 2026-09-01    10.54
    # 2026-09-02    10.72
    # Length: 7525, dtype: float64
    return realized


def align_series(vix, forward_vol):
    """Keep only the dates that exist in both series, so they line up one to one."""
    common_dates = vix.index.intersection(forward_vol.index)  # dates present in BOTH series
    vix_aligned = vix.loc[common_dates]   # the VIX on those dates only
    forward_vol_aligned = forward_vol.loc[common_dates]  # the realized volatility on those dates only

    # RETURNS a tuple of 2 pandas Series, 7,524 values each, with exactly the same dates:
    # (vix_aligned, forward_vol_aligned)
    #   vix_aligned                    forward_vol_aligned
    #   Date                           Date
    #   1996-10-07    15.11            1996-10-07    7.94
    #   1996-10-08    15.58            1996-10-08    9.07
    #   ...                            ...
    return vix_aligned, forward_vol_aligned


def compute_bias_rmse(vix_aligned, forward_vol_aligned):
    """Score the VIX against what happened: average gap (bias) and typical gap size (RMSE)."""
    gap = vix_aligned - forward_vol_aligned  # day-by-day gap: positive = VIX above what happened
    bias = gap.mean()                     # average gap; positive = VIX overpriced volatility on average
    rmse = np.sqrt((gap ** 2).mean())     # root mean squared error: typical size of the gap, big misses weigh more

    # RETURNS a tuple of 2 floats (numpy float64), both in volatility points:
    # (bias, rmse)  ->  (3.7992, 8.1640)
    #   bias = +3.80  : on average the VIX was 3.8 points ABOVE the volatility that followed
    #   rmse =  8.16  : a typical miss, in either direction, is about 8 points
    return bias, rmse


def print_report(prices, bias, rmse):
    """Print the result in the terminal."""
    print(f"{TICKER} - last close: {prices.iloc[-1]:.2f} ({prices.index[-1].date()})")  # latest S&P close and its date
    print(f"VIX vs what actually happened over the following {FORWARD_HORIZON} days:")  # title line
    print(f"  Average bias (VIX - realized): {bias:+.2f} percentage points "  # signed bias with 2 decimals...
          f"({'VIX overpriced volatility on average' if bias > 0 else 'VIX underpriced volatility on average'})")  # ...plus a plain-words reading of its sign
    print(f"  RMSE:                          {rmse:.2f}")  # typical size of the gap

    # RETURNS None (nothing). It only prints these 4 lines in the terminal:
    # ^GSPC - last close: 7722.72 (2026-10-02)
    # VIX vs what actually happened over the following 21 days:
    #   Average bias (VIX - realized): +3.80 percentage points (VIX overpriced volatility on average)
    #   RMSE:                          8.16


def main():
    """Run the steps in order."""
    prices = fetch_prices(TICKER, PERIOD)                    # step 1: S&P 500 closing prices
    log_returns = compute_log_returns(prices)                # step 2: prices -> daily log returns
    vix = fetch_prices(VIX_TICKER, PERIOD)                   # step 3: VIX closing levels
    forward_vol = forward_realized_volatility(log_returns, FORWARD_HORIZON)  # step 4: volatility that followed each date
    vix_aligned, forward_vol_aligned = align_series(vix, forward_vol)  # step 5: keep the dates both series share
    bias, rmse = compute_bias_rmse(vix_aligned, forward_vol_aligned)   # step 6: score the VIX
    print_report(prices, bias, rmse)                         # step 7: show the result in the terminal
    fig = build_figure(vix_aligned, forward_vol_aligned)     # step 8: draw the chart (html / chart code below)
    save_chart(fig)                                          # step 9: write it to VIX/output/volatility.html

    # RETURNS None (nothing). The results are its side effects:
    #   - the 4-line report printed in the terminal (see print_report)
    #   - the file VIX/output/volatility.html


# ===========================================================================
# html / chart code
# ===========================================================================

def build_figure(vix_aligned, forward_vol_aligned):
    """Draw VIX and realized volatility as two lines on one chart."""
    fig = go.Figure()                     # empty chart
    fig.add_trace(go.Scatter(x=vix_aligned.index, y=vix_aligned,  # line 1: x = dates, y = VIX
                             name="VIX (implied volatility)"))    # legend label
    fig.add_trace(go.Scatter(x=forward_vol_aligned.index, y=forward_vol_aligned,  # line 2: x = dates, y = realized volatility
                             name=f"Realized volatility (next {FORWARD_HORIZON}d, forward-looking)"))  # legend label
    fig.update_layout(
        title=f"{TICKER}: VIX vs subsequent realized volatility",  # chart title
        yaxis_title="Annualized volatility (%)",  # y-axis label
        xaxis_title="Date",                       # x-axis label
        hovermode="x unified",                    # hovering shows both lines' values for that date in one box
    )

    # RETURNS a plotly Figure object (type plotly.graph_objects.Figure), not yet a file. It holds 2 traces (lines),
    # 7,524 points each:
    #   fig.data[0].name  -> "VIX (implied volatility)"                              x = dates, y = VIX
    #   fig.data[1].name  -> "Realized volatility (next 21d, forward-looking)"       x = dates, y = realized volatility %
    #   fig.layout.title.text -> "^GSPC: VIX vs subsequent realized volatility"
    return fig


def save_chart(fig):
    """Write the chart to an interactive .html file."""
    fig.write_html(OUTPUT_PATH)           # saves the chart as a standalone web page you can open in a browser
    print(f"Chart saved to {OUTPUT_PATH}")  # tell the user where the file is
    # fig.show()                          # alternative: open the chart in the browser right away instead of saving

    # RETURNS None (nothing). The result is the file VIX/output/volatility.html (about 5 MB), and this line in the terminal:
    # Chart saved to VIX/output/volatility.html (full path of your own machine)


if __name__ == "__main__":                # True only when you run this file directly (python volatility.py), not when another file imports it
    main()                                # so importing the functions (as shocks.py does) has no side effects
