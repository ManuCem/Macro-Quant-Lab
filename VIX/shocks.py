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
"""

import json
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from volatility import (
    FORWARD_HORIZON,
    PERIOD,
    TICKER,
    VIX_TICKER,
    compute_log_returns,
    fetch_prices,
    forward_realized_volatility,
)

OUTPUT_PATH = Path(__file__).parent / "output" / "shocks.html"
# Apache ECharts, reused from the ecb/ folder; embedded in the page so it stays one standalone file.
ECHARTS_PATH = Path(__file__).parent.parent / "ecb" / "lib" / "echarts.js"

PRE_DAYS = 40    # trading days shown before day 0 (~2 months of "before")
POST_DAYS = 60   # trading days shown after day 0 (~3 months of "after")
TOLERANCE = 2.0  # |gap| under this many vol points counts as "about right"

# Day 0 = the first big panic day of each shock (not necessarily the worst day,
# so the pre-shock window stays genuinely calm). Each date was checked against
# the data: worst S&P day / biggest one-day VIX jump of the episode.
EVENTS = [
    {
        "key": "dotcom", "name": "Dot-com crash", "day0": "2000-04-14",
        "why": "Worst S&P 500 day of the 2000 sell-off, and the VIX peak of "
               "that spring. The bubble deflated slowly: this is the "
               "sharpest day inside a ~2.5-year decline that only bottomed "
               "in Oct 2002 (see the day 0 to lowest point tile).",
        "color": "#2a78d6",  # blue   - categorical slot 1
    },
    {
        "key": "gfc", "name": "2008 financial crisis", "day0": "2008-09-15",
        "why": "Lehman Brothers files for bankruptcy. Worse S&P days came "
               "later (Oct 2008), but this is the trigger, so the 40 days "
               "before it are still relatively calm.",
        "color": "#eb6834",  # orange - slot 2
    },
    {
        "key": "covid", "name": "Covid crash", "day0": "2020-02-24",
        "why": "First big panic day after the outbreak in Italy: the biggest "
               "one-day VIX jump of the episode. The worst S&P day (16 Mar) "
               "came three weeks later.",
        "color": "#1baf7a",  # aqua   - slot 3
    },
    {
        "key": "tariffs", "name": "2025 tariff shock", "day0": "2025-04-03",
        "why": "First trading day after the 'Liberation Day' tariff "
               "announcement (made after the close on 2 Apr). The S&P fell "
               "~5% and the VIX jumped ~40%.",
        "color": "#eda100",  # yellow - slot 4
    },
]

# Chart ink / surface colours (light theme), from the reference palette.
SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
OVER_COLOR, UNDER_COLOR = "#2a78d6", "#e34948"  # diverging pair: blue / red

PHASES = ["Pre-shock", "Day 0", "Aftermath"]


# --------------------------------------------------------------------------
# 1. Data
# --------------------------------------------------------------------------

def build_dataset():
    """One table: S&P close, VIX and forward realized vol on the same dates."""
    prices = fetch_prices(TICKER, PERIOD)
    log_returns = compute_log_returns(prices)
    vix = fetch_prices(VIX_TICKER, PERIOD)
    forward_vol = forward_realized_volatility(log_returns, FORWARD_HORIZON)

    data = pd.DataFrame({"sp500": prices, "vix": vix, "realized": forward_vol})
    # Keep every day that has both prices; `realized` is NaN for the last 21
    # days (their future isn't known yet) -- irrelevant for historical events.
    data = data.dropna(subset=["sp500", "vix"])
    # Save a copy as CSV next to this script (VIX/csv/data.csv). to_csv creates
    # the file but not the folder, so make the folder first.
    csv_path = Path(__file__).parent / "csv" / "data.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(csv_path)
    return data


def slice_event(data, day0):
    """Cut out [day0 - PRE_DAYS, day0 + POST_DAYS] and label each row."""
    # Position of day 0 in the table: counting TRADING days (rows) instead of
    # calendar days keeps weekends/holidays from distorting the windows.
    position0 = data.index.get_loc(pd.Timestamp(day0))
    window = data.iloc[position0 - PRE_DAYS: position0 + POST_DAYS + 1].copy()

    # event_day: -40 ... -1, 0, 1 ... 60  (0 = the shock day)
    window["event_day"] = np.arange(-PRE_DAYS, -PRE_DAYS + len(window))
    window["phase"] = np.select(
        [window["event_day"] < 0, window["event_day"] == 0],
        ["Pre-shock", "Day 0"],
        default="Aftermath",
    )
    # gap > 0: VIX above what happened (overpriced); gap < 0: underestimated
    window["gap"] = window["vix"] - window["realized"]

    return window


def verdict(gap):
    """Turn an average gap into a plain-words label."""
    if gap > TOLERANCE:
        return "VIX overreacted"
    if gap < -TOLERANCE:
        return "VIX underestimated"
    return "About right"


def phase_table(window):
    """Average VIX, realized vol and gap inside each phase."""
    rows = []
    for phase in PHASES:
        part = window[window["phase"] == phase]
        rows.append({
            "phase": phase,
            "days": len(part),
            "vix": part["vix"].mean(),
            "realized": part["realized"].mean(),
            "gap": part["gap"].mean(),
        })

    return rows


def key_facts(window):
    """Headline numbers for one shock."""
    day0 = window[window["event_day"] == 0].iloc[0]
    prev_close = window.loc[window["event_day"] == -1, "sp500"].iloc[0]
    after = window[window["event_day"] >= 0]

    vix_peak_date = after["vix"].idxmax()
    return {
        "day0_date": window.index[window["event_day"] == 0][0],
        "sp_day0_return": (day0["sp500"] / prev_close - 1) * 100,
        "vix_day0": day0["vix"],
        "vix_peak": after["vix"].max(),
        "vix_peak_day": int(window.loc[vix_peak_date, "event_day"]),
        "realized_peak": after["realized"].max(),
    }


def shock_low(data, day0):
    """S&P 500 fall from the day-0 close to the lowest point of the shock.

    The shock "ends" when the index first regains its all-time high from
    before day 0 (or at the end of the data if it hasn't yet); the low is the
    lowest close in between. Using the old high, not the day-0 close, stops a
    one-day bounce from ending the shock early. This looks at ALL the data, not
    just the 60-day window, so slow bears like 2000-02 and 2008-09 reach their
    true bottom.
    """
    day0 = pd.Timestamp(day0)
    previous_high = data["sp500"].loc[:day0].iloc[:-1].max()  # high before day 0
    closes = data["sp500"].loc[day0:]
    start = closes.iloc[0]                       # day-0 close
    back_at_high = closes.iloc[1:] >= previous_high  # True once the high is regained
    recovered = bool(back_at_high.any())
    end = back_at_high.idxmax() if recovered else closes.index[-1]
    span = closes.loc[:end]                      # day 0 -> recovery
    low_date = span.idxmin()
    return {
        "low_date": low_date,
        "fall": (span.min() / start - 1) * 100,  # % fall, day 0 close -> low
        "days_to_low": closes.index.get_loc(low_date),  # trading days after day 0
        "recovery_date": end if recovered else None,
    }


# --------------------------------------------------------------------------
# 2. Charts (Apache ECharts)
# --------------------------------------------------------------------------
# Python only prepares the numbers (as JSON); the charts themselves are built
# in the browser by ECHARTS_JS below, one chart per <div class="chart">.

def chart_data(windows):
    """Everything the browser needs to draw the charts, as plain lists."""
    def clean(series):
        # NaN is not valid JSON, so use None (-> null). Round to keep the file small.
        return [None if pd.isna(v) else round(float(v), 2) for v in series]

    events = []
    for event, window in windows:
        # S&P indexed to 100 on the day before the shock, so different index
        # levels (1,400 in 2000 vs 5,000+ in 2025) become comparable.
        base = window.loc[window["event_day"] == -1, "sp500"].iloc[0]
        events.append({
            "key": event["key"], "name": event["name"], "color": event["color"],
            "dates": [f"{d:%Y-%m-%d}" for d in window.index],
            "day0": f"{window.index[window['event_day'] == 0][0]:%Y-%m-%d}",
            "event_day": [int(v) for v in window["event_day"]],
            "vix": clean(window["vix"]),
            "realized": clean(window["realized"]),
            "gap": clean(window["gap"]),
            "sp_index": clean(window["sp500"] / base * 100),
        })
    return {
        "events": events, "horizon": FORWARD_HORIZON, "pre_days": PRE_DAYS,
        "colors": {"ink": INK, "ink2": INK_2, "muted": MUTED, "grid": GRID,
                   "axis": AXIS, "over": OVER_COLOR, "under": UNDER_COLOR},
    }


def chart_div(chart_id, height):
    """Empty box; ECHARTS_JS draws the chart into it the first time its tab is shown."""
    return f'<div class="chart" id="{chart_id}" style="height:{height}px"></div>'


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


def fmt(value, signed=False, suffix=""):
    return f"{value:+.1f}{suffix}" if signed else f"{value:.1f}{suffix}"


def tile(value, label):
    return f'<div class="tile"><div class="v">{value}</div><div class="l">{escape(label)}</div></div>'


def phase_table_html(rows):
    body = "".join(
        f"<tr><td>{r['phase']}</td><td>{r['days']}</td><td>{fmt(r['vix'])}</td>"
        f"<td>{fmt(r['realized'])}</td><td>{fmt(r['gap'], signed=True)}</td>"
        f"<td>{verdict(r['gap'])}</td></tr>"
        for r in rows)
    return ('<div class="tablewrap"><table><tr><th>Phase</th><th>Days</th>'
            '<th>Avg VIX</th><th>Avg realized</th><th>VIX - realized</th>'
            f'<th>Verdict</th></tr>{body}</table></div>')


def shock_panel(event, window):
    facts = key_facts(window)
    low = event["low"]  # day 0 -> lowest point, computed on the full history
    tiles = "".join([
        tile(fmt(facts["sp_day0_return"], True, "%"), "S&P 500 on day 0"),
        tile(fmt(facts["vix_day0"]), "VIX on day 0"),
        tile(fmt(facts["vix_peak"]), f"VIX peak (day {facts['vix_peak_day']})"),
        tile(fmt(facts["realized_peak"]), "Peak realized vol after day 0"),
        tile(fmt(low["fall"], True, "%"),
             f"S&P day 0 to lowest point ({low['low_date']:%d %b %Y}, "
             f"{low['days_to_low']} trading days later)"),
    ])
    return f"""
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


def dashboard_panel(windows):
    # One summary row per shock, pulling the phase averages together.
    rows = ""
    for event, window in windows:
        phases = {r["phase"]: r for r in phase_table(window)}
        facts = key_facts(window)
        rows += (
            f'<tr><td><span class="sw" style="background:{event["color"]}"></span>'
            f'{escape(event["name"])}</td>'
            f'<td>{facts["day0_date"]:%d %b %Y}</td>'
            f'<td>{fmt(facts["sp_day0_return"], True, "%")}</td>'
            f'<td>{fmt(phases["Pre-shock"]["gap"], True)}</td>'
            f'<td>{fmt(phases["Day 0"]["gap"], True)}</td>'
            f'<td>{fmt(phases["Aftermath"]["gap"], True)}</td>'
            f'<td>{fmt(facts["vix_peak"])} (day {facts["vix_peak_day"]})</td>'
            f'<td>{fmt(facts["realized_peak"])}</td>'
            f'<td>{fmt(event["low"]["fall"], True, "%")} '
            f'({event["low"]["low_date"]:%b %Y})</td></tr>')

    return f"""
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


def build_page(windows):
    buttons = "".join(
        f'<button data-tab="{e["key"]}" style="--tab-color:{e["color"]}" '
        f'role="tab">{escape(e["name"])}</button>' for e, _ in windows)
    buttons += '<button data-tab="dashboard" role="tab">Dashboard</button>'
    panels = "".join(shock_panel(e, w) for e, w in windows) + dashboard_panel(windows)
    return f"""<!doctype html>
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


# --------------------------------------------------------------------------
# 4. Run
# --------------------------------------------------------------------------

def main():
    data = build_dataset()
    for event in EVENTS:
        event["low"] = shock_low(data, event["day0"])  # needs the full history
    windows = [(event, slice_event(data, event["day0"])) for event in EVENTS]

    # Print the numbers too, so the result can be checked without the browser.
    for event, window in windows:
        print(f"\n{event['name']} (day 0 = {event['day0']})")
        low = event["low"]
        recovery = (f"{low['recovery_date']:%Y-%m-%d}" if low["recovery_date"] is not None
                    else "not yet")
        print(f"  S&P day 0 -> lowest point: {low['fall']:+.1f}% on {low['low_date']:%Y-%m-%d} "
              f"({low['days_to_low']} trading days later); old high regained: {recovery}")
        for row in phase_table(window):
            print(f"  {row['phase']:<10} days={row['days']:>2}  "
                  f"VIX={row['vix']:5.1f}  realized={row['realized']:5.1f}  "
                  f"gap={row['gap']:+6.1f}  -> {verdict(row['gap'])}")

    OUTPUT_PATH.write_text(build_page(windows), encoding="utf-8")
    print(f"\nDashboard saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
