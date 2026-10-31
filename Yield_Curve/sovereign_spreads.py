"""
How much extra do France and Italy pay to borrow, compared with Germany?

Germany is the euro area's "safe" borrower. Every other euro country borrows in the
same currency, so the gap between its 10-year yield and Germany's is a clean measure
of how risky the market thinks it is:

    spread (basis points) = (10y yield of the country - 10y yield of Germany) x 100
        1 basis point (bp) = 0.01 percentage point; a 150 bp spread = 1.50% more per year

A second, purer measure is the CREDIT DEFAULT SWAP (CDS): an insurance contract on a
government's debt. The buyer pays a yearly premium (quoted in bp of the amount insured)
and gets paid if the country defaults. A rule of thumb turns that premium into the
default probability the market is implying:

    yearly default probability ~= CDS premium / (1 - recovery rate)
        (recovery rate = share of the money you would get back after a default; 40% is the market convention)

Data:
    - 10-year yields of Germany, France and Italy, monthly, from the ECB data portal (free, no key).
    - 5-year CDS premiums: there is no free CDS download, so a small table of the latest
      levels reported in the press is typed in below (CDS_SNAPSHOT), each with its source.
    - The latest daily spreads (October 2026) reported in the press, also typed in with sources,
      because the ECB's monthly average for October is not published yet.

Output: Yield_Curve/sovereign_spreads.html (one standalone page, drawn with Apache ECharts).
        Yield_Curve/csv/sovereign_spreads.csv (one row per month, yields and spreads).

Layout of this file (see CLAUDE.md):
    1. python / data code  -> settings, downloads, calculations, and def main()
    2. html / chart code   -> builds the web page and the charts
"""

import json                               # turns Python lists/dicts into text the browser's JavaScript can read
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import pandas as pd                       # tables (DataFrames) and time series


# ===========================================================================
# python / data code
# ===========================================================================

HERE = Path(__file__).parent                                   # the Yield_Curve folder
OUTPUT_PATH = HERE / "sovereign_spreads.html"                  # the web page we write
CSV_PATH = HERE / "csv" / "sovereign_spreads.csv"              # a copy of the monthly table

# ECB "long-term interest rate for convergence purposes" = the 10-year government bond yield, monthly average.
# {} is replaced by the country code (DE, FR, IT). format=csvdata asks for a plain CSV answer.
ECB_URL = "https://data-api.ecb.europa.eu/service/data/IRS/M.{}.L.L40.CI.0000.EUR.N.Z?format=csvdata"

COUNTRIES = {"DE": "Germany", "FR": "France", "IT": "Italy"}   # ECB code -> name shown on the page
EURO_START = "1999-01"                    # the euro starts in Jan 1999; before that, spreads also contain currency risk
RECOVERY_RATE = 0.40                      # market convention: after a sovereign default, bondholders get back ~40%

# Latest 5-year CDS premiums reported in the press (no free data feed exists, so they are typed in by hand).
# Each row: country, premium in bp, date of the quote, who reported it, link to the source.
CDS_SNAPSHOT = [
    {"country": "Germany", "cds_bp": 7.3, "date": "2026-07-24", "source": "Börse München, Bonds Daily",
     "url": "https://www.boerse-muenchen.de/fileadmin/user_upload/Morning_News/Bonds_Daily.pdf"},
    {"country": "Italy", "cds_bp": 68.0, "date": "2026-10-09", "source": "MacroMicro",
     "url": "https://en.macromicro.me/series/27135/italy-5year-cds"},
    {"country": "France", "cds_bp": 79.5, "date": "2026-10-15", "source": "Investing.com",
     "url": "https://www.investing.com/rates-bonds/france-cds-5-years-usd-historical-data"},
]
# Latest daily 10y spreads vs Germany reported in the press (closes, not monthly averages).
LATEST_DAILY = [
    {"country": "France", "spread_bp": 154, "date": "2026-10-20", "source": "Bloomberg",
     "url": "https://www.bloomberg.com/news/articles/2026-10-20/french-bond-risk-gauge-hits-150-basis-points-after-protests"},
    {"country": "Italy", "spread_bp": 107, "date": "2026-10-16", "source": "countryeconomy.com",
     "url": "https://countryeconomy.com/risk-premium/italy"},
]

# Events marked on the history chart: (month, short label, longer explanation).
EVENTS = [
    ("2011-11", "1", "Euro crisis peak."),
    ("2012-07", "2", "Draghi: \"whatever it takes\"."),
    ("2018-05", "3", "Italy's populist budget clash."),
    ("2024-06", "4", "Macron calls a snap election."),
    ("2025-09", "5", "Bayrou government falls; Fitch cuts France."),
    ("2026-10", "6", "Riots in France and Italy."),
]


def fetch_ecb_yield(code):
    """Download one country's 10-year yield from the ECB as a monthly pandas Series."""
    table = pd.read_csv(ECB_URL.format(code))                  # the ECB answers with one row per month and ~30 columns
    series = table.set_index("TIME_PERIOD")["OBS_VALUE"]       # keep only the month ("2026-09") and the yield (4.44)
    series.index = pd.to_datetime(series.index)                # "2026-09" text -> Timestamp 2026-09-01, so dates sort and slice
    series = pd.to_numeric(series, errors="coerce")            # make sure the values are numbers (blanks become NaN)
    series.name = code                                         # name the series after the country code
    # returns a pandas Series, one value per month in % (Germany and France start Jan 1990, Italy Mar 1991),
    # e.g. fetch_ecb_yield("FR"):
    # TIME_PERIOD
    # 2026-07-01    3.85
    # 2026-08-01    4.00
    # 2026-09-01    4.44
    # Name: FR, dtype: float64
    return series


def build_dataset():
    """One monthly table: the three 10-year yields and the three spreads, euro era only."""
    yields = {code: fetch_ecb_yield(code) for code in COUNTRIES}  # download the three countries, keyed by code
    data = pd.DataFrame(yields).dropna()                       # join them by month; drop months where one is missing
    data = data.loc[EURO_START:]                               # keep Jan 1999 onward (before the euro, spreads mix in currency risk)
    data["fr_de"] = (data["FR"] - data["DE"]) * 100            # France's premium over Germany, in basis points
    data["it_de"] = (data["IT"] - data["DE"]) * 100            # Italy's premium over Germany, in basis points
    data["it_fr"] = (data["IT"] - data["FR"]) * 100            # Italy minus France: > 0 Italy pays more, < 0 France pays more
    data = data.round(2)                                       # 2 decimals is plenty for yields and bp
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)         # create the csv folder if missing
    data.to_csv(CSV_PATH)                                      # save a copy next to this script
    # returns a DataFrame, one row per month (Jan 1999 - Sep 2026, ~333 rows); yields in %, spreads in bp:
    #                DE    FR    IT  fr_de  it_de  it_fr
    # TIME_PERIOD
    # 2026-07-01   3.07  3.85  3.88  78.0   81.1    3.1
    # 2026-08-01   3.18  4.00  3.99  81.5   80.1   -1.4
    # 2026-09-01   3.47  4.44  4.36  96.7   88.9   -7.8
    return data


def spread_stats(data):
    """The headline numbers: latest month, euro-era records, and how often France paid more than Italy."""
    last = data.index[-1]                                      # most recent month in the ECB data
    fr_peak_date = data["fr_de"].idxmax()                      # month of France's widest spread since 1999
    it_peak_date = data["it_de"].idxmax()                      # month of Italy's widest spread since 1999
    flipped = data[data["it_fr"] < 0]                          # months when France paid MORE than Italy
    recent = data.loc[last - pd.DateOffset(months=11):]        # the last 12 months
    stats = {                                                  # one flat dict, easy to print and to show as tiles
        "last_month": last.strftime("%b %Y"),
        "de": float(data.loc[last, "DE"]), "fr": float(data.loc[last, "FR"]), "it": float(data.loc[last, "IT"]),
        "fr_de": float(data.loc[last, "fr_de"]), "it_de": float(data.loc[last, "it_de"]),
        "it_fr": float(data.loc[last, "it_fr"]),
        "fr_peak": float(data.loc[fr_peak_date, "fr_de"]), "fr_peak_date": fr_peak_date.strftime("%b %Y"),
        "it_peak": float(data.loc[it_peak_date, "it_de"]), "it_peak_date": it_peak_date.strftime("%b %Y"),
        "flip_months": [d.strftime("%b %Y") for d in flipped.index],   # every month France paid more than Italy
        "flip_last12": int((recent["it_fr"] < 0).sum()),       # how many of the last 12 months that happened
    }
    # returns a dict of 13 values (real output with data up to Sep 2026):
    # {'last_month': 'Sep 2026', 'de': 3.47, 'fr': 4.44, 'it': 4.36, 'fr_de': 96.7, 'it_de': 88.9, 'it_fr': -7.8,
    #  'fr_peak': 154.0, 'fr_peak_date': 'Nov 2011', 'it_peak': 519.0, 'it_peak_date': 'Nov 2011',
    #  'flip_months': ['Dec 2025', 'Jan 2026', 'Feb 2026', 'Aug 2026', 'Sep 2026'], 'flip_last12': 5}
    return stats


def implied_default_probability(premium_bp, recovery=RECOVERY_RATE):
    """Turn a credit premium (bp per year) into the yearly default probability it implies, in %."""
    premium = premium_bp / 10000                               # bp -> decimal (80 bp -> 0.0080)
    loss_if_default = 1 - recovery                             # share of the money lost in a default (0.60)
    probability = premium / loss_if_default * 100              # fair premium = probability x loss, so probability = premium / loss; in %
    # returns a float, the yearly default probability in %; e.g. implied_default_probability(79.5) -> 1.325  (1.33 once rounded)
    # (France's 79.5 bp CDS = the market pricing about a 1.3% chance of default per year)
    return probability


def cds_table():
    """The CDS snapshot as a table, with the implied default probability added."""
    table = pd.DataFrame(CDS_SNAPSHOT)                         # one row per country, from the hand-typed list
    table["default_prob"] = table["cds_bp"].apply(implied_default_probability).round(2)  # % per year
    table["vs_germany"] = (table["cds_bp"] / table.loc[table["country"] == "Germany", "cds_bp"].iloc[0]).round(1)  # times Germany's premium
    # returns a DataFrame, 3 rows x 7 columns (url column not shown):
    #    country  cds_bp        date                       source  default_prob  vs_germany
    # 0  Germany     7.3  2026-07-24  Börse München, Bonds Daily          0.12         1.0
    # 1    Italy    68.0  2026-10-09                   MacroMicro          1.13         9.3
    # 2   France    79.5  2026-10-15                Investing.com          1.33        10.9
    return table


def print_summary(stats, cds):
    """Print the key numbers in the terminal."""
    print(f"ECB monthly data up to {stats['last_month']}: 10y yields DE {stats['de']:.2f}%  FR {stats['fr']:.2f}%  IT {stats['it']:.2f}%")
    print(f"Spread vs Germany: France {stats['fr_de']:.0f} bp (record {stats['fr_peak']:.0f} bp, {stats['fr_peak_date']}), "
          f"Italy {stats['it_de']:.0f} bp (record {stats['it_peak']:.0f} bp, {stats['it_peak_date']})")
    print(f"France paid more than Italy in {stats['flip_last12']} of the last 12 months: {', '.join(stats['flip_months'])}")
    for _, row in cds.iterrows():                              # one line per country in the CDS snapshot
        print(f"CDS 5y {row['country']:<8} {row['cds_bp']:>5.1f} bp ({row['date']}) -> ~{row['default_prob']:.2f}% default risk per year")
    # returns nothing; prints 6 lines, e.g.
    # ECB monthly data up to Sep 2026: 10y yields DE 3.47%  FR 4.44%  IT 4.36%
    # Spread vs Germany: France 97 bp (record 154 bp, Nov 2011), Italy 89 bp (record 519 bp, Nov 2011)
    # France paid more than Italy in 5 of the last 12 months: Dec 2025, Jan 2026, Feb 2026, Aug 2026, Sep 2026
    # CDS 5y Germany    7.3 bp (2026-07-24) -> ~0.12% default risk per year
    # CDS 5y Italy     68.0 bp (2026-10-09) -> ~1.13% default risk per year
    # CDS 5y France    79.5 bp (2026-10-15) -> ~1.32% default risk per year
    return None


def main():
    data = build_dataset()                                     # step 1: download yields, compute spreads, save the CSV
    stats = spread_stats(data)                                 # step 2: the headline numbers
    cds = cds_table()                                          # step 3: the CDS snapshot with implied default risk
    print_summary(stats, cds)                                  # step 4: print them
    build_page(data, stats, cds)                               # step 5: write the web page (code below)
    print(f"Saved {OUTPUT_PATH}")                              # tell the user where the page is


# ===========================================================================
# html / chart code
# ===========================================================================

ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"  # Apache ECharts, a fixed version
FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"  # the Lab fonts

# Look: the "Lab" design every project page uses (see CLAUDE.md): green header band, brass accents, white panels,
# the same fonts as the homepage. Colours: one fixed hue per country, France = blue, Italy = green, Germany = grey.
# Text always uses the ink tokens and names the country in words, never colour alone.
CSS = """
:root{color-scheme:light dark;--band:#4a2414;--band-ink:#e4e6ea;--brass:#cf6e3a;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--fr:#2a5db0;--it:#1f7a55;--de:#6f7a75}
@media (prefers-color-scheme:dark){:root{--band:#33180d;--brass:#ec9665;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--fr:#6d9be0;--it:#3fa37c;--de:#a5b2ab}}
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
.chart{width:100%;height:420px}
.chart.short{height:260px}
.label{margin:18px 0 4px;font-size:13px;font-weight:600;color:var(--ink-2)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle}
.stories{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.story{border-top:3px solid var(--c);padding-top:12px}
.story h3{margin:0 0 4px;font-size:17px}
.story ul{margin:0;padding-left:1.1rem;color:var(--ink-2);font-size:15px}
.story li{margin:0 0 8px}
.story li b{color:var(--ink)}
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
.refs{margin:36px 0 0;color:var(--muted);font-size:13px;line-height:1.45}
.refs h3{margin:0 0 4px;font:700 12px/1.4 "DM Sans",system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase}
.refs ul{list-style:none;margin:0;padding:0}
.refs a{display:flex;align-items:center;min-height:40px;padding:6px 0;color:var(--muted);text-decoration:none}
.refs a:hover{color:var(--ink);text-decoration:underline}
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
@media (max-width:640px){
  .chart{height:480px}.chart.short{height:300px}
  .stories,.gloss{grid-template-columns:1fr;gap:18px}
  th,td{padding:8px 4px;font-size:13px}th{white-space:normal}
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

function tip(extra) {                                           // a tooltip in the page colours, never ECharts' default white box
  const label = {backgroundColor: css("--surface"), borderColor: css("--grid"), borderWidth: 1,   // axis-pointer label (the date/value tag on an axis)
                 color: css("--ink"), shadowBlur: 8, shadowColor: "rgba(0,0,0,.18)"};
  return Object.assign({
    triggerOn: isTouch ? "click" : "mousemove|click", confine: true,  // tap on touch screens; never spill off a phone screen
    backgroundColor: css("--surface"), borderColor: css("--grid"), borderWidth: 1,  // card colour and hairline border from the tokens
    textStyle: {color: css("--ink"), fontSize: 13},             // dark ink in light mode, light ink in dark mode
    extraCssText: "box-shadow:0 6px 20px rgba(0,0,0,.18);border-radius:8px;",  // soft shadow so the box lifts off the chart
    axisPointer: {label},                                       // the same look for axis-pointer labels
  }, extra);
}

function base(narrow) {                                         // options shared by every chart
  return {
    animation: false, backgroundColor: "transparent", textStyle: {color: css("--ink-2")},
    legend: narrow ? {bottom: 4, left: 12, orient: "vertical", itemGap: 6, textStyle: {color: css("--ink-2")}}  // below the plot on a phone
                   : {top: 6, right: 16, textStyle: {color: css("--ink-2")}},  // top right, clear of the y-axis title
    tooltip: tip({trigger: "axis"}),                            // one tooltip for every line at the tapped date
  };
}
const ax = extra => Object.assign({axisLine: {lineStyle: {color: css("--axis")}}, splitLine: {lineStyle: {color: css("--grid")}},
                                   axisLabel: {color: css("--muted"), hideOverlap: true}}, extra);
function zoom(narrow, startYear) {                              // slider under the plot; drag-zoom only with a mouse
  const start = startYear ? DATA.dates.findIndex(d => d >= startYear) / DATA.dates.length * 100 : 0;
  const z = [{type: "slider", ...sliderStyle(), start, end: 100, height: 22, bottom: narrow ? 92 : 8, borderColor: css("--grid"),
              textStyle: {color: css("--muted")}, labelFormatter: v => new Date(v).getFullYear()}];
  if (!isTouch) z.push({type: "inside", start, end: 100});      // wheel / drag zoom would trap the finger on a phone
  return z;
}
const pts = key => DATA.dates.map((d, i) => [d, DATA[key][i]]); // [[date, value], ...] for a time axis

function spreads(narrow) {                                      // France and Italy premium over Germany since 1999
  const o = base(narrow);
  o.grid = narrow ? {left: 44, right: 16, top: 56, bottom: 130} : {left: 56, right: 28, top: 60, bottom: 54};
  o.xAxis = ax({type: "time", splitNumber: narrow ? 4 : 8});   // fewer year labels on a phone
  o.yAxis = ax({type: "value", name: "bp over Germany", nameTextStyle: {color: css("--muted"), align: "left"}});
  o.dataZoom = zoom(narrow, null);
  const line = (name, key, color) => ({name, type: "line", data: pts(key), showSymbol: false, lineStyle: {color, width: 2},
    itemStyle: {color}});                                       // no end labels: France and Italy now end at almost the same level
  o.series = [line("France - Germany", "fr_de", css("--fr")), line("Italy - Germany", "it_de", css("--it"))];
  o.series[0].markLine = {silent: true, symbol: "none", lineStyle: {color: css("--axis"), type: "dashed"},  // numbered event lines
    label: {formatter: p => p.name, color: css("--ink-2"), fontSize: 11}, data: DATA.events.map((e, i) => ({name: e[1], xAxis: e[0], label: {distance: narrow ? 2 + (i % 2) * 13 : 4}}))};  // 2 label heights on a phone, one row on desktop
  o.series.push({name: "Oct 2026, latest daily close", type: "scatter", symbol: "diamond", symbolSize: 12,  // the news numbers
    data: DATA.latest.map(r => ({value: [r.date, r.spread_bp], itemStyle: {color: r.country === "France" ? css("--fr") : css("--it"),
          borderColor: css("--surface"), borderWidth: 2}, name: r.country})),
    itemStyle: {color: css("--ink-2")}, tooltip: tip({trigger: "item", formatter: p => p.name + " " + p.value[0] + ": " + p.value[1] + " bp (press report)"})});
  o.tooltip.valueFormatter = v => v == null ? "-" : Math.round(v) + " bp";
  return o;
}

function gap(narrow) {                                          // Italy minus France: who pays more?
  const o = base(narrow);
  o.legend = {show: false};                                     // a single series: the heading and the reading box name it
  o.grid = narrow ? {left: 44, right: 16, top: 16, bottom: 58} : {left: 56, right: 24, top: 20, bottom: 54};  // room for year labels above the slider
  o.xAxis = ax({type: "time", splitNumber: narrow ? 4 : 8});   // fewer year labels on a phone
  o.yAxis = ax({type: "value"});
  o.dataZoom = zoom(narrow, "2018-01");
  o.dataZoom[0].bottom = 8;
  o.series = [{name: "Italy minus France", type: "bar", barCategoryGap: "20%",
    data: DATA.dates.map((d, i) => ({value: [d, DATA.it_fr[i]], itemStyle: {color: DATA.it_fr[i] < 0 ? css("--fr") : css("--it"),
          borderRadius: DATA.it_fr[i] < 0 ? [0, 0, 3, 3] : [3, 3, 0, 0]}}))}];
  o.tooltip.formatter = p => { const v = p[0].value; const n = Math.abs(v[1]).toFixed(0);
    return v[0].slice(0, 7) + "<br>" + (v[1] < 0 ? "France pays " + n + " bp MORE than Italy" : "Italy pays " + n + " bp more than France"); };
  return o;
}

function cds(narrow) {                                          // the CDS snapshot: one bar per country
  const o = base(narrow);
  o.legend = {show: false};                                     // the axis labels name the countries
  o.grid = {left: narrow ? 70 : 80, right: narrow ? 92 : 170, top: 10, bottom: 30};
  o.xAxis = ax({type: "value", name: "", splitNumber: narrow ? 3 : 5, axisLabel: {color: css("--muted"), formatter: "{value} bp", hideOverlap: true}});
  o.yAxis = ax({type: "category", data: DATA.cds.map(r => r.country), axisLabel: {color: css("--ink"), fontSize: 13}, splitLine: {show: false}});
  const color = c => c === "France" ? css("--fr") : c === "Italy" ? css("--it") : css("--de");
  o.series = [{type: "bar", barWidth: "52%", data: DATA.cds.map(r => ({value: r.cds_bp, itemStyle: {color: color(r.country), borderRadius: [0, 4, 4, 0]}})),
    label: {show: true, position: "right", color: css("--ink-2"),
            formatter: p => { const r = DATA.cds[p.dataIndex]; return narrow ? r.cds_bp + " bp" : r.cds_bp + " bp  ~" + r.default_prob.toFixed(2) + "%/yr"; }}}];
  o.tooltip = tip({trigger: "item",                             // one bar at a time, in the page colours
    formatter: p => { const r = DATA.cds[p.dataIndex]; return r.country + ": " + r.cds_bp + " bp (" + r.date + ")<br>implied default risk ~" +
      r.default_prob.toFixed(2) + "% per year<br>" + r.vs_germany + "x Germany's premium"; }});
  return o;
}

const BUILDERS = {spreads, gap, cds};                           // chart div id -> function that builds its options
function drawAll() {                                            // (re)build every chart; called on load, rotation and theme change
  const narrow = narrowMQ.matches;
  document.querySelectorAll(".chart").forEach(div => {
    if (!INSTANCES[div.id]) INSTANCES[div.id] = echarts.init(div);
    INSTANCES[div.id].setOption(BUILDERS[div.id](narrow), true);
    INSTANCES[div.id].resize();
  });
}
if (isTouch) document.querySelectorAll(".hint").forEach(h => h.textContent = "Tap");  // say "tap", not "hover", to touch users
narrowMQ.addEventListener("change", drawAll);                   // rebuild when a phone is rotated
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawAll);  // rebuild in the new colours
window.addEventListener("resize", () => Object.values(INSTANCES).forEach(c => c.resize()));
drawAll();
"""


COUNTRY_CARDS = {                         # one card per country: its problem, then its protests (facts from SOURCES)
    "France": [
        "<b>Problem:</b> deficit 5.4% of GDP (EU limit 3%), debt 119% of GDP, a minority government "
        "(PM Lecornu) that must pass the 2027 budget, and an election in May 2027.",
        "<b>Protests:</b> student protests since September, then 550,000+ marched against the cost of "
        "living on 17 Oct. Looting, Limoges town hall burned, 1,200 arrests.",
        "<b>Market:</b> spread back above 150 bp, the 2011 record; 10y yield near 5%.",
    ],
    "Italy": [
        "<b>Problem:</b> even more debt (~135% of GDP), but a stable government since 2022, a falling "
        "deficit and rating upgrades in 2025. The diesel price shock hurts.",
        "<b>Protests:</b> truckers and farmers block roads in the South over diesel (16 Oct, fuel shortages); "
        "riots in Milan, Turin and Bologna on 17-18 Oct, 141 officers injured.",
        "<b>Market:</b> spread jumped to 131 bp on 5 Oct, then eased to ~107 bp.",
    ],
}
SOURCES = [                               # (headline, source and date, link) for the data and every news fact on the page
    ("10-year yields (IRS)", "ECB data portal", "https://data.ecb.europa.eu/data/datasets/IRS"),
    ("French spread hits 150 bp", "Bloomberg · 20 Oct 2026",
     "https://www.bloomberg.com/news/articles/2026-10-20/french-bond-risk-gauge-hits-150-basis-points-after-protests"),
    ("France 'on the brink'", "Fortune · 17 Oct 2026",
     "https://fortune.com/2026/10/17/france-debt-crisis-budget-deficit-bond-yields-spread-protests-riots/"),
    ("French CDS at 81 bp", "Fortune · 2 Oct 2026",
     "https://fortune.com/2026/10/02/france-debt-crisis-bond-investors-odds-sovereign-default-cds-yield-spread-deficit-presidential-race/"),
    ("Cost-of-living protests", "Al Jazeera · 17 Oct 2026",
     "https://www.aljazeera.com/news/2026/10/17/cost-of-living-protests-hit-belgium-italy-portugal-and-france"),
    ("Italy riots", "Anadolu · 18 Oct 2026",
     "https://www.anews.com.tr/europe/2026/10/18/28-arrested-141-officers-injured-as-cost-of-living-protests-turn-violent-in-italy"),
    ("Truckers' strike in the South", "Il Post · 16 Oct 2026", "https://www.ilpost.it/2026/10/16/proteste-autotrasportatori-sud-italia/"),
    ("Italy spread", "countryeconomy.com", "https://countryeconomy.com/risk-premium/italy"),
] + [(f"{r['country']} CDS",                                   # plus the three CDS quotes
       f"{r['source']} · {pd.Timestamp(r['date']).strftime('%d %b %Y').lstrip('0')}",  # '2026-07-24' -> '24 Jul 2026', like the press lines
       r["url"]) for r in CDS_SNAPSHOT]

GLOSSARY = [                              # (term, plain-language meaning): the explanations from the top of this file
    ("Why Germany?", "Germany is the euro area's \"safe\" borrower. Every other euro country borrows in the same currency, "
                     "so the gap between its 10-year yield and Germany's is a clean measure of how risky the market thinks it is."),
    ("Spread", "(10-year yield of the country − 10-year yield of Germany) × 100, in basis points."),
    ("Basis point (bp)", "0.01 percentage point; a 150 bp spread = 1.50% more per year."),
    ("Credit default swap (CDS)", "An insurance contract on a government's debt. The buyer pays a yearly premium (quoted in bp of "
                                  "the amount insured) and gets paid if the country defaults."),
    ("Recovery rate", f"The share of the money you would get back after a default; {RECOVERY_RATE:.0%} is the market convention."),
    ("Implied default probability", "Yearly default probability ≈ CDS premium ÷ (1 − recovery rate): the default risk the market is implying."),
]


def short_date(iso):
    """Turn an ISO date into a short day-month label, e.g. '2026-10-20' -> '20 Oct'."""
    ts = pd.Timestamp(iso)                                     # text -> Timestamp, so we can read its day and month
    # returns a str, e.g. short_date("2026-10-20") -> '20 Oct', short_date("2026-07-24") -> '24 Jul'
    return f"{ts.day} {ts:%b}"


def tile(value, label, color=None):
    """One headline number with its label; an optional coloured dot names the country."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # identity is in the text too, never colour alone
    # returns a str of HTML, e.g. '<div class="kpi"><b><i class="dot" ...></i>154 bp</b><span>France over Germany (20 Oct)</span></div>'
    return f'<div class="kpi"><b>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def country_card(country, color):
    """One card: the country's problem, protests and market reaction as a short list."""
    items = "".join(f"<li>{item}</li>" for item in COUNTRY_CARDS[country])   # our own text, already safe HTML
    # returns a str of HTML, e.g. '<div class="story" style="--c:var(--fr)"><h3>...France</h3><ul><li>...</li> x3</ul></div>'
    return (f'<div class="story" style="--c:var({color})"><h3><i class="dot" style="background:var({color})"></i>'
            f'{country}</h3><ul>{items}</ul></div>')


def recent_table(data):
    """HTML table of the last 6 months: the three spreads."""
    rows = "".join(                                            # newest month first
        f"<tr><td>{d.strftime('%b %Y')}</td><td>{r['fr_de']:.0f}</td><td>{r['it_de']:.0f}</td><td>{r['it_fr']:+.0f}</td></tr>"
        for d, r in data.tail(6).iloc[::-1].iterrows())
    head = "<tr><th>Month</th><th>France vs DE</th><th>Italy vs DE</th><th>Italy vs FR</th></tr>"   # short headers so it fits a phone
    # returns a str of HTML: a header and 6 rows, e.g. <tr><td>Sep 2026</td><td>97</td><td>89</td><td>-8</td></tr>
    return f'<div class="scroll"><table>{head}{rows}</table></div>'


def answer_text(stats, fr_cds, it_cds):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    fr_now = LATEST_DAILY[0]["spread_bp"]                      # France's latest daily spread from the press (bp)
    if stats["flip_last12"] > 0:                               # France paid more than Italy in at least one recent month
        lead = "<b>Italy used to be the risky one. Now France pays as much or more.</b> "
    else:                                                      # the old order still holds
        lead = "<b>Italy still pays more than France.</b> "
    level = "back at" if fr_now >= stats["fr_peak"] - 10 else "below"   # within 10 bp of the monthly record counts as "back at"
    dearer = "more" if fr_cds["cds_bp"] > it_cds["cds_bp"] else "less"   # is French default insurance dearer than Italian?
    body = (f"Its premium over Germany is {level} the {stats['fr_peak_date'][-4:]} euro-crisis record (~{fr_now} bp), "
            f"and insuring French debt costs {dearer} than insuring Italian debt.")
    # returns a str of HTML, about 230 characters, e.g.
    # '<b>Italy used to be the risky one. Now France pays as much or more.</b> Its premium over Germany is back at the
    #  2011 euro-crisis record (~154 bp), and insuring French debt costs more than insuring Italian debt.'
    return lead + body


def conclusions(stats, cds):
    """The 'What did we learn?' list, assembled from the findings already on the page."""
    fr_cds = cds.set_index("country").loc["France"]            # France's row of the CDS table
    it_cds = cds.set_index("country").loc["Italy"]             # Italy's row
    fr_now, it_now = LATEST_DAILY[0], LATEST_DAILY[1]          # the latest daily press figures
    items = [
        (f"<b>France now pays as much as Italy, or more.</b> France paid more than Italy in {stats['flip_last12']} of the "
         f"last 12 months ({', '.join(stats['flip_months'])})."),
        (f"<b>France is back at its euro-crisis level:</b> {fr_now['spread_bp']} bp on {short_date(fr_now['date'])}, against a "
         f"monthly record of {stats['fr_peak']:.0f} bp in {stats['fr_peak_date']}. Italy, at {it_now['spread_bp']} bp, is far from "
         f"its own record of {stats['it_peak']:.0f} bp ({stats['it_peak_date']})."),
        (f"<b>Default insurance tells the same story.</b> France's 5-year CDS is {fr_cds['cds_bp']:.1f} bp (~{fr_cds['default_prob']:.2f}% "
         f"default risk per year), Italy's {it_cds['cds_bp']:.1f} bp (~{it_cds['default_prob']:.2f}%): {fr_cds['vs_germany']}x and "
         f"{it_cds['vs_germany']}x Germany's premium."),
        ("<b>The reasons differ.</b> France: a large deficit and a minority government that must pass the 2027 budget. "
         "Italy: even more debt, but a stable government and a falling deficit."),
        ("<b>Limits.</b> The ECB yields are monthly averages, so the October daily closes come from the press. The CDS quotes are "
         f"from different days (Germany's from July) because there is no free CDS feed, and the {RECOVERY_RATE:.0%} recovery rate "
         "is a convention, so the implied default risks are rough."),
    ]
    # returns a list of 5 HTML strings, e.g.
    # ['<b>France now pays as much as Italy, or more.</b> France paid more than Italy in 5 of the last 12 months (Dec 2025, ...).',
    #  '<b>France is back at its euro-crisis level:</b> 154 bp on 20 Oct, against a monthly record of 154 bp in Nov 2011. ...', ...]
    return items


def panel(number, question, finding, how, body, so=""):
    """One numbered section: a question, its one-line finding, how to read it, the chart or table, and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""          # optional reading guide
    so_html = f'<div class="so">{so}</div>' if so else ""                                  # optional takeaway
    # returns a str of HTML, e.g. '<section class="panel"><p class="tag">01</p><h2>How much more do France and Italy pay ...</h2><p class="dek">...'
    return (f'<section class="panel"><p class="tag">{number:02d}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def references():
    """The quiet 'References' list after the last panel: one tappable line per source (who, when, what)."""
    lines = "".join(                                           # one <li> per source in SOURCES
        f'<li><a href="{escape(u)}" target="_blank" rel="noopener">{escape(w)} — {escape(h)}</a></li>'  # "who · when — what"
        for h, w, u in SOURCES)                                # h = headline, w = source and date, u = link
    # returns a str of HTML, one <li> per source (11 lines), e.g.
    # '<section class="refs" aria-label="References"><h3>References</h3><ul>
    #  <li><a href="https://data.ecb.europa.eu/data/datasets/IRS" ...>ECB data portal — 10-year yields (IRS)</a></li>
    #  <li><a href="https://www.bloomberg.com/news/..." ...>Bloomberg · 20 Oct 2026 — French spread hits 150 bp</a></li> ...</ul></section>'
    return f'<section class="refs" aria-label="References"><h3>References</h3><ul>{lines}</ul></section>'


def build_page(data, stats, cds):
    """Assemble the standalone HTML page and write it to disk."""
    payload = {                                                # everything the page's JavaScript needs
        "dates": [d.strftime("%Y-%m-%d") for d in data.index],  # x values for every chart
        **{key: [round(float(v), 2) for v in data[key]] for key in ["fr_de", "it_de", "it_fr"]},  # the three spreads
        "events": [[f"{month}-01", label] for month, label, _ in EVENTS],  # where to draw the numbered event lines
        "latest": LATEST_DAILY,                                # the October press figures (diamonds on the chart)
        "cds": cds.drop(columns="url").to_dict(orient="records"),  # the CDS bars
    }
    s = stats                                                  # short name
    by_country = cds.set_index("country")                      # CDS table indexed by country name
    fr_cds, it_cds, de_cds = by_country.loc["France"], by_country.loc["Italy"], by_country.loc["Germany"]  # one row each
    fr_now, it_now = LATEST_DAILY[0], LATEST_DAILY[1]          # the latest daily press figures
    latest_quote = short_date(max(r["date"] for r in LATEST_DAILY + CDS_SNAPSHOT))  # newest press date on the page, e.g. '20 Oct'
    kpis = "".join([                                           # the four headline numbers under the header
        tile(f"{fr_now['spread_bp']} bp", f"France over Germany ({short_date(fr_now['date'])})", "--fr"),
        tile(f"{it_now['spread_bp']} bp", f"Italy over Germany ({short_date(it_now['date'])})", "--it"),
        tile(f"{fr_cds['cds_bp']:.1f} bp", f"France 5y CDS: ~{fr_cds['default_prob']:.1f}% default risk/yr", "--fr"),
        tile(f"{it_cds['cds_bp']:.1f} bp", f"Italy 5y CDS: ~{it_cds['default_prob']:.1f}% default risk/yr", "--it"),
    ])
    events = " · ".join(f"<b>{label}</b> {escape(text)}" for _, label, text in EVENTS)   # one compact line of event keys
    gloss = '<dl class="gloss">' + "".join(f"<div><dt>{escape(t)}</dt><dd>{escape(d)}</dd></div>" for t, d in GLOSSARY) + "</dl>"
    cards = f'<div class="stories">{country_card("France", "--fr")}{country_card("Italy", "--it")}</div>'   # the two country cards
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in conclusions(stats, cds)) + "</ol>"   # numbered takeaways
    hint = '<span class="hint">Hover over or click</span>'     # turned into "Tap" on touch screens by the JavaScript

    panels = "".join([
        panel(1, "How much more do France and Italy pay than Germany?",
              f"France {s['fr_de']:.0f} bp and Italy {s['it_de']:.0f} bp in {s['last_month']} (monthly average); "
              f"{fr_now['spread_bp']} and {it_now['spread_bp']} bp at the latest daily close.",
              "Each line is the country's 10-year yield minus Germany's: monthly ECB averages since the euro began in 1999. "
              "Diamonds = latest daily close. 100 bp = 1 percentage point. The numbered dashed lines are the events listed under "
              f"the chart. {hint} the chart to read a month; drag the slider to zoom.",
              '<div class="chart" id="spreads" role="img" aria-label="France and Italy 10-year spreads over Germany since 1999"></div>'
              f'<p class="note">{events}</p>',
              f"<p>Records since 1999: France {s['fr_peak']:.0f} bp ({s['fr_peak_date']}), Italy {s['it_peak']:.0f} bp "
              f"({s['it_peak_date']}). France's latest daily close ({fr_now['spread_bp']} bp) is at that level again; "
              f"Italy ({it_now['spread_bp']} bp) is far below its own.</p>"
              if fr_now["spread_bp"] >= s["fr_peak"] - 10 else    # only claim "at that level again" when it is true
              f"<p>Records since 1999: France {s['fr_peak']:.0f} bp ({s['fr_peak_date']}), Italy {s['it_peak']:.0f} bp "
              f"({s['it_peak_date']}).</p>"),
        panel(2, "How do you measure the price of risk?", "Two prices: the spread over Germany and the CDS premium.",
              "", gloss),
        panel(3, "Who pays more, France or Italy?",
              f"France paid more than Italy in {s['flip_last12']} of the last 12 months.",
              "Italy's yield minus France's. <b>Blue bars below zero = France pays more</b>; green bars above zero = Italy pays more. "
              f"The chart opens on 2018; drag the slider back to 1999. {hint} a bar to read the month.",
              '<div class="chart short" id="gap" role="img" aria-label="Italy\'s yield minus France\'s yield"></div>'
              '<p class="label">Last 6 months (bp)</p>' + recent_table(data),
              f"<p>Since 1999 France paid more than Italy in only {len(s['flip_months'])} months: {', '.join(s['flip_months'])}.</p>"),
        panel(4, "How much does it cost to insure against a default?",
              f"France {fr_cds['cds_bp']:.1f} bp, Italy {it_cds['cds_bp']:.1f} bp, Germany {de_cds['cds_bp']:.1f} bp a year.",
              f"Each bar is a 5-year CDS premium. Default risk per year ≈ CDS ÷ (1 − {RECOVERY_RATE:.0%} recovery). "
              f"France: {fr_cds['cds_bp']} bp → ~{fr_cds['default_prob']:.2f}%. {hint} a bar for its date.",
              '<div class="chart short" id="cds" role="img" aria-label="5-year CDS premiums for Germany, Italy and France"></div>'
              '<p class="note">Latest press quotes from different days (there is no free CDS feed). Germany\'s is from July.</p>',
              f"<p>Insuring French debt costs {fr_cds['vs_germany']}x Germany's premium, Italian debt {it_cds['vs_germany']}x.</p>"),
        panel(5, "Why now, and what happened in October?",
              "France has a budget and government problem; Italy has more debt but a stable government.",
              "", cards),
        panel(6, "What did we learn?", "Five takeaways.", "", take),
    ])                                                         # the sources are no panel: a quiet References list follows (CLAUDE.md)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>France &amp; Italy Risk Premium</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
<script src="{ECHARTS_URL}"></script>
</head>
<body>
<header class="band"><div class="in">
<a class="back" href="../index.html">&larr; Macro Quant Lab</a>
<p class="eyebrow">France vs Italy: the price of risk</p>
<h1>What do France and Italy pay over Germany to borrow?</h1>
<p class="answer">{answer_text(stats, fr_cds, it_cds)}</p>
<p class="meta">ECB monthly data to {s['last_month']} · press quotes to {latest_quote} · Not investment advice</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{panels}
{references()}
</main>
<footer><div class="in">Built by <code>Yield_Curve/sovereign_spreads.py</code> from ECB 10-year yields and press reports.
A learning project, not investment advice.</div></footer>
<script>{JS.replace('__DATA__', json.dumps(payload))}</script>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # write the page
    # returns nothing; writes Yield_Curve/sovereign_spreads.html (~35 KB; ECharts is loaded from the jsDelivr CDN)
    return None


if __name__ == "__main__":
    main()
