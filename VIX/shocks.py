"""
How did the VIX behave around four market shocks, compared with the volatility
that actually followed?

For each shock we cut the data into three phases around "day 0" (the first big
panic day):

    Pre-shock  : the 40 trading days BEFORE day 0
    Day 0      : the shock day itself
    Aftermath  : the 60 trading days AFTER day 0

and score the VIX in each phase as (VIX - realized volatility over the next 21
trading days). A positive gap means the VIX overpriced volatility; a negative
gap means the market underestimated what was coming.

Output: VIX/output/shocks.html, a "Lab" page (see CLAUDE.md): the four shocks compared side by side,
        then one tab per shock, drawn with Apache ECharts (loaded from a CDN).
Reuses the data helpers from volatility.py so both scripts measure the same way.

Layout of this file (see CLAUDE.md):
    1. python / data code  -> settings, the calculations, and def main()
    2. html / chart code   -> builds the web page and the charts
"""

import json                               # turns Python lists/dicts into text the browser's JavaScript can read
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import numpy as np                        # number tools (arange, select)
import pandas as pd                       # tables (DataFrames) and time series

from volatility import (                  # reuse the data helpers so both scripts measure volatility the same way
    FORWARD_HORIZON,                      # 21: days ahead used for "realized" volatility
    PERIOD,                               # "30y": how much history to download
    TICKER,                               # "^GSPC": the S&P 500
    VIX_TICKER,                           # "^VIX": the VIX
    compute_log_returns,                  # prices -> daily log returns
    fetch_prices,                         # downloads closing prices from Yahoo Finance
    forward_realized_volatility,          # volatility over the next N days, per date
)


# ===========================================================================
# python / data code
# ===========================================================================

OUTPUT_PATH = Path(__file__).parent / "output" / "shocks.html"  # where the web page is saved

PRE_DAYS = 40                             # trading days shown before day 0 (~2 months of "before")
POST_DAYS = 60                            # trading days shown after day 0 (~3 months of "after")
TOLERANCE = 2.0                           # |gap| under this many vol points counts as "about right"

# Day 0 = the first big panic day of each shock (not necessarily the worst day,
# so the pre-shock window stays genuinely calm). Each date was checked against
# the data: worst S&P day / biggest one-day VIX jump of the episode.
EVENTS = [                                # one dictionary per shock
    {
        "key": "dotcom", "name": "Dot-com crash", "day0": "2000-04-14",  # key = short id used in HTML ids; day0 = the shock date
        "why": "Worst S&P 500 day of the 2000 sell-off, and the VIX peak of "  # text shown under the tab title
               "that spring. The bubble deflated slowly: this is the "
               "sharpest day inside a ~2.5-year decline that only bottomed "
               "in Oct 2002 (see the day 0 to lowest point tile).",
        "color": "--dotcom",              # CSS colour token (blue), defined for light and dark mode in the CSS below
    },
    {
        "key": "gfc", "name": "2008 financial crisis", "day0": "2008-09-15",
        "why": "Lehman Brothers files for bankruptcy. Worse S&P days came "
               "later (Oct 2008), but this is the trigger, so the 40 days "
               "before it are still relatively calm.",
        "color": "--gfc",                 # red token
    },
    {
        "key": "covid", "name": "Covid crash", "day0": "2020-02-24",
        "why": "First big panic day after the outbreak in Italy: the biggest "
               "one-day VIX jump of the episode. The worst S&P day (16 Mar) "
               "came three weeks later.",
        "color": "--covid",               # green token
    },
    {
        "key": "tariffs", "name": "2025 tariff shock", "day0": "2025-04-03",
        "why": "First trading day after the 'Liberation Day' tariff "
               "announcement (made after the close on 2 Apr). The S&P fell "
               "~5% and the VIX jumped ~40%.",
        "color": "--tariffs",             # amber token
    },
]

PHASES = ["Pre-shock", "Day 0", "Aftermath"]  # the three phases, in order


def build_dataset():
    """One table: S&P close, VIX and forward realized vol on the same dates."""
    prices = fetch_prices(TICKER, PERIOD)                    # S&P 500 closing prices (Series: date -> price)
    log_returns = compute_log_returns(prices)                # daily log returns of the S&P
    vix = fetch_prices(VIX_TICKER, PERIOD)                   # VIX closing levels (Series: date -> VIX)
    forward_vol = forward_realized_volatility(log_returns, FORWARD_HORIZON)  # volatility of the NEXT 21 days, per date

    data = pd.DataFrame({"sp500": prices, "vix": vix, "realized": forward_vol})  # one table; pandas lines the three series up BY DATE
    # Keep every day that has both prices; `realized` is NaN for the last 21
    # days (their future isn't known yet) -- irrelevant for historical events.
    data = data.dropna(subset=["sp500", "vix"])              # drop days missing the S&P or the VIX (only those two columns are checked)
    # Save a copy as CSV next to this script (VIX/csv/data.csv). to_csv creates
    # the file but not the folder, so make the folder first.
    csv_path = Path(__file__).parent / "csv" / "data.csv"    # path to VIX/csv/data.csv, wherever the script is run from
    csv_path.parent.mkdir(parents=True, exist_ok=True)       # create the csv folder if it is missing (no error if it exists)
    data.to_csv(csv_path)                                    # write the table to the file; the dates become the first column

    # RETURNS a pandas DataFrame, shape (7545, 3): one row per trading day, index = Date, columns = sp500, vix, realized.
    # Prints as (the first date moves forward as the "30y" window rolls):
    #               sp500    vix  realized
    # Date
    # 1996-10-07   703.34  15.11      7.94
    # 1996-10-08   700.64  15.58      9.07
    # 1996-10-09   696.74  16.09      8.73
    # ...
    # 2026-09-30  7651.54  16.34       NaN      <- the last 21 days have no 'realized' value:
    # 2026-10-01  7666.45  16.39       NaN         their next 21 days haven't happened yet
    # 2026-10-02  7722.72  15.31       NaN
    # (the same table is also saved to VIX/csv/data.csv)
    return data


def slice_event(data, day0):
    """Cut out [day0 - PRE_DAYS, day0 + POST_DAYS] and label each row."""
    # Position of day 0 in the table: counting TRADING days (rows) instead of
    # calendar days keeps weekends/holidays from distorting the windows.
    position0 = data.index.get_loc(pd.Timestamp(day0))       # row number of the shock date (text -> real date -> row number)
    window = data.iloc[position0 - PRE_DAYS: position0 + POST_DAYS + 1].copy()  # 40 rows before, day 0, 60 after (+1: the end of a slice is excluded); .copy() so we can add columns safely

    # event_day: -40 ... -1, 0, 1 ... 60  (0 = the shock day)
    window["event_day"] = np.arange(-PRE_DAYS, -PRE_DAYS + len(window))  # number the rows relative to day 0
    window["phase"] = np.select(                             # label each row with its phase
        [window["event_day"] < 0, window["event_day"] == 0],  # conditions, checked in order: before day 0, exactly day 0
        ["Pre-shock", "Day 0"],                              # the label that goes with each condition
        default="Aftermath",                                 # everything else is after day 0
    )
    # gap > 0: VIX above what happened (overpriced); gap < 0: underestimated
    window["gap"] = window["vix"] - window["realized"]       # how far the VIX was from the volatility that followed, per day

    # RETURNS a pandas DataFrame, shape (101, 6): 40 rows before + day 0 + 60 after, index = Date,
    # the 3 original columns (sp500, vix, realized) plus 3 new ones (event_day, phase, gap).
    # slice_event(data, "2020-02-24") prints as (middle rows left out):
    #               sp500    vix  realized  event_day      phase    gap
    # Date
    # 2019-12-24  3223.38  12.67      9.81        -40  Pre-shock   2.86
    # 2019-12-26  3239.91  12.65     10.25        -39  Pre-shock   2.40
    # ...
    # 2020-02-20  3373.23  15.56     84.69         -2  Pre-shock -69.13
    # 2020-02-21  3337.75  17.08     84.74         -1  Pre-shock -67.66
    # 2020-02-24  3225.89  25.03     92.46          0      Day 0 -67.43
    # 2020-02-25  3128.21  27.85     92.61          1  Aftermath -64.76
    # ...
    # 2020-05-19  2922.94  30.53     27.52         60  Aftermath   3.01
    return window


def verdict(gap):
    """Turn an average gap into a plain-words label."""
    if gap > TOLERANCE:                       # VIX clearly above what happened
        label = "VIX overreacted"
    elif gap < -TOLERANCE:                    # VIX clearly below what happened
        label = "VIX underestimated"
    else:                                     # within +/- TOLERANCE of zero
        label = "About right"

    # RETURNS a str, one of exactly three values:
    #   verdict(+5.0) -> "VIX overreacted"      (gap above +TOLERANCE)
    #   verdict(-5.0) -> "VIX underestimated"   (gap below -TOLERANCE)
    #   verdict(+0.5) -> "About right"          (gap within +/- TOLERANCE)
    return label


def phase_table(window):
    """Average VIX, realized vol and gap inside each phase."""
    rows = []                                 # will collect one small dictionary per phase
    for phase in PHASES:                      # "Pre-shock", then "Day 0", then "Aftermath"
        part = window[window["phase"] == phase]  # keep only the rows that belong to this phase
        rows.append({                         # summarize this phase in one dictionary
            "phase": phase,                   # the phase name
            "days": len(part),                # how many trading days it has
            "vix": part["vix"].mean(),        # average VIX in the phase
            "realized": part["realized"].mean(),  # average realized volatility in the phase
            "gap": part["gap"].mean(),        # average gap (VIX - realized) in the phase
        })

    # RETURNS a list of 3 dictionaries (one per phase, in the order Pre-shock, Day 0, Aftermath).
    # For the Covid window it prints as (numbers shown rounded to 1 decimal):
    # [{"phase": "Pre-shock", "days": 40, "vix": 14.3, "realized": 31.9, "gap": -17.6},
    #  {"phase": "Day 0",     "days":  1, "vix": 25.0, "realized": 92.5, "gap": -67.4},
    #  {"phase": "Aftermath", "days": 60, "vix": 44.9, "realized": 47.1, "gap":  -2.1}]
    return rows


def key_facts(window):
    """Headline numbers for one shock."""
    day0 = window[window["event_day"] == 0].iloc[0]          # the single row of the shock day (as a small Series)
    prev_close = window.loc[window["event_day"] == -1, "sp500"].iloc[0]  # S&P close on the day before the shock
    after = window[window["event_day"] >= 0]                 # day 0 and everything after it (peaks are searched here)
    vix_peak_date = after["vix"].idxmax()                    # the DATE on which the VIX was highest (idxmax = label of the max)

    facts = {
        "day0_date": window.index[window["event_day"] == 0][0],  # the shock date as a real date
        "sp_day0_return": (day0["sp500"] / prev_close - 1) * 100,  # S&P % change on day 0 vs the day before
        "vix_day0": day0["vix"],                             # VIX level on day 0
        "vix_peak": after["vix"].max(),                      # highest VIX after the shock
        "vix_peak_day": int(window.loc[vix_peak_date, "event_day"]),  # how many trading days after day 0 that peak was
        "realized_peak": after["realized"].max(),            # highest realized volatility after the shock
    }

    # RETURNS a dict with 6 keys. For the Covid window it prints as (floats shown rounded to 2 decimals):
    # {"day0_date": Timestamp("2020-02-24 00:00:00"),   # a pandas date
    #  "sp_day0_return": -3.35,                         # S&P % change on day 0
    #  "vix_day0": 25.03,                               # VIX level on day 0
    #  "vix_peak": 82.69,                               # highest VIX in days 0..60
    #  "vix_peak_day": 15,                              # an int: the peak came 15 trading days after day 0
    #  "realized_peak": 97.56}                          # highest realized volatility in days 0..60
    return facts


def shock_low(data, day0):
    """S&P 500 fall from the day-0 close to the lowest point of the shock.

    The shock "ends" when the index first regains its all-time high from
    before day 0 (or at the end of the data if it hasn't yet); the low is the
    lowest close in between. Using the old high, not the day-0 close, stops a
    one-day bounce from ending the shock early. This looks at ALL the data, not
    just the 60-day window, so slow bears like 2000-02 and 2008-09 reach their
    true bottom.
    """
    day0 = pd.Timestamp(day0)                                # text date -> real date
    previous_high = data["sp500"].loc[:day0].iloc[:-1].max()  # highest close up to day 0; .iloc[:-1] drops day 0 itself
    closes = data["sp500"].loc[day0:]                        # every close from day 0 to the end of the data
    start = closes.iloc[0]                                   # the day-0 close: all falls are measured from here
    back_at_high = closes.iloc[1:] >= previous_high          # True/False per later day: "is the index back at its old high?"
    recovered = bool(back_at_high.any())                     # did that ever happen? (at least one True)
    end = back_at_high.idxmax() if recovered else closes.index[-1]  # first True = recovery date; otherwise the last date in the data
    span = closes.loc[:end]                                  # the closes from day 0 to the end of the shock
    low_date = span.idxmin()                                 # the date of the lowest close in that span

    result = {
        "low_date": low_date,                                # when the bottom was
        "fall": (span.min() / start - 1) * 100,              # % fall from the day-0 close to the bottom
        "days_to_low": closes.index.get_loc(low_date),       # trading days from day 0 to the bottom
        "recovery_date": end if recovered else None,         # when the old high was regained (None = not yet)
    }

    # RETURNS a dict with 4 keys. shock_low(data, "2008-09-15") prints as (floats shown rounded to 2 decimals):
    # {"low_date": Timestamp("2009-03-09 00:00:00"),      # the date of the bottom
    #  "fall": -43.28,                                    # % fall from the day-0 close to the bottom
    #  "days_to_low": 120,                                # an int: trading days from day 0 to the bottom
    #  "recovery_date": Timestamp("2013-03-28 00:00:00")} # when the old high was regained (None if not yet)
    return result


def print_summary(windows):
    """Print the numbers in the terminal, so they can be checked without the browser."""
    for event, window in windows:                            # one block of text per shock
        print(f"\n{event['name']} (day 0 = {event['day0']})")  # title line
        low = event["low"]                                   # the day-0-to-bottom result stored on the event
        recovery = (f"{low['recovery_date']:%Y-%m-%d}" if low["recovery_date"] is not None  # recovery date as text...
                    else "not yet")                          # ...or "not yet" if the old high was never regained
        print(f"  S&P day 0 -> lowest point: {low['fall']:+.1f}% on {low['low_date']:%Y-%m-%d} "  # the fall and the date of the bottom
              f"({low['days_to_low']} trading days later); old high regained: {recovery}")
        for row in phase_table(window):                      # one line per phase
            print(f"  {row['phase']:<10} days={row['days']:>2}  "  # phase name and number of days (aligned in columns)
                  f"VIX={row['vix']:5.1f}  realized={row['realized']:5.1f}  "  # average VIX and realized volatility
                  f"gap={row['gap']:+6.1f}  -> {verdict(row['gap'])}")  # average gap with its sign, plus the verdict

    # RETURNS None (nothing). It only prints one block of text per shock in the terminal, for example:
    # Covid crash (day 0 = 2020-02-24)
    #   S&P day 0 -> lowest point: -30.6% on 2020-03-23 (20 trading days later); old high regained: 2020-08-18
    #   Pre-shock  days=40  VIX= 14.3  realized= 31.9  gap= -17.6  -> VIX underestimated
    #   Day 0      days= 1  VIX= 25.0  realized= 92.5  gap= -67.4  -> VIX underestimated
    #   Aftermath  days=60  VIX= 44.9  realized= 47.1  gap=  -2.1  -> VIX underestimated


def main():
    """Run the steps in order."""
    data = build_dataset()                                   # step 1: download and build the big table
    for event in EVENTS:                                     # step 2: for each shock...
        event["low"] = shock_low(data, event["day0"])        # ...measure the fall to the bottom (needs the full history)
    windows = [(event, slice_event(data, event["day0"])) for event in EVENTS]  # step 3: cut the 101-day window of each shock; a list of (event, table) pairs
    print_summary(windows)                                   # step 4: show the numbers in the terminal
    OUTPUT_PATH.write_text(build_page(windows, data), encoding="utf-8")  # step 5: build the web page (html / chart code below) and save it
    print(f"\nPage saved to {OUTPUT_PATH}")             # tell the user where the page is

    # RETURNS None (nothing). The results are its side effects:
    #   - the text summary printed in the terminal (see print_summary)
    #   - the file VIX/output/shocks.html (about 70 KB), and this last line in the terminal:
    #     Page saved to VIX/output/shocks.html (full path of your own machine)


# ===========================================================================
# html / chart code
# ===========================================================================
# Python only prepares the numbers (as JSON) and the text; the charts themselves are built
# in the browser by ECHARTS_JS below, one chart per <div class="chart">.
# Look: the "Lab" design every project page uses (see CLAUDE.md and nasdaq-bonds/nasdaq_bonds.py):
# burgundy header band (the VIX colour), rose accents, white panels, the homepage fonts, light and dark mode via colour tokens.
# Each shock keeps one fixed hue (dot-com = blue, 2008 = red, Covid = green, 2025 tariffs = amber), and the
# text always names the shock in words too, never by colour alone.

ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"  # Apache ECharts, a fixed version
FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"  # the homepage fonts


def chart_data(windows):
    """Everything the browser needs to draw the charts, as plain lists."""
    def clean(series):
        # NaN is not valid JSON, so use None (-> null). Round to keep the file small.
        values = [None if pd.isna(v) else round(float(v), 2) for v in series]  # one float (or None) per day
        # returns a list of floats/None, e.g. clean(window["vix"]) -> [12.67, 12.65, 13.43, ...] (101 items)
        return values

    events = []                                              # will hold one dictionary of lists per shock
    for event, window in windows:
        # S&P indexed to 100 on the day before the shock, so different index
        # levels (1,400 in 2000 vs 5,000+ in 2025) become comparable.
        base = window.loc[window["event_day"] == -1, "sp500"].iloc[0]  # the S&P close on day -1 (this becomes 100)
        events.append({
            "key": event["key"], "name": event["name"], "color": event["color"],  # identity and colour token of the shock
            "dates": [f"{d:%Y-%m-%d}" for d in window.index],  # x-axis labels for the shock tab
            "day0": f"{window.index[window['event_day'] == 0][0]:%Y-%m-%d}",  # the shock date, to draw the vertical line
            "event_day": [int(v) for v in window["event_day"]],  # -40 ... 60, the x-axis of the comparison charts
            "vix": clean(window["vix"]),                     # VIX values
            "realized": clean(window["realized"]),           # realized volatility values
            "gap": clean(window["gap"]),                     # gap values
            "sp_index": clean(window["sp500"] / base * 100),  # S&P indexed to 100 on day -1
        })

    # RETURNS a dict with 3 keys, made only of strings, ints, floats, None and lists (so json.dumps can turn it
    # into text for the browser). Each list inside an event has 101 items. For the Covid window (first 3 items shown):
    # {"events": [{"key": "covid", "name": "Covid crash", "color": "--covid",   # colour = a CSS token, read by the browser
    #              "dates":     ["2019-12-24", "2019-12-26", "2019-12-27", ...],
    #              "day0":      "2020-02-24",
    #              "event_day": [-40, -39, -38, ...],
    #              "vix":       [12.67, 12.65, 13.43, ...],
    #              "realized":  [9.81, 10.25, 10.26, ...],
    #              "gap":       [2.86, 2.4, 3.17, ...],
    #              "sp_index":  [96.57, 97.07, 97.07, ...]},     # S&P with day -1 = 100
    #             ... one such dict per shock (4 in the real page) ...],
    #  "horizon": 21, "pre_days": 40}
    return {"events": events, "horizon": FORWARD_HORIZON, "pre_days": PRE_DAYS}


def chart_div(chart_id, height, label):
    """Empty box; ECHARTS_JS draws the chart into it (shock charts: the first time their tab is shown)."""
    box = (f'<div class="chart" id="{chart_id}" data-h="{height}" style="height:{height}px" '  # an id, the desktop height (data-h) and a starting height
           f'role="img" aria-label="{escape(label)}"></div>')  # a text description for screen readers

    # RETURNS a str of HTML. chart_div("chart-covid", 480, "Covid crash: VIX against realized volatility") gives:
    # '<div class="chart" id="chart-covid" data-h="480" style="height:480px" role="img" aria-label="Covid crash: ..."></div>'
    # (data-h = the desktop height; the JavaScript makes some boxes taller on a phone)
    return box


# ---- the CSS and JavaScript that live inside the page ----

ECHARTS_JS = """
const DATA = __DATA__;                                          // everything Python computed, as JSON
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();  // read a colour token
let K = {};                                                     // the current colours (light or dark), read from the CSS tokens
function readColors() {                                         // (re)read every colour, e.g. after a light/dark switch
  K = { ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"), grid: css("--grid"), axis: css("--axis"),
        over: css("--over"), under: css("--under"), surface: css("--surface") };
  DATA.events.forEach(e => e.c = css(e.color));                 // each shock's line colour, e.g. "--covid" -> "#1f7a55"
}
readColors();
const FONT = "'DM Sans', system-ui, -apple-system, 'Segoe UI', sans-serif";
const fmt1 = v => (v === null || v === undefined) ? "-" : Number(v).toFixed(1);

// ---- phone layout ----
// narrow = a phone-sized screen. It is re-checked when the window changes, so rotating the phone redraws the charts.
const narrowMQ = window.matchMedia("(max-width: 640px)");
const isNarrow = () => narrowMQ.matches;
const isTouch = window.matchMedia("(pointer: coarse)").matches;   // a finger instead of a mouse
// Chart box heights (px) on a phone; on desktop each box keeps the height in its data-h attribute.
const NARROW_H = { "chart-levels": 640, "chart-gap": 420, "chart-sp": 420 };
function fitHeight(div) { div.style.height = ((isNarrow() && NARROW_H[div.id]) || div.dataset.h) + "px"; }

// Axis look shared by every chart: recessive grid, light axis line.
const axisStyle = () => ({
  axisLine: { lineStyle: { color: K.axis } }, axisTick: { lineStyle: { color: K.axis } },
  axisLabel: { color: K.ink2 }, splitLine: { lineStyle: { color: K.grid } }
});
// Tooltip look: the page's own surface, border and ink colours (never ECharts' default white box, which glares in
// dark mode), plus a soft shadow so the box lifts off the chart. Read from K, so a theme switch + redraw updates it.
const tipBox = () => ({ backgroundColor: K.surface, borderColor: K.grid, borderWidth: 1,
  extraCssText: "box-shadow: 0 6px 18px rgba(0,0,0,.18); border-radius: 8px;" });
// Axis-pointer labels (the small value boxes on an axis) get the same colours as the tooltip.
const pointerLabel = () => ({ backgroundColor: K.surface, borderColor: K.grid, borderWidth: 1, color: K.ink,
  shadowBlur: 8, shadowColor: "rgba(0,0,0,.18)" });
// Options shared by every chart. Tooltips open on a tap on touch screens.
const base = () => ({
  animation: false, backgroundColor: "transparent", textStyle: { fontFamily: FONT, color: K.ink2 },
  tooltip: { trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click", valueFormatter: fmt1, confine: true,
             ...tipBox(), textStyle: { color: K.ink, fontSize: isNarrow() ? 12 : 14 },
             axisPointer: { label: pointerLabel() } },          // the pointer's own value label, if one is shown
  axisPointer: { link: [{ xAxisIndex: "all" }], label: pointerLabel() }
});
const yAxis = (name, extra = {}) => ({ type: "value", name, nameLocation: "middle", nameGap: isNarrow() ? 34 : 42,
  nameTextStyle: { color: K.ink2 }, scale: true, ...axisStyle(), ...extra });
// Phone: legend one entry per line, BELOW the plot. Desktop: one row above the plot.
const legendFor = (narrow, data) => narrow
  ? { bottom: 0, left: 0, orient: "vertical", itemGap: 6, data, textStyle: { color: K.ink2 } }
  : { top: 0, left: 0, data, textStyle: { color: K.ink2 } };

// Legend icons drawn by hand so "solid" and "dashed" are obvious (34 x 4 px, same as itemWidth x itemHeight).
const SOLID_ICON = "path://M0,0 L34,0 L34,4 L0,4 Z";                 // one long bar = solid line
const DASHED_ICON = "path://M0,0 L9,0 L9,4 L0,4 Z M12.5,0 L21.5,0 L21.5,4 L12.5,4 Z M25,0 L34,0 L34,4 L25,4 Z";  // three short bars = dashed line

// ---- one shock: VIX vs realized (top), gap bars (bottom) ----
function shockOption(e) {
  const narrow = isNarrow();
  // On a phone the 3 legend entries are stacked one per line, so the plots start lower and sit closer to the edges.
  const L = narrow ? 48 : 56, R = narrow ? 18 : 16;               // left / right margin of the plots
  const topMain = narrow ? 86 : 40, hMain = narrow ? 222 : 270;   // top plot: start and height
  const topGap = topMain + hMain + 30, hGap = narrow ? 90 : 110;  // bottom (gap bars) plot
  // dotted vertical line on day 0
  const day0Line = { silent: true, symbol: "none", lineStyle: { color: K.ink, width: 1.5, type: "dotted" },
                     label: { show: false }, data: [{ xAxis: e.day0 }] };
  // shaded band (pre-shock) or invisible band (aftermath) that only carries a text label
  const phaseArea = (name, from, to, shade) => [
    { name, xAxis: from, itemStyle: { color: shade ? K.muted : "transparent", opacity: shade ? 0.12 : 1 },
      label: { position: "insideTop", color: K.ink2 } },
    { xAxis: to }];
  const last = e.dates.length - 1;
  const ax = axisStyle();
  return { ...base(),
    legend: { top: 0, left: 0, orient: narrow ? "vertical" : "horizontal", itemWidth: narrow ? 28 : 34, itemHeight: 4,
      itemGap: narrow ? 6 : 28, textStyle: { color: K.ink2, fontSize: 12 },
      data: [{ name: "VIX - expected (solid line)", icon: SOLID_ICON },
             { name: "Realized, next " + DATA.horizon + "d - actual (dashed line)", icon: DASHED_ICON },
             { name: "Gap (VIX - realized)", icon: "rect", itemStyle: { color: K.muted } }] },
    grid: [{ left: L, right: R, top: topMain, height: hMain }, { left: L, right: R, top: topGap, height: hGap }],
    xAxis: [{ type: "category", gridIndex: 0, data: e.dates, axisLabel: { show: false }, axisLine: ax.axisLine, axisTick: { show: false } },
            // alignMin/MaxLabel keep the first and last date from being cut off at the edges of the screen
            { type: "category", gridIndex: 1, data: e.dates, ...ax, splitLine: { show: false },
              axisLabel: { color: K.ink2, hideOverlap: true, alignMinLabel: "left", alignMaxLabel: "right",
                           ...(narrow ? { interval: Math.floor((e.dates.length - 1) / 2) - 1 } : {}) } }],  // phone: first, middle and last date only
    yAxis: [yAxis("Annualized vol (%)", { gridIndex: 0 }), yAxis("VIX - realized (pts)", { gridIndex: 1, scale: false })],
    // On a touch screen a finger drag over the chart would zoom it instead of scrolling the page, so zoom is mouse-only.
    dataZoom: isTouch ? [] : [{ type: "inside", xAxisIndex: [0, 1] }],
    series: [
      { name: "VIX - expected (solid line)", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: e.vix, showSymbol: false,
        lineStyle: { color: e.c, width: 2 }, itemStyle: { color: e.c }, markLine: day0Line,
        markArea: { silent: true, data: [phaseArea("Pre-shock", e.dates[0], e.day0, true), phaseArea("Aftermath", e.day0, e.dates[last], false)] } },
      { name: "Realized, next " + DATA.horizon + "d - actual (dashed line)", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: e.realized, showSymbol: false,
        lineStyle: { color: e.c, width: 2, type: "dashed" }, itemStyle: { color: e.c } },
      // blue bar = VIX too high (overpriced), red bar = VIX too low (underestimated)
      { name: "Gap (VIX - realized)", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: e.gap, markLine: day0Line,
        itemStyle: { color: p => p.value >= 0 ? K.over : K.under } }
    ] };
}

// ---- comparison charts: four shocks overlaid on one "days since day 0" axis ----
const names = DATA.events.map(e => e.name);
const pairs = (e, field) => e.event_day.map((d, i) => [d, e[field][i]]);   // [x = day, y = value]
const day0Marker = () => ({ silent: true, symbol: "none", lineStyle: { color: K.ink, width: 1.5, type: "dotted" }, label: { show: false }, data: [{ xAxis: 0 }] });
const lineSeries = (e, field, extra = {}) => ({ name: e.name, type: "line", data: pairs(e, field), showSymbol: false,
  lineStyle: { color: e.c, width: 2 }, itemStyle: { color: e.c }, ...extra });
const dayAxis = (extra = {}) => ({ type: "value", min: -DATA.pre_days, name: "Trading days since day 0", nameLocation: "middle", nameGap: 28,
  nameTextStyle: { color: K.ink2 }, ...axisStyle(), splitLine: { show: false },
  axisPointer: { label: { ...pointerLabel(), formatter: p => "Day " + Math.round(p.value) } },  // tooltip title "Day 15", not "15.00"
  ...extra });
// a reference line on the first series only: dotted vertical at day 0 + a solid horizontal one
const refLines = (yValue, yColor) => ({ markLine: { silent: true, symbol: "none", label: { show: false }, data: [
  { xAxis: 0, lineStyle: { color: K.ink, width: 1.5, type: "dotted" } }, { yAxis: yValue, lineStyle: { color: yColor, width: 1, type: "solid" } }] } });
const panelTitle = (text, left, top) => ({ text, left, top, textStyle: { color: K.ink2, fontSize: 13, fontWeight: 600 } });

function levelsOption() {
  const narrow = isNarrow();
  // Same y range on both panels so VIX and realized can be compared by eye.
  const all = DATA.events.flatMap(e => [...e.vix, ...e.realized]).filter(v => v !== null);
  const top = Math.ceil(Math.max(...all) / 10) * 10;
  const laneY = (gridIndex, name) => yAxis(name, { gridIndex, min: 0, max: top, scale: false });
  return { ...base(),
    legend: legendFor(narrow, names),
    // Desktop: VIX and realized side by side. Phone: stacked, one above the other, so each gets the full width.
    title: narrow ? [panelTitle("VIX (expected)", 48, 0), panelTitle("Realized, next " + DATA.horizon + "d (actual)", 48, 262)]
                  : [panelTitle("VIX (expected)", 56, 34), panelTitle("Realized, next " + DATA.horizon + "d (actual)", "54%", 34)],
    grid: narrow ? [{ left: 48, right: 18, top: 26, height: 200 }, { left: 48, right: 18, top: 288, height: 200 }]
                 : [{ left: 56, width: "40%", top: 70, height: 250 }, { left: "54%", right: 16, top: 70, height: 250 }],
    xAxis: narrow ? [dayAxis({ gridIndex: 0, name: "" }), dayAxis({ gridIndex: 1 })]
                  : [dayAxis({ gridIndex: 0 }), dayAxis({ gridIndex: 1, name: "" })],
    yAxis: [laneY(0, "Annualized vol (%)"), laneY(1, narrow ? "Annualized vol (%)" : "")],
    series: DATA.events.flatMap(e => [
      lineSeries(e, "vix", { xAxisIndex: 0, yAxisIndex: 0, markLine: day0Marker() }),
      lineSeries(e, "realized", { xAxisIndex: 1, yAxisIndex: 1, markLine: day0Marker() })]) };
}
function gapOption() {
  const narrow = isNarrow();
  return { ...base(),
    legend: legendFor(narrow, names),
    // Desktop: the hint sits top-right. Phone: it sits above the plot (the legend is below).
    // On a phone the one-line hint was wider than the screen and got cut off, so it is split over two lines there.
    title: { text: narrow ? "above 0: VIX overpriced\\nbelow 0: underestimated" : "above 0: VIX overpriced  |  below 0: underestimated",
             ...(narrow ? { left: 0, top: 0 } : { right: 16, top: 2 }),
             textStyle: { color: K.muted, fontSize: 12, fontWeight: "normal" } },
    grid: { left: narrow ? 48 : 56, right: narrow ? 18 : 16, top: narrow ? 46 : 40, height: narrow ? 240 : 260 },  // phone: room for the 2-line hint
    xAxis: dayAxis(), yAxis: yAxis("VIX - realized (pts)", { scale: false }),
    series: DATA.events.map((e, i) => lineSeries(e, "gap", i === 0 ? refLines(0, K.ink) : {})) };
}
function spOption() {
  const narrow = isNarrow();
  return { ...base(),
    legend: legendFor(narrow, names),
    grid: { left: narrow ? 48 : 56, right: narrow ? 18 : 16, top: narrow ? 14 : 40, height: 260 },
    xAxis: dayAxis(), yAxis: yAxis("S&P 500 (day -1 = 100)"),
    series: DATA.events.map((e, i) => lineSeries(e, "sp_index", i === 0 ? refLines(100, K.axis) : {})) };
}

// chart id -> function that builds its option
const BUILDERS = { "chart-levels": levelsOption, "chart-gap": gapOption, "chart-sp": spOption };
DATA.events.forEach(e => BUILDERS["chart-" + e.key] = () => shockOption(e));
const INSTANCES = {};
function initChart(div) {                                       // draw a chart the first time, or just refit it
  fitHeight(div);                                               // taller boxes on a phone
  if (!INSTANCES[div.id]) {
    INSTANCES[div.id] = echarts.init(div);
    INSTANCES[div.id].setOption(BUILDERS[div.id]());
  } else {
    INSTANCES[div.id].resize();
  }
}
function redrawAll() {                                          // rebuild every drawn chart (new layout or new colours)
  Object.entries(INSTANCES).forEach(([id, chart]) => {
    fitHeight(document.getElementById(id)); chart.resize(); chart.setOption(BUILDERS[id](), true); });
}
// Keep charts fitted when the window changes. If the screen crosses the phone/desktop line (e.g. the phone is
// rotated), resize the box and rebuild the chart with the other layout.
let wasNarrow = isNarrow();
addEventListener("resize", () => {
  const changed = isNarrow() !== wasNarrow;
  wasNarrow = isNarrow();
  if (changed) redrawAll(); else Object.values(INSTANCES).forEach(c => c.resize());
});
// A switch between light and dark mode: read the new colours and redraw, so lines AND tooltips take the new tokens.
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { readColors(); redrawAll(); });
"""


CSS = """
:root{color-scheme:light dark;--band:#4a1626;--band-ink:#e4e6ea;--brass:#d0506c;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--dotcom:#2a5db0;--gfc:#c4452f;--covid:#1f7a55;--tariffs:#c98f17;--over:#2a5db0;--under:#c4452f}
@media (prefers-color-scheme:dark){:root{--band:#33101b;--brass:#ec8098;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--dotcom:#6d9be0;--gfc:#e8775f;--covid:#3fa37c;--tariffs:#e2b04e;--over:#6d9be0;--under:#e8775f}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 "DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
h1,h2,h3,.kpi b{font-family:"DM Serif Display",Georgia,serif;font-weight:400}
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
.kpis.five{grid-template-columns:repeat(5,1fr);margin:0 0 18px}
.kpi{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:16px 18px}
.top .kpi{box-shadow:0 14px 34px rgba(0,0,0,.10)}
.kpi b{display:block;font-size:30px;font-variant-numeric:tabular-nums}
.kpi span{display:block;font-size:13px;line-height:1.45;color:var(--ink-2)}
.five .kpi{padding:12px 14px}
.five .kpi b{font-size:24px}
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
.label{margin:18px 0 4px;font-size:13px;font-weight:600;color:var(--ink-2)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle;flex:none}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 18px}
.tabs button{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border:1px solid var(--grid);border-radius:999px;
  background:transparent;color:var(--ink-2);font:inherit;font-size:14px;font-weight:600;cursor:pointer}
.tabs button[aria-selected=true]{background:var(--ink);color:var(--page);border-color:var(--ink)}
.tabpanel[hidden]{display:none}
.tabpanel h3{margin:0 0 4px;font-size:22px;line-height:1.2}
.why{margin:0 0 16px;color:var(--ink-2);font-size:15px}
.gloss{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;margin:0}
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
.sum th{white-space:normal;vertical-align:bottom}   /* 9 columns: wrap the headers so the table fits a desktop screen */
.swipe-hint{display:none;margin:8px 0 0;font-size:13px;color:var(--muted)}
.refs{margin:32px 0 0;padding:0 2px;color:var(--muted);font-size:13px;line-height:1.5}   /* quiet: no panel box, small muted text */
.refs-title{margin:0 0 2px;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
.refs ul{list-style:none;margin:0;padding:0}
.refs a{display:inline-flex;align-items:center;min-height:40px;padding:4px 0;color:var(--ink-2);   /* 40px tall: easy to tap */
  text-decoration:underline;text-decoration-color:var(--axis);text-underline-offset:3px}
.refs a:hover{color:var(--ink)}
@media (max-width:640px){.refs a{display:flex}.refs .sep{display:none}.refs li{margin:0 0 8px}}   /* phone: link on its own 40px line, what it gave just below */
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:720px){.kpis,.kpis.five{grid-template-columns:1fr 1fr;gap:10px}.five .kpi:last-child{grid-column:1/-1}
  .panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
@media (max-width:640px){
  .gloss{grid-template-columns:1fr;gap:18px}
  th,td{padding:8px 4px;font-size:13px}
  .phase th,.phase td{white-space:normal;padding:8px 3px;font-size:12.5px}
  .phase th{text-transform:none;letter-spacing:0}
  .phase th:first-child,.phase td:first-child{position:static}   /* 5 narrow columns fit, no need to pin the first */
  .phase th:nth-child(2),.phase td:nth-child(2){display:none}   /* drop the "Days" column so Verdict stays on screen */
  .sum th{white-space:nowrap}   /* phone: keep the table one line high and let it scroll sideways */
  .swipe-hint{display:block}
}
"""

JS = """
function showTab(id) {
  document.querySelectorAll('.tabpanel').forEach(p => p.hidden = (p.id !== id));
  document.querySelectorAll('.tabs button').forEach(b =>
    b.setAttribute('aria-selected', b.dataset.tab === id));
  // ECharts can't measure a hidden box, so each shock chart is created the
  // first time its tab is shown (and just resized on later visits).
  document.querySelectorAll('#' + id + ' .chart').forEach(initChart);
}
document.querySelectorAll('.tabs button').forEach(b =>
  b.addEventListener('click', () => showTab(b.dataset.tab)));
// Every chart that is not inside a hidden tab is visible: draw it now.
document.querySelectorAll('.chart').forEach(div => { if (!div.closest('[hidden]')) initChart(div); });
if (isTouch) document.querySelectorAll('.hint').forEach(h => h.textContent = 'Tap');   // say "tap", not "hover", to touch users
"""


# ---- Python helpers that build the HTML text ----

def fmt(value, signed=False, suffix=""):
    """Format a number with 1 decimal (optionally with a +/- sign and a suffix like %)."""
    text = f"{value:+.1f}{suffix}" if signed else f"{value:.1f}{suffix}"  # "+" forces a sign; .1f = one decimal

    # RETURNS a str:
    #   fmt(-3.4412, True, "%") -> '-3.4%'
    #   fmt(25.04)              -> '25.0'
    return text


def tile(value, label, color=None):
    """One headline number with its caption; an optional dot names the shock by its chart colour."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""  # identity is in the caption too, never colour alone
    html = f'<div class="kpi"><b>{dot}{value}</b><span>{escape(label)}</span></div>'  # escape() keeps odd characters in the caption from breaking the HTML

    # RETURNS a str of HTML. tile("-3.4%", "S&P 500 on day 0") gives:
    # '<div class="kpi"><b>-3.4%</b><span>S&amp;P 500 on day 0</span></div>'
    return html


def scorecard(windows):
    """Gather, per shock, the phase averages, the key facts and the fall to the low (used by all the text below)."""
    card = []                                                # one dict per shock, in the order of EVENTS
    for event, window in windows:
        card.append({
            "name": event["name"],                           # e.g. "Covid crash"
            "color": event["color"],                         # its colour token, e.g. "--covid"
            "phases": {r["phase"]: r for r in phase_table(window)},  # look up a phase's averages by its name
            "facts": key_facts(window),                      # day-0 move, VIX peak, realized peak...
            "low": event["low"],                             # day 0 -> lowest point (full history)
        })

    # RETURNS a list of 4 dicts (one per shock). The Covid one prints as (floats rounded):
    # {"name": "Covid crash", "color": "--covid",
    #  "phases": {"Pre-shock": {"phase": "Pre-shock", "days": 40, "vix": 14.3, "realized": 31.9, "gap": -17.6},
    #             "Day 0": {..., "gap": -67.4}, "Aftermath": {..., "gap": -2.1}},
    #  "facts": {"day0_date": Timestamp("2020-02-24"), "sp_day0_return": -3.35, "vix_day0": 25.03, "vix_peak": 82.69,
    #            "vix_peak_day": 15, "realized_peak": 97.56},
    #  "low": {"low_date": Timestamp("2020-03-23"), "fall": -30.6, "days_to_low": 20, "recovery_date": Timestamp("2020-08-18")}}
    return card


def names_with(card, phase, label):
    """The shocks whose average gap in `phase` got the verdict `label`."""
    names = [c["name"] for c in card if verdict(c["phases"][phase]["gap"]) == label]  # keep a shock when its verdict matches

    # RETURNS a list of str, e.g. names_with(card, "Aftermath", "VIX overreacted") -> ['Dot-com crash', '2025 tariff shock']
    return names


def join_names(names):
    """Write a list of names as readable English: 'A', 'A and B', 'A, B and C', or 'none'."""
    if not names:                                            # empty list
        text = "none"
    elif len(names) == 1:                                    # one name
        text = names[0]
    else:                                                    # two or more: commas, then "and" before the last
        text = ", ".join(names[:-1]) + " and " + names[-1]

    # RETURNS a str, e.g. join_names(['Dot-com crash', '2025 tariff shock']) -> 'Dot-com crash and 2025 tariff shock'
    return text


def aftermath_text(card):
    """One sentence on the aftermath verdicts, naming only the verdicts that actually occur."""
    parts = []                                               # e.g. ["overreacted in Dot-com crash and 2025 tariff shock", ...]
    for label, phrase in [("VIX overreacted", "overreacted in"), ("VIX underestimated", "was still too low in"),
                          ("About right", "was about right in")]:
        names = names_with(card, "Aftermath", label)         # the shocks with this verdict
        if names:                                            # skip verdicts nobody got, so the text never says "in none"
            parts.append(f"{phrase} {join_names(names)}")
    text = f"After day 0 the VIX {join_names(parts)}."       # glue the parts with commas and a final "and"

    # RETURNS a str, e.g. 'After day 0 the VIX overreacted in Dot-com crash and 2025 tariff shock and was still too low
    #  in 2008 financial crisis and Covid crash.'
    return text


def answer_text(card):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    n = len(card)                                            # number of shocks (4)
    pre_low = names_with(card, "Pre-shock", "VIX underestimated")  # VIX too low before day 0
    pre_high = names_with(card, "Pre-shock", "VIX overreacted")    # VIX too high before day 0
    day0_low = names_with(card, "Day 0", "VIX underestimated")     # VIX too low on day 0
    post_high = names_with(card, "Aftermath", "VIX overreacted")   # VIX too high after day 0
    post_low = names_with(card, "Aftermath", "VIX underestimated")  # VIX still too low after day 0
    pre_gaps = [c["phases"]["Pre-shock"]["gap"] for c in card]     # average pre-shock gap of each shock
    if len(pre_low) > n / 2:                                 # most shocks: the VIX was too low going in
        lead = "<b>Mostly no: it was too low going in.</b> "
    elif len(pre_high) > n / 2:                              # most shocks: too high going in
        lead = "<b>Mostly no: it was too high going in.</b> "
    else:                                                    # no clear majority
        lead = "<b>Only partly.</b> "
    text = (lead + f"In {len(pre_low)} of {n} shocks the VIX sat below the volatility that followed during the {PRE_DAYS} "
            f"trading days before day 0 (average gap {fmt(min(pre_gaps), True)} to {fmt(max(pre_gaps), True)} points), and on "
            f"day 0 itself it was too low in {len(day0_low)} of {n}. In the {POST_DAYS} days after, it overreacted in "
            f"{len(post_high)} and was still too low in {len(post_low)}.")

    # RETURNS a str of HTML, about 330 characters, e.g.
    # '<b>Mostly no: it was too low going in.</b> In 4 of 4 shocks the VIX sat below the volatility that followed during
    #  the 40 trading days before day 0 (average gap -17.6 to -5.4 points), and on day 0 itself it was too low in 3 of 4.
    #  In the 60 days after, it overreacted in 2 and was still too low in 2.'
    return text


def summary_table(card):
    """The table of all four shocks: day 0, gap per phase, peaks and the fall to the low."""
    rows = ""                                                # HTML table rows, built up one shock at a time
    for c in card:
        f, p, low = c["facts"], c["phases"], c["low"]        # short names for this shock's numbers
        rows += (
            f'<tr><td><i class="dot" style="background:var({c["color"]})"></i>'  # colour dot...
            f'{escape(c["name"])}</td>'                      # ...and the shock name
            f'<td>{f["day0_date"]:%d %b %Y}</td>'            # day 0 date
            f'<td>{fmt(f["sp_day0_return"], True, "%")}</td>'  # S&P move on day 0
            f'<td>{fmt(p["Pre-shock"]["gap"], True)}</td>'   # average gap before
            f'<td>{fmt(p["Day 0"]["gap"], True)}</td>'       # gap on day 0
            f'<td>{fmt(p["Aftermath"]["gap"], True)}</td>'   # average gap after
            f'<td>{fmt(f["vix_peak"])} (day {f["vix_peak_day"]})</td>'  # VIX peak and when
            f'<td>{fmt(f["realized_peak"])}</td>'            # peak realized volatility
            f'<td>{fmt(low["fall"], True, "%")} ({low["low_date"]:%b %Y})</td></tr>')  # fall from day 0 to the bottom, and its month
    html = ('<div class="scroll"><table class="sum">'       # the table sits in its own sideways-scrolling box
            '<tr><th>Shock</th><th>Day 0</th><th>S&amp;P day 0</th><th>Gap: pre-shock</th>'
            '<th>Gap: day 0</th><th>Gap: aftermath</th><th>VIX peak</th>'
            f'<th>Peak realized</th><th>S&amp;P day 0 to low</th></tr>{rows}</table></div>'
            '<p class="swipe-hint">Swipe the table sideways to see all columns &rarr;</p>')  # shown on phones only

    # RETURNS a str of HTML: a header and one row per shock (4 rows), plus a swipe hint shown only on phones, e.g.
    # <tr><td><i class="dot" ...></i>Covid crash</td><td>24 Feb 2020</td><td>-3.4%</td><td>-17.6</td><td>-67.4</td>
    #     <td>-2.1</td><td>82.7 (day 15)</td><td>97.6</td><td>-30.6% (Mar 2020)</td></tr>
    return html


def phase_table_html(rows):
    """The small 3-row table of averages at the bottom of each shock tab."""
    body = "".join(                                          # glue the rows together into one string
        f"<tr><td>{r['phase']}</td><td>{r['days']}</td><td>{fmt(r['vix'])}</td>"  # phase, days, average VIX
        f"<td>{fmt(r['realized'])}</td><td>{fmt(r['gap'], signed=True)}</td>"  # average realized, average gap
        f"<td>{verdict(r['gap']).replace('underestimated', 'under&shy;estimated').replace('overreacted', 'over&shy;reacted')}</td></tr>"  # the verdict label; &shy; = an invisible hyphenation point, so the long word can break on a phone
        for r in rows)                                       # one <tr> per phase
    html = ('<div class="scroll"><table class="phase"><tr><th>Phase</th><th>Days</th>'  # header row...
            '<th>Avg VIX</th><th>Avg realized</th><th>VIX - realized</th>'
            f'<th>Verdict</th></tr>{body}</table></div>')    # ...then the body rows

    # RETURNS a str of HTML (about 600 characters): a <table> with a header row and 3 body rows. For the Covid window:
    # '<div class="scroll"><table class="phase"><tr><th>Phase</th><th>Days</th><th>Avg VIX</th><th>Avg realized</th>
    #  <th>VIX - realized</th><th>Verdict</th></tr>
    #  <tr><td>Pre-shock</td><td>40</td><td>14.3</td><td>31.9</td><td>-17.6</td><td>VIX underestimated</td></tr>
    #  <tr><td>Day 0</td><td>1</td><td>25.0</td><td>92.5</td><td>-67.4</td><td>VIX underestimated</td></tr>
    #  <tr><td>Aftermath</td><td>60</td><td>44.9</td><td>47.1</td><td>-2.1</td><td>VIX underestimated</td></tr>
    #  </table></div>'
    return html


def shock_tab(event, window, first):
    """The content of one shock's tab: title, why this day, tiles, chart and phase table."""
    facts = key_facts(window)                                # headline numbers from the window
    low = event["low"]                                       # day 0 -> lowest point, computed on the full history
    tiles = "".join([                                        # five tiles glued into one string
        tile(fmt(facts["sp_day0_return"], True, "%"), "S&P 500 on day 0"),
        tile(fmt(facts["vix_day0"]), "VIX on day 0"),
        tile(fmt(facts["vix_peak"]), f"VIX peak (day {facts['vix_peak_day']})"),
        tile(fmt(facts["realized_peak"]), "Peak realized vol after day 0"),
        tile(fmt(low["fall"], True, "%"),
             f"S&P day 0 to lowest point ({low['low_date']:%d %b %Y}, "
             f"{low['days_to_low']} trading days later)"),
    ])
    hidden = "" if first else " hidden"                      # only the first tab is visible when the page opens
    html = f"""
<div class="tabpanel" id="{event['key']}" role="tabpanel"{hidden}>
  <h3><i class="dot" style="background:var({event['color']})"></i>{escape(event['name'])} - day 0 = {facts['day0_date']:%d %b %Y}</h3>
  <p class="why">{escape(event['why'])}</p>
  <div class="kpis five">{tiles}</div>
  {chart_div('chart-' + event['key'], 480, event['name'] + ': VIX against the realized volatility that followed, with the daily gap')}
  <p class="label">Averages by phase</p>
  {phase_table_html(phase_table(window))}
</div>"""

    # RETURNS a str of HTML (about 1,700 characters): one tab panel, hidden unless it is the first tab.
    # For the Covid window it is built like this:
    # <div class="tabpanel" id="covid" role="tabpanel" hidden>
    #   <h3><i class="dot" ...></i>Covid crash - day 0 = 24 Feb 2020</h3>
    #   <p class="why">First big panic day after the outbreak in Italy: ...</p>
    #   <div class="kpis five"> ...5 <div class="kpi"> boxes... </div>
    #   <div class="chart" id="chart-covid" ...></div>      <- empty; the browser draws the chart here
    #   <p class="label">Averages by phase</p> + the phase table
    # </div>
    return html


def panel(number, question, finding, how, body, so=""):
    """One numbered section: a question, its one-line finding, how to read it, the chart or table, and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""          # optional reading guide
    so_html = f'<div class="so">{so}</div>' if so else ""                                  # optional takeaway

    # RETURNS a str of HTML, e.g. '<section class="panel"><p class="tag">01</p><h2>How did the VIX score in each shock?</h2>
    #  <p class="dek">Before day 0 the VIX was too low in 4 of 4 shocks ...</p><p class="how">...</p>...</section>'
    return (f'<section class="panel"><p class="tag">{number:02d}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def glossary():
    """The key ideas, in plain words, with the settings of this study filled in from the constants."""
    terms = [                                                # (term, plain-language meaning)
        ("VIX (expected)", "The market's expectation of S&amp;P 500 volatility over roughly the next month, read from option "
                           "prices and quoted as an annualized %. VIX(t) is a claim about the days AFTER t."),
        (f"Realized volatility, next {FORWARD_HORIZON}d (actual)",
         f"What volatility actually turned out to be: the spread (standard deviation) of the S&amp;P 500's daily log returns "
         f"over the {FORWARD_HORIZON} trading days after each date, annualized (x &radic;252) and in %. It looks at the days "
         f"after t, not the days before, which would compare the VIX to the wrong time window."),
        ("Gap (VIX - realized)", "How far the VIX was from the volatility that followed, in annualized vol points. A positive "
                                 "gap means the VIX overpriced volatility; a negative gap means the market underestimated what was coming."),
        ("Day 0", "The first big panic day of each shock, not necessarily the worst day, so the pre-shock window stays "
                  "genuinely calm. Each date was checked against the data: worst S&amp;P day or biggest one-day VIX jump of the episode."),
        ("Pre-shock and aftermath", f"Pre-shock: the {PRE_DAYS} trading days before day 0. Aftermath: the {POST_DAYS} trading "
                                    f"days after it. Counting trading days, not calendar days, keeps weekends and holidays out."),
        ("Verdict", f"Average gap above +{TOLERANCE:.0f} pts: VIX overreacted. Below -{TOLERANCE:.0f}: VIX underestimated. "
                    f"In between: about right."),
    ]
    html = '<dl class="gloss">' + "".join(f"<div><dt>{t}</dt><dd>{d}</dd></div>" for t, d in terms) + "</dl>"  # one <dt>/<dd> pair per term

    # RETURNS a str of HTML: a <dl> with 6 terms, e.g.
    # '<dl class="gloss"><div><dt>VIX (expected)</dt><dd>The market's expectation of S&amp;P 500 volatility ...</dd></div> ...</dl>'
    return html


REFERENCES = [                            # (source name = the link text, what it gave us, link) for the data and the companion page
    ("Yahoo Finance, ^GSPC", "daily S&P 500 closes, downloaded with yfinance", "https://finance.yahoo.com/quote/%5EGSPC/"),
    ("Yahoo Finance, ^VIX", "daily VIX closes, downloaded with yfinance", "https://finance.yahoo.com/quote/%5EVIX/"),
    ("Does the VIX overprice volatility?", "companion page: the VIX against what followed over 30 years (VIX/volatility.py)",
     "volatility.html"),
]


def references():
    """The quiet 'References' block after the last panel: small muted lines, no panel box, no question heading."""
    items = ""                                               # the <li> lines, built one by one
    for name, gave, url in REFERENCES:
        new_tab = ' target="_blank" rel="noopener"' if url.startswith("http") else ""  # outside sites in a new tab, our own page in the same tab
        items += (f'<li><a href="{escape(url)}"{new_tab}>{escape(name)}</a>'  # the source name is the link (40px tall via CSS)
                  f'<span class="sep"> &middot; </span>{escape(gave)}</li>')         # then, in plain muted text, what it gave us
    html = (f'<aside class="refs" aria-label="References"><p class="refs-title">References</p>'  # small uppercase label, not a question
            f'<ul>{items}</ul></aside>')                     # the lines themselves

    # RETURNS a str of HTML (about 600 characters): an <aside> with a small label and a <ul> of 3 lines, e.g.
    # '<aside class="refs" aria-label="References"><p class="refs-title">References</p><ul>
    #  <li><a href="https://finance.yahoo.com/quote/%5EGSPC/" target="_blank" rel="noopener">Yahoo Finance, ^GSPC</a>
    #      <span class="sep"> &middot; </span>daily S&amp;P 500 closes, downloaded with yfinance</li>
    #  ... ^VIX line ...
    #  <li><a href="volatility.html">Does the VIX overprice volatility?</a> &middot; companion page: ...</li></ul></aside>'
    return html


def conclusions(card):
    """The 'What did we learn?' list, written from the numbers."""
    n = len(card)                                            # number of shocks
    pre_low = names_with(card, "Pre-shock", "VIX underestimated")  # VIX too low before day 0
    day0_low = names_with(card, "Day 0", "VIX underestimated")     # VIX too low on day 0
    day0_other = [c["name"] for c in card if c["name"] not in day0_low]  # the exceptions on day 0
    worst = min(card, key=lambda c: c["phases"]["Day 0"]["gap"])  # the shock with the most negative day-0 gap
    falls = [c["low"]["fall"] for c in card]                 # S&P fall from day 0 to the low, per shock
    days = [c["low"]["days_to_low"] for c in card]           # trading days from day 0 to the low, per shock
    items = [
        (f"<b>Going in, the VIX was too low.</b> In {len(pre_low)} of {n} shocks the average gap over the {PRE_DAYS} "
         f"pre-shock days was below -{TOLERANCE:.0f} points: the market underestimated what was coming."),
        (f"<b>On day 0 it was still too low in {len(day0_low)} of {n}</b> (exception: {join_names(day0_other)}). The biggest "
         f"miss was {fmt(worst['phases']['Day 0']['gap'], True)} points in the {worst['name']}."),
        f"<b>Mixed in the aftermath.</b> {aftermath_text(card)}",
        (f"<b>The shocks were very different.</b> From day 0 to the lowest point the S&amp;P 500 fell between "
         f"{fmt(max(falls), True, '%')} and {fmt(min(falls), True, '%')}, and the bottom came {min(days)} to {max(days)} "
         f"trading days after day 0."),
        (f"<b>Limits.</b> Four shocks is a tiny sample, and day 0 was picked by hand. The pre-shock gap is partly built in: "
         f"from day -{FORWARD_HORIZON} onward the realized volatility of the next {FORWARD_HORIZON} days already includes the "
         f"shock, which no forecast made on those days could know."),
    ]

    # RETURNS a list of 5 HTML strings, e.g.
    # ['<b>Going in, the VIX was too low.</b> In 4 of 4 shocks the average gap over the 40 pre-shock days was below -2 points ...',
    #  '<b>On day 0 it was still too low in 3 of 4</b> (exception: Dot-com crash). The biggest miss was -67.4 points in the Covid crash.',
    #  ...]
    return items


def build_page(windows, data):
    """Assemble the whole standalone web page."""
    card = scorecard(windows)                                # per-shock numbers, used by every piece of text
    n = len(card)                                            # number of shocks
    pre_low = names_with(card, "Pre-shock", "VIX underestimated")  # VIX too low before day 0
    day0_low = names_with(card, "Day 0", "VIX underestimated")     # VIX too low on day 0
    worst = min(card, key=lambda c: c["phases"]["Day 0"]["gap"])  # biggest day-0 miss
    vix_top = max(card, key=lambda c: c["facts"]["vix_peak"])      # highest VIX peak
    real_top = max(card, key=lambda c: c["facts"]["realized_peak"])  # highest realized-volatility peak

    kpis = "".join(                                          # one headline card per shock: its day-0 gap
        tile(fmt(c["phases"]["Day 0"]["gap"], True), f"{c['name']} · VIX - realized on day 0, pts", c["color"]) for c in card)
    buttons = "".join(                                       # one tab button per shock
        f'<button type="button" data-tab="{e["key"]}" role="tab" aria-selected="{str(i == 0).lower()}">'  # data-tab says which tab panel it opens
        f'<i class="dot" style="background:var({e["color"]})"></i>{escape(e["name"])}</button>'
        for i, (e, _) in enumerate(windows))
    tabs = "".join(shock_tab(e, w, i == 0) for i, (e, w) in enumerate(windows))  # the four shock tabs, the first one visible
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in conclusions(card)) + "</ol>"  # numbered takeaways
    hint = '<p class="note"><span class="hint">Hover over or click</span> a chart to read the values of a day.</p>'  # "Tap" on touch screens (JS)
    lows = "; ".join(                                        # per shock: days to the bottom and when the old high came back
        f"{c['name']}: {c['low']['days_to_low']} trading days, old high regained {c['low']['recovery_date']:%b %Y}"
        if c["low"]["recovery_date"] is not None
        else f"{c['name']}: {c['low']['days_to_low']} trading days, old high not regained yet" for c in card)

    panels = "".join([
        panel(1, "How did the VIX score in each shock?",
              f"Before day 0 the VIX was too low in {len(pre_low)} of {n} shocks; on day 0, in {len(day0_low)} of {n}.",
              f"Every shock re-aligned so that day 0 is the same point. Gap = VIX - realized volatility over the next "
              f"{FORWARD_HORIZON} trading days, in annualized vol points: above 0 the VIX overpriced volatility, below 0 the "
              f"market underestimated what was coming. Pre-shock and aftermath are averages over the {PRE_DAYS} days before "
              f"and the {POST_DAYS} days after.",
              summary_table(card),
              f"<p>Pre-shock days from -{FORWARD_HORIZON} onward already \"look into\" the shock: their next {FORWARD_HORIZON} "
              f"days include it. That is part of why the VIX looks so wrong just before day 0.</p>"),
        panel(2, "What exactly are we measuring?",
              f"The VIX on each day, scored against the volatility of the next {FORWARD_HORIZON} trading days.",
              "", glossary()),
        panel(3, "How far off was the VIX, day by day?",
              f"The biggest day-0 miss: {fmt(worst['phases']['Day 0']['gap'], True)} points in the {worst['name']}.",
              "One line per shock: VIX - realized volatility, on the same \"trading days since day 0\" axis. Above 0 the VIX "
              "overpriced volatility; below 0 the market underestimated what was coming. The dotted line is day 0.",
              chart_div("chart-gap", 320, "Gap between the VIX and realized volatility, four shocks, 40 days before to 60 days after day 0") + hint,
              f"<p>{aftermath_text(card)}</p>"),
        panel(4, "Did the VIX jump as high as volatility did?",
              f"Highest VIX: {fmt(vix_top['facts']['vix_peak'])} ({vix_top['name']}); highest realized volatility: "
              f"{fmt(real_top['facts']['realized_peak'])} ({real_top['name']}).",
              f"Left: the VIX (expected). Right: the volatility that actually followed over the next {FORWARD_HORIZON} days. "
              "Both use the same scale, so they can be compared by eye. On a phone the two are stacked.",
              chart_div("chart-levels", 360, "VIX and realized volatility for the four shocks, aligned on day 0")),
        panel(5, "How far did the S&P 500 fall?",
              "From day 0 to the lowest point: " + ", ".join(f"{c['name']} {fmt(c['low']['fall'], True, '%')}" for c in card) + ".",
              f"The S&amp;P 500 is set to 100 on the day before day 0, so index levels decades apart become comparable. The "
              f"chart shows {POST_DAYS} days after day 0; the fall to the lowest point is measured on the full history, until the "
              f"index first regains its old high.",
              chart_div("chart-sp", 320, "S&P 500 indexed to 100 on the day before day 0, four shocks"),
              f"<p>The bottom came after {lows}.</p>"),
        panel(6, "What happened in each shock?",
              "Day 0 is the first big panic day of each shock, not always the worst one.",
              f"Solid line = VIX (the market's expectation); dashed = the volatility that actually followed over the next "
              f"{FORWARD_HORIZON} trading days. The bars below are the gap: blue = VIX too high, red = VIX too low. Shaded = "
              f"the {PRE_DAYS} pre-shock days. Verdict threshold: +/-{TOLERANCE:.0f} pts.",
              f'<div class="tabs" role="tablist" aria-label="Shock">{buttons}</div>{tabs}{hint}'),
        panel(7, "What did we learn?", "Five takeaways.", "", take),  # always the last panel
    ])

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>VIX Around Market Shocks</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
<script src="{ECHARTS_URL}"></script>
</head>
<body>
<header class="band"><div class="in">
<a class="back" href="../../index.html">&larr; Macro Quant Lab</a>
<p class="eyebrow">VIX vs realized volatility</p>
<h1>Was the VIX right about four market shocks?</h1>
<p class="answer">{answer_text(card)}</p>
<p class="meta">{PRE_DAYS} trading days before day 0, day 0, and {POST_DAYS} days after · S&amp;P 500 and VIX daily data
{data.index[0]:%b %Y} to {data.index[-1]:%d %b %Y}, Yahoo Finance · Not investment advice</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{panels}
{references()}
</main>
<footer><div class="in">Generated by VIX/shocks.py from Yahoo Finance daily closes (S&amp;P 500 ^GSPC, VIX ^VIX).
Learning project, not investment advice.</div></footer>
<script>{ECHARTS_JS.replace('__DATA__', json.dumps(chart_data(windows)))}{JS}</script>
</body>
</html>
"""

    # RETURNS a str of about 70,000 characters (~70 KB; ECharts itself is loaded from the CDN): a complete,
    # standalone HTML document. It starts like this:
    # <!doctype html>
    # <html lang="en">
    # <head>
    # <meta charset="utf-8">
    # ...and contains the Lab CSS, the burgundy header with the question and short answer, 4 headline cards,
    # 7 numbered panels (summary table, key ideas, 3 comparison charts, the 4 shock tabs, takeaways), then the
    # quiet "References" lines, the chart data as JSON and the JavaScript that draws the charts.
    return page


if __name__ == "__main__":                                   # True only when you run this file directly (python shocks.py), not when it is imported
    main()                                                   # run the whole pipeline
