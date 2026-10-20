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

CSS = """
:root{color-scheme:light dark;--page:#fbfaf7;--surface:#ffffff;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
  --fr:#2a78d6;--it:#1baf7a;--de:#52514e;--accent:#eb6834}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#9a988f;
  --grid:#2c2c2a;--axis:#4a4a46;--fr:#5b9be6;--it:#2fc48f;--de:#b5b3aa}}
:root[data-theme=dark]{--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#9a988f;--grid:#2c2c2a;--axis:#4a4a46;--fr:#5b9be6;--it:#2fc48f;--de:#b5b3aa}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1000px;margin:0 auto;padding:16px max(16px,env(safe-area-inset-right)) 40px max(16px,env(safe-area-inset-left))}
h1{font-size:1.45rem;line-height:1.25;margin:.4rem 0}
h2{font-size:1.1rem;margin:2rem 0 .4rem}
h3{font-size:1rem;margin:1rem 0 .3rem}
p{margin:.4rem 0 .8rem}
.sub{color:var(--ink-2)}
a{color:var(--fr)}
a.back{display:inline-flex;align-items:center;min-height:44px;text-decoration:none}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--surface);border:1px solid var(--grid);border-radius:10px;padding:10px 12px}
.tile b{display:block;font-size:1.35rem}
.tile span{color:var(--muted);font-size:.85rem}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
.chart{width:100%;height:420px;background:var(--surface);border:1px solid var(--grid);border-radius:10px}
.chart.short{height:260px}
.note{color:var(--muted);font-size:.85rem}
.read{background:var(--surface);border-left:4px solid var(--accent);border-radius:6px;padding:10px 14px;margin:12px 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--surface);border:1px solid var(--grid);border-top:4px solid var(--c);border-radius:10px;padding:4px 16px 10px}
.card ul{padding-left:1.1rem;margin:.3rem 0}
.card li{margin:.3rem 0}
details{margin-top:1.5rem}summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--ink-2)}
.scroll{overflow-x:auto;border:1px solid var(--grid);border-radius:10px}
table{border-collapse:collapse;width:100%;background:var(--surface);font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--surface)}
.sources li{margin:.2rem 0}
.sources a{display:inline-block;padding:11px 0;margin:-5px 0}
ul.sources{padding-left:1.1rem}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--grid);color:var(--muted);font-size:.85rem}
@media (max-width:640px){th{white-space:normal}th,td{padding:8px 6px}.cols{grid-template-columns:1fr}.chart{height:480px}.chart.short{height:300px}h1{font-size:1.25rem}}
"""

JS = """
const DATA = __DATA__;                                          // everything Python computed, as JSON
const narrowMQ = window.matchMedia("(max-width: 640px)");       // true on a phone-width screen
const isTouch = window.matchMedia("(pointer: coarse)").matches; // a finger instead of a mouse
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();  // read a colour token
const INSTANCES = {};                                           // chart div id -> ECharts instance

function base(narrow) {                                         // options shared by every chart
  return {
    animation: false, backgroundColor: "transparent", textStyle: {color: css("--ink-2")},
    legend: narrow ? {bottom: 4, left: 12, orient: "vertical", textStyle: {color: css("--ink-2")}}   // below the plot on a phone
                   : {top: 6, right: 16, textStyle: {color: css("--ink-2")}},  // top right, clear of the y-axis title
    tooltip: {trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click", confine: true},     // tap on touch screens
  };
}
const ax = extra => Object.assign({axisLine: {lineStyle: {color: css("--axis")}}, splitLine: {lineStyle: {color: css("--grid")}},
                                   axisLabel: {color: css("--muted"), hideOverlap: true}}, extra);
function zoom(narrow, startYear) {                              // slider under the plot; drag-zoom only with a mouse
  const start = startYear ? DATA.dates.findIndex(d => d >= startYear) / DATA.dates.length * 100 : 0;
  const z = [{type: "slider", start, end: 100, height: 22, bottom: narrow ? 92 : 8, borderColor: css("--grid"),
              textStyle: {color: css("--muted")}, labelFormatter: v => new Date(v).getFullYear()}];
  if (!isTouch) z.push({type: "inside", start, end: 100});      // wheel / drag zoom would trap the finger on a phone
  return z;
}
const pts = key => DATA.dates.map((d, i) => [d, DATA[key][i]]); // [[date, value], ...] for a time axis

function spreads(narrow) {                                      // France and Italy premium over Germany since 1999
  const o = base(narrow);
  o.grid = narrow ? {left: 44, right: 16, top: 56, bottom: 130} : {left: 56, right: 28, top: 60, bottom: 54};
  o.xAxis = ax({type: "time"});
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
    itemStyle: {color: css("--ink-2")}, tooltip: {trigger: "item", formatter: p => p.name + " " + p.value[0] + ": " + p.value[1] + " bp (press report)"}});
  o.tooltip.valueFormatter = v => v == null ? "-" : Math.round(v) + " bp";
  return o;
}

function gap(narrow) {                                          // Italy minus France: who pays more?
  const o = base(narrow);
  o.legend = {show: false};                                     // a single series: the title and the note name it
  o.grid = narrow ? {left: 44, right: 16, top: 16, bottom: 44} : {left: 56, right: 24, top: 20, bottom: 54};
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
  o.xAxis = ax({type: "value", name: "", axisLabel: {color: css("--muted"), formatter: "{value} bp"}});
  o.yAxis = ax({type: "category", data: DATA.cds.map(r => r.country), axisLabel: {color: css("--ink"), fontSize: 13}, splitLine: {show: false}});
  const color = c => c === "France" ? css("--fr") : c === "Italy" ? css("--it") : css("--de");
  o.series = [{type: "bar", barWidth: "52%", data: DATA.cds.map(r => ({value: r.cds_bp, itemStyle: {color: color(r.country), borderRadius: [0, 4, 4, 0]}})),
    label: {show: true, position: "right", color: css("--ink-2"),
            formatter: p => { const r = DATA.cds[p.dataIndex]; return narrow ? r.cds_bp + " bp" : r.cds_bp + " bp  ~" + r.default_prob.toFixed(2) + "%/yr"; }}}];
  o.tooltip = {trigger: "item", triggerOn: isTouch ? "click" : "mousemove|click", confine: true,
    formatter: p => { const r = DATA.cds[p.dataIndex]; return r.country + ": " + r.cds_bp + " bp (" + r.date + ")<br>implied default risk ~" +
      r.default_prob.toFixed(2) + "% per year<br>" + r.vs_germany + "x Germany's premium"; }};
  return o;
}

const BUILDERS = {spreads, gap, cds};                   // chart div id -> function that builds its options
function drawAll() {                                            // (re)build every chart; called on load, rotation and theme change
  const narrow = narrowMQ.matches;
  document.querySelectorAll(".chart").forEach(div => {
    if (!INSTANCES[div.id]) INSTANCES[div.id] = echarts.init(div);
    INSTANCES[div.id].setOption(BUILDERS[div.id](narrow), true);
    INSTANCES[div.id].resize();
  });
}
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
SOURCES = [                               # (label, link) for every news fact on the page
    ("ECB data portal: 10-year yields (IRS)", "https://data.ecb.europa.eu/data/datasets/IRS"),
    ("Bloomberg, 20 Oct 2026: French spread hits 150 bp",
     "https://www.bloomberg.com/news/articles/2026-10-20/french-bond-risk-gauge-hits-150-basis-points-after-protests"),
    ("Fortune, 17 Oct 2026: France 'on the brink'",
     "https://fortune.com/2026/10/17/france-debt-crisis-budget-deficit-bond-yields-spread-protests-riots/"),
    ("Fortune, 2 Oct 2026: French CDS at 81 bp",
     "https://fortune.com/2026/10/02/france-debt-crisis-bond-investors-odds-sovereign-default-cds-yield-spread-deficit-presidential-race/"),
    ("Al Jazeera, 17 Oct 2026: cost-of-living protests",
     "https://www.aljazeera.com/news/2026/10/17/cost-of-living-protests-hit-belgium-italy-portugal-and-france"),
    ("Anadolu, 18 Oct 2026: Italy riots",
     "https://www.anews.com.tr/europe/2026/10/18/28-arrested-141-officers-injured-as-cost-of-living-protests-turn-violent-in-italy"),
    ("Il Post, 16 Oct 2026: truckers' strike in the South", "https://www.ilpost.it/2026/10/16/proteste-autotrasportatori-sud-italia/"),
    ("countryeconomy.com: Italy spread", "https://countryeconomy.com/risk-premium/italy"),
] + [(f"{r['source']}: {r['country']} CDS", r["url"]) for r in CDS_SNAPSHOT]  # plus the three CDS quotes


def tile(value, label, color=None):
    """One small stat box; an optional coloured dot names the country."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # identity is in the text too, never colour alone
    # returns a str of HTML, e.g. '<div class="tile"><b><i class="dot" ...></i>154 bp</b><span>France over Germany (20 Oct)</span></div>'
    return f'<div class="tile"><b>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def country_card(country, color):
    """One card: the country's problem, protests and market reaction as a short list."""
    items = "".join(f"<li>{item}</li>" for item in COUNTRY_CARDS[country])   # our own text, already safe HTML
    # returns a str of HTML, e.g. '<div class="card" style="--c:var(--fr)"><h3>...France</h3><ul><li>...</li> x3</ul></div>'
    return (f'<div class="card" style="--c:var({color})"><h3><i class="dot" style="background:var({color})"></i>'
            f'{country}</h3><ul>{items}</ul></div>')


def recent_table(data):
    """HTML table of the last 6 months: the three spreads."""
    rows = "".join(                                            # newest month first
        f"<tr><td>{d.strftime('%b %Y')}</td><td>{r['fr_de']:.0f}</td><td>{r['it_de']:.0f}</td><td>{r['it_fr']:+.0f}</td></tr>"
        for d, r in data.tail(6).iloc[::-1].iterrows())
    head = "<tr><th>Month</th><th>France vs DE</th><th>Italy vs DE</th><th>Italy vs FR</th></tr>"   # short headers so it fits a phone
    # returns a str of HTML: a header and 6 rows, e.g. <tr><td>Sep 2026</td><td>97</td><td>89</td><td>-8</td></tr>
    return f'<div class="scroll"><table>{head}{rows}</table></div>'


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
    fr_cds = cds.set_index("country").loc["France"]            # France's row of the CDS table
    it_cds = cds.set_index("country").loc["Italy"]             # Italy's row
    tiles = "".join([                                          # the four headline numbers
        tile(f"{LATEST_DAILY[0]['spread_bp']} bp", "France over Germany (20 Oct)", "--fr"),
        tile(f"{LATEST_DAILY[1]['spread_bp']} bp", "Italy over Germany (16 Oct)", "--it"),
        tile(f"{fr_cds['cds_bp']:.1f} bp", f"France 5y CDS: ~{fr_cds['default_prob']:.1f}% default risk/yr", "--fr"),
        tile(f"{it_cds['cds_bp']:.1f} bp", f"Italy 5y CDS: ~{it_cds['default_prob']:.1f}% default risk/yr", "--it"),
    ])
    events = " · ".join(f"<b>{label}</b> {escape(text)}" for _, label, text in EVENTS)   # one compact line of event keys
    sources = "".join(f'<li><a href="{escape(url)}">{escape(label)}</a></li>' for label, url in SOURCES)  # links, folded away
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>France &amp; Italy Risk Premium</title>
<style>{CSS}</style>
<script src="{ECHARTS_URL}"></script>
</head><body><main>
<a class="back" href="../index.html">&larr; Macro Quant Lab</a>
<h1>France vs Italy: the price of risk</h1>
<div class="read"><b>The point:</b> Italy used to be the risky one. Now France pays as much or more. Its premium over
Germany is back at the 2011 euro-crisis record (~{LATEST_DAILY[0]['spread_bp']} bp), and insuring French debt costs
more than insuring Italian debt.</div>
<div class="tiles">{tiles}</div>

<h2>Premium over Germany, 10-year bonds</h2>
<div class="chart" id="spreads" role="img" aria-label="France and Italy 10-year spreads over Germany since 1999"></div>
<p class="note">{events} Monthly ECB averages; diamonds = latest daily close. 100 bp = 1 percentage point.</p>

<h2>Who pays more?</h2>
<p>Italy's yield minus France's. <b>Blue bars below zero = France pays more</b>: {s['flip_last12']} of the last 12 months.</p>
<div class="chart short" id="gap" role="img" aria-label="Italy's yield minus France's yield"></div>

<h2>CDS: the price of default insurance</h2>
<p>Default risk per year ≈ CDS ÷ (1 − 40% recovery). France: {fr_cds['cds_bp']} bp → ~{fr_cds['default_prob']:.2f}%.</p>
<div class="chart short" id="cds" role="img" aria-label="5-year CDS premiums for Germany, Italy and France"></div>
<p class="note">Latest press quotes from different days (there is no free CDS feed). Germany's is from July.</p>

<h2>Why, and the October protests</h2>
<div class="cols">{country_card("France", "--fr")}{country_card("Italy", "--it")}</div>

<h2>Last 6 months (bp)</h2>
{recent_table(data)}

<details><summary>Sources</summary><ul class="note sources">{sources}</ul></details>
<footer>Built by <code>Yield_Curve/sovereign_spreads.py</code>. A learning project, not investment advice.</footer>
<script>{JS.replace('__DATA__', json.dumps(payload))}</script>
</main></body></html>"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # write the page
    # returns nothing; writes Yield_Curve/sovereign_spreads.html (~30 KB; ECharts is loaded from the jsDelivr CDN)
    return None


if __name__ == "__main__":
    main()
