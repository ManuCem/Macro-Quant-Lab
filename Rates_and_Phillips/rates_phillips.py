"""
Did cutting interest rates to (almost) zero bring the US economy back?

The Phillips curve says unemployment and inflation trade off against each other.
The Fed's tool for moving along that trade-off is the interest rate. So for two
US crises we ask, with real data from FRED:

    1. How far did the Fed cut, and for how long did it sit at the floor (<= 0.25%)?
    2. How many months did unemployment need to get back to its pre-crisis level?
    3. What happened to inflation, and to the REAL rate (Fed funds minus inflation)?

Episodes: 2008 crisis (2006-2019) and Covid (2018-2026).

Output: Rates_and_Phillips/rates_phillips.html (Lab page: one numbered panel per question), drawn with Apache ECharts.

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

FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"
SOURCES = [                               # (who, what it gave, link) for the quiet References list after the last panel
    ("FRED (St. Louis Fed)", "UNRATE, the US unemployment rate, monthly, %", "https://fred.stlouisfed.org/series/UNRATE"),
    ("FRED (St. Louis Fed)", "CPILFESL, core CPI: consumer prices without food and energy (index)", "https://fred.stlouisfed.org/series/CPILFESL"),
    ("FRED (St. Louis Fed)", "FEDFUNDS, the effective Fed funds rate, monthly average, %", "https://fred.stlouisfed.org/series/FEDFUNDS"),
]
GLOSSARY = [                              # (term, plain-language meaning): the ideas a reader needs for the charts
    ("Phillips curve", "The idea that unemployment and inflation trade off: when few people are out of work, wages and prices "
                       "tend to rise faster, and when many are out of work, inflation slows."),
    ("Fed funds rate", "The overnight interest rate US banks charge each other, steered by the Federal Reserve. It is the Fed's "
                       "main tool for moving along that trade-off."),
    ("The floor", f"The Fed cannot cut much below zero. Here a Fed funds rate at or below {FLOOR}% counts as \"at the floor\"."),
    ("Core inflation", "The % change in consumer prices over the last 12 months, leaving out food and energy, whose prices jump around."),
    ("Real rate", "The Fed funds rate minus core inflation: what borrowing really costs once rising prices are taken into account. "
                  "Below zero, borrowers gain."),
    ("Phillips slope", "The slope of the best-fit line through the dots: how many points core inflation changes when unemployment "
                       "is one point higher. Negative is the textbook trade-off."),
]
QUESTIONS = {                             # the heading of each crisis panel
    "gfc": "What did the Fed do in 2008, and did jobs come back?",
    "covid": "What did the Fed do in Covid, and did jobs come back?",
}

# Look: the "Lab" design every project page uses (see CLAUDE.md): petrol header band, aqua accent (--brass), white panels,
# the same fonts as the homepage. Colours: one fixed hue per crisis (2008 = orange, Covid = teal) and per series
# (unemployment = blue, core inflation = red, Fed funds = ink, real rate = amber dashed). Text names them in words too.
CSS = """
:root{color-scheme:light dark;--band:#0e3a46;--band-ink:#e4e6ea;--brass:#2a9db0;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--gfc:#c4572a;--covid:#1f8a70;--un:#2a5db0;--inf:#b8423f;--real:#c27a2c;
  --floor:rgba(135,145,140,.18);--seq0:#d6e3f5;--seq1:#8fb3e6;--seq2:#2a5db0;--seq3:#0d2f66}
@media (prefers-color-scheme:dark){:root{--band:#0a2832;--brass:#5cc4d2;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--gfc:#e98a5a;--covid:#3fb894;--un:#6d9be0;--inf:#e07a72;--real:#d99a52;
  --floor:rgba(165,178,171,.13);--seq0:#1d3557;--seq1:#2f62a8;--seq2:#6d9be0;--seq3:#c4dbf7}}
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
.kpis.six{grid-template-columns:repeat(3,1fr);margin:0 0 6px}
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
.panel .kpi{background:var(--page);border:0;padding:12px 14px}
.panel .kpi b{font-size:22px}
.chart{width:100%;height:380px}
.label{margin:18px 0 4px;font-size:13px;font-weight:600;color:var(--ink-2)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle}
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
th:first-child,td:first-child{text-align:left;padding-left:0}
th{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.refs{margin:32px 0 0;padding:0 4px;font-size:13px;line-height:1.5;color:var(--muted)}
.refs h3{margin:0 0 2px;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.refs ul{list-style:none;padding:0;margin:0}
.refs a{display:flex;align-items:center;min-height:44px;padding:6px 0;color:var(--muted);text-decoration:none;overflow-wrap:anywhere}
.refs b{font-weight:600;color:var(--ink-2)}
.refs a:hover span{text-decoration:underline}
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:720px){.kpis,.kpis.six{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
@media (max-width:640px){
  .chart{height:460px}
  .gloss{grid-template-columns:1fr;gap:18px}
  .panel .kpi b{font-size:19px}
  th,td{padding:8px 4px;font-size:13px}th{white-space:normal}td:first-child{white-space:normal}
}
"""

JS = """
const DATA = __DATA__;                                          // everything Python computed, as JSON
const narrowMQ = window.matchMedia("(max-width: 640px)");       // true on a phone-width screen
const isTouch = window.matchMedia("(pointer: coarse)").matches; // a finger instead of a mouse
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();  // read a colour token
const INSTANCES = {};                                           // chart div id -> ECharts instance

function tipStyle() {                                           // tooltip look from the page tokens, never ECharts' default white box
  return {
    backgroundColor: css("--surface"),                          // white in light mode, near-black in dark mode
    borderColor: css("--grid"), borderWidth: 1,                 // the same thin border as the panels
    textStyle: {color: css("--ink"), fontFamily: "DM Sans, system-ui, sans-serif", fontSize: 13},  // readable text in both modes
    extraCssText: "box-shadow: 0 6px 20px rgba(0,0,0,.18); border-radius: 8px;",                    // a soft shadow lifts it off the chart
    axisPointer: {label: {backgroundColor: css("--surface"), borderColor: css("--grid"), borderWidth: 1,
                          color: css("--ink")}},                // any axis-pointer label uses the same tokens
  };
}

function base(narrow) {                                         // options shared by every chart
  return {
    animation: false, backgroundColor: "transparent", textStyle: {color: css("--ink-2")},
    legend: narrow ? {bottom: 4, left: 12, orient: "vertical", itemGap: 6, textStyle: {color: css("--ink-2")}}  // below the plot on a phone
                   : {top: 6, left: 48, textStyle: {color: css("--ink-2")}},   // one row above the plot on desktop
    tooltip: Object.assign(tipStyle(),                          // themed box (rebuilt by drawAll, so it follows a theme change)
      {trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click", confine: true}),           // tap on touch screens
    grid: narrow ? {left: 40, right: 20, top: 16, bottom: 130} : {left: 52, right: 28, top: 44, bottom: 40},
  };
}
const ax = extra => Object.assign({axisLine: {lineStyle: {color: css("--axis")}}, splitLine: {lineStyle: {color: css("--grid")}},
                                  axisLabel: {color: css("--muted"), hideOverlap: true}, nameTextStyle: {color: css("--muted")}}, extra);

function timeline(ep, narrow) {                                 // unemployment, inflation, Fed funds and real rate over time
  const o = base(narrow);
  if (narrow) o.grid.right = 32;                                // room for half of the last date label ("Oct 2019")
  o.xAxis = ax({type: "category", data: ep.dates});
  o.yAxis = ax({type: "value", axisLabel: {color: css("--muted"), formatter: v => v + "%"}});   // % on each label: no axis title to collide with the legend
  const line = (name, key, color, extra) => Object.assign({name, type: "line", data: ep[key], showSymbol: false,
    lineStyle: {color, width: 2}, itemStyle: {color}}, extra || {});
  o.series = [
    line("Unemployment", "unemployment", css("--un")),
    line("Core inflation", "core_inflation", css("--inf")),
    line("Fed funds rate", "fedfunds", css("--ink"), {lineStyle: {color: css("--ink"), width: 3},
      markArea: {silent: true, itemStyle: {color: css("--floor")},              // grey band = rate at the floor
                 data: ep.floor.map(s => [{xAxis: s[0]}, {xAxis: s[1]}])}}),
    line("Real rate (Fed funds - inflation)", "real_rate", css("--real"), {lineStyle: {color: css("--real"), width: 2, type: "dashed"}}),
  ];
  o.tooltip.valueFormatter = v => v == null ? "-" : v.toFixed(2) + "%";
  return o;
}

function phillips(ep, narrow) {                                 // unemployment vs inflation, coloured by the Fed funds rate
  const pts = ep.points;                                        // [[unemployment, inflation, "Mon YYYY", fedfunds], ...]
  const o = base(narrow);
  o.legend = {show: false};                                     // one series: the colour scale below explains it
  o.tooltip = Object.assign(tipStyle(), {trigger: "item", triggerOn: isTouch ? "click" : "mousemove|click", confine: true});  // one dot at a time, same themed box
  o.grid = {left: narrow ? 40 : 56, right: 24, top: 16, bottom: 96};
  o.xAxis = ax({type: "value", name: "Unemployment rate (%)", nameLocation: "middle", nameGap: 28, scale: true});
  o.yAxis = ax({type: "value", scale: true, axisLabel: {color: css("--muted"), formatter: v => v + "%"}});   // core inflation, %
  o.visualMap = {type: "continuous", dimension: 3, min: 0, max: DATA.ff_max, seriesIndex: 0, orient: "horizontal",
                 left: "center", bottom: 4, itemWidth: 14, itemHeight: narrow ? 150 : 260, calculable: false,
                 text: ["Fed funds " + DATA.ff_max.toFixed(1) + "%", "0%"], textStyle: {color: css("--ink-2")},
                 inRange: {color: [css("--seq0"), css("--seq1"), css("--seq2"), css("--seq3")]}};
  o.series = [
    {name: "Months", type: "scatter", symbolSize: 8, data: pts,
     tooltip: {formatter: q => q.data[2] + "<br>unemployment " + q.data[0].toFixed(1) + "%<br>core inflation " + q.data[1].toFixed(1) +
                               "%<br>Fed funds " + q.data[3].toFixed(2) + "%"}},
    {name: "Path", type: "line", data: pts.map(p => [p[0], p[1]]), showSymbol: false, silent: true,
     lineStyle: {color: css("--muted"), width: 1, opacity: .4}, tooltip: {show: false}},
  ];
  return o;
}

function recovery(narrow) {                                     // the two crises overlaid, counted from the unemployment peak
  const o = base(narrow);
  o.grid = narrow ? {left: 58, right: 20, top: 16, bottom: 110} : {left: 70, right: 28, top: 44, bottom: 50};  // room for the rotated y title
  o.xAxis = ax({type: "value", name: "Months since unemployment peaked", nameLocation: "middle", nameGap: 28});
  o.yAxis = ax({type: "value", min: 0, name: "Unemployment above its pre-crisis level (points)", nameLocation: "middle",
                nameRotate: 90, nameGap: narrow ? 36 : 44, nameTextStyle: {color: css("--ink-2"), fontSize: narrow ? 10 : 12}});
  o.series = DATA.episodes.map(ep => ({name: ep.name, type: "line", showSymbol: false, data: ep.recovery.map((v, i) => [i, v]),
    lineStyle: {color: css("--" + ep.key), width: 3}, itemStyle: {color: css("--" + ep.key)}}));
  o.series[0].markLine = {silent: true, symbol: "none", lineStyle: {color: css("--muted"), type: "dotted"}, label: {show: false},
                          data: [{yAxis: DATA.band}]};          // dotted line = "recovered" (within RECOVERY_BAND points of normal)
  o.tooltip.valueFormatter = v => v == null ? "-" : v.toFixed(1) + " pts";
  return o;
}

function build(div) {                                           // which chart goes in which div
  const narrow = narrowMQ.matches;
  if (div.id === "recovery") return recovery(narrow);
  const ep = DATA.episodes.find(e => div.id.endsWith(e.key));
  return div.id.startsWith("phil-") ? phillips(ep, narrow) : timeline(ep, narrow);
}

function drawAll() {                                            // (re)build every chart; called on load, rotation and theme change
  document.querySelectorAll(".chart").forEach(div => {
    if (!INSTANCES[div.id]) INSTANCES[div.id] = echarts.init(div);
    INSTANCES[div.id].setOption(build(div), true);
    INSTANCES[div.id].resize();
  });
}
if (isTouch) document.querySelectorAll(".hint").forEach(h => h.textContent = "Tap");  // say "tap", not "hover", to touch users
narrowMQ.addEventListener("change", drawAll);                   // rebuild when a phone is rotated
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawAll);  // rebuild in the new colours
window.addEventListener("resize", () => Object.values(INSTANCES).forEach(c => c.resize()));
drawAll();
"""


def fmt(value, digits=1, signed=False):
    """Format a number for display, with a real minus sign."""
    text = f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"  # sign only when asked
    # returns a str, e.g. fmt(4.4) -> '4.4', fmt(-2.2066) -> '−2.2', fmt(-0.1339, 2, True) -> '−0.13', fmt(5.26, 2) -> '5.26'
    return text.replace("-", "−")                         # typographic minus (−) instead of a hyphen


def tile(value, label, color=None):
    """One headline number with its label; an optional dot names the crisis by its chart colour."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # identity is in the text too, never colour alone
    # returns a str of HTML, e.g. '<div class="kpi"><b><i class="dot" style="background:var(--gfc)"></i>75</b><span>months ...</span></div>'
    return f'<div class="kpi"><b>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def recovery_text(s):
    """'20 months' or 'not yet' for the recovery time of one crisis."""
    text = f"{s['recovery_months']} months" if s["recovery_months"] is not None else "not yet"  # None means never recovered
    # returns a str, e.g. '75 months' (2008 crisis), '20 months' (Covid), or 'not yet'
    return text


def by_key(rows):
    """Look up each crisis by its key ('gfc', 'covid')."""
    found = {episode["key"]: (episode, stats, window) for episode, stats, window in rows}  # key -> the (episode, stats, window) row
    # returns a dict of 2 tuples, e.g. {'gfc': ({'key': 'gfc', 'name': '2008 crisis', ...}, {'u_peak': 10.0, ...}, <DataFrame 168x4>),
    #                                   'covid': ({'key': 'covid', ...}, {'u_peak': 14.8, ...}, <DataFrame 104x4>)}
    return found


def floor_start(window):
    """The first month the Fed funds rate reached the floor in this window, as text."""
    spans = floor_spans(window)                                # [[first month, last month], ...] at the floor
    start = spans[0][0] if spans else "never"                  # the first run, if there is one
    # returns a str, e.g. 'Dec 2008' (2008 window), 'Apr 2020' (Covid window), or 'never'
    return start


def story_text(episode, s, window, other):
    """The 'what it tells us' story of one crisis, written from the numbers (other = stats of the other crisis)."""
    if episode["key"] == "gfc":                                # 2008: long at the floor, slow recovery, low inflation
        years = s["recovery_months"] // 12 if s["recovery_months"] is not None else None   # whole years of the recovery
        need = f"needed {recovery_text(s)} (over {years} years)" if years else "had not got"  # wording for slow / no recovery
        text = (f"The Fed hit the floor in {floor_start(window)} and stayed there for {s['floor_months']} months. Unemployment "
                f"peaked at {fmt(s['u_peak'])}% and {need} to get back near normal, while inflation stayed low (core peak "
                f"{fmt(s['infl_peak'])}%): cheap money alone did not fix it.")
    else:                                                      # Covid: short at the floor, fast recovery, inflation later
        faster = ("much faster than" if s["recovery_months"] is not None and other["recovery_months"] is not None
                  and s["recovery_months"] < other["recovery_months"] else "not faster than")   # compare the two recoveries
        text = (f"Rates hit the floor in {floor_start(window)} for {s['floor_months']} months, but unemployment recovered "
                f"{faster} in 2008 ({recovery_text(s)} against {recovery_text(other)}). The cost came later: inflation reached "
                f"{fmt(s['infl_peak'])}% while the real rate was deeply negative ({fmt(s['real_low'])}% in {s['real_low_date']}).")
    # returns a str, e.g. 'The Fed hit the floor in Dec 2008 and stayed there for 85 months. Unemployment peaked at 10.0% and
    # needed 75 months (over 6 years) to get back near normal, while inflation stayed low (core peak 2.9%): cheap money alone did not fix it.'
    return text


def answer_text(rows):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    k = by_key(rows)                                           # crisis key -> (episode, stats, window)
    g, c = k["gfc"][1], k["covid"][1]                          # the stats of each crisis
    text = (f"<b>Not on their own.</b> The Fed cut to the floor in both crises. After 2008 the recovery was slow and weak: "
            f"{g['floor_months']} months at the floor, and unemployment needed {recovery_text(g)} to get back near normal. "
            f"After Covid it was fast ({recovery_text(c)}), but inflation came back: core inflation reached {fmt(c['infl_peak'])}%.")
    # returns a str of HTML, about 330 characters, e.g.
    # '<b>Not on their own.</b> The Fed cut to the floor in both crises. After 2008 the recovery was slow and weak: 85 months at the
    #  floor, and unemployment needed 75 months to get back near normal. After Covid it was fast (20 months), but ... reached 6.6%.'
    return text


def compare_table(rows):
    """The two crises side by side: rows = measures, one column per crisis (fits a phone)."""
    measures = [                                               # (row label, function that formats one crisis's stats)
        ("Peak unemployment", lambda s: f"{fmt(s['u_peak'])}%"),
        ("Months to recover", recovery_text),
        ("Months at the floor", lambda s: str(s["floor_months"])),
        ("Peak core inflation", lambda s: f"{fmt(s['infl_peak'])}%"),
        ("Lowest real rate", lambda s: f"{fmt(s['real_low'])}%"),
    ]
    head = "<tr><th>Measure</th>" + "".join(f"<th>{escape(e['name'])}</th>" for e, _, _ in rows) + "</tr>"  # one column per crisis
    body = "".join("<tr><td>" + escape(label) + "</td>" + "".join(f"<td>{escape(f(s))}</td>" for _, s, _ in rows) + "</tr>"
                   for label, f in measures)
    # returns a str of HTML: a header and 5 rows, e.g. <tr><td>Months to recover</td><td>75 months</td><td>20 months</td></tr>
    return f'<div class="scroll"><table>{head}{body}</table></div>'


def episode_tiles(s):
    """The six numbers of one crisis as small cards."""
    tiles = "".join([                                          # six stat boxes
        tile(f"{fmt(s['u_base'])}% to {fmt(s['u_peak'])}%", f"unemployment, normal vs peak ({s['u_peak_date']})"),
        tile(recovery_text(s), "for unemployment to get back near normal"),
        tile(f"{fmt(s['ff_high'], 2)}% to {fmt(s['ff_low'], 2)}%", f"Fed funds, high ({s['ff_high_date']}) to lowest"),
        tile(str(s["floor_months"]), f"months with the rate at the floor ({FLOOR}% or less)"),
        tile(f"{fmt(s['infl_peak'])}%", f"peak core inflation ({s['infl_peak_date']})"),
        tile(f"{fmt(s['real_low'])}%", f"lowest real rate ({s['real_low_date']})"),
    ])
    # returns a str of HTML: a grid of 6 cards, e.g. '<div class="kpis six"><div class="kpi"><b>4.4% to 10.0%</b><span>unemployment ...'
    return f'<div class="kpis six">{tiles}</div>'


def conclusions(rows):
    """The 'What did we learn?' list, written from the numbers."""
    k = by_key(rows)                                           # crisis key -> (episode, stats, window)
    g, c = k["gfc"][1], k["covid"][1]                          # the stats of each crisis
    both_negative = g["slope"] < 0 and c["slope"] < 0          # did both windows show the textbook trade-off?
    slope_lead = ("<b>The Phillips slope was negative in both crises, as the theory says.</b>" if both_negative
                  else "<b>The Phillips slope did not have the textbook sign in both crises.</b>")
    items = [
        (f"<b>Cheap money alone did not fix 2008.</b> The rate sat at the floor for {g['floor_months']} months, but unemployment "
         f"needed {recovery_text(g)} to get back near normal, while core inflation stayed low (peak {fmt(g['infl_peak'])}%)."),
        (f"<b>Covid recovered fast.</b> Unemployment jumped to {fmt(c['u_peak'])}% ({c['u_peak_date']}) but was back near normal "
         f"after {recovery_text(c)}, with {c['floor_months']} months at the floor."),
        (f"<b>The cost came later.</b> Core inflation reached {fmt(c['infl_peak'])}% ({c['infl_peak_date']}) and the real rate "
         f"fell to {fmt(c['real_low'])}% ({c['real_low_date']})."),
        (f"{slope_lead} One more point of unemployment went with {fmt(g['slope'], 2, True)} points of core inflation after 2008 "
         f"and {fmt(c['slope'], 2, True)} in Covid."),
        (f"<b>Limits.</b> Two crises are a small sample, and the charts show what moved together, not what caused what: the Fed "
         f"funds rate was not the only thing that changed. \"Recovered\" (within {RECOVERY_BAND} points of the pre-crisis low) and "
         f"\"the floor\" ({FLOOR}% or less) are choices made in this script."),
    ]
    # returns a list of 5 HTML strings, e.g.
    # ['<b>Cheap money alone did not fix 2008.</b> The rate sat at the floor for 85 months, ...', '<b>Covid recovered fast.</b> ...', ...]
    return items


def panel(number, question, finding, how, body, so=""):
    """One numbered section: a question, its one-line finding, how to read it, the chart or table, and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""          # optional reading guide
    so_html = f'<div class="so">{so}</div>' if so else ""                                  # optional takeaway
    # returns a str of HTML, e.g. '<section class="panel"><p class="tag">01</p><h2>How did the two crises compare?</h2><p class="dek">...'
    return (f'<section class="panel"><p class="tag">{number:02d}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def references():
    """The quiet 'References' list after the last panel: no panel box, no question, one muted line per source."""
    items = "".join(                                           # one <li> per source; the whole line is the link (44px tap target)
        f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><span><b>{escape(who)}</b>: {escape(what)}.</span></a></li>'
        for who, what, u in SOURCES)
    # returns a str of HTML: a small heading and 3 links, e.g.
    # '<aside class="refs" aria-label="References"><h3>References</h3><ul>
    #   <li><a href="https://fred.stlouisfed.org/series/UNRATE" ...><span><b>FRED (St. Louis Fed)</b>: UNRATE, the US unemployment rate, monthly, %.</span></a></li>
    #   <li><a href="https://fred.stlouisfed.org/series/CPILFESL" ...>...</a></li>
    #   <li><a href="https://fred.stlouisfed.org/series/FEDFUNDS" ...>...</a></li></ul></aside>'
    return f'<aside class="refs" aria-label="References"><h3>References</h3><ul>{items}</ul></aside>'


def episode_panel(number, episode, s, window, other):
    """One crisis: its numbers, the timeline chart and the Phillips chart."""
    key = episode["key"]                                       # 'gfc' or 'covid', used in the chart div ids
    body = (episode_tiles(s)
            + '<p class="label">Rates, unemployment and inflation over time</p>'
            + f'<div class="chart" id="time-{key}" role="img" aria-label="{escape(episode["name"])}: unemployment, core inflation, Fed funds and real rate"></div>'
            + '<p class="label">The Phillips curve, coloured by the Fed funds rate</p>'
            + f'<div class="chart" id="phil-{key}" role="img" aria-label="{escape(episode["name"])}: unemployment against core inflation, one dot per month"></div>'
            + f'<p class="note">Phillips slope in this window: {fmt(s["slope"], 2, True)}. '
            + '<span class="hint">Hover over or tap</span> a chart for exact values.</p>')
    html = panel(number, QUESTIONS[key],
                 f"{s['floor_months']} months at the floor; unemployment back near normal after {recovery_text(s)}.",
                 "<b>Top chart:</b> month by month. Grey band = Fed funds at the floor. Dashed line = real rate (Fed funds minus "
                 "inflation). <b>Bottom chart:</b> each dot is one month (unemployment on the x axis, core inflation on the y axis); "
                 "its colour is the Fed funds rate that month, on the scale under the chart.",
                 body, f"<p>{escape(story_text(episode, s, window, other))}</p>")
    # returns a str of HTML: one <section class="panel"> with 6 cards and 2 chart divs (time-gfc, phil-gfc for the 2008 crisis)
    return html


def build_page(rows):
    """Assemble the standalone HTML page and write it to disk."""
    ff_max = max(float(w["fedfunds"].max()) for _, _, w in rows)  # highest Fed funds rate in any window = top of the shared colour scale
    episodes_json = []                                         # per-episode data for the browser
    for episode, stats, window in rows:                        # one entry per crisis
        episodes_json.append({
            "key": episode["key"], "name": episode["name"],    # the chart colour comes from the page's --gfc / --covid tokens
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
    payload = {"episodes": episodes_json, "ff_max": ff_max, "band": RECOVERY_BAND}  # everything the page's JavaScript needs

    k = by_key(rows)                                           # crisis key -> (episode, stats, window)
    g_ep, g, g_win = k["gfc"]                                  # 2008 crisis
    c_ep, c, c_win = k["covid"]                                # Covid
    first = min(w.index.min() for _, _, w in rows).strftime("%b %Y")   # first month shown on the page
    last = max(w.index.max() for _, _, w in rows).strftime("%b %Y")    # last month shown on the page
    g_start, c_start = recovery_curve(g_win).iloc[0], recovery_curve(c_win).iloc[0]   # points above normal at each peak

    months = lambda s: str(s["recovery_months"]) if s["recovery_months"] is not None else "not yet"  # short KPI value
    kpis = "".join([                                           # the four headline numbers under the header
        tile(months(g), "months for unemployment to recover · 2008 crisis", "--gfc"),
        tile(months(c), "months for unemployment to recover · Covid", "--covid"),
        tile(f"{g['floor_months']} / {c['floor_months']}", "months with the rate at the floor · 2008 / Covid"),
        tile(f"{fmt(c['infl_peak'])}%", f"peak core inflation after Covid ({c['infl_peak_date']})", "--covid"),
    ])
    gloss = '<dl class="gloss">' + "".join(f"<div><dt>{escape(t)}</dt><dd>{escape(d)}</dd></div>" for t, d in GLOSSARY) + "</dl>"
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in conclusions(rows)) + "</ol>"

    panels = "".join([
        panel(1, "How did the two crises compare?",
              f"Unemployment got back near normal in {recovery_text(c)} after Covid, {recovery_text(g)} after 2008.",
              f"One column per crisis. <b>Months to recover</b> counts from the month unemployment peaked to the first month it is "
              f"back within {RECOVERY_BAND} points of its pre-crisis low. <b>Months at the floor</b> counts months with the Fed funds "
              f"rate at {FLOOR}% or less. The <b>real rate</b> is the Fed funds rate minus core inflation.",
              compare_table(rows),
              "<p><b>The question:</b> when the Fed cuts rates to the floor, does the economy recover? Compare the two crises. "
              "After 2008 the answer was slow and weak. After Covid it was fast, but inflation came back.</p>"),
        panel(2, "Which recovery was faster?",
              f"Covid started {fmt(c_start)} points above normal and took {recovery_text(c)}; 2008 started {fmt(g_start)} points "
              f"above and took {recovery_text(g)}.",
              f"The vertical axis is how many percentage points the unemployment rate is above where it was before the crisis. "
              f"Example: 2008 starts at {fmt(g_start)} because unemployment hit {fmt(g['u_peak'])}% against a {fmt(g['u_base'])}% low. "
              f"The horizontal axis is months since unemployment peaked, so both crises start at month 0. The faster a line falls, "
              f"the faster the recovery. The dotted line at {RECOVERY_BAND} means \"recovered\" (back within {RECOVERY_BAND} points of normal).",
              '<div class="chart" id="recovery" role="img" aria-label="Unemployment above its pre-crisis level, months since the peak, both crises"></div>',
              f"<p>Both crises put the rate at the floor, yet the lines fall at very different speeds: {g['floor_months']} months "
              f"of near-zero rates after 2008 did not bring unemployment down quickly.</p>"),
        episode_panel(3, g_ep, g, g_win, c),
        episode_panel(4, c_ep, c, c_win, g),
        panel(5, "What is the Phillips curve, and why does the rate matter?",
              "Unemployment and inflation trade off; the interest rate is how the Fed moves along that trade-off.",
              "", gloss),
        panel(6, "What did we learn?", "Five takeaways.", "", take),
    ]) + references()                                          # the sources follow the last panel as a quiet list, not a panel

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Rates and the Phillips Curve</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
<script>{ECHARTS_PATH.read_text(encoding='utf-8')}</script>
</head>
<body>
<header class="band"><div class="in">
<a class="back" href="index.html">&larr; Interest rates &amp; Phillips curve</a>
<p class="eyebrow">Monetary policy · Phillips curve</p>
<h1>Did low interest rates bring the recovery?</h1>
<p class="answer">{answer_text(rows)}</p>
<p class="meta">US monthly data, {first} to {last}: unemployment, core CPI inflation and the Fed funds rate · FRED</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{panels}
</main>
<footer><div class="in">Generated by rates_phillips.py from FRED monthly data (UNRATE, CPILFESL, FEDFUNDS).
Learning project, not investment advice.</div></footer>
<script>{JS.replace('__DATA__', json.dumps(payload))}</script>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # write the page
    # returns nothing; writes Rates_and_Phillips/rates_phillips.html (~1 MB, standalone, ECharts embedded)
    return None


if __name__ == "__main__":
    main()
