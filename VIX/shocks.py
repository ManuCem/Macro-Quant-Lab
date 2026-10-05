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

Output: VIX/output/shocks.html (one tab per shock + a dashboard tab), drawn with Apache ECharts.
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
# Apache ECharts, reused from the ecb/ folder; embedded in the page so it stays one standalone file.
ECHARTS_PATH = Path(__file__).parent.parent / "ecb" / "lib" / "echarts.js"  # the chart library file (one folder up, in ecb/lib/)

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
        "color": "#2a78d6",               # blue   - categorical slot 1
    },
    {
        "key": "gfc", "name": "2008 financial crisis", "day0": "2008-09-15",
        "why": "Lehman Brothers files for bankruptcy. Worse S&P days came "
               "later (Oct 2008), but this is the trigger, so the 40 days "
               "before it are still relatively calm.",
        "color": "#eb6834",               # orange - slot 2
    },
    {
        "key": "covid", "name": "Covid crash", "day0": "2020-02-24",
        "why": "First big panic day after the outbreak in Italy: the biggest "
               "one-day VIX jump of the episode. The worst S&P day (16 Mar) "
               "came three weeks later.",
        "color": "#1baf7a",               # aqua   - slot 3
    },
    {
        "key": "tariffs", "name": "2025 tariff shock", "day0": "2025-04-03",
        "why": "First trading day after the 'Liberation Day' tariff "
               "announcement (made after the close on 2 Apr). The S&P fell "
               "~5% and the VIX jumped ~40%.",
        "color": "#eda100",               # yellow - slot 4
    },
]

# Chart ink colours (light theme), from the reference palette.
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"  # main text, secondary text, muted/labels
GRID, AXIS = "#e1e0d9", "#c3c2b7"         # faint grid lines, axis lines
OVER_COLOR, UNDER_COLOR = "#2a78d6", "#e34948"  # diverging pair for the gap bars: blue = VIX too high, red = too low

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
    OUTPUT_PATH.write_text(build_page(windows), encoding="utf-8")  # step 5: build the web page (html / chart code below) and save it
    print(f"\nDashboard saved to {OUTPUT_PATH}")             # tell the user where the page is

    # RETURNS None (nothing). The results are its side effects:
    #   - the text summary printed in the terminal (see print_summary)
    #   - the file VIX/output/shocks.html (about 1 MB), and this last line in the terminal:
    #     Dashboard saved to VIX/output/shocks.html (full path of your own machine)


# ===========================================================================
# html / chart code
# ===========================================================================
# Python only prepares the numbers (as JSON); the charts themselves are built
# in the browser by ECHARTS_JS below, one chart per <div class="chart">.

def chart_data(windows):
    """Everything the browser needs to draw the charts, as plain lists."""
    def clean(series):
        # NaN is not valid JSON, so use None (-> null). Round to keep the file small.
        return [None if pd.isna(v) else round(float(v), 2) for v in series]

    events = []                                              # will hold one dictionary of lists per shock
    for event, window in windows:
        # S&P indexed to 100 on the day before the shock, so different index
        # levels (1,400 in 2000 vs 5,000+ in 2025) become comparable.
        base = window.loc[window["event_day"] == -1, "sp500"].iloc[0]  # the S&P close on day -1 (this becomes 100)
        events.append({
            "key": event["key"], "name": event["name"], "color": event["color"],  # identity and colour of the shock
            "dates": [f"{d:%Y-%m-%d}" for d in window.index],  # x-axis labels for the shock tab
            "day0": f"{window.index[window['event_day'] == 0][0]:%Y-%m-%d}",  # the shock date, to draw the vertical line
            "event_day": [int(v) for v in window["event_day"]],  # -40 ... 60, the x-axis of the dashboard
            "vix": clean(window["vix"]),                     # VIX values
            "realized": clean(window["realized"]),           # realized volatility values
            "gap": clean(window["gap"]),                     # gap values
            "sp_index": clean(window["sp500"] / base * 100),  # S&P indexed to 100 on day -1
        })

    # RETURNS a dict with 4 keys, made only of strings, ints, floats, None and lists (so json.dumps can turn it
    # into text for the browser). Each list inside an event has 101 items. For the Covid window (first 3 items shown):
    # {"events": [{"key": "covid", "name": "Covid crash", "color": "#1baf7a",
    #              "dates":     ["2019-12-24", "2019-12-26", "2019-12-27", ...],
    #              "day0":      "2020-02-24",
    #              "event_day": [-40, -39, -38, ...],
    #              "vix":       [12.67, 12.65, 13.43, ...],
    #              "realized":  [9.81, 10.25, 10.26, ...],
    #              "gap":       [2.86, 2.4, 3.17, ...],
    #              "sp_index":  [96.57, 97.07, 97.07, ...]},     # S&P with day -1 = 100
    #             ... one such dict per shock (4 in the real page) ...],
    #  "horizon": 21, "pre_days": 40,
    #  "colors": {"ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9",
    #             "axis": "#c3c2b7", "over": "#2a78d6", "under": "#e34948"}}
    return {
        "events": events, "horizon": FORWARD_HORIZON, "pre_days": PRE_DAYS,
        "colors": {"ink": INK, "ink2": INK_2, "muted": MUTED, "grid": GRID,
                   "axis": AXIS, "over": OVER_COLOR, "under": UNDER_COLOR},
    }


def chart_div(chart_id, height):
    """Empty box; ECHARTS_JS draws the chart into it the first time its tab is shown."""
    box = f'<div class="chart" id="{chart_id}" style="height:{height}px"></div>'  # an empty <div> with an id and a fixed height

    # RETURNS a str of HTML. chart_div("chart-covid", 480) gives:
    # '<div class="chart" id="chart-covid" style="height:480px"></div>'
    return box


# ---- the CSS and JavaScript that live inside the page (unchanged text) ----

ECHARTS_JS = """
const DATA = __DATA__;
const K = DATA.colors;                     // shared ink / grid / diverging colours
const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const fmt1 = v => (v === null || v === undefined) ? "-" : Number(v).toFixed(1);

// Axis look shared by every chart: recessive grid, light axis line.
const axisStyle = {
  axisLine: { lineStyle: { color: K.axis } }, axisTick: { lineStyle: { color: K.axis } },
  axisLabel: { color: K.ink2 }, splitLine: { lineStyle: { color: K.grid } }
};
// Options shared by every chart.
const base = () => ({
  animation: false, backgroundColor: "transparent", textStyle: { fontFamily: FONT, color: K.ink2 },
  tooltip: { trigger: "axis", valueFormatter: fmt1, confine: true },
  axisPointer: { link: [{ xAxisIndex: "all" }] }
});
const yAxis = (name, extra = {}) => ({ type: "value", name, nameLocation: "middle", nameGap: 42,
  nameTextStyle: { color: K.ink2 }, scale: true, ...axisStyle, ...extra });

// ---- one shock: VIX vs realized (top), gap bars (bottom) ----
function shockOption(e) {
  // dotted vertical line on day 0
  const day0Line = { silent: true, symbol: "none", lineStyle: { color: K.ink, width: 1.5, type: "dotted" },
                     label: { show: false }, data: [{ xAxis: e.day0 }] };
  // shaded band (pre-shock) or invisible band (aftermath) that only carries a text label
  const phaseArea = (name, from, to, shade) => [
    { name, xAxis: from, itemStyle: { color: shade ? K.muted : "transparent", opacity: shade ? 0.1 : 1 },
      label: { position: "insideTop", color: K.ink2 } },
    { xAxis: to }];
  const last = e.dates.length - 1;
  return { ...base(),
    legend: { top: 0, left: 0, textStyle: { color: K.ink2 } },
    grid: [{ left: 56, right: 16, top: 40, height: 270 }, { left: 56, right: 16, top: 340, height: 110 }],
    xAxis: [{ type: "category", gridIndex: 0, data: e.dates, axisLabel: { show: false }, axisLine: axisStyle.axisLine, axisTick: { show: false } },
            { type: "category", gridIndex: 1, data: e.dates, ...axisStyle, splitLine: { show: false } }],
    yAxis: [yAxis("Annualized vol (%)", { gridIndex: 0 }), yAxis("VIX - realized (pts)", { gridIndex: 1, scale: false })],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1] }],
    series: [
      { name: "VIX (expected)", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: e.vix, showSymbol: false,
        lineStyle: { color: e.color, width: 2 }, itemStyle: { color: e.color }, markLine: day0Line,
        markArea: { silent: true, data: [phaseArea("Pre-shock", e.dates[0], e.day0, true), phaseArea("Aftermath", e.day0, e.dates[last], false)] } },
      { name: "Realized, next " + DATA.horizon + "d (actual)", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: e.realized, showSymbol: false,
        lineStyle: { color: e.color, width: 2, type: "dashed" }, itemStyle: { color: e.color } },
      // blue bar = VIX too high (overpriced), red bar = VIX too low (underestimated)
      { name: "Gap (VIX - realized)", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: e.gap, markLine: day0Line,
        itemStyle: { color: p => p.value >= 0 ? K.over : K.under } }
    ] };
}

// ---- dashboard: four shocks overlaid on one "days since day 0" axis ----
const names = DATA.events.map(e => e.name);
const pairs = (e, field) => e.event_day.map((d, i) => [d, e[field][i]]);   // [x = day, y = value]
const day0Marker = { silent: true, symbol: "none", lineStyle: { color: K.ink, width: 1.5, type: "dotted" }, label: { show: false }, data: [{ xAxis: 0 }] };
const lineSeries = (e, field, extra = {}) => ({ name: e.name, type: "line", data: pairs(e, field), showSymbol: false,
  lineStyle: { color: e.color, width: 2 }, itemStyle: { color: e.color }, ...extra });
const dayAxis = (extra = {}) => ({ type: "value", min: -DATA.pre_days, name: "Trading days since day 0", nameLocation: "middle", nameGap: 28,
  nameTextStyle: { color: K.ink2 }, ...axisStyle, splitLine: { show: false }, ...extra });
// a reference line on the first series only: dotted vertical at day 0 + a solid horizontal one
const refLines = (yValue, yColor) => ({ markLine: { silent: true, symbol: "none", label: { show: false }, data: [
  { xAxis: 0, lineStyle: { color: K.ink, width: 1.5, type: "dotted" } }, { yAxis: yValue, lineStyle: { color: yColor, width: 1, type: "solid" } }] } });

function levelsOption() {
  // Same y range on both panels so VIX and realized can be compared by eye.
  const all = DATA.events.flatMap(e => [...e.vix, ...e.realized]).filter(v => v !== null);
  const top = Math.ceil(Math.max(...all) / 10) * 10;
  return { ...base(),
    legend: { top: 0, left: 0, data: names, textStyle: { color: K.ink2 } },
    title: [{ text: "VIX (expected)", left: 56, top: 34, textStyle: { color: K.ink2, fontSize: 13, fontWeight: 600 } },
            { text: "Realized, next " + DATA.horizon + "d (actual)", left: "54%", top: 34, textStyle: { color: K.ink2, fontSize: 13, fontWeight: 600 } }],
    grid: [{ left: 56, width: "40%", top: 70, height: 250 }, { left: "54%", right: 16, top: 70, height: 250 }],
    xAxis: [dayAxis({ gridIndex: 0 }), dayAxis({ gridIndex: 1, name: "" })],
    yAxis: [yAxis("Annualized vol (%)", { gridIndex: 0, min: 0, max: top, scale: false }), yAxis("", { gridIndex: 1, min: 0, max: top, scale: false })],
    series: DATA.events.flatMap(e => [
      lineSeries(e, "vix", { xAxisIndex: 0, yAxisIndex: 0, markLine: day0Marker }),
      lineSeries(e, "realized", { xAxisIndex: 1, yAxisIndex: 1, markLine: day0Marker })]) };
}
function gapOption() {
  return { ...base(),
    legend: { top: 0, left: 0, data: names, textStyle: { color: K.ink2 } },
    title: { text: "above 0: VIX overpriced  |  below 0: underestimated", right: 16, top: 2, textStyle: { color: K.muted, fontSize: 12, fontWeight: "normal" } },
    grid: { left: 56, right: 16, top: 40, height: 260 },
    xAxis: dayAxis(), yAxis: yAxis("VIX - realized (pts)", { scale: false }),
    series: DATA.events.map((e, i) => lineSeries(e, "gap", i === 0 ? refLines(0, K.ink) : {})) };
}
function spOption() {
  return { ...base(),
    legend: { top: 0, left: 0, data: names, textStyle: { color: K.ink2 } },
    grid: { left: 56, right: 16, top: 40, height: 260 },
    xAxis: dayAxis(), yAxis: yAxis("S&P 500 (day -1 = 100)"),
    series: DATA.events.map((e, i) => lineSeries(e, "sp_index", i === 0 ? refLines(100, K.axis) : {})) };
}

// chart id -> function that builds its option
const BUILDERS = { "chart-levels": levelsOption, "chart-gap": gapOption, "chart-sp": spOption };
DATA.events.forEach(e => BUILDERS["chart-" + e.key] = () => shockOption(e));
const INSTANCES = {};
addEventListener("resize", () => Object.values(INSTANCES).forEach(c => c.resize()));
"""


CSS = """
:root { color-scheme: light; }
body { margin: 0; padding: 24px 16px 48px; background: #f9f9f7; color: #0b0b0b;
       font: 14px/1.5 system-ui, -apple-system, 'Segoe UI', sans-serif; }
main { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 0 0 4px; }
p.sub { margin: 0 0 16px; color: #52514e; }
.tabs { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid #c3c2b7; }
.tabs button { font: inherit; padding: 8px 14px; border: 0; background: none;
               color: #52514e; cursor: pointer; border-bottom: 3px solid transparent; }
.tabs button[aria-selected=true] { color: #0b0b0b; font-weight: 600;
                                   border-bottom-color: var(--tab-color, #0b0b0b); }
.panel { background: #fcfcfb; border: 1px solid #e1e0d9; border-top: 0;
         padding: 16px; }
.panel[hidden] { display: none; }
.tiles { display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; }
.tile { flex: 1 1 150px; border: 1px solid #e1e0d9; border-radius: 6px; padding: 8px 12px; }
.tile .v { font-size: 20px; font-weight: 600; }
.tile .l { color: #52514e; font-size: 12px; }
.tablewrap { overflow-x: auto; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 10px; border-bottom: 1px solid #e1e0d9; text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: #52514e; font-weight: 600; }
.note { color: #52514e; font-size: 12px; margin-top: 8px; }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
"""

JS = """
function showTab(id) {
  document.querySelectorAll('.panel').forEach(p => p.hidden = (p.id !== id));
  document.querySelectorAll('.tabs button').forEach(b =>
    b.setAttribute('aria-selected', b.dataset.tab === id));
  // ECharts can't measure a hidden box, so each chart is created the first
  // time its tab is shown (and just resized on later visits).
  document.querySelectorAll('#' + id + ' .chart').forEach(div => {
    if (!INSTANCES[div.id]) {
      INSTANCES[div.id] = echarts.init(div);
      INSTANCES[div.id].setOption(BUILDERS[div.id]());
    } else {
      INSTANCES[div.id].resize();
    }
  });
}
document.querySelectorAll('.tabs button').forEach(b =>
  b.addEventListener('click', () => showTab(b.dataset.tab)));
"""


# ---- Python helpers that build the HTML text ----

def fmt(value, signed=False, suffix=""):
    """Format a number with 1 decimal (optionally with a +/- sign and a suffix like %)."""
    text = f"{value:+.1f}{suffix}" if signed else f"{value:.1f}{suffix}"  # "+" forces a sign; .1f = one decimal

    # RETURNS a str:
    #   fmt(-3.4412, True, "%") -> '-3.4%'
    #   fmt(25.04)              -> '25.0'
    return text


def tile(value, label):
    """One small box with a big number and a caption."""
    html = f'<div class="tile"><div class="v">{value}</div><div class="l">{escape(label)}</div></div>'  # escape() keeps odd characters in the caption from breaking the HTML

    # RETURNS a str of HTML. tile("-3.4%", "S&P 500 on day 0") gives:
    # '<div class="tile"><div class="v">-3.4%</div><div class="l">S&amp;P 500 on day 0</div></div>'
    return html


def phase_table_html(rows):
    """The small 3-row table of averages at the bottom of each shock tab."""
    body = "".join(                                          # glue the rows together into one string
        f"<tr><td>{r['phase']}</td><td>{r['days']}</td><td>{fmt(r['vix'])}</td>"  # phase, days, average VIX
        f"<td>{fmt(r['realized'])}</td><td>{fmt(r['gap'], signed=True)}</td>"  # average realized, average gap
        f"<td>{verdict(r['gap'])}</td></tr>"                 # the verdict label
        for r in rows)                                       # one <tr> per phase
    html = ('<div class="tablewrap"><table><tr><th>Phase</th><th>Days</th>'  # header row...
            '<th>Avg VIX</th><th>Avg realized</th><th>VIX - realized</th>'
            f'<th>Verdict</th></tr>{body}</table></div>')    # ...then the body rows

    # RETURNS a str of HTML (about 600 characters): a <table> with a header row and 3 body rows. For the Covid window:
    # '<div class="tablewrap"><table><tr><th>Phase</th><th>Days</th><th>Avg VIX</th><th>Avg realized</th>
    #  <th>VIX - realized</th><th>Verdict</th></tr>
    #  <tr><td>Pre-shock</td><td>40</td><td>14.3</td><td>31.9</td><td>-17.6</td><td>VIX underestimated</td></tr>
    #  <tr><td>Day 0</td><td>1</td><td>25.0</td><td>92.5</td><td>-67.4</td><td>VIX underestimated</td></tr>
    #  <tr><td>Aftermath</td><td>60</td><td>44.9</td><td>47.1</td><td>-2.1</td><td>VIX underestimated</td></tr>
    #  </table></div>'
    return html


def shock_panel(event, window):
    """The full content of one shock's tab: title, tiles, chart, table, note."""
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
    html = f"""
<section class="panel" id="{event['key']}" hidden>
  <h2>{escape(event['name'])} - day 0 = {facts['day0_date']:%d %b %Y}</h2>
  <p class="sub">{escape(event['why'])}</p>
  <div class="tiles">{tiles}</div>
  {chart_div('chart-' + event['key'], 480)}
  {phase_table_html(phase_table(window))}
  <p class="note">Solid line = VIX (the market's expectation); dashed = the
  volatility that actually followed over the next {FORWARD_HORIZON} trading
  days. Pre-shock days from -{FORWARD_HORIZON} onward already "look into" the
  shock, which is why the VIX looks wrong there. Verdict threshold:
  +/-{TOLERANCE:.0f} pts.</p>
</section>"""

    # RETURNS a str of HTML (about 1,600 characters): one <section> that stays hidden until its tab is clicked.
    # For the Covid window it is built like this:
    # <section class="panel" id="covid" hidden>
    #   <h2>Covid crash - day 0 = 24 Feb 2020</h2>
    #   <p class="sub">First big panic day after the outbreak in Italy: ...</p>
    #   <div class="tiles"> ...5 <div class="tile"> boxes... </div>
    #   <div class="chart" id="chart-covid" style="height:480px"></div>      <- empty; the browser draws the chart here
    #   <div class="tablewrap"> ...the phase table... </div>
    #   <p class="note"> ...explanation... </p>
    # </section>
    return html


def dashboard_panel(windows):
    """The Dashboard tab: a summary table of all four shocks plus three overlay charts."""
    # One summary row per shock, pulling the phase averages together.
    rows = ""                                                # HTML table rows, built up one shock at a time
    for event, window in windows:
        phases = {r["phase"]: r for r in phase_table(window)}  # look up a phase's numbers by its name
        facts = key_facts(window)                            # headline numbers for this shock
        rows += (
            f'<tr><td><span class="sw" style="background:{event["color"]}"></span>'  # colour swatch...
            f'{escape(event["name"])}</td>'                  # ...and the shock name
            f'<td>{facts["day0_date"]:%d %b %Y}</td>'        # day 0 date
            f'<td>{fmt(facts["sp_day0_return"], True, "%")}</td>'  # S&P move on day 0
            f'<td>{fmt(phases["Pre-shock"]["gap"], True)}</td>'  # average gap before
            f'<td>{fmt(phases["Day 0"]["gap"], True)}</td>'  # gap on day 0
            f'<td>{fmt(phases["Aftermath"]["gap"], True)}</td>'  # average gap after
            f'<td>{fmt(facts["vix_peak"])} (day {facts["vix_peak_day"]})</td>'  # VIX peak and when
            f'<td>{fmt(facts["realized_peak"])}</td>'        # peak realized volatility
            f'<td>{fmt(event["low"]["fall"], True, "%")} '   # fall from day 0 to the bottom...
            f'({event["low"]["low_date"]:%b %Y})</td></tr>')  # ...and the month of the bottom

    html = f"""
<section class="panel" id="dashboard" hidden>
  <h2>All four shocks together</h2>
  <p class="sub">Every shock re-aligned so that day 0 is the same point on the
  x-axis. Avg gap = VIX - realized volatility, in annualized vol points.</p>
  <div class="tablewrap"><table>
    <tr><th>Shock</th><th>Day 0</th><th>S&P day 0</th><th>Gap: pre-shock</th>
    <th>Gap: day 0</th><th>Gap: aftermath</th><th>VIX peak</th>
    <th>Peak realized</th><th>S&P day 0 to low</th></tr>{rows}
  </table></div>
  {chart_div('chart-levels', 340)}
  {chart_div('chart-gap', 320)}
  {chart_div('chart-sp', 320)}
  <p class="note">Gap above 0 = VIX overpriced volatility; below 0 = the market
  underestimated what was coming.</p>
</section>"""

    # RETURNS a str of HTML: one <section id="dashboard" hidden> built like this:
    # <section class="panel" id="dashboard" hidden>
    #   <h2>All four shocks together</h2>
    #   <div class="tablewrap"><table> ...header + one row per shock (4 rows)... </table></div>
    #   <div class="chart" id="chart-levels" style="height:340px"></div>    <- 3 empty chart boxes;
    #   <div class="chart" id="chart-gap" style="height:320px"></div>       <- the browser draws
    #   <div class="chart" id="chart-sp" style="height:320px"></div>        <- the charts in them
    #   <p class="note"> ...explanation... </p>
    # </section>
    return html


def build_page(windows):
    """Assemble the whole standalone web page."""
    buttons = "".join(                                       # one tab button per shock
        f'<button data-tab="{e["key"]}" style="--tab-color:{e["color"]}" '  # data-tab says which panel it opens
        f'role="tab">{escape(e["name"])}</button>' for e, _ in windows)
    buttons += '<button data-tab="dashboard" role="tab">Dashboard</button>'  # plus the Dashboard tab at the end
    panels = "".join(shock_panel(e, w) for e, w in windows) + dashboard_panel(windows)  # the four shock panels, then the dashboard panel
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VIX around market shocks</title>
<style>{CSS}</style>
<script>{ECHARTS_PATH.read_text(encoding='utf-8')}</script>
</head><body><main>
<h1>VIX vs what actually happened, around four market shocks</h1>
<p class="sub">{PRE_DAYS} trading days before day 0, day 0, and {POST_DAYS} days
after. S&amp;P 500 and VIX data from Yahoo Finance.</p>
<div class="tabs" role="tablist">{buttons}</div>
{panels}
<script>{ECHARTS_JS.replace('__DATA__', json.dumps(chart_data(windows)))}{JS}showTab('{windows[0][0]['key']}');</script>
</main></body></html>"""

    # RETURNS a str of about 1,047,000 characters (~1 MB, because the ECharts library is embedded): a complete,
    # standalone HTML document. It starts like this:
    # <!doctype html>
    # <html lang="en"><head><meta charset="utf-8">
    # <meta name="viewport" content="width=device-width, initial-scale=1">
    # <title>VIX around market shocks</title>
    # ...and contains the CSS, the ECharts library, the 4 tab buttons + Dashboard button, the 5 panels,
    # the chart data as JSON and the JavaScript that draws the charts.
    return page


if __name__ == "__main__":                                   # True only when you run this file directly (python shocks.py), not when it is imported
    main()                                                   # run the whole pipeline
