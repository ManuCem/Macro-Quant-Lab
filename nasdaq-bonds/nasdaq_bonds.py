"""
Do bond yields and the Nasdaq 100 move together? Is money rotating between big tech, bonds and gold?
------------------------------------------------------------------------------------------------------
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
    GC=F  gold futures, $ per ounce

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
TICKERS = {"^NDX": "nasdaq", "^TNX": "y10", "TLT": "bonds", "GC=F": "gold"}
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
    closes = closes[list(TICKERS.values())]                    # fixed column order: nasdaq, y10, bonds, gold
    closes = closes.dropna()                                   # keep only days where all four have a price (gold trades on some US holidays)
    closes.index = pd.to_datetime(closes.index).tz_localize(None)  # plain dates, no time zone, so they print and slice cleanly
    closes.index.name = "Date"                                 # name the index for the CSV header
    closes.columns.name = None                                 # drop the leftover "Ticker" label above the column names
    ny_now = pd.Timestamp.now(tz="America/New_York")           # current time on Wall Street
    if closes.index[-1].date() == ny_now.date() and ny_now.hour < 17:   # today's row exists but the session has not closed yet
        closes = closes.iloc[:-1]                              # drop it: an intraday price is not a close and changes every minute
    # returns a DataFrame, one row per closed trading day (1,506 rows x 4 columns, 29 Oct 2020 - 28 Oct 2026);
    # nasdaq in index points, y10 in %, bonds = TLT price in $ (adjusted for its monthly payouts), gold in $/oz:
    #                   nasdaq    y10      bonds         gold
    # Date
    # 2026-10-26  29273.400391  4.986  81.680000  4038.399902
    # 2026-10-27  29651.439453  4.993  81.629997  4074.600098
    # 2026-10-28  29813.160156  5.045  80.989998  4051.600098
    return closes


def daily_moves(closes):
    """Turn closes into daily moves: % for the three prices, basis points for the yield."""
    moves = pd.DataFrame(index=closes.index)                   # empty table on the same dates
    moves["nasdaq"] = closes["nasdaq"].pct_change() * 100      # Nasdaq 100 daily return, in %
    moves["y10_bp"] = closes["y10"].diff() * 100               # 10y yield change in bp (4.99% -> 5.05% = +6 bp)
    moves["bonds"] = closes["bonds"].pct_change() * 100        # TLT daily return, in % (rises when yields fall)
    moves["gold"] = closes["gold"].pct_change() * 100          # gold daily return, in %
    moves = moves.dropna()                                     # the first day has no previous close, drop it
    # returns a DataFrame, one row per trading day (1,505 rows x 4 columns), all daily moves (rounded here):
    #             nasdaq  y10_bp  bonds  gold
    # Date
    # 2026-10-26    1.09    -0.2   0.42  0.76
    # 2026-10-27    1.29     0.7  -0.06  0.90
    # 2026-10-28    0.55     5.2  -0.78 -0.56
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
    # 2026-10-26   -0.04    0.59
    # 2026-10-27   -0.01    0.58
    # 2026-10-28    0.07    0.59
    return roll


def link_label(corr):
    """Name the regime a Nasdaq-vs-yield correlation points to."""
    if corr > LINK_THRESHOLD:                                  # stocks and yields rise together
        label = "Rotation"                                     # money moves between bonds and tech
    elif corr < -LINK_THRESHOLD:                               # yields up, stocks down
        label = "Rate fear"                                    # higher yields hurt tech valuations
    else:                                                      # in between
        label = "No clear link"
    # returns a str, one of 3 labels, e.g. link_label(0.59) -> 'Rotation', link_label(0.07) -> 'No clear link', link_label(-0.67) -> 'Rate fear'
    return label


def window_stats(closes, moves):
    """For each look-back window: correlations, sensitivity of the Nasdaq to yields, and how each asset performed."""
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
            "corr_gold": m["nasdaq"].corr(m["gold"]),          # Nasdaq returns vs gold returns
            "nasdaq_pct": (c["nasdaq"].iloc[-1] / c["nasdaq"].iloc[0] - 1) * 100,  # Nasdaq total change over the window, %
            "y10_bp": (c["y10"].iloc[-1] - c["y10"].iloc[0]) * 100,                # 10y yield change over the window, bp
            "bonds_pct": (c["bonds"].iloc[-1] / c["bonds"].iloc[0] - 1) * 100,     # TLT total change, %
            "gold_pct": (c["gold"].iloc[-1] / c["gold"].iloc[0] - 1) * 100,        # gold total change, %
            "same_dir": ((m["nasdaq"] > 0) == (m["y10_bp"] > 0)).mean() * 100,     # % of days Nasdaq and yield moved the same way
        })
    table = pd.DataFrame(rows).set_index("window").round(2)   # windows as rows, 2 decimals
    table["regime"] = table["corr_yield"].apply(link_label)    # name the regime of each window
    # returns a DataFrame, 3 rows x 11 columns (real output, data up to 28 Oct 2026, some columns rounded here):
    #               days  corr_yield  per_10bp  corr_bonds  corr_gold  nasdaq_pct  y10_bp  bonds_pct  gold_pct  same_dir         regime
    # window
    # Last 20 days    20        0.59      1.28       -0.59       0.44       -2.0    -25.0       4.5      -3.2      ...       Rotation
    # Last 60 days    60        0.07      0.14       -0.03       0.30        0.3     42.0      -1.4      -2.4      ...  No clear link
    # Last year      250       -0.19     -0.57        0.20       0.30       14.1     99.0      -7.0       1.3      ...  No clear link
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
    # returns a dict of 10 values (real output, data up to 28 Oct 2026):
    # {'start': 'Oct 2021', 'share_positive': 42.9, 'avg_2022': -0.07, 'low': -0.67, 'low_date': 'Jun 2026',
    #  'high': 0.46, 'high_date': 'Apr 2025', 'latest60': 0.07, 'latest20': 0.59, 'last_date': '28 Oct 2026'}
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
    """Count the four kinds of day over the last `days`, and what bonds and gold did when tech fell."""
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
        "gold_up_on_down": int((down["gold"] > 0).sum()),      # on how many of those gold rose (a cushion)
        "bonds_avg_on_down": round(float(down["bonds"].mean()), 2) if len(down) else 0.0,  # average TLT move on those days, %
        "gold_avg_on_down": round(float(down["gold"].mean()), 2) if len(down) else 0.0,    # average gold move on those days, %
        "nasdaq_avg_on_down": round(float(down["nasdaq"].mean()), 2) if len(down) else 0.0,  # average Nasdaq move on those days, %
    }
    # returns a dict of 9 values (real output, last 20 days to 28 Oct 2026):
    # {'days': 20, 'counts': {'Into tech': 5, 'Into bonds': 8, 'Both up': 5, 'Both down': 2}, 'rotation_days': 13,
    #  'down_days': 10, 'bonds_up_on_down': 8, 'gold_up_on_down': 3, 'bonds_avg_on_down': 0.56,
    #  'gold_avg_on_down': -0.54, 'nasdaq_avg_on_down': -1.02}
    return result


def biggest_days(moves, days=SCATTER_DAYS, top=TOP_DAYS):
    """The Nasdaq's biggest moves (up or down) of the last `days`, with what yields, bonds and gold did that day."""
    m = moves.tail(days).copy()                                # the recent window (copy so we can add a column safely)
    biggest = m["nasdaq"].abs().sort_values(ascending=False).index[:top]   # dates of the `top` largest absolute moves
    table = m.loc[biggest].sort_index(ascending=False)         # those rows, newest first
    table["type"] = [classify_day(n, b) for n, b in zip(table["nasdaq"], table["bonds"])]  # label each day
    table = table.round(2)                                     # 2 decimals
    # returns a DataFrame, 8 rows x 5 columns (real output, first 3 of 8 rows):
    #             nasdaq  y10_bp  bonds  gold        type
    # Date
    # 2026-10-22   -2.90   -19.3   1.87 -2.16  Into bonds
    # 2026-10-16   -2.50     0.9   0.10  0.26  Into bonds
    # 2026-10-14   -2.02    -2.7   0.66 -1.66  Into bonds
    return table


def save_csv(closes, moves):
    """Save closes and daily moves side by side in one CSV next to this script."""
    table = closes.join(moves.add_suffix("_move"))             # closes + moves on the same dates (moves renamed nasdaq_move, ...)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)         # create the csv folder if missing
    table.round(4).to_csv(CSV_PATH)                            # write it
    # returns nothing; writes csv/nasdaq_bonds.csv with 1,506 rows (the first, 2020-10-29, has empty moves), like
    # Date,nasdaq,y10,bonds,gold,nasdaq_move,y10_bp_move,bonds_move,gold_move
    # 2020-10-30,11052.9502,0.86,129.7903,1879.9,-2.6235,2.5,-0.9866,0.637
    return None


def print_summary(stats, history, rotation, biggest):
    """Print the key numbers in the terminal."""
    print(f"Data up to {history['last_date']}")
    for name, r in stats.iterrows():                           # one line per look-back window
        print(f"  {name:<13} corr(Nasdaq, yield) {r['corr_yield']:+.2f} [{r['regime']}]  Nasdaq {r['per_10bp']:+.2f}% per +10 bp  "
              f"corr(Nasdaq, bonds) {r['corr_bonds']:+.2f}  corr(Nasdaq, gold) {r['corr_gold']:+.2f}")
        print(f"  {'':<13} Nasdaq {r['nasdaq_pct']:+.1f}%  10y {r['y10_bp']:+.0f} bp  bonds {r['bonds_pct']:+.1f}%  gold {r['gold_pct']:+.1f}%")
    print(f"60-day correlation since {history['start']}: positive {history['share_positive']}% of days, "
          f"2022 average {history['avg_2022']:+.2f}, low {history['low']:+.2f} ({history['low_date']}), high {history['high']:+.2f} ({history['high_date']})")
    print(f"Last {rotation['days']} days: {rotation['counts']}  -> Nasdaq fell on {rotation['down_days']} days; "
          f"bonds rose on {rotation['bonds_up_on_down']}, gold rose on {rotation['gold_up_on_down']}")
    print("Biggest Nasdaq days of the last 60:")
    print(biggest.to_string())
    # returns nothing; prints ~20 lines, e.g.
    # Data up to 28 Oct 2026
    #   Last 20 days  corr(Nasdaq, yield) +0.59 [Rotation]  Nasdaq +1.28% per +10 bp  corr(Nasdaq, bonds) -0.59  corr(Nasdaq, gold) +0.44
    #                 Nasdaq -2.0%  10y -25 bp  bonds +4.5%  gold -3.2%
    #   ... (Last 60 days, Last year)
    # 60-day correlation since Oct 2021: positive 42.9% of days, 2022 average -0.07, low -0.67 (Jun 2026), high +0.46 (Apr 2025)
    # Last 20 days: {'Into tech': 5, 'Into bonds': 8, 'Both up': 5, 'Both down': 2}  -> Nasdaq fell on 10 days; bonds rose on 8, gold rose on 3
    #   ... (then the biggest-days table)
    return None


def main():
    closes = fetch_closes()                                    # step 1: download the four daily series
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

# Colours: one fixed hue per asset (validated for colour-blind readers, light and dark steps chosen separately).
# Nasdaq = blue, long bonds = aqua, gold = yellow, 10y yield = orange. Text always uses the ink tokens, never these.
CSS = """
:root{color-scheme:light dark;--page:#fbfaf7;--surface:#ffffff;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
  --nq:#2a78d6;--bd:#1baf7a;--gd:#eda100;--y10:#eb6834;--zone-rot:rgba(27,175,122,.09);--zone-fear:rgba(235,104,52,.09)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#9a988f;
  --grid:#2c2c2a;--axis:#4a4a46;--nq:#3987e5;--bd:#199e70;--gd:#c98500;--y10:#d95926;--zone-rot:rgba(25,158,112,.16);--zone-fear:rgba(217,89,38,.16)}}
:root[data-theme=dark]{--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#9a988f;--grid:#2c2c2a;--axis:#4a4a46;
  --nq:#3987e5;--bd:#199e70;--gd:#c98500;--y10:#d95926;--zone-rot:rgba(25,158,112,.16);--zone-fear:rgba(217,89,38,.16)}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px max(16px,env(safe-area-inset-right)) 40px max(16px,env(safe-area-inset-left))}
h1{font-size:1.45rem;line-height:1.25;margin:.4rem 0}
h2{font-size:1.1rem;margin:2.2rem 0 .4rem}
h3{font-size:1rem;margin:.8rem 0 .3rem}
p{margin:.4rem 0 .8rem}
.sub{color:var(--ink-2)}
a{color:var(--nq)}
a.back{display:inline-flex;align-items:center;min-height:44px;text-decoration:none}
.tag{display:inline-block;font-size:.8rem;color:var(--ink-2);border:1px solid var(--grid);border-radius:999px;padding:2px 10px;margin:0 4px 4px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--surface);border:1px solid var(--grid);border-radius:10px;padding:10px 12px}
.tile b{display:block;font-size:1.35rem;font-variant-numeric:tabular-nums}
.tile span{color:var(--muted);font-size:.85rem}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
.read{background:var(--surface);border-left:4px solid var(--nq);border-radius:6px;padding:10px 14px;margin:12px 0}
.chart{width:100%;height:360px;background:var(--surface);border:1px solid var(--grid);border-radius:10px;margin:8px 0}
.chart.short{height:240px}
.note{color:var(--muted);font-size:.85rem}
.periods{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 4px}
.periods button{min-height:44px;min-width:56px;padding:0 14px;border:1px solid var(--grid);border-radius:8px;background:var(--surface);
  color:var(--ink);font:inherit;font-weight:600;cursor:pointer}
.periods button[aria-pressed=true]{background:var(--ink);color:var(--page);border-color:var(--ink)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--surface);border:1px solid var(--grid);border-top:4px solid var(--c);border-radius:10px;padding:4px 16px 10px}
.card p{margin:.3rem 0}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--grid);border-radius:10px}
table{border-collapse:collapse;width:100%;background:var(--surface);font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--surface)}
th{font-weight:600;color:var(--ink-2)}
.sources li{margin:.2rem 0}
.sources a{display:inline-block;padding:11px 0;margin:-5px 0}
ul.sources{padding-left:1.1rem}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--grid);color:var(--muted);font-size:.85rem}
@media (max-width:640px){h1{font-size:1.25rem}.cols{grid-template-columns:1fr}.chart{height:440px}.chart.short{height:300px}
  .tiles{grid-template-columns:1fr 1fr}th,td{padding:8px 4px;font-size:.88rem}th{white-space:normal}
  th:first-child,td:first-child{padding-left:8px}th:last-child,td:last-child{padding-right:8px}
  .metrics td{white-space:normal}.metrics td:first-child,.metrics th:first-child{position:static}
  .days td:last-child{white-space:normal;text-align:left}}
"""

JS = """
const DATA = __DATA__;                                          // everything Python computed, as JSON
const narrowMQ = window.matchMedia("(max-width: 640px)");       // true on a phone-width screen
const isTouch = window.matchMedia("(pointer: coarse)").matches; // a finger instead of a mouse
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();  // read a colour token
const INSTANCES = {};                                           // chart div id -> ECharts instance
let PERIOD = 63;                                                // trading days shown in the first two charts (3 months)
const sign = (v, d) => (v > 0 ? "+" : v < 0 ? "\\u2212" : "") + Math.abs(v).toFixed(d);  // +1.2 / \\u22121.2 with a real minus sign

function base(narrow) {                                         // options shared by every chart
  return {
    animation: false, backgroundColor: "transparent", textStyle: {color: css("--ink-2")},
    legend: narrow ? {bottom: 4, left: 12, orient: "vertical", itemGap: 6, textStyle: {color: css("--ink-2")}}  // below the plot on a phone
                   : {top: 6, left: 56, textStyle: {color: css("--ink-2")}},   // one row above the plot on desktop
    tooltip: {trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click", confine: true},     // tap on touch screens
  };
}
const ax = extra => Object.assign({axisLine: {lineStyle: {color: css("--axis")}}, splitLine: {lineStyle: {color: css("--grid")}},
                                  axisLabel: {color: css("--muted"), hideOverlap: true}}, extra);
const window_ = () => {                                         // the slice of the 1-year data the period buttons select
  const n = DATA.perf.dates.length;                             // up to 253 closes
  const s = Math.max(0, n - 1 - PERIOD);                        // index of the first close in the window
  return {s, dates: DATA.perf.dates.slice(s)};
};
const rebased = key => { const w = window_(); const first = DATA.perf[key][w.s];   // % change since the first day of the window
  return w.dates.map((d, i) => [d, +(DATA.perf[key][w.s + i] / first * 100 - 100).toFixed(2)]); };

function perf(narrow) {                                         // Nasdaq, long bonds and gold, all rebased to 0% on day one
  const o = base(narrow);
  o.grid = narrow ? {left: 44, right: 16, top: 16, bottom: 92} : {left: 56, right: 120, top: 44, bottom: 36};
  o.xAxis = ax({type: "time", splitNumber: narrow ? 3 : 6});
  o.yAxis = ax({type: "value", axisLabel: {color: css("--muted"), formatter: v => sign(v, 0) + "%"}});
  const line = (name, key, color) => ({name, type: "line", data: rebased(key), showSymbol: false, lineStyle: {color, width: 2},
    itemStyle: {color}, endLabel: {show: !narrow, color: css("--ink"), formatter: p => name.split(" (")[0] + " " + sign(p.value[1], 1) + "%"},
    labelLayout: {moveOverlap: "shiftY"}});                     // push end labels apart when two lines finish at the same level
  o.series = [line("Nasdaq 100", "nasdaq", css("--nq")), line("Long bonds (TLT)", "bonds", css("--bd")), line("Gold", "gold", css("--gd"))];
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
     markArea: {silent: true, label: {color: css("--ink-2"), position: "insideTopLeft", fontSize: 12}, data: [
       [{name: "Rotation zone: tech and yields move together", yAxis: DATA.threshold, itemStyle: {color: css("--zone-rot")}}, {yAxis: 1}],
       [{name: "Rate-fear zone: yields up, tech down", yAxis: -1, itemStyle: {color: css("--zone-fear")}, label: {position: "insideBottomLeft"}}, {yAxis: -DATA.threshold}]]},
     markLine: {silent: true, symbol: "none", label: {show: false}, lineStyle: {color: css("--axis")}, data: [{yAxis: 0}]}},
    {name: "20-day correlation (fast)", type: "line", data: pts("corr20"), showSymbol: false, lineStyle: {color: css("--muted"), width: 1}, itemStyle: {color: css("--muted")}},
  ];
  o.dataZoom = [{type: "slider", start: 0, end: 100, height: 22, bottom: narrow ? 66 : 8, borderColor: css("--grid"),
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
  o.tooltip = {trigger: "item", triggerOn: isTouch ? "click" : "mousemove|click", confine: true,
    formatter: p => p.data.date + "<br>10y yield " + sign(p.value[0], 1) + " bp<br>Nasdaq 100 " + sign(p.value[1], 2) + "%"};
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

SOURCES = [                               # (label, link) for the data and every press fact on the page
    ("Yahoo Finance via yfinance: ^NDX, ^TNX, TLT, GC=F daily closes", "https://finance.yahoo.com/quote/%5ENDX/"),
    ("TheStreet Pro, 15 Oct 2026: bonds are the new safe haven as money rotates out of tech",
     "https://pro.thestreet.com/market-commentary/bonds-are-the-new-safe-haven-as-money-rotates-out-of-tech"),
    ("roic.ai, 13 Oct 2026: BofA survey, Treasury yields near 6% would trigger a shift from stocks to bonds",
     "https://www.roic.ai/news/bofa-survey-treasury-yields-near-6-would-trigger-shift-from-stocks-to-bonds-10-13-2026"),
]


def pct(value, digits=1):
    """Format a number with an explicit sign and a real minus sign, e.g. -3.85 -> '−3.9'."""
    text = f"{abs(value):.{digits}f}"                          # the size of the number, without its sign
    # returns a str, e.g. pct(-2.04) -> '−2.0', pct(4.49) -> '+4.5', pct(0) -> '0.0'
    return ("+" if value > 0 else "−" if value < 0 else "") + text


def tile(value, label, color=None):
    """One small stat box; an optional coloured dot names the asset."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # identity is in the text too, never colour alone
    # returns a str of HTML, e.g. '<div class="tile"><b><i class="dot" ...></i>−2.0%</b><span>Nasdaq 100, last 20 days</span></div>'
    return f'<div class="tile"><b>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def answer_text(stats, rotation):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    s20, s60, s1y = stats.iloc[0], stats.iloc[1], stats.iloc[2]   # the three windows: 20 days, 60 days, 1 year
    if s20["regime"] == "Rotation":                            # the pattern the question is about
        lead = (f"<b>Yes, in the last {int(s20['days'])} trading days money has been rotating between big tech and bonds.</b> "
                f"The Nasdaq 100 and the 10-year yield moved together (correlation {pct(s20['corr_yield'], 2)}), so tech and "
                f"long bonds moved in opposite directions ({pct(s20['corr_bonds'], 2)}). ")
    elif s20["regime"] == "Rate fear":                         # the classic story instead
        lead = (f"<b>Not rotation but rate fear:</b> in the last {int(s20['days'])} trading days rising yields went with a falling "
                f"Nasdaq (correlation {pct(s20['corr_yield'], 2)}). ")
    else:                                                      # neither
        lead = (f"<b>No clear link in the last {int(s20['days'])} trading days</b> (correlation {pct(s20['corr_yield'], 2)}). ")
    cushion = (f"On {rotation['down_days']} days the Nasdaq fell; long bonds rose on {rotation['bonds_up_on_down']} of them, "
               f"gold on only {rotation['gold_up_on_down']}. ")
    if rotation["gold_up_on_down"] * 2 < rotation["down_days"]:   # gold rose on fewer than half the bad days
        cushion += "Lately the safe place has been Treasuries, not gold: gold has tended to fall <i>with</i> tech. "
    longer = (f"Over longer windows the link is weak and can flip sign: {pct(s60['corr_yield'], 2)} over 60 days, "
              f"{pct(s1y['corr_yield'], 2)} over a year.")
    # returns a str of HTML, about 600 characters, e.g.
    # '<b>Yes, in the last 20 trading days money has been rotating between big tech and bonds.</b> The Nasdaq 100 and the
    #  10-year yield moved together (correlation +0.59), ... over 60 days, −0.19 over a year.'
    return lead + cushion + longer


def metrics_table(stats):
    """Every window number in one table: rows = measures, columns = windows (3 columns fit a phone)."""
    rows = [                                                   # (row label, column in stats, formatter)
        ("Correlation: Nasdaq vs 10y yield", "corr_yield", lambda v: pct(v, 2)),
        ("Nasdaq move on a +10 bp yield day", "per_10bp", lambda v: pct(v, 2) + "%"),
        ("Correlation: Nasdaq vs long bonds", "corr_bonds", lambda v: pct(v, 2)),
        ("Correlation: Nasdaq vs gold", "corr_gold", lambda v: pct(v, 2)),
        ("Days Nasdaq and yield moved the same way", "same_dir", lambda v: f"{v:.0f}%"),
        ("Nasdaq 100 change", "nasdaq_pct", lambda v: pct(v) + "%"),
        ("10y yield change", "y10_bp", lambda v: pct(v, 0) + " bp"),
        ("Long bonds (TLT) change", "bonds_pct", lambda v: pct(v) + "%"),
        ("Gold change", "gold_pct", lambda v: pct(v) + "%"),
        ("Regime", "regime", str),
    ]
    head = "<tr><th>Measure</th>" + "".join(f"<th>{escape(w)}</th>" for w in stats.index) + "</tr>"  # one column per window
    body = "".join("<tr><td>" + escape(label) + "</td>" + "".join(f"<td>{escape(fmt(stats.loc[w, key]))}</td>" for w in stats.index) + "</tr>"
                   for label, key, fmt in rows)
    # returns a str of HTML: a header and 10 rows, e.g. <tr><td>Correlation: Nasdaq vs 10y yield</td><td>+0.59</td><td>+0.07</td><td>−0.19</td></tr>
    return f'<div class="scroll"><table class="metrics">{head}{body}</table></div>'


def days_table(biggest):
    """The biggest recent Nasdaq days, newest first, with what the yield, bonds and gold did."""
    head = ("<tr><th>Day</th><th>Nasdaq %</th><th>10y yield bp</th><th>Bonds %</th><th>Gold %</th><th>Type</th></tr>")  # units in the headers keep cells narrow on a phone
    body = "".join(f"<tr><td>{d.strftime('%d %b')}</td><td>{pct(r['nasdaq'])}</td><td>{pct(r['y10_bp'])}</td>"
                   f"<td>{pct(r['bonds'])}</td><td>{pct(r['gold'])}</td><td>{escape(r['type'])}</td></tr>"
                   for d, r in biggest.iterrows())
    # returns a str of HTML: a header and 8 rows, e.g. <tr><td>22 Oct</td><td>−2.9</td><td>−19.3</td><td>+1.9</td><td>−2.2</td><td>Into bonds</td></tr>
    return f'<div class="scroll"><table class="days">{head}{body}</table></div>'


def build_page(closes, moves, roll, stats, history, rotation, biggest):
    """Assemble the standalone HTML page and write it to disk."""
    recent = closes.tail(PERF_DAYS + 1)                        # 1 year of closes for the performance charts
    scatter_moves = moves.tail(SCATTER_DAYS)                   # the days shown in the scatter plot
    payload = {                                                # everything the page's JavaScript needs
        "perf": {"dates": [d.strftime("%Y-%m-%d") for d in recent.index],
                 **{k: [round(float(v), 3) for v in recent[k]] for k in ["nasdaq", "bonds", "gold", "y10"]}},
        "roll": {"dates": [d.strftime("%Y-%m-%d") for d in roll.index],
                 **{k: [round(float(v), 3) for v in roll[k]] for k in ["corr60", "corr20"]}},
        "scatter": {"dates": [d.strftime("%d %b %Y") for d in scatter_moves.index],
                    **{k: [round(float(v), 2) for v in scatter_moves[k]] for k in ["y10_bp", "nasdaq"]}},
        "recentDays": ROLL_SHORT,                              # how many of the scatter dots are "recent"
        "slope20": float(stats.iloc[0]["per_10bp"]) / 10,      # Nasdaq % per 1 bp in the last 20 days
        "threshold": LINK_THRESHOLD,                           # where the shaded regime zones start
    }
    s20 = stats.iloc[0]                                        # the "last 20 days" row drives the tiles
    tiles = "".join([
        tile(pct(s20["corr_yield"], 2), f"Correlation Nasdaq vs 10y yield, last 20 days ({s20['regime']})"),
        tile(pct(s20["nasdaq_pct"]) + "%", "Nasdaq 100, last 20 days", "--nq"),
        tile(pct(s20["y10_bp"], 0) + " bp", f"10-year yield, last 20 days (now {closes['y10'].iloc[-1]:.2f}%)", "--y10"),
        tile(pct(s20["bonds_pct"]) + "%", "Long bonds (TLT), last 20 days", "--bd"),
        tile(pct(s20["gold_pct"]) + "%", "Gold, last 20 days", "--gd"),
    ])
    c = rotation["counts"]                                     # the four day types, last 20 days
    day_tiles = "".join([
        tile(f"{c['Into bonds']} days", "Into bonds: Nasdaq down, bonds up"),
        tile(f"{c['Into tech']} days", "Into tech: Nasdaq up, bonds down"),
        tile(f"{c['Both up']} days", "Both up"),
        tile(f"{c['Both down']} days", "Both down"),
    ])
    sources = "".join(f'<li><a href="{escape(url)}" target="_blank" rel="noopener">{escape(label)}</a></li>' for label, url in SOURCES)
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Nasdaq vs bond yields</title>
<style>{CSS}</style>
<script src="{ECHARTS_URL}"></script>
</head>
<body>
<main>
<a class="back" href="../index.html">&larr; Macro-Quant-Lab</a>
<h1>Bond yields vs the Nasdaq 100: is money rotating between big tech, bonds and gold?</h1>
<p class="sub">Daily data to {history['last_date']}. The question: when big tech sells off, where does the money go, and do bond yields
and the Nasdaq 100 move together or against each other?</p>
<p><span class="tag">Data: Yahoo Finance</span><span class="tag">Not investment advice</span></p>

<div class="tiles">{tiles}</div>
<div class="read">{answer_text(stats, rotation)}</div>

<h2>1. Tech, long bonds and gold since the start of the window</h2>
<p class="sub">Each line starts at 0% on the first day, so you compare how much each one gained or lost. Below, the 10-year yield
over the same days: when it falls, the price of long bonds (TLT) rises.</p>
<div class="periods" role="group" aria-label="Period">
<button type="button" data-days="21" aria-pressed="false">1M</button><button type="button" data-days="63" aria-pressed="true">3M</button><button type="button" data-days="126" aria-pressed="false">6M</button><button type="button" data-days="252" aria-pressed="false">1Y</button>
</div>
<div id="perf" class="chart" role="img" aria-label="Nasdaq 100, long bonds and gold, percent change since the start of the period"></div>
<h3>10-year Treasury yield</h3>
<div id="y10" class="chart short" role="img" aria-label="US 10-year Treasury yield over the same period"></div>
<p class="note"><span class="hint">Hover over or click</span> a chart to read the values of a day. Both charts share the same dates.</p>

<h2>2. Two stories that pull in opposite directions</h2>
<div class="cols">
<div class="card" style="--c:var(--y10)"><h3>Rate fear: yields up, tech down</h3>
<p>Most of a tech company's value sits in profits many years away. Those profits are worth less today when interest rates are
higher (they are "discounted" at a higher rate). So a day of rising yields is a bad day for the Nasdaq.</p>
<p><b>Signature:</b> Nasdaq returns and yield changes are <b>negatively</b> correlated.</p></div>
<div class="card" style="--c:var(--bd)"><h3>Rotation: tech down, money into bonds</h3>
<p>Investors sell tech and park the money in Treasuries. Buying bonds pushes their price up and their yield down. On good days the
reverse happens: bonds are sold to buy tech, and yields rise.</p>
<p><b>Signature:</b> Nasdaq returns and yield changes are <b>positively</b> correlated (and tech vs bond prices negatively).</p></div>
</div>
<p class="note">Correlation runs from &minus;1 (always opposite) to +1 (always together); near 0 means no linear link. Here it is measured on
daily moves: the Nasdaq's % change and the yield's change in basis points (1 bp = 0.01 percentage point).</p>

<h2>3. Which story is in charge? Five years of rolling correlation</h2>
<p class="sub">The correlation between Nasdaq moves and yield changes, measured over the previous 60 trading days (blue) and 20 days (grey),
recomputed every day. Above +{LINK_THRESHOLD} = rotation; below &minus;{LINK_THRESHOLD} = rate fear.</p>
<div id="roll" class="chart" role="img" aria-label="Rolling correlation between Nasdaq 100 returns and 10-year yield changes, five years"></div>
<div class="read">The link keeps flipping. Since {history['start']} the 60-day correlation was positive on {history['share_positive']:.0f}% of days.
Its most negative reading was {pct(history['low'], 2)} in {history['low_date']} (rate fear), its most positive {pct(history['high'], 2)}
in {history['high_date']}. Today: {pct(history['latest60'], 2)} over 60 days, but {pct(history['latest20'], 2)} over 20 days: the
rotation is recent, a few weeks old. Even 2022, the year of the Fed's fastest hikes, averaged only {pct(history['avg_2022'], 2)} on
daily moves, a reminder that "yields up = tech down" is a slow, level story more than a day-to-day one.</div>

<h2>4. The last {SCATTER_DAYS} days, one dot per day</h2>
<p class="sub">Across: how much the 10-year yield moved that day. Up: how much the Nasdaq 100 moved. Dots rising to the right = rotation days.</p>
<div id="scatter" class="chart" role="img" aria-label="Scatter of daily 10-year yield changes against Nasdaq 100 returns, last 60 days"></div>
<p class="note">In the last {ROLL_SHORT} days, a day when the 10-year yield rose 10 bp came with a Nasdaq move of {pct(s20['per_10bp'], 2)}% on
average (slope of the dashed line), and the two moved the same way on {s20['same_dir']:.0f}% of days.</p>

<h2>5. Where did the money go on tech's bad days?</h2>
<p class="sub">Each of the last {rotation['days']} trading days, named by which way the Nasdaq 100 and long bonds (TLT) moved.</p>
<div class="tiles">{day_tiles}</div>
<p>On the {rotation['down_days']} days the Nasdaq fell (average {pct(rotation['nasdaq_avg_on_down'], 2)}%), long bonds rose on
{rotation['bonds_up_on_down']} (average {pct(rotation['bonds_avg_on_down'], 2)}%) and gold on {rotation['gold_up_on_down']}
(average {pct(rotation['gold_avg_on_down'], 2)}%).</p>
<h3>The Nasdaq's {TOP_DAYS} biggest days of the last {SCATTER_DAYS}</h3>
{days_table(biggest)}

<h2>6. All the numbers by window</h2>
{metrics_table(stats)}

<h2>7. What the press says</h2>
<p>The data matches what was being written in mid-October 2026. A TheStreet column (15 Oct) argued that bonds have become the new safe
haven as money rotates out of tech, helped by their high yields. A Bank of America fund-manager survey reported on 13 Oct found that
37% of managers would move money from stocks into bonds if the 10-year yield reached about 6% (it was near 5.2% then), while their
overweight in tech was the largest since August 2020: a crowded trade that can unwind into bonds.</p>
<ul class="sources">{sources}</ul>

<footer>Generated by nasdaq_bonds.py from Yahoo Finance daily closes (Nasdaq 100 ^NDX, US 10-year yield ^TNX, iShares 20+ Year
Treasury Bond ETF TLT, gold futures GC=F). Correlation describes how things moved together; it does not say which one caused the other.
Learning project, not investment advice.</footer>
</main>
<script>{JS.replace("__DATA__", json.dumps(payload))}</script>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # save the page
    # returns nothing; writes nasdaq_bonds.html (~75 KB: the HTML text plus about 3,500 numbers as JSON)
    return None


if __name__ == "__main__":
    main()
