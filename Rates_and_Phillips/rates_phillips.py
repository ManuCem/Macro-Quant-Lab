"""
Did cutting interest rates to (almost) zero bring the US economy back?

The Phillips curve says unemployment and inflation trade off against each other.
The Fed's tool for moving along that trade-off is the interest rate. So for two
US crises we ask, with real data from FRED:

    1. How far did the Fed cut, and for how long did it sit at the floor (<= 0.25%)?
    2. How many months did unemployment need to get back to its pre-crisis level?
    3. What happened to inflation, and to the REAL rate (Fed funds minus inflation)?

Episodes: 2008 crisis (2006-2019) and Covid (2018-2026).

Output: Rates_and_Phillips/rates_phillips.html (one tab per crisis + an overview), drawn with Apache ECharts.

Layout of this file (see CLAUDE.md):
    1. python / data code  -> settings, the calculations, and def main()
    2. html / chart code   -> builds the web page and the charts
"""

import json                               # turns Python lists/dicts into text the browser's JavaScript can read
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import pandas as pd                       # tables (DataFrames) and time series
import statsmodels.api as sm              # regression for the Phillips slope


# ===========================================================================
# python / data code
# ===========================================================================

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"  # FRED's free CSV download; {} is replaced by the series id
OUTPUT_PATH = Path(__file__).parent / "rates_phillips.html"         # where the web page is saved
CSV_PATH = Path(__file__).parent / "csv" / "rates_phillips.csv"      # where a copy of the table is saved
ECHARTS_PATH = Path(__file__).parent / "lib" / "echarts.js"          # Apache ECharts, embedded so the page is one standalone file

FLOOR = 0.25                              # a Fed funds rate at or below this (in %) counts as "at the floor"
RECOVERY_BAND = 0.5                       # unemployment counts as "recovered" when within 0.5 points of its pre-crisis low

EPISODES = [                              # one dictionary per crisis
    {"key": "gfc", "name": "2008 crisis", "start": "2006-01-01", "end": "2019-12-01",
     "color": "#eb6834"},                 # orange - slot 2
    {"key": "covid", "name": "Covid", "start": "2018-01-01", "end": "2026-08-01",
     "color": "#1baf7a"},                 # aqua   - slot 3
]


def fetch_fred(series_id):
    """Download one FRED series as a pandas Series indexed by date."""
    table = pd.read_csv(FRED_URL.format(series_id), index_col=0, parse_dates=True)  # CSV: date (index) + value
    series = pd.to_numeric(table.iloc[:, 0], errors="coerce")  # the value column as numbers; "." (missing) becomes NaN
    # returns a pandas Series, one value per month (UNRATE starts in 1948), e.g. fetch_fred("UNRATE"):
    # observation_date
    # 2026-06-01    4.2
    # 2026-07-01    4.1
    # 2026-08-01    4.1
    # Name: UNRATE, dtype: float64
    return series


def build_dataset():
    """One monthly table: unemployment, core inflation, Fed funds rate and the real rate."""
    unemployment = fetch_fred("UNRATE")                        # unemployment rate, %
    core_cpi = fetch_fred("CPILFESL")                          # core CPI index level (no food or energy)
    fedfunds = fetch_fred("FEDFUNDS")                          # effective Fed funds rate, monthly average, %
    data = pd.DataFrame({                                      # join the series into one table, matched by date
        "unemployment": unemployment,
        "core_inflation": core_cpi.pct_change(12) * 100,       # % change vs the same month a year earlier
        "fedfunds": fedfunds,
    }).dropna()                                                # drop months where any value is missing
    data["real_rate"] = data["fedfunds"] - data["core_inflation"]  # REAL rate = nominal rate minus inflation (what borrowing really costs)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)         # create the csv folder if missing
    data.to_csv(CSV_PATH)                                      # save a copy next to this script
    # returns a DataFrame, one row per month (Jan 1958 onward, ~820 rows), 4 columns in %:
    #                   unemployment  core_inflation  fedfunds  real_rate
    # observation_date
    # 2026-06-01                 4.2            2.57      3.63       1.06
    # 2026-07-01                 4.1            2.47      3.63       1.16
    # 2026-08-01                 4.1            2.45      3.63       1.18
    return data


def slice_episode(data, start, end):
    """Cut the months of one crisis out of the full table."""
    window = data.loc[start:end].copy()                        # rows between the two dates (inclusive)
    # returns a DataFrame with the same 4 columns as `data`, one row per month
    # (2008 window: 168 rows, Jan 2006 - Dec 2019).
    #             unemployment  core_inflation  fedfunds  real_rate
    return window


def floor_spans(window):
    """Date ranges where the Fed funds rate sat at or below FLOOR (to shade them on the chart)."""
    at_floor = window["fedfunds"] <= FLOOR                     # True/False per month
    spans = []                                                 # list of [first_month, last_month] labels
    start = None                                               # first month of the current run, if inside one
    for date, flag in at_floor.items():                        # walk through the months in order
        if flag and start is None:                             # a run of floor months begins
            start = date
        if not flag and start is not None:                     # the run just ended: close it at the previous month
            spans.append([start, previous])
            start = None
        previous = date                                        # remember this month for the next loop
    if start is not None:                                      # the window ended while still at the floor
        spans.append([start, previous])
    spans = [[a.strftime("%b %Y"), b.strftime("%b %Y")] for a, b in spans]  # Timestamps -> text labels used by the chart
    # returns a list of [start, end] pairs of month labels; e.g. for the 2008 window:
    # [['Dec 2008', 'Dec 2015']]  (an empty list [] if the rate never hit the floor)
    return spans


def episode_stats(window):
    """The numbers that answer the three questions for one crisis."""
    peak_date = window["unemployment"].idxmax()                # month of highest unemployment
    before = window.loc[:peak_date, "unemployment"]            # unemployment from the window start up to the peak
    baseline = float(before.min())                             # pre-crisis low = the level we call "normal"
    after = window.loc[peak_date:]                             # months from the peak onward
    recovered = after[after["unemployment"] <= baseline + RECOVERY_BAND]  # months already back near normal
    if len(recovered):                                         # unemployment did get back
        rec_date = recovered.index[0]                          # first month back near normal
        months = len(window.loc[peak_date:rec_date]) - 1       # months between the peak and that month
    else:                                                      # never recovered inside the window
        rec_date, months = None, None
    floor_months = int((window["fedfunds"] <= FLOOR).sum())    # number of months at the floor
    rate_high_date = window.loc[:peak_date, "fedfunds"].idxmax()  # month of the highest Fed funds rate before the unemployment peak
    real_low_date = window["real_rate"].idxmin()               # month of the most negative real rate
    infl_peak_date = window["core_inflation"].idxmax()         # month of the highest core inflation
    x = sm.add_constant(window["unemployment"])                # unemployment plus an intercept column
    slope = float(sm.OLS(window["core_inflation"], x).fit().params["unemployment"])  # Phillips slope: inflation points per +1pt unemployment
    stats = {                                                  # one flat dict, easy to print and to show as tiles
        "u_peak": float(window.loc[peak_date, "unemployment"]), "u_peak_date": peak_date.strftime("%b %Y"),
        "u_base": baseline,
        "recovery_months": months, "recovery_date": rec_date.strftime("%b %Y") if rec_date is not None else None,
        "ff_high": float(window.loc[rate_high_date, "fedfunds"]), "ff_high_date": rate_high_date.strftime("%b %Y"),
        "ff_low": float(window["fedfunds"].min()),
        "floor_months": floor_months,
        "real_low": float(window.loc[real_low_date, "real_rate"]), "real_low_date": real_low_date.strftime("%b %Y"),
        "infl_peak": float(window.loc[infl_peak_date, "core_inflation"]), "infl_peak_date": infl_peak_date.strftime("%b %Y"),
        "slope": slope,
    }
    # returns a dict of 14 values (real output for the 2008 window):
    # {'u_peak': 10.0, 'u_peak_date': 'Oct 2009', 'u_base': 4.4, 'recovery_months': 75, 'recovery_date': 'Jan 2016',
    #  'ff_high': 5.26, 'ff_high_date': 'Feb 2007', 'ff_low': 0.07, 'floor_months': 85, 'real_low': -2.21,
    #  'real_low_date': 'Dec 2011', 'infl_peak': 2.93, 'infl_peak_date': 'Sep 2006', 'slope': -0.134}
    # (recovery_months and recovery_date are None if unemployment never got back near normal)
    return stats


def recovery_curve(window):
    """Unemployment minus its pre-crisis low, month by month, counted from the unemployment peak."""
    peak_date = window["unemployment"].idxmax()                # month of the peak (month 0 on the x axis)
    baseline = window.loc[:peak_date, "unemployment"].min()    # the pre-crisis low
    after = window.loc[peak_date:, "unemployment"] - baseline  # points above normal, from the peak onward
    curve = after.reset_index(drop=True)                       # replace dates by 0, 1, 2, ... = months since the peak
    # returns a pandas Series; the index is months since the peak, the value is points above the pre-crisis low:
    # 0    5.6      (unemployment 5.6 points above its 4.4% low at the 2008 peak)
    # 1    5.5
    # 2    5.5
    # ...  (75 months later it is 0.5 or less; one value per month until the window ends)
    # Name: unemployment, dtype: float64
    return curve


def print_summary(rows):
    """Print one block per crisis with the key numbers."""
    for episode, stats, _ in rows:                             # each row = (episode dict, stats dict, window)
        s = stats                                              # short name
        recovery = f"{s['recovery_months']} months (back by {s['recovery_date']})" if s["recovery_months"] is not None else "not recovered"
        print(f"{episode['name']:<13} unemployment {s['u_base']:.1f}% -> {s['u_peak']:.1f}% ({s['u_peak_date']}), recovery: {recovery}")
        print(f"{'':<13} Fed funds {s['ff_high']:.2f}% -> {s['ff_low']:.2f}%, {s['floor_months']} months at the floor, "
              f"real rate low {s['real_low']:.1f}% ({s['real_low_date']}), core inflation peak {s['infl_peak']:.1f}%")  # two lines per crisis
    # returns nothing; prints two lines per crisis (the real output is shown when you run the script)
    return None


def main():
    data = build_dataset()                                     # step 1: download and build the monthly table
    rows = []                                                  # will hold (episode, stats, window) per crisis
    for episode in EPISODES:                                   # step 2: the same analysis for each crisis
        window = slice_episode(data, episode["start"], episode["end"])  # cut this crisis
        rows.append((episode, episode_stats(window), window))  # compute its numbers
    print_summary(rows)                                        # step 3: print the key numbers
    build_page(rows)                                           # step 4: write the web page (code below)
    print(f"Saved {OUTPUT_PATH}")                              # tell the user where the page is


# ===========================================================================
# html / chart code
# ===========================================================================

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#fbfaf7;color:#0b0b0b;font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px max(16px,env(safe-area-inset-right)) 32px max(16px,env(safe-area-inset-left))}
h1{font-size:1.4rem;margin:.4rem 0}
h2{font-size:1.05rem;margin:1.2rem 0 .4rem}
.sub,.why{color:#52514e;margin:.2rem 0 1rem}
a.back{display:inline-flex;align-items:center;min-height:44px;color:#2a78d6;text-decoration:none}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.tabs button{min-height:44px;padding:0 16px;border:1px solid #c3c2b7;border-radius:10px;background:#fff;font:inherit;cursor:pointer}
.tabs button[aria-selected=true]{background:#0b0b0b;color:#fff;border-color:#0b0b0b}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}
.tile{background:#fff;border:1px solid #e1e0d9;border-radius:10px;padding:10px 12px}
.tile b{display:block;font-size:1.3rem}
.tile span{color:#898781;font-size:.85rem}
.chart{width:100%;height:400px;background:#fff;border:1px solid #e1e0d9;border-radius:10px}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;background:#fff}
th,td{padding:8px 10px;border-bottom:1px solid #e1e0d9;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:#fff}
.note{color:#898781;font-size:.85rem}
.read{background:#fff;border-left:4px solid #eb6834;border-radius:6px;padding:10px 14px;margin:12px 0}
@media (max-width:640px){.charts{grid-template-columns:1fr}.chart{height:440px}}
"""

JS = """
const DATA = __DATA__;                                          // everything Python computed, as JSON
const narrowMQ = window.matchMedia("(max-width: 640px)");       // true on a phone-width screen
const isTouch = window.matchMedia("(pointer: coarse)").matches; // a finger instead of a mouse
const INK = "#0b0b0b", INK_2 = "#52514e", MUTED = "#898781", GRID = "#e1e0d9", AXIS = "#c3c2b7";
const INSTANCES = {};                                           // chart div id -> ECharts instance

function base(narrow) {                                         // options shared by every chart
  return {
    animation: false, textStyle: {color: INK_2},
    legend: narrow ? {bottom: 0, orient: "vertical", left: 16, textStyle: {color: INK_2}}   // below the plot on a phone
                   : {top: 0, right: 8, textStyle: {color: INK_2}},
    tooltip: {trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click"},           // tap on touch screens
    grid: narrow ? {left: 40, right: 20, top: 16, bottom: 130} : {left: 52, right: 28, top: 44, bottom: 40},
  };
}
const ax = (extra) => Object.assign({axisLine: {lineStyle: {color: AXIS}}, splitLine: {lineStyle: {color: GRID}}, axisLabel: {color: MUTED}}, extra);

function timeline(ep, narrow) {                                 // unemployment, inflation, Fed funds and real rate over time
  const o = base(narrow);
  o.xAxis = ax({type: "category", data: ep.dates, axisLabel: {color: MUTED, hideOverlap: true}});
  o.yAxis = ax({type: "value", name: narrow ? "" : "%"});
  const line = (name, key, color, extra) => Object.assign({name, type: "line", data: ep[key], showSymbol: false,
    lineStyle: {color, width: 2}, itemStyle: {color}}, extra || {});
  o.series = [
    line("Unemployment", "unemployment", "#2a78d6"),
    line("Core inflation", "core_inflation", "#e34948"),
    line("Fed funds rate", "fedfunds", INK, {lineStyle: {color: INK, width: 3},
      markArea: {silent: true, itemStyle: {color: "rgba(137,135,129,.18)"},       // grey band = rate at the floor
                 data: ep.floor.map(s => [{xAxis: s[0]}, {xAxis: s[1]}])}}),
    line("Real rate (Fed funds - inflation)", "real_rate", "#eda100", {lineStyle: {color: "#eda100", width: 2, type: "dashed"}}),
  ];
  return o;
}

function phillips(ep, narrow) {                                 // unemployment vs inflation, coloured by the Fed funds rate
  const pts = ep.points;                                        // [[unemployment, inflation, "Mon YYYY", fedfunds], ...]
  const o = base(narrow);
  o.legend = {show: false};
  o.tooltip = {trigger: "item", triggerOn: isTouch ? "click" : "mousemove|click"};
  o.grid = {left: narrow ? 44 : 56, right: 24, top: 16, bottom: 90};
  o.xAxis = ax({type: "value", name: "Unemployment rate (%)", nameLocation: "middle", nameGap: 28, scale: true});
  o.yAxis = ax({type: "value", name: narrow ? "" : "Core inflation (%)", scale: true});
  o.visualMap = {type: "continuous", dimension: 3, min: 0, max: DATA.ff_max, seriesIndex: 0, orient: "horizontal",
                 left: "center", bottom: 4, itemWidth: 14, itemHeight: narrow ? 150 : 260, calculable: false,
                 text: ["Fed funds " + DATA.ff_max.toFixed(1) + "%", "0%"], textStyle: {color: INK_2},
                 inRange: {color: ["#cde0f5", "#7fb0e6", "#2a78d6", "#0b2f66"]}};
  o.series = [
    {name: "Months", type: "scatter", symbolSize: 8, data: pts,
     tooltip: {formatter: q => q.data[2] + "<br>unemployment " + q.data[0].toFixed(1) + "%<br>core inflation " + q.data[1].toFixed(1) +
                               "%<br>Fed funds " + q.data[3].toFixed(2) + "%"}},
    {name: "Path", type: "line", data: pts.map(p => [p[0], p[1]]), showSymbol: false, silent: true,
     lineStyle: {color: MUTED, width: 1, opacity: .4}, tooltip: {show: false}},
  ];
  return o;
}

function recovery(narrow) {                                     // the two crises overlaid, counted from the unemployment peak
  const o = base(narrow);
  o.xAxis = ax({type: "value", name: "Months since unemployment peaked", nameLocation: "middle", nameGap: 28});
  o.grid.left = narrow ? 58 : 70;                                // extra room on the left so the rotated axis title is not cut off
  o.yAxis = ax({type: "value", min: 0, name: "Unemployment above its pre-crisis level (points)", nameLocation: "middle",
                nameRotate: 90, nameGap: narrow ? 36 : 44, nameTextStyle: {color: INK_2, fontSize: narrow ? 10 : 12}});
  o.series = DATA.episodes.map(ep => ({name: ep.name, type: "line", showSymbol: false, data: ep.recovery.map((v, i) => [i, v]),
    lineStyle: {color: ep.color, width: 3}, itemStyle: {color: ep.color},
    markLine: {silent: true, symbol: "none", lineStyle: {color: ep.color, type: "dotted"}, label: {show: false}, data: [{yAxis: 0.5}]}}));
  o.series[0].markLine.data = [{yAxis: 0.5}];                   // dotted line = "recovered" (within 0.5 points of normal)
  return o;
}

function build(div) {                                           // which chart goes in which div
  const narrow = narrowMQ.matches;
  if (div.id === "recovery") return recovery(narrow);
  const ep = DATA.episodes.find(e => div.id.endsWith(e.key));
  return div.id.startsWith("phil-") ? phillips(ep, narrow) : timeline(ep, narrow);
}

function drawVisible() {                                        // (re)build the charts of the visible tab only
  document.querySelectorAll(".panel:not([hidden]) .chart").forEach(div => {
    if (!INSTANCES[div.id]) INSTANCES[div.id] = echarts.init(div);
    INSTANCES[div.id].setOption(build(div), true);
    INSTANCES[div.id].resize();
  });
}
function showTab(key) {                                         // switch tab
  document.querySelectorAll(".panel").forEach(p => p.hidden = p.id !== key);
  document.querySelectorAll(".tabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.key === key));
  drawVisible();
}
narrowMQ.addEventListener("change", drawVisible);               // rebuild when a phone is rotated
window.addEventListener("resize", () => Object.values(INSTANCES).forEach(c => c.resize()));
"""

WHY = {                                   # the story of each crisis, written from the numbers checked in the data
    "gfc": "The Fed hit the floor in Dec 2008 and stayed there for 85 months. Unemployment peaked at 10% and needed "
           "over six years to get back near normal, while inflation stayed low: cheap money alone did not fix it.",
    "covid": "Rates hit the floor in April 2020 for 24 months, but unemployment recovered much faster than in 2008. "
             "The cost came later: inflation reached 6.6% while the real rate was deeply negative.",
}


def fmt(value, digits=1, signed=False):
    """Format a number for display."""
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"  # sign only when asked


def tile(value, label):
    """One small stat box."""
    return f'<div class="tile"><b>{escape(value)}</b><span>{escape(label)}</span></div>'  # big number + small caption


def recovery_text(s):
    """'20 months' or 'not yet' for the recovery time of one crisis."""
    return f"{s['recovery_months']} months" if s["recovery_months"] is not None else "not yet"  # None means never recovered


def episode_panel(episode, s):
    """HTML of one tab: story, tiles, timeline chart, Phillips chart."""
    tiles = "".join([                                          # six stat boxes
        tile(f"{fmt(s['u_base'])}% to {fmt(s['u_peak'])}%", f"unemployment, normal vs peak ({s['u_peak_date']})"),
        tile(recovery_text(s), "months for unemployment to get back near normal"),
        tile(f"{fmt(s['ff_high'], 2)}% to {fmt(s['ff_low'], 2)}%", f"Fed funds, high ({s['ff_high_date']}) to lowest"),
        tile(str(s["floor_months"]), "months with the rate at the floor (0.25% or less)"),
        tile(f"{fmt(s['infl_peak'])}%", f"peak core inflation ({s['infl_peak_date']})"),
        tile(f"{fmt(s['real_low'])}%", f"lowest real rate ({s['real_low_date']})"),
    ])
    return f"""<section class="panel" id="{episode['key']}" hidden>
<h2>{escape(episode['name'])}</h2>
<p class="why">{escape(WHY[episode['key']])}</p>
<div class="tiles">{tiles}</div>
<h2>Rates, unemployment and inflation over time</h2>
<div class="chart" id="time-{episode['key']}"></div>
<p class="note">Grey band = Fed funds at the floor. Dashed line = real rate (Fed funds minus inflation). Tap the chart for exact values.</p>
<h2>The Phillips curve, coloured by the Fed funds rate</h2>
<div class="chart" id="phil-{episode['key']}"></div>
<p class="note">Each dot is one month (unemployment on the x axis, core inflation on the y axis). Darker = higher Fed funds rate. Phillips slope in this window: {fmt(s['slope'], 2, True)}.</p>
</section>"""


def overview_panel(rows):
    """HTML of the overview tab: comparison table, recovery race and a plain-English reading."""
    body = "".join(                                            # one table row per crisis
        f"<tr><td>{escape(e['name'])}</td><td>{fmt(s['u_peak'])}%</td><td>{recovery_text(s)}</td>"
        f"<td>{s['floor_months']}</td><td>{fmt(s['infl_peak'])}%</td><td>{fmt(s['real_low'])}%</td></tr>"
        for e, s, _ in rows)
    return f"""<section class="panel" id="overview" hidden>
<div class="read"><b>The question:</b> when the Fed cuts rates to the floor, does the economy recover? Compare the two crises.
After 2008 the answer was slow and weak. After Covid it was fast, but inflation came back.</div>
<div class="scroll"><table><tr><th>Crisis</th><th>Peak unemployment</th><th>Months to recover</th><th>Months at floor</th><th>Peak inflation</th><th>Lowest real rate</th></tr>{body}</table></div>
<p class="note">Swipe the table sideways if it does not fit.</p>
<h2>The recovery race</h2>
<p class="why"><b>How to read it:</b> the vertical axis is how many percentage points the unemployment rate is above where it was before the crisis. Example: 2008 starts at 5.6 because unemployment hit 10.0% against a 4.4% low. The horizontal axis is months since unemployment peaked, so both crises start at month 0. The faster a line falls, the faster the recovery. The dotted line at 0.5 means "recovered" (within half a point of normal).</p>
<div class="chart" id="recovery"></div>
</section>"""


def build_page(rows):
    """Assemble the standalone HTML page and write it to disk."""
    ff_max = max(float(w["fedfunds"].max()) for _, _, w in rows)  # highest Fed funds rate in any window = top of the shared colour scale
    episodes_json = []                                         # per-episode data for the browser
    for episode, stats, window in rows:                        # one entry per crisis
        episodes_json.append({
            "key": episode["key"], "name": episode["name"], "color": episode["color"],
            "dates": [d.strftime("%b %Y") for d in window.index],          # x labels for the timeline
            "unemployment": [round(float(v), 2) for v in window["unemployment"]],
            "core_inflation": [round(float(v), 2) for v in window["core_inflation"]],
            "fedfunds": [round(float(v), 2) for v in window["fedfunds"]],
            "real_rate": [round(float(v), 2) for v in window["real_rate"]],
            "floor": floor_spans(window),                      # spans to shade
            "recovery": [round(float(v), 2) for v in recovery_curve(window)],  # points above normal per month since the peak
            "points": [[round(float(r["unemployment"]), 2), round(float(r["core_inflation"]), 2), d.strftime("%b %Y"), round(float(r["fedfunds"]), 2)]
                       for d, r in window.iterrows()],         # [unemployment, inflation, date, fedfunds] per month
        })
    payload = {"episodes": episodes_json, "ff_max": ff_max}    # everything the page's JavaScript needs
    buttons = '<button data-key="overview" onclick="showTab(\'overview\')">Overview</button>' + "".join(
        f'<button data-key="{e["key"]}" onclick="showTab(\'{e["key"]}\')">{escape(e["name"])}</button>' for e, _, _ in rows)
    panels = overview_panel(rows) + "".join(episode_panel(e, s) for e, s, _ in rows)  # all tab contents
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interest rates and the Phillips curve</title>
<style>{CSS}</style>
<script>{ECHARTS_PATH.read_text(encoding='utf-8')}</script>
</head><body><main>
<a class="back" href="index.html">&larr; Interest rates &amp; Phillips</a>
<h1>Did low interest rates bring the recovery?</h1>
<p class="sub">US data from FRED: unemployment, core CPI inflation and the Fed funds rate, monthly, in two crises.</p>
<div class="tabs" role="tablist">{buttons}</div>
{panels}
<script>{JS.replace('__DATA__', json.dumps(payload))}
showTab("overview");</script>
</main></body></html>"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # write the page
    # returns nothing; writes Rates_and_Phillips/rates_phillips.html (~1 MB, standalone, ECharts embedded)
    return None


if __name__ == "__main__":
    main()
