"""
S&P 500 volatility: VIX (implied) vs what volatility actually turned out to
be over the following period (forward-looking realized volatility).

VIX(t) is a claim about the ~21 days AFTER date t, so it's scored against
realized volatility computed from the 21 days after t -- not the 21 days
before, which would compare it to the wrong time window.

Layout of this file (see CLAUDE.md):
    1. python / data code  -> download, calculate, print, and def main()
    2. html / chart code   -> draws the Plotly chart and writes the "Lab" page VIX/output/volatility.html
"""

import json                               # turns Python lists into text the page's JavaScript can read
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import numpy as np                        # number tools: log, sqrt, mean
import pandas as pd                       # tables and time series (Series / DataFrame)
import plotly.graph_objects as go         # chart library (only used by the html / chart code below)
import yfinance as yf                     # downloads market prices from Yahoo Finance


# ===========================================================================
# python / data code
# ===========================================================================

OUTPUT_PATH = Path(__file__).parent / "output" / "volatility.html"  # where the page is saved: VIX/output/volatility.html

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
    build_page(prices, vix_aligned, forward_vol_aligned, bias, rmse)  # step 8: draw the chart and write the page (html / chart code below)

    # RETURNS None (nothing). The results are its side effects:
    #   - the 4-line report printed in the terminal (see print_report)
    #   - the file VIX/output/volatility.html (about 500 KB), and the line "Page saved to ..." in the terminal


# ===========================================================================
# html / chart code
# ===========================================================================
# Look: the "Lab" design every project page uses (see CLAUDE.md and nasdaq-bonds/nasdaq_bonds.py): burgundy header
# band (the VIX colour), rose accents, white panels, the homepage fonts, light and dark mode via colour tokens. The Plotly chart sits
# inside a panel; its colours are read from the same tokens by the JavaScript below, so it follows light/dark mode.

FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"  # the homepage fonts
CHART_ID = "vol-chart"                    # the id of the <div> Plotly draws into
VIX_NAME = "VIX - implied volatility (solid line)"                                      # legend label of line 1
REALIZED_NAME = f"Realized volatility, next {FORWARD_HORIZON}d - actual (dashed line)"  # legend label of line 2
# The same labels with a line break, for a phone: one long label would be wider than the screen.
NARROW_NAMES = ["VIX - implied volatility<br>(solid line)", f"Realized volatility, next {FORWARD_HORIZON}d<br>- actual (dashed line)"]


def build_figure(vix_aligned, forward_vol_aligned):
    """Draw VIX and realized volatility as two lines on one chart."""
    fig = go.Figure()                     # empty chart
    fig.add_trace(go.Scatter(x=vix_aligned.index, y=vix_aligned,  # line 1: x = dates, y = VIX
                             name=VIX_NAME,                       # legend label; says which line style is the VIX
                             hovertemplate="VIX (expected): %{y:.1f}<extra></extra>",  # hover line: short name, 1 decimal; <extra></extra> hides the long legend name
                             line=dict(dash="solid", width=1.5, color="#2a5db0")))  # solid blue line (light-mode colour; the page JS swaps in the token)
    fig.add_trace(go.Scatter(x=forward_vol_aligned.index, y=forward_vol_aligned,  # line 2: x = dates, y = realized volatility
                             name=REALIZED_NAME,                  # legend label; says which line style is the realized volatility
                             hovertemplate=f"Realized, next {FORWARD_HORIZON}d (actual): %{{y:.1f}}<extra></extra>",  # same short form
                             line=dict(dash="dash", width=1.5, color="#c27a2c")))  # dashed amber line
    fig.update_layout(
        template="none",                          # start from a blank style; colours come from the Lab tokens
        paper_bgcolor="rgba(0,0,0,0)",            # transparent: the panel behind shows through (light or dark)
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, system-ui, sans-serif", size=13, color="#55625c"),  # Lab text font and secondary ink
        yaxis_title="Annualized volatility (%)",  # y-axis label
        xaxis_title="Date",                       # x-axis label
        hovermode="x unified",                    # hovering shows both lines' values for that date in one box
        # The hover box in the light-mode tokens (--surface, --grid, --ink); LAB_JS swaps in the dark ones in dark mode.
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#e4e2dc",
                        font=dict(color="#16181d", family="DM Sans, system-ui, sans-serif", size=13)),
        # Desktop: legend in one row ABOVE the plot. The page JS moves it BELOW the plot, one entry per line, on a phone
        # (on the right, the long labels took the whole width of a phone and squeezed the plot to a sliver).
        legend=dict(orientation="h", yref="container", y=1, yanchor="top", x=0, xanchor="left"),
        margin=dict(l=60, r=20, t=48, b=56),      # left/right/top/bottom space around the plot
        height=500,                               # chart height on a desktop (taller on a phone, see LAB_JS)
    )
    fig.update_xaxes(gridcolor="#e6e1d5", linecolor="#cbc5b6", zeroline=False,  # faint grid, light axis line
                     hoverformat="%d %b %Y",                              # the hover box title shows the full day, e.g. "15 Sep 2020"
                     spikecolor="#868b94", spikethickness=1, spikedash="dot")  # thin dotted guide line at the hovered date (--muted)
    fig.update_yaxes(gridcolor="#e6e1d5", linecolor="#cbc5b6", zeroline=False, rangemode="tozero")  # the y-axis starts at 0

    # RETURNS a plotly Figure object (type plotly.graph_objects.Figure), not yet a file. It holds 2 traces (lines),
    # 7,524 points each:
    #   fig.data[0].name  -> "VIX - implied volatility (solid line)"                     x = dates, y = VIX, solid line
    #   fig.data[1].name  -> "Realized volatility, next 21d - actual (dashed line)"      x = dates, y = realized volatility %, dashed line
    #   fig.layout.height -> 500
    #   fig.layout.hoverlabel.bgcolor -> "#ffffff"   (light-mode --surface; the page JS switches it in dark mode)
    return fig


# JavaScript run once Plotly has drawn the chart ("{plot_id}" is replaced by the chart's id). It
#   - reads the Lab colour tokens, so the chart (lines, grid and the hover box) follows light and dark mode;
#   - switches to the phone layout under 640px: legend below the plot, one entry per line, taller chart;
#   - turns drag-zoom off on touch screens: a one-finger drag would draw a zoom box instead of scrolling the page,
#     which traps the reader (tap to read values still works).
LAB_JS = """
const gd = document.getElementById('{plot_id}');
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();   // read a colour token
const narrowMQ = window.matchMedia('(max-width: 640px)');      // true on a phone-width screen
const isTouch = window.matchMedia('(pointer: coarse)').matches; // a finger instead of a mouse
const NAMES = __NAMES__;                                        // legend labels: {wide: [...], narrow: [...]}
function labStyle() {
  const narrow = narrowMQ.matches, grid = css('--grid'), axis = css('--axis');
  gd.style.height = (narrow ? 560 : 500) + 'px';                // the chart's own box grows with it, so nothing spills out
  Plotly.restyle(gd, {'line.color': [css('--vix'), css('--real')], name: narrow ? NAMES.narrow : NAMES.wide});
  Plotly.relayout(gd, {
    height: narrow ? 560 : 500,                                 // taller box on a phone
    'font.color': css('--ink-2'),
    'xaxis.gridcolor': grid, 'yaxis.gridcolor': grid, 'xaxis.linecolor': axis, 'yaxis.linecolor': axis,
    'xaxis.title.text': narrow ? '' : 'Date',                   // the dates speak for themselves on a small screen
    'xaxis.nticks': narrow ? 5 : 12,                            // fewer date labels on a phone, so none overlap
    // hover box = page tokens, never Plotly's default (which would not follow dark mode)
    'hoverlabel.bgcolor': css('--surface'), 'hoverlabel.bordercolor': grid, 'hoverlabel.font.color': css('--ink'),
    'xaxis.spikecolor': css('--muted'),                         // the dotted guide line at the hovered date
    // Paint the plot in the panel's own colour (it looks the same as transparent). Plotly outlines the guide line in a
    // colour that contrasts with this background; with a transparent one it picked white, a glaring bar in dark mode.
    paper_bgcolor: css('--surface'), plot_bgcolor: css('--surface'),
    legend: narrow ? {orientation: 'v', yref: 'container', y: 0, yanchor: 'bottom', x: 0, xanchor: 'left', font: {size: 12}}
                   : {orientation: 'h', yref: 'container', y: 1, yanchor: 'top', x: 0, xanchor: 'left', font: {size: 13}},
    margin: narrow ? {l: 50, r: 10, t: 12, b: 120} : {l: 60, r: 20, t: 48, b: 56},
    dragmode: isTouch ? false : 'zoom',                         // no drag-zoom for a finger
  });
}
labStyle();
narrowMQ.addEventListener('change', labStyle);                  // rebuild when a phone is rotated
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', labStyle);   // theme switch: re-read the tokens, so lines AND hover box change
if (isTouch) document.querySelectorAll('.hint').forEach(h => h.textContent = 'Tap the chart to read the values of a day.');
"""

CSS = """
:root{color-scheme:light dark;--band:#4a1626;--band-ink:#e4e6ea;--brass:#d0506c;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--vix:#2a5db0;--real:#c27a2c}
@media (prefers-color-scheme:dark){:root{--band:#33101b;--brass:#ec8098;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--vix:#6d9be0;--real:#d99a52}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 "DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
h1,h2,.kpi b{font-family:"DM Serif Display",Georgia,serif;font-weight:400}
a{color:inherit}
.in{max-width:1000px;margin:0 auto;padding:0 max(20px,env(safe-area-inset-right)) 0 max(20px,env(safe-area-inset-left))}
.band{background:var(--band);color:var(--band-ink);padding:8px 0 96px}
a.back{display:inline-flex;align-items:center;min-height:44px;color:var(--band-ink);text-decoration:none;font-size:14px}
a.back:hover{color:#fff}
.eyebrow{margin:24px 0 12px;color:var(--brass);font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}
h1{margin:0;color:#fff;font-size:clamp(32px,5.5vw,50px);line-height:1.08;max-width:20ch}
.answer{margin:18px 0 0;max-width:68ch}
.answer b{color:#fff}
.meta{margin:14px 0 0;font-size:13px;opacity:.75}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.kpis.top{margin-top:-64px}
.kpi{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:16px 18px}
.top .kpi{box-shadow:0 14px 34px rgba(0,0,0,.10)}
.kpi b{display:block;font-size:30px;font-variant-numeric:tabular-nums}
.kpi span{display:block;font-size:13px;line-height:1.45;color:var(--ink-2)}
.panel{background:var(--surface);border:1px solid var(--grid);border-radius:14px;padding:28px;margin-top:20px}
.panel .tag{margin:0;color:var(--brass);font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
h2{margin:4px 0 2px;font-size:28px;line-height:1.15}
.dek{margin:0 0 18px;font-weight:700}
.how{background:var(--page);border-radius:10px;padding:12px 16px;margin:0 0 18px;font-size:15px;color:var(--ink-2)}
.how b,.so b{color:var(--ink)}
.so{border-left:3px solid var(--brass);padding:2px 0 2px 16px;margin:20px 0 0}
.so p{margin:0 0 8px}
.label{margin:0 0 4px;font-size:13px;font-weight:600;color:var(--ink-2)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.chart{width:100%;min-height:500px}
.gloss{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;margin:0}
.gloss div{margin:0}
.gloss dt{font-weight:700}
.gloss dd{margin:2px 0 0;color:var(--ink-2);font-size:15px}
.take{margin:0;padding-left:1.2rem}
.take li{margin:0 0 12px}
.take li::marker{color:var(--brass)}
.refs{margin:32px 0 0;padding:0 2px;color:var(--muted);font-size:13px;line-height:1.5}   /* quiet: no panel box, small muted text */
.refs-title{margin:0 0 2px;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
.refs ul{list-style:none;margin:0;padding:0}
.refs a{display:inline-flex;align-items:center;min-height:40px;padding:4px 0;color:var(--ink-2);   /* 40px tall: easy to tap */
  text-decoration:underline;text-decoration-color:var(--axis);text-underline-offset:3px}
.refs a:hover{color:var(--ink)}
@media (max-width:640px){.refs a{display:flex}.refs .sep{display:none}.refs li{margin:0 0 8px}}   /* phone: link on its own 40px line, what it gave just below */
/* Plotly's hover box: colours come from the tokens (set in LAB_JS); CSS adds the soft shadow and rounded corners */
#vol-chart .hoverlayer .hovertext,#vol-chart .hoverlayer .legend{filter:drop-shadow(0 4px 10px rgba(0,0,0,.18))}
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
@media (max-width:640px){.gloss{grid-template-columns:1fr;gap:18px}.chart{min-height:560px}.modebar-container{display:none}}  /* Plotly's toolbar icons are too small for a finger */
@media (pointer:coarse){.dragtip{display:none}}
"""

REFERENCES = [                            # (source name = the link text, what it gave us, link) for the data and the companion page
    ("Yahoo Finance, ^GSPC", "daily S&P 500 closes, downloaded with yfinance", "https://finance.yahoo.com/quote/%5EGSPC/"),
    ("Yahoo Finance, ^VIX", "daily VIX closes, downloaded with yfinance", "https://finance.yahoo.com/quote/%5EVIX/"),
    ("Was the VIX right about four market shocks?", "companion page: the VIX around four crashes (VIX/shocks.py)",
     "shocks.html"),
]

GLOSSARY = [                              # (term, plain-language meaning): the ideas a reader needs for the chart
    ("VIX (implied volatility)", "The market's expectation of S&amp;P 500 volatility over roughly the next month, read from "
                                 "option prices and quoted as an annualized %."),
    (f"Realized volatility, next {FORWARD_HORIZON}d",
     f"What volatility actually turned out to be: the standard deviation of the S&amp;P 500's daily returns over the "
     f"{FORWARD_HORIZON} trading days AFTER each date, the fair comparison for a forward-looking measure like the VIX. "
     f"A backward rolling standard deviation would look the wrong way."),
    ("Log return", "ln(today / yesterday). Used instead of the simple % change because log returns add up over time and "
                   "treat gains and losses symmetrically, which is what the annualization math assumes."),
    ("Annualizing", f"Daily volatility x &radic;{TRADING_DAYS_PER_YEAR} (trading days in a year) x 100, so it is in the same "
                    f"units as the VIX."),
    ("Bias", "The average gap, VIX - realized. Positive: the VIX overpriced volatility on average."),
    ("RMSE", "Root mean squared error: the typical size of the gap in either direction. Big misses weigh more."),
]


def tile(value, label):
    """One headline number with its label."""
    html = f'<div class="kpi"><b>{escape(value)}</b><span>{escape(label)}</span></div>'  # escape() keeps odd characters from breaking the HTML
    # RETURNS a str of HTML, e.g. '<div class="kpi"><b>+3.80</b><span>Average gap, VIX - realized (pts)</span></div>'
    return html


def panel(number, question, finding, how, body, so=""):
    """One numbered section: a question, its one-line finding, how to read it, the chart or list, and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""          # optional reading guide
    so_html = f'<div class="so">{so}</div>' if so else ""                                  # optional takeaway
    # RETURNS a str of HTML, e.g. '<section class="panel"><p class="tag">01</p><h2>Was the VIX above or below ...?</h2>
    #  <p class="dek">On average +3.80 points above ...</p><p class="how">...</p>...</section>'
    return (f'<section class="panel"><p class="tag">{number:02d}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def references():
    """The quiet 'References' block after the last panel: small muted lines, no panel box, no question heading."""
    items = ""                                                 # the <li> lines, built one by one
    for name, gave, url in REFERENCES:
        new_tab = ' target="_blank" rel="noopener"' if url.startswith("http") else ""  # outside sites in a new tab, our own page in the same tab
        items += (f'<li><a href="{escape(url)}"{new_tab}>{escape(name)}</a>'  # the source name is the link (40px tall via CSS)
                  f'<span class="sep"> &middot; </span>{escape(gave)}</li>')           # then, in plain muted text, what it gave us
    html = (f'<aside class="refs" aria-label="References"><p class="refs-title">References</p>'  # small uppercase label, not a question
            f'<ul>{items}</ul></aside>')                       # the lines themselves
    # RETURNS a str of HTML (about 600 characters): an <aside> with a small label and a <ul> of 3 lines, e.g.
    # '<aside class="refs" aria-label="References"><p class="refs-title">References</p><ul>
    #  <li><a href="https://finance.yahoo.com/quote/%5EGSPC/" target="_blank" rel="noopener">Yahoo Finance, ^GSPC</a>
    #      <span class="sep"> &middot; </span>daily S&amp;P 500 closes, downloaded with yfinance</li>
    #  ... ^VIX line ...
    #  <li><a href="shocks.html">Was the VIX right about four market shocks?</a> &middot; companion page: ...</li></ul></aside>'
    return html


def answer_text(bias, rmse, vix_aligned):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    start, end = vix_aligned.index[0].year, vix_aligned.index[-1].year   # first and last year scored
    if bias > 0:                                               # the VIX sat above what followed, on average
        lead = "<b>Yes, on average.</b> "
    else:                                                      # it sat below
        lead = "<b>No, on average it underpriced it.</b> "
    text = (lead + f"From {start} to {end} the VIX sat {abs(bias):.2f} points {'above' if bias > 0 else 'below'} the volatility the S&amp;P 500 actually "
            f"had over the next {FORWARD_HORIZON} trading days. A typical miss, in either direction, was about {rmse:.2f} "
            f"points, so on any given day it could be far off both ways.")
    # RETURNS a str of HTML, e.g. '<b>Yes, on average.</b> From 1996 to 2026 the VIX sat 3.80 points above the volatility
    #  the S&amp;P 500 actually had over the next 21 trading days. A typical miss, in either direction, was about 8.16 points, ...'
    return text


def conclusions(bias, rmse, vix_aligned):
    """The 'What did we learn?' list, written from the numbers."""
    side = "above" if bias > 0 else "below"                    # which side of reality the VIX sat on, on average
    items = [
        (f"<b>On average the VIX sat {side} what followed</b>, by {abs(bias):.2f} points over {len(vix_aligned):,} trading days."),
        (f"<b>The misses are bigger than the average.</b> The typical miss (RMSE {rmse:.2f}) is larger than the average gap "
         f"({bias:+.2f}): on a given day the VIX can be well off in either direction."),
        ("<b>The average hides the shocks.</b> Around big sell-offs the VIX was often too low, not too high: see the "
         "companion page on four market shocks."),
        (f"<b>Limits.</b> One average over three decades mixes calm and crisis years. Realized volatility uses daily closes "
         f"only, and {FORWARD_HORIZON} trading days is close to, but not exactly, the VIX's one-month window. The last "
         f"{FORWARD_HORIZON} days cannot be scored yet: their future has not happened."),
    ]
    # RETURNS a list of 4 HTML strings, e.g.
    # ['<b>On average the VIX sat above what followed</b>, by 3.80 points over 7,524 trading days.',
    #  '<b>The misses are bigger than the average.</b> The typical miss (RMSE 8.16) is larger than the average gap (+3.80): ...', ...]
    return items


def build_page(prices, vix_aligned, forward_vol_aligned, bias, rmse):
    """Draw the chart and write the whole Lab page to VIX/output/volatility.html."""
    fig = build_figure(vix_aligned, forward_vol_aligned)       # the Plotly chart (two lines)
    names = {"wide": [VIX_NAME, REALIZED_NAME], "narrow": NARROW_NAMES}   # legend labels for desktop and phone
    chart_html = fig.to_html(full_html=False,                 # only the chart <div> and its script, not a whole page
                             include_plotlyjs="cdn",           # load plotly.js from its CDN instead of embedding 3.5 MB
                             div_id=CHART_ID,                  # a fixed id, so LAB_JS can find the chart
                             config={"responsive": True,       # the chart resizes with the window (and when a phone is rotated)
                                     "displaylogo": False,     # no Plotly logo in the toolbar
                                     "scrollZoom": False},     # the mouse wheel / finger scrolls the page, never zooms the chart
                             post_script=LAB_JS.replace("__NAMES__", json.dumps(names)))  # Lab colours + phone layout, run once drawn
    n_days = len(vix_aligned)                                  # days scored
    first, last = vix_aligned.index[0], vix_aligned.index[-1]  # first and last scored date
    kpis = "".join([                                           # the four headline numbers under the header
        tile(f"{bias:+.2f}", "Average gap, VIX - realized (pts)"),
        tile(f"{rmse:.2f}", "Typical miss, RMSE (pts)"),
        tile(f"{n_days:,}", f"Trading days scored, {first:%b %Y} to {last:%b %Y}"),
        tile(f"{prices.iloc[-1]:,.0f}", f"S&P 500 last close, {prices.index[-1]:%d %b %Y}"),
    ])
    gloss = '<dl class="gloss">' + "".join(f"<div><dt>{t}</dt><dd>{d}</dd></div>" for t, d in GLOSSARY) + "</dl>"
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in conclusions(bias, rmse, vix_aligned)) + "</ol>"

    panels = "".join([
        panel(1, "Was the VIX above or below the volatility that followed?",
              f"On average {abs(bias):.2f} points {'above' if bias > 0 else 'below'}, over {n_days:,} trading days.",
              f"Solid line: the VIX on each date, the market's expectation. Dashed line: the volatility the S&amp;P 500 "
              f"actually had over the {FORWARD_HORIZON} trading days after that date, annualized, in %. Where the solid line "
              f"is above the dashed one, the VIX overpriced volatility. <span class=\"dragtip\">Drag across the chart to zoom "
              f"into a period; double-click to zoom back out.</span>",   # dragtip: hidden on touch screens, where drag-zoom is off
              f'<p class="label">{escape(TICKER)}: VIX vs subsequent realized volatility</p>'
              f'<div class="chart">{chart_html}</div>'
              '<p class="note hint">Hover over the chart to read the values of a day.</p>',
              f"<p>VIX(t) is a claim about the ~{FORWARD_HORIZON} days AFTER date t, so it is scored against realized "
              f"volatility computed from the {FORWARD_HORIZON} days after t, not the {FORWARD_HORIZON} days before, which "
              f"would compare it to the wrong time window. That is also why the chart stops {FORWARD_HORIZON} trading days "
              f"before the last price, on {last:%d %b %Y}: the days after have no full future yet.</p>"),
        panel(2, "How do we score a forecast?", f"Two numbers: the average gap ({bias:+.2f}) and the typical miss ({rmse:.2f}).",
              "", gloss),
        panel(3, "What did we learn?", "Four takeaways.", "", take),  # always the last panel
    ])

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>VIX vs Realized Volatility</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="band"><div class="in">
<a class="back" href="../../index.html">&larr; Macro Quant Lab</a>
<p class="eyebrow">VIX vs realized volatility</p>
<h1>Does the VIX overprice volatility?</h1>
<p class="answer">{answer_text(bias, rmse, vix_aligned)}</p>
<p class="meta">Daily data {prices.index[0]:%b %Y} to {prices.index[-1]:%d %b %Y} · S&amp;P 500 ({escape(TICKER)}) and VIX
({escape(VIX_TICKER)}) from Yahoo Finance · Not investment advice</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{panels}
{references()}
</main>
<footer><div class="in">Generated by VIX/volatility.py from Yahoo Finance daily closes. Learning project, not investment advice.</div></footer>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # save the page
    print(f"Page saved to {OUTPUT_PATH}")                      # tell the user where the file is
    # RETURNS None (nothing). The result is the file VIX/output/volatility.html (about 500 KB: the page text plus the
    # 2 x 7,524 chart points; plotly.js itself comes from its CDN), and this line in the terminal:
    # Page saved to VIX/output/volatility.html (full path of your own machine)
    return None


if __name__ == "__main__":                # True only when you run this file directly (python volatility.py), not when another file imports it
    main()                                # so importing the functions (as shocks.py does) has no side effects
