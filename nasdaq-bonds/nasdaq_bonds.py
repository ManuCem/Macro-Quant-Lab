"""
Do bond yields and the Nasdaq 100 move together? Is money rotating between big tech and bonds?
-----------------------------------------------------------------------------------------------
Two textbook stories pull in opposite directions:

    1. "Rate fear"   yields UP   -> tech DOWN.
       A tech company's value sits mostly in profits far in the future. Those profits are
       discounted back to today with an interest rate, so a higher yield shrinks their value
       today. Daily Nasdaq returns and daily yield changes are then NEGATIVELY correlated.

    2. "Rotation"    tech DOWN   -> money goes INTO bonds -> bond prices UP -> yields DOWN.
       Investors sell tech and park the money in Treasuries (a "flight to safety"), and the
       reverse on good days. Nasdaq returns and yield changes are then POSITIVELY correlated,
       and Nasdaq returns and bond PRICES are negatively correlated.

Which story is in charge changes over time, so the key tool is a ROLLING correlation:
the correlation measured only over the last 20 or 60 trading days, recomputed every day.

    correlation = a number between -1 and +1: +1 = always move the same way, -1 = always opposite,
                  0 = no linear link.
    1 basis point (bp) = 0.01 percentage point of yield; a yield going 4.99% -> 5.09% is +10 bp.

Data (Yahoo Finance via yfinance, free, no key), daily closes, last 6 years:
    ^NDX  Nasdaq 100 index (the 100 biggest non-financial Nasdaq companies, mostly big tech)
    ^TNX  US 10-year Treasury yield, in %
    TLT   iShares 20+ Year Treasury Bond ETF: "owning long bonds" (its price moves opposite to yields)

Output: nasdaq-bonds/nasdaq_bonds.html (one standalone page, drawn with Apache ECharts).
        nasdaq-bonds/csv/nasdaq_bonds.csv (one row per trading day: closes and daily moves).

Run:
    pip install yfinance pandas numpy
    python nasdaq-bonds/nasdaq_bonds.py

Layout of this file (see CLAUDE.md):
    1. python / data code  -> settings, download, calculations, and def main()
    2. html / chart code   -> builds the web page and the charts

Not investment advice.
"""

import json                               # turns Python lists/dicts into text the browser's JavaScript can read
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import numpy as np                        # maths on arrays (the regression slope)
import pandas as pd                       # tables (DataFrames) and time series
import yfinance as yf                     # free daily prices from Yahoo Finance


# ===========================================================================
# python / data code
# ===========================================================================

HERE = Path(__file__).parent                                   # the nasdaq-bonds folder
OUTPUT_PATH = HERE / "nasdaq_bonds.html"                       # the web page we write
CSV_PATH = HERE / "csv" / "nasdaq_bonds.csv"                   # a copy of the daily table

# Yahoo ticker -> short column name used everywhere below
TICKERS = {"^NDX": "nasdaq", "^TNX": "y10", "TLT": "bonds"}
HISTORY = "6y"                            # 6 years: 5 years of rolling correlation after the first 60-day warm-up
WINDOWS = {"Last 20 days": 20, "Last 60 days": 60, "Last year": 250}   # look-back windows, in trading days (~1 month, ~3 months, ~1 year)
ROLL_LONG = 60                            # long rolling window: ~3 months of trading days, smooth
ROLL_SHORT = 20                           # short rolling window: ~1 month, reacts fast ("the last days")
SCATTER_DAYS = 60                         # how many recent days the scatter plot and the biggest-days table look at
TOP_DAYS = 8                              # how many of the biggest Nasdaq days to list
LINK_THRESHOLD = 0.2                      # |correlation| below 0.2 is treated as "no clear link"
DAY_TYPES = ["Into tech", "Into bonds", "Both up", "Both down"]   # the four kinds of day (see classify_day)


def fetch_closes():
    """Download daily closes of the four assets and line them up on common trading days."""
    raw = yf.download(list(TICKERS), period=HISTORY, auto_adjust=True, progress=False)  # one table, columns grouped by field
    closes = raw["Close"].rename(columns=TICKERS)              # keep the closing prices; ^NDX -> nasdaq, etc.
    closes = closes[list(TICKERS.values())]                    # fixed column order: nasdaq, y10, bonds
    closes = closes.dropna()                                   # keep only days where all three have a price
    closes.index = pd.to_datetime(closes.index).tz_localize(None)  # plain dates, no time zone, so they print and slice cleanly
    closes.index.name = "Date"                                 # name the index for the CSV header
    closes.columns.name = None                                 # drop the leftover "Ticker" label above the column names
    ny_now = pd.Timestamp.now(tz="America/New_York")           # current time on Wall Street
    if closes.index[-1].date() == ny_now.date() and ny_now.hour < 17:   # today's row exists but the session has not closed yet
        closes = closes.iloc[:-1]                              # drop it: an intraday price is not a close and changes every minute
    # returns a DataFrame, one row per closed trading day (1,506 rows x 3 columns, 30 Oct 2020 - 29 Oct 2026);
    # nasdaq in index points, y10 in %, bonds = TLT price in $ (adjusted for its monthly payouts):
    #                   nasdaq    y10      bonds
    # Date
    # 2026-10-27  29651.439453  4.993  81.629997
    # 2026-10-28  29813.160156  5.045  80.989998
    # 2026-10-29  29402.509766  4.989  81.489998
    return closes


def daily_moves(closes):
    """Turn closes into daily moves: % for the two prices, basis points for the yield."""
    moves = pd.DataFrame(index=closes.index)                   # empty table on the same dates
    moves["nasdaq"] = closes["nasdaq"].pct_change() * 100      # Nasdaq 100 daily return, in %
    moves["y10_bp"] = closes["y10"].diff() * 100               # 10y yield change in bp (4.99% -> 5.05% = +6 bp)
    moves["bonds"] = closes["bonds"].pct_change() * 100        # TLT daily return, in % (rises when yields fall)
    moves = moves.dropna()                                     # the first day has no previous close, drop it
    # returns a DataFrame, one row per trading day (1,505 rows x 3 columns), all daily moves (rounded here):
    #             nasdaq  y10_bp  bonds
    # Date
    # 2026-10-27    1.29     0.7  -0.06
    # 2026-10-28    0.55     5.2  -0.78
    # 2026-10-29   -1.38    -5.6   0.62
    return moves


def rolling_correlations(moves):
    """Correlation between Nasdaq returns and yield changes, recomputed every day over the last 60 and 20 days."""
    roll = pd.DataFrame(index=moves.index)                     # empty table on the same dates
    roll["corr60"] = moves["nasdaq"].rolling(ROLL_LONG).corr(moves["y10_bp"])   # ~3-month correlation, slow and stable
    roll["corr20"] = moves["nasdaq"].rolling(ROLL_SHORT).corr(moves["y10_bp"])  # ~1-month correlation, fast and noisy
    roll = roll.dropna()                                       # the first 60 days have no full window yet
    roll = roll.loc[roll.index[-1] - pd.DateOffset(years=5):]  # keep the last 5 years for the chart
    # returns a DataFrame, one row per trading day over 5 years (1,255 rows x 2 columns), between -1 and +1 (rounded here):
    #             corr60  corr20
    # Date
    # 2026-10-27   -0.01    0.58
    # 2026-10-28    0.07    0.59
    # 2026-10-29    0.09    0.63
    return roll


def link_label(corr):
    """Name the regime a Nasdaq-vs-yield correlation points to."""
    if corr > LINK_THRESHOLD:                                  # stocks and yields rise together
        label = "Rotation"                                     # money moves between bonds and tech
    elif corr < -LINK_THRESHOLD:                               # yields up, stocks down
        label = "Rate fear"                                    # higher yields hurt tech valuations
    else:                                                      # in between
        label = "No clear link"
    # returns a str, one of 3 labels, e.g. link_label(0.63) -> 'Rotation', link_label(0.09) -> 'No clear link', link_label(-0.67) -> 'Rate fear'
    return label


def window_stats(closes, moves):
    """For each look-back window: correlations, sensitivity of the Nasdaq to yields, and how tech, yields and bonds performed."""
    rows = []                                                  # one dict per window, turned into a table at the end
    for name, days in WINDOWS.items():                         # e.g. ("Last 20 days", 20)
        m = moves.tail(days)                                   # the last `days` daily moves
        c = closes.iloc[-(days + 1):]                          # days + 1 closes, so first->last spans exactly `days` moves
        slope = np.polyfit(m["y10_bp"], m["nasdaq"], 1)[0]     # best-fit line nasdaq% = slope * yield_bp + b; slope in % per 1 bp
        rows.append({
            "window": name,                                    # row label
            "days": days,                                      # number of trading days
            "corr_yield": m["nasdaq"].corr(m["y10_bp"]),       # Nasdaq returns vs yield changes
            "per_10bp": slope * 10,                            # Nasdaq % move on a typical +10 bp yield day, in this window
            "corr_bonds": m["nasdaq"].corr(m["bonds"]),        # Nasdaq returns vs long-bond (TLT) returns
            "nasdaq_pct": (c["nasdaq"].iloc[-1] / c["nasdaq"].iloc[0] - 1) * 100,  # Nasdaq total change over the window, %
            "y10_bp": (c["y10"].iloc[-1] - c["y10"].iloc[0]) * 100,                # 10y yield change over the window, bp
            "bonds_pct": (c["bonds"].iloc[-1] / c["bonds"].iloc[0] - 1) * 100,     # TLT total change, %
            "same_dir": ((m["nasdaq"] > 0) == (m["y10_bp"] > 0)).mean() * 100,     # % of days Nasdaq and yield moved the same way
        })
    table = pd.DataFrame(rows).set_index("window").round(2)   # windows as rows, 2 decimals
    table["regime"] = table["corr_yield"].apply(link_label)    # name the regime of each window
    # returns a DataFrame, 3 rows x 9 columns (real output, data up to 29 Oct 2026):
    #               days  corr_yield  per_10bp  corr_bonds  nasdaq_pct  y10_bp  bonds_pct  same_dir         regime
    # window
    # Last 20 days    20        0.63      1.40       -0.61       -3.60   -24.8       4.86      75.0       Rotation
    # Last 60 days    60        0.09      0.19       -0.04       -0.29    37.2      -1.05      55.0  No clear link
    # Last year      250       -0.18     -0.53        0.19       14.25    89.6      -5.84      48.8  No clear link
    return table


def regime_history(roll):
    """Headline facts about the 60-day correlation over the last 5 years."""
    corr = roll["corr60"]                                      # the slow correlation line
    history = {                                                # one flat dict, easy to print and to show in the text
        "start": corr.index[0].strftime("%b %Y"),              # first month on the chart
        "share_positive": round(float((corr > 0).mean() * 100), 1),        # % of days the link was positive (rotation side)
        "avg_2022": round(float(corr.loc["2022"].mean()), 2),              # 2022 = the Fed's fastest hikes in 40 years
        "low": round(float(corr.min()), 2), "low_date": corr.idxmin().strftime("%b %Y"),    # most negative reading
        "high": round(float(corr.max()), 2), "high_date": corr.idxmax().strftime("%b %Y"),  # most positive reading
        "latest60": round(float(corr.iloc[-1]), 2),                        # today's 60-day value
        "latest20": round(float(roll["corr20"].iloc[-1]), 2),              # today's 20-day value
        "last_date": corr.index[-1].strftime("%d %b %Y"),                  # last trading day in the data
    }
    # returns a dict of 10 values (real output, data up to 29 Oct 2026):
    # {'start': 'Oct 2021', 'share_positive': 42.9, 'avg_2022': -0.07, 'low': -0.67, 'low_date': 'Jun 2026',
    #  'high': 0.46, 'high_date': 'Apr 2025', 'latest60': 0.09, 'latest20': 0.63, 'last_date': '29 Oct 2026'}
    return history


def classify_day(nasdaq_pct, bonds_pct):
    """Name one trading day by which way tech and long bonds moved."""
    if nasdaq_pct > 0 and bonds_pct <= 0:                      # tech up, bonds down
        label = "Into tech"                                    # money left bonds for tech (risk-on)
    elif nasdaq_pct <= 0 and bonds_pct > 0:                    # tech down, bonds up
        label = "Into bonds"                                   # money left tech for bonds (flight to safety)
    elif nasdaq_pct > 0:                                       # both up
        label = "Both up"                                      # no rotation: everything rallied (e.g. yields fell on good news)
    else:                                                      # both down
        label = "Both down"                                    # no rotation: everything sold off (e.g. yields jumped)
    # returns a str, one of DAY_TYPES, e.g. classify_day(-2.9, 1.8) -> 'Into bonds'
    return label


def rotation_days(moves, days=ROLL_SHORT):
    """Count the four kinds of day over the last `days`, and what bonds did when tech fell."""
    m = moves.tail(days)                                       # the last `days` daily moves
    labels = [classify_day(n, b) for n, b in zip(m["nasdaq"], m["bonds"])]  # one label per day
    counts = pd.Series(labels).value_counts().reindex(DAY_TYPES, fill_value=0)  # count each type, fixed order, zeros kept
    down = m[m["nasdaq"] < 0]                                  # only the days the Nasdaq fell
    result = {
        "days": days,                                          # window length
        "counts": {k: int(v) for k, v in counts.items()},     # {'Into tech': 7, ...}
        "rotation_days": int(counts["Into tech"] + counts["Into bonds"]),   # days tech and bonds went opposite ways
        "down_days": int(len(down)),                           # how many Nasdaq down days
        "bonds_up_on_down": int((down["bonds"] > 0).sum()),    # on how many of those bonds rose (a cushion)
        "bonds_avg_on_down": round(float(down["bonds"].mean()), 2) if len(down) else 0.0,  # average TLT move on those days, %
        "nasdaq_avg_on_down": round(float(down["nasdaq"].mean()), 2) if len(down) else 0.0,  # average Nasdaq move on those days, %
    }
    # returns a dict of 7 values (real output, last 20 days to 29 Oct 2026):
    # {'days': 20, 'counts': {'Into tech': 5, 'Into bonds': 9, 'Both up': 4, 'Both down': 2}, 'rotation_days': 14,
    #  'down_days': 11, 'bonds_up_on_down': 9, 'bonds_avg_on_down': 0.57, 'nasdaq_avg_on_down': -1.05}
    return result


def biggest_days(moves, days=SCATTER_DAYS, top=TOP_DAYS):
    """The Nasdaq's biggest moves (up or down) of the last `days`, with what yields and bonds did that day."""
    m = moves.tail(days).copy()                                # the recent window (copy so we can add a column safely)
    biggest = m["nasdaq"].abs().sort_values(ascending=False).index[:top]   # dates of the `top` largest absolute moves
    table = m.loc[biggest].sort_index(ascending=False)         # those rows, newest first
    table["type"] = [classify_day(n, b) for n, b in zip(table["nasdaq"], table["bonds"])]  # label each day
    table = table.round(2)                                     # 2 decimals
    # returns a DataFrame, 8 rows x 4 columns (real output, first 3 of 8 rows):
    #             nasdaq  y10_bp  bonds        type
    # Date
    # 2026-10-22   -2.90   -19.3   1.87  Into bonds
    # 2026-10-16   -2.50     0.9   0.10  Into bonds
    # 2026-10-14   -2.02    -2.7   0.66  Into bonds
    return table


def save_csv(closes, moves):
    """Save closes and daily moves side by side in one CSV next to this script."""
    table = closes.join(moves.add_suffix("_move"))             # closes + moves on the same dates (moves renamed nasdaq_move, ...)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)         # create the csv folder if missing
    table.round(4).to_csv(CSV_PATH)                            # write it
    # returns nothing; writes csv/nasdaq_bonds.csv with 1,506 rows (the first, 2020-10-30, has empty moves), like
    # Date,nasdaq,y10,bonds,nasdaq_move,y10_bp_move,bonds_move
    # 2020-11-02,11084.7598,0.849,130.7625,0.2878,-1.1,0.749
    return None


def print_summary(stats, history, rotation, biggest):
    """Print the key numbers in the terminal."""
    print(f"Data up to {history['last_date']}")
    for name, r in stats.iterrows():                           # one line per look-back window
        print(f"  {name:<13} corr(Nasdaq, yield) {r['corr_yield']:+.2f} [{r['regime']}]  Nasdaq {r['per_10bp']:+.2f}% per +10 bp  "
              f"corr(Nasdaq, bonds) {r['corr_bonds']:+.2f}")
        print(f"  {'':<13} Nasdaq {r['nasdaq_pct']:+.1f}%  10y {r['y10_bp']:+.0f} bp  bonds {r['bonds_pct']:+.1f}%")
    print(f"60-day correlation since {history['start']}: positive {history['share_positive']}% of days, "
          f"2022 average {history['avg_2022']:+.2f}, low {history['low']:+.2f} ({history['low_date']}), high {history['high']:+.2f} ({history['high_date']})")
    print(f"Last {rotation['days']} days: {rotation['counts']}  -> Nasdaq fell on {rotation['down_days']} days; "
          f"bonds rose on {rotation['bonds_up_on_down']}")
    print("Biggest Nasdaq days of the last 60:")
    print(biggest.to_string())
    # returns nothing; prints ~20 lines, e.g.
    # Data up to 29 Oct 2026
    #   Last 20 days  corr(Nasdaq, yield) +0.63 [Rotation]  Nasdaq +1.40% per +10 bp  corr(Nasdaq, bonds) -0.61
    #                 Nasdaq -3.6%  10y -25 bp  bonds +4.9%
    #   ... (Last 60 days, Last year)
    # 60-day correlation since Oct 2021: positive 42.9% of days, 2022 average -0.07, low -0.67 (Jun 2026), high +0.46 (Apr 2025)
    # Last 20 days: {'Into tech': 5, 'Into bonds': 9, 'Both up': 4, 'Both down': 2}  -> Nasdaq fell on 11 days; bonds rose on 9
    #   ... (then the biggest-days table)
    return None


def main():
    closes = fetch_closes()                                    # step 1: download the three daily series
    moves = daily_moves(closes)                                # step 2: daily % moves and yield changes in bp
    save_csv(closes, moves)                                    # step 3: keep a copy of the data
    roll = rolling_correlations(moves)                         # step 4: 60- and 20-day rolling correlation
    stats = window_stats(closes, moves)                        # step 5: correlations and performance per window
    history = regime_history(roll)                             # step 6: 5-year facts about the correlation
    rotation = rotation_days(moves)                            # step 7: count rotation days in the last 20
    biggest = biggest_days(moves)                              # step 8: the biggest recent Nasdaq days
    print_summary(stats, history, rotation, biggest)           # step 9: print the numbers
    build_page(closes, moves, roll, stats, history, rotation, biggest)  # step 10: write the web page (code below)
    print(f"Saved {OUTPUT_PATH}")                              # tell the user where the page is


# ===========================================================================
# html / chart code
# ===========================================================================

ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"  # Apache ECharts, a fixed version
PERF_DAYS = 252                           # the performance charts can show up to 1 year of trading days
FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"

# Look: the "Lab" design every project page uses (see CLAUDE.md): green header band, brass accents, white panels,
# the same fonts as the homepage. Colours: one fixed hue per asset, Nasdaq = blue, long bonds = green, 10y yield = amber.
# Text always uses the ink tokens and names the asset in words, never colour alone.
CSS = """
:root{color-scheme:light dark;--band:#142a4f;--band-ink:#e4e6ea;--brass:#4a7fe0;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--nq:#2a5db0;--bd:#1f7a55;--y10:#c27a2c;--zone-rot:rgba(31,122,85,.08);--zone-fear:rgba(194,122,44,.09)}
@media (prefers-color-scheme:dark){:root{--band:#0d1d38;--brass:#7fa8f0;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--nq:#6d9be0;--bd:#3fa37c;--y10:#d99a52;--zone-rot:rgba(63,163,124,.13);--zone-fear:rgba(217,154,82,.13)}}
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
.kpi span{font-size:13px;color:var(--ink-2)}
.panel{background:var(--surface);border:1px solid var(--grid);border-radius:14px;padding:28px;margin-top:20px}
.panel .tag{margin:0;color:var(--brass);font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
h2{margin:4px 0 2px;font-size:28px;line-height:1.15}
.dek{margin:0 0 18px;font-weight:700}
.how{background:var(--page);border-radius:10px;padding:12px 16px;margin:0 0 18px;font-size:15px;color:var(--ink-2)}
.how b,.so b{color:var(--ink)}
.so{border-left:3px solid var(--brass);padding:2px 0 2px 16px;margin:20px 0 0}
.so p{margin:0 0 8px}
.panel .kpi{background:var(--page);border:0}
.chart{width:100%;height:340px}
.chart.short{height:190px}
.label{margin:18px 0 4px;font-size:13px;font-weight:600;color:var(--ink-2)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle}
.periods{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
.periods button{min-height:44px;min-width:52px;padding:0 12px;border:1px solid var(--grid);border-radius:999px;
  background:transparent;color:var(--ink-2);font:inherit;font-size:14px;font-weight:600;cursor:pointer}
.periods button[aria-pressed=true]{background:var(--ink);color:var(--page);border-color:var(--ink)}
.stories{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.story{border-top:3px solid var(--c);padding-top:12px}
.story h3{margin:0 0 4px;font-size:17px}
.story p{margin:0 0 8px;color:var(--ink-2);font-size:15px}
.gloss{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;margin:24px 0 0;padding-top:20px;border-top:1px solid var(--grid)}
.gloss div{margin:0}
.gloss dt{font-weight:700}
.gloss dd{margin:2px 0 0;color:var(--ink-2);font-size:15px}
.take{margin:0;padding-left:1.2rem}
.take li{margin:0 0 12px}
.take li::marker{color:var(--brass)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--surface);padding-left:0}
th{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.refs{margin:32px 0 0;padding:0 4px;font-size:13px;line-height:1.5;color:var(--muted)}
.refs h3{margin:0 0 2px;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.refs ul{list-style:none;padding:0;margin:0}
.refs a{display:flex;align-items:center;min-height:44px;padding:6px 0;color:var(--muted);text-decoration:none}
.refs b{font-weight:600;color:var(--ink-2);text-decoration:underline;text-decoration-color:var(--axis);text-underline-offset:3px}
.refs a:hover span{text-decoration:underline}
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
@media (max-width:640px){
  .chart{height:420px}.chart.short{height:260px}
  .stories,.gloss{grid-template-columns:1fr;gap:18px}
  th,td{padding:8px 4px;font-size:13px}th{white-space:normal}
  .metrics td{white-space:normal}.metrics td:first-child,.metrics th:first-child{position:static}
  .days td:last-child{white-space:normal;text-align:left}
}
"""

JS = """
const DATA = __DATA__;                                          // everything Python computed, as JSON
const narrowMQ = window.matchMedia("(max-width: 640px)");       // true on a phone-width screen
const isTouch = window.matchMedia("(pointer: coarse)").matches; // a finger instead of a mouse
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();  // read a colour token
const sliderStyle = () => ({                                   // zoom slider in the page colours (the ECharts default bar is light grey and glares in dark mode)
  backgroundColor: "transparent", fillerColor: "rgba(128,128,128,.16)",
  handleStyle: {color: css("--surface"), borderColor: css("--axis")},
  moveHandleStyle: {color: css("--axis"), opacity: 1},
  emphasis: {handleStyle: {borderColor: css("--muted")}, moveHandleStyle: {color: css("--muted")}},
  dataBackground: {lineStyle: {color: css("--axis")}, areaStyle: {color: css("--grid")}},
  selectedDataBackground: {lineStyle: {color: css("--muted")}, areaStyle: {color: css("--axis"), opacity: .35}},
});
const INSTANCES = {};                                           // chart div id -> ECharts instance
let PERIOD = 63;                                                // trading days shown in the first two charts (3 months)
const sign = (v, d) => (v > 0 ? "+" : v < 0 ? "\\u2212" : "") + Math.abs(v).toFixed(d);  // +1.2 / \\u22121.2 with a real minus sign

function tipStyle() {                                           // tooltip look from the page tokens, never ECharts' default white box
  return {
    backgroundColor: css("--surface"),                          // white in light mode, near-black in dark mode
    borderColor: css("--grid"), borderWidth: 1,                 // the same thin border as the panels
    textStyle: {color: css("--ink"), fontFamily: "DM Sans, system-ui, sans-serif", fontSize: 13},  // readable text in both modes
    extraCssText: "box-shadow: 0 6px 20px rgba(0,0,0,.18); border-radius: 8px;",                    // a soft shadow lifts it off the chart
    axisPointer: {label: {backgroundColor: css("--ink-2"), color: css("--surface")}},              // any axis-pointer label uses the tokens too
  };
}

function base(narrow) {                                         // options shared by every chart
  return {
    animation: false, backgroundColor: "transparent", textStyle: {color: css("--ink-2")},
    legend: narrow ? {bottom: 4, left: 12, orient: "vertical", itemGap: 6, textStyle: {color: css("--ink-2")}}  // below the plot on a phone
                   : {top: 6, left: 56, textStyle: {color: css("--ink-2")}},   // one row above the plot on desktop
    tooltip: Object.assign(tipStyle(),                          // themed box (rebuilt by drawAll, so it follows a theme change)
      {trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click", confine: true}),           // tap on touch screens
  };
}
const ax = extra => Object.assign({axisLine: {lineStyle: {color: css("--axis")}}, splitLine: {lineStyle: {color: css("--grid")}},
                                  axisLabel: {color: css("--muted"), hideOverlap: true},
                                  // tooltip header on a time axis: "14 Sep 2026" instead of ECharts' raw "2026-09-14 00:00:00"
                                  axisPointer: {label: {formatter: p => extra.type === "time"
                                    ? new Date(p.value).toLocaleDateString("en-GB", {day: "numeric", month: "short", year: "numeric"})
                                    : String(p.value)}}}, extra);
const window_ = () => {                                         // the slice of the 1-year data the period buttons select
  const n = DATA.perf.dates.length;                             // up to 253 closes
  const s = Math.max(0, n - 1 - PERIOD);                        // index of the first close in the window
  return {s, dates: DATA.perf.dates.slice(s)};
};
const rebased = key => { const w = window_(); const first = DATA.perf[key][w.s];   // % change since the first day of the window
  return w.dates.map((d, i) => [d, +(DATA.perf[key][w.s + i] / first * 100 - 100).toFixed(2)]); };

function perf(narrow) {                                         // Nasdaq and long bonds, both rebased to 0% on day one
  const o = base(narrow);
  o.grid = narrow ? {left: 44, right: 16, top: 16, bottom: 92} : {left: 56, right: 120, top: 44, bottom: 36};
  o.xAxis = ax({type: "time", splitNumber: narrow ? 3 : 6});
  o.yAxis = ax({type: "value", axisLabel: {color: css("--muted"), formatter: v => sign(v, 0) + "%"}});
  const line = (name, key, color) => ({name, type: "line", data: rebased(key), showSymbol: false, lineStyle: {color, width: 2},
    itemStyle: {color}, endLabel: {show: !narrow, color: css("--ink"), formatter: p => name.split(" (")[0] + " " + sign(p.value[1], 1) + "%"},
    labelLayout: {moveOverlap: "shiftY"}});                     // push end labels apart when two lines finish at the same level
  o.series = [line("Nasdaq 100", "nasdaq", css("--nq")), line("Long bonds (TLT)", "bonds", css("--bd"))];
  o.series[0].markLine = {silent: true, symbol: "none", label: {show: false}, lineStyle: {color: css("--axis")}, data: [{yAxis: 0}]};  // the 0% start line
  o.tooltip.valueFormatter = v => sign(v, 2) + "%";
  return o;
}

function yieldChart(narrow) {                                   // the 10-year yield over the same window, in %
  const o = base(narrow);
  o.legend = {show: false};                                     // a single series: the heading names it
  o.grid = narrow ? {left: 44, right: 16, top: 16, bottom: 30} : {left: 56, right: 120, top: 16, bottom: 30};
  o.xAxis = ax({type: "time", splitNumber: narrow ? 3 : 6});
  o.yAxis = ax({type: "value", scale: true, axisLabel: {color: css("--muted"), formatter: v => v.toFixed(1) + "%"}});
  const w = window_();
  const c = css("--y10");
  o.series = [{name: "10-year yield", type: "line", data: w.dates.map((d, i) => [d, DATA.perf.y10[w.s + i]]), showSymbol: false,
    lineStyle: {color: c, width: 2}, itemStyle: {color: c},
    endLabel: {show: !narrow, color: css("--ink"), formatter: p => "10y " + p.value[1].toFixed(2) + "%"}}];
  o.tooltip.valueFormatter = v => v.toFixed(2) + "%";
  return o;
}

function roll(narrow) {                                         // 60- and 20-day correlation, with the two regime zones shaded
  const o = base(narrow);
  o.grid = narrow ? {left: 40, right: 16, top: 16, bottom: 120} : {left: 52, right: 28, top: 44, bottom: 60};
  o.xAxis = ax({type: "time", splitNumber: narrow ? 3 : 6});
  o.yAxis = ax({type: "value", min: -1, max: 1, interval: 0.5});
  const pts = key => DATA.roll.dates.map((d, i) => [d, DATA.roll[key][i]]);
  o.series = [
    {name: "60-day correlation", type: "line", data: pts("corr60"), showSymbol: false, lineStyle: {color: css("--nq"), width: 2}, itemStyle: {color: css("--nq")}, z: 3,
     markArea: {silent: true, label: {color: css("--ink-2"), position: "insideTopLeft", fontSize: 12}, data: [   // short labels: long ones were cut off on a phone
       [{name: "Rotation zone", yAxis: DATA.threshold, itemStyle: {color: css("--zone-rot")}}, {yAxis: 1}],
       [{name: "Rate-fear zone", yAxis: -1, itemStyle: {color: css("--zone-fear")}, label: {position: "insideBottomLeft"}}, {yAxis: -DATA.threshold}]]},
     markLine: {silent: true, symbol: "none", label: {show: false}, lineStyle: {color: css("--axis")}, data: [{yAxis: 0}]}},
    {name: "20-day correlation (fast)", type: "line", data: pts("corr20"), showSymbol: false, lineStyle: {color: css("--muted"), width: 1}, itemStyle: {color: css("--muted")}},
  ];
  o.dataZoom = [{type: "slider", ...sliderStyle(), start: 0, end: 100, height: 22, bottom: narrow ? 66 : 8, borderColor: css("--grid"),
                 textStyle: {color: css("--muted")}, labelFormatter: v => new Date(v).getFullYear()}];
  if (!isTouch) o.dataZoom.push({type: "inside"});              // wheel / drag zoom would trap the finger on a phone
  o.tooltip.valueFormatter = v => v == null ? "-" : sign(v, 2);
  return o;
}

function scatter(narrow) {                                      // each dot = one day: yield change (x) against Nasdaq move (y)
  const o = base(narrow);
  o.grid = narrow ? {left: 44, right: 16, top: 16, bottom: 110} : {left: 56, right: 28, top: 44, bottom: 50};
  o.xAxis = ax({type: "value", name: "10y yield change, bp", nameLocation: "middle", nameGap: 26, nameTextStyle: {color: css("--muted")}});
  o.yAxis = ax({type: "value", axisLabel: {color: css("--muted"), formatter: v => sign(v, 0) + "%"}});
  const S = DATA.scatter, n = S.dates.length, recent = DATA.recentDays;
  const dot = i => ({value: [S.y10_bp[i], S.nasdaq[i]], date: S.dates[i]});
  const old = [], neu = [];
  for (let i = 0; i < n; i++) (i >= n - recent ? neu : old).push(dot(i));     // last 20 days vs the 40 before
  const xs = neu.map(p => p.value[0]), ys = neu.map(p => p.value[1]);
  const mx = xs.reduce((a, b) => a + b, 0) / xs.length, my = ys.reduce((a, b) => a + b, 0) / ys.length;
  const slope = DATA.slope20, icpt = my - slope * mx;            // best-fit line through the recent dots (slope from Python)
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  o.series = [
    {name: "Earlier " + (n - recent) + " days", type: "scatter", data: old, symbolSize: 8, itemStyle: {color: css("--axis")}},
    {name: "Last " + recent + " days", type: "scatter", data: neu, symbolSize: 10, itemStyle: {color: css("--nq"), borderColor: css("--surface"), borderWidth: 2}, z: 3},
    {name: "Trend, last " + recent + " days", type: "line", data: [[x0, slope * x0 + icpt], [x1, slope * x1 + icpt]], showSymbol: false,
     lineStyle: {color: css("--nq"), type: "dashed", width: 2}, itemStyle: {color: css("--nq")}, tooltip: {show: false}},
  ];
  o.tooltip = Object.assign(tipStyle(), {trigger: "item", triggerOn: isTouch ? "click" : "mousemove|click", confine: true,   // same themed box
    formatter: p => p.data.date + "<br>10y yield " + sign(p.value[0], 1) + " bp<br>Nasdaq 100 " + sign(p.value[1], 2) + "%"});
  return o;
}

const BUILDERS = {perf, y10: yieldChart, roll, scatter};        // chart div id -> function that builds its options
function drawAll() {                                            // (re)build every chart; called on load, rotation, theme and period change
  const narrow = narrowMQ.matches;
  document.querySelectorAll(".chart").forEach(div => {
    if (!INSTANCES[div.id]) INSTANCES[div.id] = echarts.init(div);
    INSTANCES[div.id].setOption(BUILDERS[div.id](narrow), true);
    INSTANCES[div.id].resize();
  });
}
document.querySelectorAll(".periods button").forEach(b => b.addEventListener("click", () => {   // 1M / 3M / 6M / 1Y buttons
  PERIOD = +b.dataset.days;
  document.querySelectorAll(".periods button").forEach(x => x.setAttribute("aria-pressed", x === b));
  drawAll();
}));
if (isTouch) document.querySelectorAll(".hint").forEach(h => h.textContent = "Tap");  // say "tap", not "hover", to touch users
narrowMQ.addEventListener("change", drawAll);                   // rebuild when a phone is rotated
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawAll);  // rebuild in the new colours
window.addEventListener("resize", () => Object.values(INSTANCES).forEach(c => c.resize()));
drawAll();
echarts.connect([INSTANCES.perf, INSTANCES.y10]);               // one tooltip across both stacked charts (same dates)
"""

SOURCES = [                               # (who and when, what it gave us, link): the data and the two press items, one quiet line each
    ("Yahoo Finance", "daily closes of the Nasdaq 100 (^NDX), the US 10-year Treasury yield (^TNX) and the "
     "iShares 20+ Year Treasury Bond ETF (TLT), downloaded with yfinance", "https://finance.yahoo.com/quote/%5ENDX/"),
    ("TheStreet Pro, 15 Oct 2026", "bonds are the new safe haven as money rotates out of tech, helped by their high yields",
     "https://pro.thestreet.com/market-commentary/bonds-are-the-new-safe-haven-as-money-rotates-out-of-tech"),
    ("roic.ai, 13 Oct 2026", "BofA fund-manager survey: 37% would move money from stocks into bonds if the 10-year yield "
     "reached about 6%; the tech overweight was the largest since August 2020",
     "https://www.roic.ai/news/bofa-survey-treasury-yields-near-6-would-trigger-shift-from-stocks-to-bonds-10-13-2026"),
]

GLOSSARY = [                              # (term, plain-language meaning): the ideas a reader needs for the charts below
    ("Correlation", "A number from −1 (always move opposite) to +1 (always move together); near 0 means no linear link. "
                    "Here it is measured on daily moves."),
    ("Basis point (bp)", "0.01 percentage point of yield. A yield going from 4.99% to 5.09% is +10 bp."),
    ("Long bonds (TLT)", "An ETF holding US Treasuries with 20+ years left to run. Its price rises when long-term yields fall."),
    ("Rolling window", "The same calculation repeated every day over only the most recent N days, so you can see the link change over time."),
]


def pct(value, digits=1):
    """Format a number with an explicit sign and a real minus sign, e.g. -3.85 -> '−3.9'."""
    text = f"{abs(value):.{digits}f}"                          # the size of the number, without its sign
    # returns a str, e.g. pct(-2.04) -> '−2.0', pct(4.49) -> '+4.5', pct(0) -> '0.0'
    return ("+" if value > 0 else "−" if value < 0 else "") + text


def tile(value, label, color=None):
    """One headline number with its label; an optional dot names the asset by its chart colour."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # identity is in the text too, never colour alone
    # returns a str of HTML, e.g. '<div class="kpi"><b><i class="dot" ...></i>−3.6%</b><span>Nasdaq 100, last 20 days</span></div>'
    return f'<div class="kpi"><b>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def answer_text(stats, rotation):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    s20, s60, s1y = stats.iloc[0], stats.iloc[1], stats.iloc[2]   # the three windows: 20 days, 60 days, 1 year
    if s20["regime"] == "Rotation":                            # the pattern the question is about
        lead = (f"<b>Yes, for now.</b> In the last {int(s20['days'])} trading days the Nasdaq 100 and the 10-year yield moved "
                f"together (correlation {pct(s20['corr_yield'], 2)}), so tech and long bonds moved in opposite directions. ")
    elif s20["regime"] == "Rate fear":                         # the classic story instead
        lead = (f"<b>No, it is rate fear.</b> In the last {int(s20['days'])} trading days rising yields went with a falling "
                f"Nasdaq (correlation {pct(s20['corr_yield'], 2)}). ")
    else:                                                      # neither
        lead = f"<b>No clear link right now</b> (correlation {pct(s20['corr_yield'], 2)} over the last {int(s20['days'])} trading days). "
    cushion = (f"Long bonds rose on {rotation['bonds_up_on_down']} of the {rotation['down_days']} days the Nasdaq fell. ")
    longer = (f"Over longer windows the link is weak: {pct(s60['corr_yield'], 2)} over 60 days, {pct(s1y['corr_yield'], 2)} over a year.")
    # returns a str of HTML, about 350 characters, e.g.
    # '<b>Yes, for now.</b> In the last 20 trading days the Nasdaq 100 and the 10-year yield moved together (correlation +0.63),
    #  ... Long bonds rose on 9 of the 11 days the Nasdaq fell. Over longer windows the link is weak: +0.09 over 60 days, −0.18 over a year.'
    return lead + cushion + longer


def window_text(stats):
    """Does the last-20-days pattern hold over 60 days and a year? Written from the regimes."""
    s20, s60, s1y = stats.iloc[0], stats.iloc[1], stats.iloc[2]   # the three windows
    if s20["regime"] == s60["regime"] == s1y["regime"]:        # same story in every window
        text = f"<b>Yes.</b> All three windows point to {s20['regime'].lower()}, so the pattern is not just a few weeks old."
    else:                                                      # the story changes with the window
        says = {"Rotation": "points to rotation", "Rate fear": "points to rate fear", "No clear link": "shows no clear link"}  # regime -> readable phrase
        text = (f"<b>No.</b> Over 60 days the correlation {says[s60['regime']]} ({pct(s60['corr_yield'], 2)}); over a year it "
                f"{says[s1y['regime']]} ({pct(s1y['corr_yield'], 2)}). What the last {int(s20['days'])} days show "
                f"({s20['regime'].lower()}, {pct(s20['corr_yield'], 2)}) is recent, and a short window can swing quickly.")
    # returns a str of HTML, e.g. '<b>No.</b> Over 60 days the correlation shows no clear link (+0.09); over a year it shows no clear link (−0.18). ...'
    return text


def conclusions(stats, history, rotation):
    """The 'What did we learn?' list, written from the numbers."""
    s20 = stats.iloc[0]                                        # the last-20-days row
    first = {                                                  # the headline lesson depends on today's regime
        "Rotation": "<b>Right now money is rotating.</b> On tech's bad days investors bought Treasuries, pushing bond prices up and yields down.",
        "Rate fear": "<b>Right now it is rate fear.</b> Rising yields are hurting tech valuations day by day.",
        "No clear link": "<b>Right now there is no clear link</b> between daily tech moves and yield changes.",
    }[s20["regime"]]
    items = [
        first,
        (f"<b>Bonds worked as a cushion:</b> they rose on {rotation['bonds_up_on_down']} of the {rotation['down_days']} days the "
         f"Nasdaq fell (average {pct(rotation['bonds_avg_on_down'], 2)}% vs {pct(rotation['nasdaq_avg_on_down'], 2)}% for the Nasdaq)."),
        (f"<b>The link is not stable.</b> Since {history['start']} the 60-day correlation was positive on "
         f"{history['share_positive']:.0f}% of days, ranging from {pct(history['low'], 2)} ({history['low_date']}) to "
         f"{pct(history['high'], 2)} ({history['high_date']}). Which story wins changes every few months."),
        (f"<b>\"Yields up, tech down\" is a slow story.</b> Even in 2022, the year of the Fed's fastest hikes, the daily correlation "
         f"averaged only {pct(history['avg_2022'], 2)}. Rates hit tech through the level of yields over months, not day by day."),
        ("<b>Limits.</b> Correlation shows how things moved together, not what caused what. Twenty days is a small sample: "
         "one busy week can flip it."),
    ]
    # returns a list of 5 HTML strings, e.g.
    # ['<b>Right now money is rotating.</b> On tech's bad days ...', '<b>Bonds worked as a cushion:</b> they rose on 9 of the 11 days ...', ...]
    return items


def metrics_table(stats):
    """Every window number in one table: rows = measures, columns = windows (3 columns fit a phone)."""
    rows = [                                                   # (row label, column in stats, formatter)
        ("Correlation: Nasdaq vs 10y yield", "corr_yield", lambda v: pct(v, 2)),
        ("Nasdaq move on a +10 bp yield day", "per_10bp", lambda v: pct(v, 2) + "%"),
        ("Correlation: Nasdaq vs long bonds", "corr_bonds", lambda v: pct(v, 2)),
        ("Days Nasdaq and yield moved the same way", "same_dir", lambda v: f"{v:.0f}%"),
        ("Nasdaq 100 change", "nasdaq_pct", lambda v: pct(v) + "%"),
        ("10y yield change", "y10_bp", lambda v: pct(v, 0) + " bp"),
        ("Long bonds (TLT) change", "bonds_pct", lambda v: pct(v) + "%"),
        ("Regime", "regime", str),
    ]
    head = "<tr><th>Measure</th>" + "".join(f"<th>{escape(w)}</th>" for w in stats.index) + "</tr>"  # one column per window
    body = "".join("<tr><td>" + escape(label) + "</td>" + "".join(f"<td>{escape(fmt(stats.loc[w, key]))}</td>" for w in stats.index) + "</tr>"
                   for label, key, fmt in rows)
    # returns a str of HTML: a header and 8 rows, e.g. <tr><td>Correlation: Nasdaq vs 10y yield</td><td>+0.63</td><td>+0.09</td><td>−0.18</td></tr>
    return f'<div class="scroll"><table class="metrics">{head}{body}</table></div>'


def days_table(biggest):
    """The biggest recent Nasdaq days, newest first, with what the yield and bonds did."""
    head = ("<tr><th>Day</th><th>Nasdaq %</th><th>10y yield bp</th><th>Bonds %</th><th>Type</th></tr>")  # units in the headers keep cells narrow on a phone
    body = "".join(f"<tr><td>{d.strftime('%d %b')}</td><td>{pct(r['nasdaq'])}</td><td>{pct(r['y10_bp'])}</td>"
                   f"<td>{pct(r['bonds'])}</td><td>{escape(r['type'])}</td></tr>"
                   for d, r in biggest.iterrows())
    # returns a str of HTML: a header and 8 rows, e.g. <tr><td>22 Oct</td><td>−2.9</td><td>−19.3</td><td>+1.9</td><td>Into bonds</td></tr>
    return f'<div class="scroll"><table class="days">{head}{body}</table></div>'


def panel(number, question, finding, how, body, so=""):
    """One numbered section: a question, its one-line finding, how to read it, the chart or table, and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""          # optional reading guide
    so_html = f'<div class="so">{so}</div>' if so else ""                                  # optional takeaway
    # returns a str of HTML, e.g. '<section class="panel"><p class="tag">01</p><h2>What did tech and bonds do?</h2><p class="dek">Nasdaq −3.6% ...'
    return (f'<section class="panel"><p class="tag">{number:02d}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def references():
    """The quiet 'References' list after the last panel: no panel box, no question, one muted line per source."""
    items = "".join(                                           # one <li> per source; the whole line is the link (big tap target)
        f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><span><b>{escape(who)}</b>: {escape(what)}.</span></a></li>'
        for who, what, u in SOURCES)
    # returns a str of HTML: a small heading and 3 links, e.g.
    # '<aside class="refs" aria-label="References"><h3>References</h3><ul>
    #   <li><a href="https://finance.yahoo.com/quote/%5ENDX/" ...><span><b>Yahoo Finance</b>: daily closes of the Nasdaq 100 (^NDX), ...</span></a></li>
    #   <li><a href="https://pro.thestreet.com/..." ...><span><b>TheStreet Pro, 15 Oct 2026</b>: bonds are the new safe haven ...</span></a></li> ...</ul></aside>'
    return f'<aside class="refs" aria-label="References"><h3>References</h3><ul>{items}</ul></aside>'


def build_page(closes, moves, roll, stats, history, rotation, biggest):
    """Assemble the standalone HTML page and write it to disk."""
    recent = closes.tail(PERF_DAYS + 1)                        # 1 year of closes for the performance charts
    scatter_moves = moves.tail(SCATTER_DAYS)                   # the days shown in the scatter plot
    payload = {                                                # everything the page's JavaScript needs
        "perf": {"dates": [d.strftime("%Y-%m-%d") for d in recent.index],
                 **{k: [round(float(v), 3) for v in recent[k]] for k in ["nasdaq", "bonds", "y10"]}},
        "roll": {"dates": [d.strftime("%Y-%m-%d") for d in roll.index],
                 **{k: [round(float(v), 3) for v in roll[k]] for k in ["corr60", "corr20"]}},
        "scatter": {"dates": [d.strftime("%d %b %Y") for d in scatter_moves.index],
                    **{k: [round(float(v), 2) for v in scatter_moves[k]] for k in ["y10_bp", "nasdaq"]}},
        "recentDays": ROLL_SHORT,                              # how many of the scatter dots are "recent"
        "slope20": float(stats.iloc[0]["per_10bp"]) / 10,      # Nasdaq % per 1 bp in the last 20 days
        "threshold": LINK_THRESHOLD,                           # where the shaded regime zones start
    }
    s20, s60, s1y = stats.iloc[0], stats.iloc[1], stats.iloc[2]   # the three look-back windows
    y_now = closes["y10"].iloc[-1]                             # today's 10-year yield, in %
    c = rotation["counts"]                                     # the four day types, last 20 days

    kpis = "".join([                                           # the four headline numbers under the header
        tile(pct(s20["corr_yield"], 2), f"Correlation Nasdaq vs 10y yield, 20 days · {s20['regime']}"),
        tile(pct(s20["nasdaq_pct"]) + "%", "Nasdaq 100, 20 days", "--nq"),
        tile(pct(s20["y10_bp"], 0) + " bp", f"10-year yield, 20 days · now {y_now:.2f}%", "--y10"),
        tile(pct(s20["bonds_pct"]) + "%", "Long bonds (TLT), 20 days", "--bd"),
    ])
    periods = ('<div class="periods" role="group" aria-label="Period">'
               + "".join(f'<button type="button" data-days="{d}" aria-pressed="{str(d == 63).lower()}">{n}</button>'
                         for n, d in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)]) + "</div>")
    stories = ('<div class="stories">'
               '<div class="story" style="--c:var(--y10)"><h3>Rate fear: yields up, tech down</h3>'
               '<p>Most of a tech company\'s value sits in profits many years away. Those future profits are discounted back to '
               'today with an interest rate, so when yields rise they are worth less, and a day of rising yields is a bad day for the Nasdaq.</p>'
               '<p><b>Signature:</b> Nasdaq returns and yield changes move in opposite directions (correlation below 0).</p></div>'
               '<div class="story" style="--c:var(--bd)"><h3>Rotation: tech down, money into bonds</h3>'
               '<p>Investors sell tech and park the money in Treasuries. Buying bonds pushes their price up and their yield down. '
               'On good days the reverse happens: bonds are sold to buy tech, and yields rise.</p>'
               '<p><b>Signature:</b> Nasdaq returns and yield changes move the same way (correlation above 0), and tech and bond prices move opposite.</p></div>'
               '</div>')
    gloss = '<dl class="gloss">' + "".join(f"<div><dt>{escape(t)}</dt><dd>{escape(d)}</dd></div>" for t, d in GLOSSARY) + "</dl>"
    day_tiles = ('<div class="kpis">'
                 + tile(str(c["Into bonds"]), "Into bonds · tech down, bonds up")
                 + tile(str(c["Into tech"]), "Into tech · tech up, bonds down")
                 + tile(str(c["Both up"]), "Both up · no rotation")
                 + tile(str(c["Both down"]), "Both down · no rotation") + "</div>")
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in conclusions(stats, history, rotation)) + "</ol>"

    panels = "".join([
        panel(1, "What did tech and long bonds do?",
              f"Nasdaq {pct(s20['nasdaq_pct'])}%, long bonds {pct(s20['bonds_pct'])}% in the last {ROLL_SHORT} trading days.",
              "Both lines start at 0% on the first day of the period, so you compare gains and losses directly. Below, the 10-year "
              "yield over the same days. A bond's price moves opposite to its yield: when the yield falls, long bonds (TLT) rise.",
              periods + '<div id="perf" class="chart" role="img" aria-label="Nasdaq 100 and long bonds, % change since the start of the period"></div>'
              '<p class="label">10-year Treasury yield</p>'
              '<div id="y10" class="chart short" role="img" aria-label="US 10-year Treasury yield over the same period"></div>'
              '<p class="note"><span class="hint">Hover over or click</span> a chart to read the values of a day.</p>',
              f"<p>Over {ROLL_SHORT} days the 10-year yield moved {pct(s20['y10_bp'], 0)} bp to {y_now:.2f}%. Switch to <b>1Y</b> and the "
              f"picture changes: the Nasdaq is {pct(s1y['nasdaq_pct'])}% and long bonds {pct(s1y['bonds_pct'])}% over the year, "
              f"with the yield {pct(s1y['y10_bp'], 0)} bp. Which story you see depends on the window you look at.</p>"),
        panel(2, "Why would bond yields and tech move together at all?", "Two textbook stories, with opposite signs.",
              "", stories + gloss),
        panel(3, "Which story is in charge?",
              f"It keeps flipping. Today {pct(history['latest20'], 2)} over 20 days, {pct(history['latest60'], 2)} over 60.",
              f"Each point is the correlation of the previous 60 (blue) or 20 (grey) trading days of daily moves, recomputed every day. "
              f"The green zone above +{LINK_THRESHOLD} is rotation; the orange zone below &minus;{LINK_THRESHOLD} is rate fear; "
              f"in between there is no clear link. Drag the slider under the chart to zoom into a period.",
              '<div id="roll" class="chart" role="img" aria-label="Rolling correlation, Nasdaq 100 vs 10-year yield, five years"></div>',
              f"<p>Since {history['start']} the 60-day correlation was positive on {history['share_positive']:.0f}% of days. Its most "
              f"negative reading was {pct(history['low'], 2)} in {history['low_date']} (rate fear), its most positive "
              f"{pct(history['high'], 2)} in {history['high_date']} (rotation). The 20-day line jumps much more: it reacts to a few "
              f"big days, which makes it the first to show a new pattern and the first to give a false alarm.</p>"),
        panel(4, "What does a single day look like?",
              f"A +10 bp yield day came with a {pct(s20['per_10bp'], 2)}% Nasdaq move in the last {ROLL_SHORT} days.",
              f"One dot per trading day over the last {SCATTER_DAYS}. Across: how much the 10-year yield moved that day. Up: how much "
              f"the Nasdaq 100 moved. Blue dots are the last {ROLL_SHORT} days, with their trend line (dashed).",
              '<div id="scatter" class="chart" role="img" aria-label="Daily 10-year yield change against Nasdaq 100 move, last 60 days"></div>',
              f"<p>A line rising to the right means tech and yields go up and down together: rotation. A falling line would be rate fear. "
              f"In the last {ROLL_SHORT} days the two moved the same way on {s20['same_dir']:.0f}% of days.</p>"),
        panel(5, "Where did the money go on tech's bad days?",
              f"Bonds rose on {rotation['bonds_up_on_down']} of the {rotation['down_days']} days the Nasdaq fell.",
              f"Each of the last {rotation['days']} trading days is named by which way the Nasdaq 100 and long bonds moved. "
              "Opposite directions (into bonds or into tech) is a rotation day; the same direction is not.",
              day_tiles + f'<p class="label">The Nasdaq\'s {TOP_DAYS} biggest days of the last {SCATTER_DAYS}</p>' + days_table(biggest),
              f"<p>On the days the Nasdaq fell (average {pct(rotation['nasdaq_avg_on_down'], 2)}%), long bonds moved "
              f"{pct(rotation['bonds_avg_on_down'], 2)}% on average: they worked as a cushion. {rotation['rotation_days']} of the "
              f"{rotation['days']} days were rotation days.</p>"),
        panel(6, "Does the pattern hold over longer windows?",
              f"20 days {pct(s20['corr_yield'], 2)}, 60 days {pct(s60['corr_yield'], 2)}, 1 year {pct(s1y['corr_yield'], 2)}.",
              "Every measure for three look-back windows. \"Nasdaq move on a +10 bp yield day\" is the slope of the best-fit line, "
              "as in the dot chart above.",
              metrics_table(stats), f"<p>{window_text(stats)}</p>"),
        panel(7, "What did we learn?", "Five takeaways.", "", take),
    ]) + references()                                          # the sources follow the last panel as a quiet list, not a panel

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Nasdaq vs Bond Yields</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
<script src="{ECHARTS_URL}"></script>
</head>
<body>
<header class="band"><div class="in">
<a class="back" href="../index.html">&larr; Macro Quant Lab</a>
<p class="eyebrow">Nasdaq 100 vs bond yields</p>
<h1>Is money rotating between big tech and bonds?</h1>
<p class="answer">{answer_text(stats, rotation)}</p>
<p class="meta">Daily data to {history['last_date']} · Yahoo Finance · Not investment advice</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{panels}
</main>
<footer><div class="in">Generated by nasdaq_bonds.py from Yahoo Finance daily closes (Nasdaq 100 ^NDX, US 10-year yield ^TNX,
iShares 20+ Year Treasury Bond ETF TLT). Learning project, not investment advice.</div></footer>
<script>{JS.replace("__DATA__", json.dumps(payload))}</script>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # save the page
    # returns nothing; writes nasdaq_bonds.html (~80 KB: the HTML text plus about 3,500 numbers as JSON)
    return None


if __name__ == "__main__":
    main()
