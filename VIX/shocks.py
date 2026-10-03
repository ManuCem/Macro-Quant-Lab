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

Output: VIX/output/shocks.html (one tab per shock + a dashboard tab).
Reuses the data helpers from volatility.py so both scripts measure the same way.
"""

from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

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
# 2. Charts
# --------------------------------------------------------------------------

def style_axes(fig, **kwargs):
    """Shared look: recessive grid, light axes, system font."""
    fig.update_layout(
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif",
                  color=INK_2, size=12),
        margin=dict(l=56, r=16, t=40, b=40),
        legend=dict(orientation="h", y=1.12, x=0),
        hovermode="x unified",
        **kwargs,
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)


def shock_figure(window, event):
    """Top: VIX vs realized vol. Bottom: the gap, coloured by its sign."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.66, 0.34], vertical_spacing=0.06)

    # Solid line = VIX (what the market expected); dashed = what happened.
    fig.add_trace(go.Scatter(
        x=window.index, y=window["vix"], name="VIX (expected)",
        line=dict(color=event["color"], width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=window.index, y=window["realized"],
        name=f"Realized, next {FORWARD_HORIZON}d (actual)",
        line=dict(color=event["color"], width=2, dash="dash")), row=1, col=1)

    # Bottom panel: blue bar = VIX too high, red bar = VIX too low.
    bar_colors = np.where(window["gap"] >= 0, OVER_COLOR, UNDER_COLOR)
    fig.add_trace(go.Bar(
        x=window.index, y=window["gap"], marker_color=bar_colors,
        name="Gap (VIX - realized)", showlegend=False), row=2, col=1)

    # Phase shading + the day-0 marker, drawn across both panels.
    day0 = window.index[window["event_day"] == 0][0]
    fig.add_vrect(x0=window.index[0], x1=day0, fillcolor=MUTED, opacity=0.10,
                  line_width=0, layer="below")
    fig.add_vline(x=day0, line=dict(color=INK, width=1.5, dash="dot"))
    for label, x in [("Pre-shock", window.index[PRE_DAYS // 2]),
                     ("Day 0", day0),
                     ("Aftermath", window.index[PRE_DAYS + POST_DAYS // 2])]:
        fig.add_annotation(x=x, y=1.0, yref="paper", text=label, showarrow=False,
                           yanchor="bottom", font=dict(color=INK_2, size=12))

    style_axes(fig, height=520)
    fig.update_yaxes(title_text="Annualized vol (%)", row=1, col=1)
    fig.update_yaxes(title_text="VIX - realized (pts)", row=2, col=1)
    return fig


def dashboard_figures(windows):
    """Four shocks overlaid on one 'days since day 0' axis."""
    # A) VIX and realized side by side (same y range so they can be compared)
    levels = make_subplots(rows=1, cols=2, shared_yaxes=True,
                           subplot_titles=("VIX (expected)",
                                           f"Realized, next {FORWARD_HORIZON}d (actual)"))
    gap = go.Figure()
    sp = go.Figure()

    for event, window in windows:
        common = dict(x=window["event_day"], legendgroup=event["key"],
                      line=dict(color=event["color"], width=2))
        levels.add_trace(go.Scatter(y=window["vix"], name=event["name"], **common),
                         row=1, col=1)
        levels.add_trace(go.Scatter(y=window["realized"], showlegend=False, **common),
                         row=1, col=2)
        gap.add_trace(go.Scatter(y=window["gap"], name=event["name"], **common))

        # S&P indexed to 100 on the day before the shock, so different index
        # levels (1,400 in 2000 vs 5,000+ in 2025) become comparable.
        base = window.loc[window["event_day"] == -1, "sp500"].iloc[0]
        sp.add_trace(go.Scatter(y=window["sp500"] / base * 100,
                                name=event["name"], **common))

    style_axes(levels, height=420)
    # This chart has subplot titles, so lift the legend above them.
    levels.update_layout(margin=dict(l=56, r=16, t=80, b=40),
                         legend=dict(orientation="h", y=1.2, x=0))
    levels.update_yaxes(title_text="Annualized vol (%)", col=1)
    levels.update_xaxes(title_text="Trading days since day 0")

    style_axes(gap, height=380)
    gap.add_hline(y=0, line=dict(color=INK, width=1))
    gap.update_yaxes(title_text="VIX - realized (pts)")
    gap.update_xaxes(title_text="Trading days since day 0")
    gap.add_annotation(xref="paper", yref="paper", x=1, y=1.0, xanchor="right",
                       yanchor="bottom", showarrow=False, font=dict(color=MUTED),
                       text="above 0: VIX overpriced  |  below 0: underestimated")

    style_axes(sp, height=380)
    sp.add_hline(y=100, line=dict(color=AXIS, width=1))
    sp.update_yaxes(title_text="S&P 500 (day -1 = 100)")
    sp.update_xaxes(title_text="Trading days since day 0")

    for fig in (levels, gap, sp):
        fig.add_vline(x=0, line=dict(color=INK, width=1.5, dash="dot"))
    return levels, gap, sp


def to_div(fig):
    """Plotly figure -> an HTML <div>; plotly.js itself is embedded only once."""
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"responsive": True, "displaylogo": False})


# --------------------------------------------------------------------------
# 3. HTML page
# --------------------------------------------------------------------------

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
  // Plotly charts drawn inside a hidden panel have no size; fix on show.
  document.querySelectorAll('#' + id + ' .plotly-graph-div')
    .forEach(g => Plotly.Plots.resize(g));
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
  {to_div(shock_figure(window, event))}
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

    levels, gap, sp = dashboard_figures(windows)
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
  {to_div(levels)}
  {to_div(gap)}
  {to_div(sp)}
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
<script>{get_plotlyjs()}</script>
</head><body><main>
<h1>VIX vs what actually happened, around four market shocks</h1>
<p class="sub">{PRE_DAYS} trading days before day 0, day 0, and {POST_DAYS} days
after. S&amp;P 500 and VIX data from Yahoo Finance.</p>
<div class="tabs" role="tablist">{buttons}</div>
{panels}
<script>{JS}showTab('{windows[0][0]['key']}');</script>
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
