"""
Five minimalist designs for the "Nasdaq 100 vs bond yields" page
----------------------------------------------------------------
Same question, same data and same four charts as nasdaq-bonds/nasdaq_bonds.py. Only the layout,
the colours and the text change (the text is much shorter), so the designs can be compared side by side.

Data: reuses the calculations of nasdaq_bonds.py on its saved CSV (nasdaq-bonds/csv/nasdaq_bonds.csv),
so nothing is downloaded and every option shows identical numbers. Run nasdaq_bonds.py first to refresh the data.

Output: five pages next to this script:
    option_1_swiss.html  option_2_serif.html  option_3_lab.html  option_4_dashboard.html  option_5_statement.html

Run:
    python Nasdaq100Bonds_options/build_options.py

Layout of this file (see CLAUDE.md):
    1. python / data code  -> load, calculate, short texts, and def main()
    2. html / chart code   -> shared pieces + one function per design

Not investment advice.
"""

import json                               # turns Python lists/dicts into text the browser's JavaScript can read
import sys                                # lets us add the nasdaq-bonds folder to the import path
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import pandas as pd                       # tables (DataFrames) and time series

HERE = Path(__file__).parent                                   # this folder: Nasdaq100Bonds_options
sys.path.insert(0, str(HERE.parent / "nasdaq-bonds"))          # so "import nasdaq_bonds" finds the original script
import nasdaq_bonds as nb                 # the original page: its calculations, chart JavaScript and helpers  # noqa: E402

pct = nb.pct                              # signed number with a real minus sign, e.g. pct(-3.6) -> '−3.6'


# ===========================================================================
# python / data code
# ===========================================================================

def load_closes():
    """Read the daily closes that nasdaq_bonds.py saved, instead of downloading them again."""
    table = pd.read_csv(nb.CSV_PATH, index_col="Date", parse_dates=True)   # closes + daily moves, one row per day
    closes = table[["nasdaq", "y10", "bonds"]]                 # keep only the three closing prices
    # returns a DataFrame, one row per trading day (1,506 rows x 3 columns, 30 Oct 2020 - 29 Oct 2026):
    #                 nasdaq    y10     bonds
    # Date
    # 2026-10-27  29651.4395  4.993   81.6300
    # 2026-10-28  29813.1602  5.045   80.9900
    # 2026-10-29  29402.5098  4.989   81.4900
    return closes


def analyse(closes):
    """Run every calculation of the original page, in the same order."""
    moves = nb.daily_moves(closes)                             # daily % moves and yield changes in bp
    roll = nb.rolling_correlations(moves)                      # 60- and 20-day rolling correlation, 5 years
    results = {
        "closes": closes,                                      # the three daily closes
        "moves": moves,                                        # the daily moves
        "roll": roll,                                          # the rolling correlations
        "stats": nb.window_stats(closes, moves),               # correlations and performance for 20 days, 60 days, 1 year
        "history": nb.regime_history(roll),                    # 5-year facts about the 60-day correlation
        "rotation": nb.rotation_days(moves),                   # the four kinds of day over the last 20
        "biggest": nb.biggest_days(moves),                     # the 8 biggest Nasdaq days of the last 60
    }
    # returns a dict of 7 items: 3 DataFrames (closes, moves, roll), the stats DataFrame, 2 dicts and the biggest-days DataFrame, e.g.
    # {'closes': <1506 x 3>, 'moves': <1505 x 3>, 'roll': <1255 x 2>, 'stats': <3 x 9>,
    #  'history': {'start': 'Oct 2021', 'share_positive': 42.9, ..., 'last_date': '29 Oct 2026'},
    #  'rotation': {'days': 20, 'counts': {'Into tech': 5, 'Into bonds': 9, 'Both up': 4, 'Both down': 2}, ...},
    #  'biggest': <8 x 4>}
    return results


def chart_payload(r):
    """The numbers the charts need, in the exact shape the original page's JavaScript expects."""
    recent = r["closes"].tail(nb.PERF_DAYS + 1)                # 1 year of closes for the performance charts
    scatter_moves = r["moves"].tail(nb.SCATTER_DAYS)           # the 60 days shown in the scatter plot
    payload = {
        "perf": {"dates": [d.strftime("%Y-%m-%d") for d in recent.index],                          # 253 dates
                 **{k: [round(float(v), 3) for v in recent[k]] for k in ["nasdaq", "bonds", "y10"]}},  # 253 closes each
        "roll": {"dates": [d.strftime("%Y-%m-%d") for d in r["roll"].index],                       # 1,255 dates
                 **{k: [round(float(v), 3) for v in r["roll"][k]] for k in ["corr60", "corr20"]}},
        "scatter": {"dates": [d.strftime("%d %b %Y") for d in scatter_moves.index],               # 60 dates
                    **{k: [round(float(v), 2) for v in scatter_moves[k]] for k in ["y10_bp", "nasdaq"]}},
        "recentDays": nb.ROLL_SHORT,                           # the last 20 dots are highlighted
        "slope20": float(r["stats"].iloc[0]["per_10bp"]) / 10, # Nasdaq % per 1 bp of yield, last 20 days
        "threshold": nb.LINK_THRESHOLD,                        # where the shaded regime zones start (0.2)
    }
    # returns a dict of 6 keys (about 3,500 numbers), e.g.
    # {'perf': {'dates': ['2025-10-27', ...], 'nasdaq': [24502.1, ...], 'bonds': [...], 'y10': [...]},
    #  'roll': {'dates': [...], 'corr60': [...], 'corr20': [...]}, 'scatter': {...},
    #  'recentDays': 20, 'slope20': 0.14, 'threshold': 0.2}
    return payload


def headlines(r):
    """Short, punchy text written from the numbers, so it stays true after a re-run."""
    s20, s60, s1y = r["stats"].iloc[0], r["stats"].iloc[1], r["stats"].iloc[2]   # the three look-back windows
    h, rot = r["history"], r["rotation"]                       # 5-year facts and last-20-day counts
    verdict = {                                                # one headline per regime of the last 20 days
        "Rotation": "Yes. Money is rotating between tech and bonds.",
        "Rate fear": "No. It is rate fear: yields up, tech down.",
        "No clear link": "No clear link right now.",
    }[s20["regime"]]
    texts = {
        "verdict": verdict,                                    # the answer, in one line
        "verdict_line": (f"Last 20 trading days to {h['last_date']}: Nasdaq moves and 10-year yield changes "
                         f"correlate at {pct(s20['corr_yield'], 2)}."),          # the number behind it
        "perf": f"Nasdaq {pct(s20['nasdaq_pct'])}%, long bonds {pct(s20['bonds_pct'])}% in 20 days.",
        "stories": "Two textbook stories, opposite signs.",
        "roll": f"The link flips. Now {pct(h['latest20'], 2)} over 20 days, {pct(h['latest60'], 2)} over 60.",
        "scatter": f"A +10 bp yield day came with a {pct(s20['per_10bp'], 2)}% Nasdaq move.",
        "cushion": f"Bonds rose on {rot['bonds_up_on_down']} of the {rot['down_days']} days tech fell.",
        "window": (f"20 days {pct(s20['corr_yield'], 2)}, 60 days {pct(s60['corr_yield'], 2)}, "
                   f"1 year {pct(s1y['corr_yield'], 2)}."),
        "press": "October's coverage tells the same story.",
    }
    # returns a dict of 9 short strings (real output, data to 29 Oct 2026), e.g.
    # {'verdict': 'Yes. Money is rotating between tech and bonds.',
    #  'verdict_line': 'Last 20 trading days to 29 Oct 2026: Nasdaq moves and 10-year yield changes correlate at +0.63.',
    #  'perf': 'Nasdaq −3.6%, long bonds +4.9% in 20 days.',
    #  'cushion': 'Bonds rose on 9 of the 11 days tech fell.', ...}
    return texts


def main():
    closes = load_closes()                                     # step 1: read the saved daily closes
    r = analyse(closes)                                        # step 2: run the original calculations
    payload = chart_payload(r)                                 # step 3: numbers for the charts
    texts = headlines(r)                                       # step 4: the short texts
    b = blocks(r, texts)                                       # step 5: HTML pieces shared by every design (code below)
    for name, build in PAGES.items():                          # step 6: one file per design
        (HERE / name).write_text(build(b, texts, payload), encoding="utf-8")   # write the page
        print(f"Saved {HERE / name}")                          # tell the user where it is


# ===========================================================================
# html / chart code
# ===========================================================================

FONTS = "https://fonts.googleapis.com/css2?family="           # Google Fonts address; each design appends its families

# Structure shared by every design: charts, buttons, tables, phone rules. Colours come from each design's tokens.
SHARED_CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink)}
a{color:inherit}
a.back{display:inline-flex;align-items:center;min-height:44px;color:var(--ink-2);text-decoration:none;font-size:14px}
a.back:hover{color:var(--ink)}
.chart{width:100%;height:340px}
.chart.short{height:190px}
.label{margin:18px 0 4px;font-size:13px;font-weight:600;color:var(--ink-2)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle}
.periods{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
.periods button{min-height:44px;min-width:52px;padding:0 12px;border:1px solid var(--grid);border-radius:var(--r,6px);
  background:transparent;color:var(--ink-2);font:inherit;font-size:14px;font-weight:600;cursor:pointer}
.periods button[aria-pressed=true]{background:var(--ink);color:var(--page);border-color:var(--ink)}
.stories{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.story h3{margin:0 0 4px;font-size:17px}
.story p{margin:0;color:var(--ink-2);font-size:15px}
.story .sig{margin-top:8px;font-size:13px;color:var(--muted)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--surface);padding-left:0}
th{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.press{list-style:none;padding:0;margin:0}
.press li{padding:6px 0;border-bottom:1px solid var(--grid)}
.press li:last-child{border-bottom:0}
.press a{display:block;padding:8px 0;text-decoration:none}
.press a:hover b{text-decoration:underline}
.press span{display:block;color:var(--muted);font-size:13px}
@media (max-width:640px){
  .chart{height:420px}.chart.short{height:260px}
  .stories{grid-template-columns:1fr;gap:18px}
  th,td{padding:8px 4px;font-size:13px}th{white-space:normal}
  .metrics td{white-space:normal}.metrics td:first-child,.metrics th:first-child{position:static}
  .days td:last-child{white-space:normal;text-align:left}
}
"""

SECTIONS = [                              # (title, key of the short text in `texts`, keys of the HTML blocks it holds)
    ("Tech vs bonds", "perf", ["perf"]),
    ("Two stories", "stories", ["stories"]),
    ("Who is in charge", "roll", ["roll"]),
    ("Day by day", "scatter", ["scatter"]),
    ("Tech's bad days", "cushion", ["days", "biggest"]),
    ("By window", "window", ["metrics"]),
    ("In the press", "press", ["press"]),
]

PRESS = [                                 # (date, one-line summary, source name, link): the facts the original page cites
    ("15 Oct 2026", "Bonds are the new safe haven as money leaves tech.", "TheStreet Pro",
     "https://pro.thestreet.com/market-commentary/bonds-are-the-new-safe-haven-as-money-rotates-out-of-tech"),
    ("13 Oct 2026", "37% of fund managers would switch to bonds near a 6% 10-year yield.", "BofA survey via roic.ai",
     "https://www.roic.ai/news/bofa-survey-treasury-yields-near-6-would-trigger-shift-from-stocks-to-bonds-10-13-2026"),
]


def kpi(value, label, color=None):
    """One headline number with its label; an optional dot names the asset by its chart colour."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # the label names the asset too
    # returns a str of HTML, e.g. '<div class="kpi"><b><i class="dot" style="background:var(--nq)"></i>−3.6%</b><span>Nasdaq 100, 20 days</span></div>'
    return f'<div class="kpi"><b>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def blocks(r, t):
    """The HTML pieces every design arranges in its own way."""
    s20 = r["stats"].iloc[0]                                   # the last-20-days row drives the headline numbers
    c = r["rotation"]["counts"]                                # the four kinds of day
    y_now = r["closes"]["y10"].iloc[-1]                        # today's 10-year yield, in %
    b = {}
    b["back"] = '<a class="back" href="../index.html">&larr; Macro Quant Lab</a>'
    b["kpis"] = "".join([
        kpi(pct(s20["corr_yield"], 2), f"Correlation, 20 days · {s20['regime']}"),
        kpi(pct(s20["nasdaq_pct"]) + "%", "Nasdaq 100, 20 days", "--nq"),
        kpi(pct(s20["y10_bp"], 0) + " bp", f"10y yield, 20 days · now {y_now:.2f}%", "--y10"),
        kpi(pct(s20["bonds_pct"]) + "%", "Long bonds (TLT), 20 days", "--bd"),
    ])
    b["perf"] = ('<div class="periods" role="group" aria-label="Period">'
                 + "".join(f'<button type="button" data-days="{d}" aria-pressed="{str(d == 63).lower()}">{n}</button>'
                           for n, d in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)])
                 + '</div><div id="perf" class="chart" role="img" aria-label="Nasdaq 100 and long bonds, % change since the start of the period"></div>'
                 '<p class="label">10-year Treasury yield</p>'
                 '<div id="y10" class="chart short" role="img" aria-label="US 10-year Treasury yield over the same period"></div>'
                 '<p class="note"><span class="hint">Hover</span> a chart for daily values. Both start at 0%; yields down = bonds up.</p>')
    b["stories"] = ('<div class="stories">'
                    '<div class="story" style="--c:var(--y10)"><h3>Rate fear</h3><p>Yields up, tech down. '
                    'Future profits are worth less at higher rates.</p><p class="sig">Correlation below 0</p></div>'
                    '<div class="story" style="--c:var(--bd)"><h3>Rotation</h3><p>Tech down, money into bonds, '
                    'yields down. Reversed on good days.</p><p class="sig">Correlation above 0</p></div></div>')
    b["roll"] = ('<div id="roll" class="chart" role="img" aria-label="Rolling correlation, Nasdaq 100 vs 10-year yield, five years"></div>'
                 f'<p class="note">Daily moves, rolling 60 and 20 days. Above +{nb.LINK_THRESHOLD}: rotation. '
                 f'Below &minus;{nb.LINK_THRESHOLD}: rate fear.</p>')
    b["scatter"] = ('<div id="scatter" class="chart" role="img" aria-label="Daily 10-year yield change against Nasdaq 100 move, last 60 days"></div>'
                    '<p class="note">One dot per day, last 60. Right: yield up. Up: Nasdaq up.</p>')
    b["days"] = ('<div class="kpis four">'
                 + kpi(str(c["Into bonds"]), "Into bonds · tech down, bonds up")
                 + kpi(str(c["Into tech"]), "Into tech · tech up, bonds down")
                 + kpi(str(c["Both up"]), "Both up")
                 + kpi(str(c["Both down"]), "Both down") + "</div>")
    b["biggest"] = f'<p class="label">Biggest Nasdaq days, last {nb.SCATTER_DAYS}</p>' + nb.days_table(r["biggest"])
    b["metrics"] = nb.metrics_table(r["stats"])
    b["press"] = ('<ul class="press">' + "".join(
        f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><b>{escape(s)}</b><span>{escape(src)} · {escape(d)}</span></a></li>'
        for d, s, src, u in PRESS) + "</ul>")
    b["footer"] = (f"Data: Yahoo Finance (^NDX, ^TNX, TLT) to {r['history']['last_date']}. "
                   "Correlation is not causation. Not investment advice.")
    # returns a dict of 11 HTML strings: back, kpis, perf, stories, roll, scatter, days, biggest, metrics, press, footer, e.g.
    # {'back': '<a class="back" href="../index.html">&larr; Macro Quant Lab</a>', 'kpis': '<div class="kpi"><b>+0.63</b>...', ...}
    return b


def content(b, keys):
    """Join the blocks of one section."""
    # returns a str of HTML, e.g. content(b, ["days", "biggest"]) -> '<div class="kpis four">...</div><p class="label">Biggest...'
    return "".join(b[k] for k in keys)


def doc(css, fonts, body, payload):
    """Wrap a design's CSS and body into a full page with ECharts and the original chart code."""
    js = nb.JS.replace("__DATA__", json.dumps(payload))        # the original chart code with this page's numbers
    js = js.replace("Rotation zone: tech and yields move together", "Rotation zone")   # short zone labels: the long ones were cut
    js = js.replace("Rate-fear zone: yields up, tech down", "Rate-fear zone")          # off on a phone; the note under the chart explains them
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Nasdaq vs Bond Yields</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}{fonts}&display=swap" rel="stylesheet">
<style>{SHARED_CSS}{css}</style>
<script src="{nb.ECHARTS_URL}"></script>
</head>
<body>
{body}
<script>{js}</script>
</body>
</html>
"""
    # returns a str, one full HTML page (~70 KB, most of it the chart data)
    return html


# ---------------------------------------------------------------------------
# Option 1 · Swiss: white, black rules, one red accent, label column on the left
# ---------------------------------------------------------------------------
SWISS_CSS = """
:root{color-scheme:light dark;--page:#fff;--surface:#fff;--ink:#0a0a0a;--ink-2:#4d4d4d;--muted:#8a8a8a;--grid:#e8e8e8;--axis:#c8c8c8;
  --accent:#d0021b;--nq:#1f5fd6;--bd:#13976b;--y10:#e0531f;--zone-rot:rgba(19,151,107,.08);--zone-fear:rgba(224,83,31,.08);--r:0}
@media (prefers-color-scheme:dark){:root{--page:#0a0a0a;--surface:#0a0a0a;--ink:#f5f5f5;--ink-2:#b5b5b5;--muted:#7d7d7d;--grid:#242424;
  --axis:#3a3a3a;--accent:#ff4d5e;--nq:#5b93f0;--bd:#2bb886;--y10:#f0703c;--zone-rot:rgba(43,184,134,.12);--zone-fear:rgba(240,112,60,.12)}}
body{font:16px/1.55 "Inter Tight",system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:8px 20px 40px}
header{padding:28px 0 32px;border-bottom:3px solid var(--ink)}
.q{margin:0 0 14px;font-size:13px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
h1{margin:0;font-size:clamp(32px,6vw,58px);line-height:1.02;letter-spacing:-.035em;font-weight:700;max-width:17ch}
.lead{margin:16px 0 0;color:var(--ink-2);max-width:60ch}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;padding:28px 0}
.kpi{border-top:2px solid var(--ink);padding-top:10px}
.kpi b{display:block;font-size:30px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.kpi span{font-size:13px;color:var(--ink-2)}
.row{display:grid;grid-template-columns:230px 1fr;gap:32px;padding:36px 0;border-top:1px solid var(--grid)}
.row h2{margin:0;font-size:21px;letter-spacing:-.015em}
.row h2 span{display:block;color:var(--accent);font-size:13px;margin-bottom:6px}
.row .dek{margin:8px 0 0;color:var(--ink-2);font-size:15px}
.row .kpis{padding:0 0 8px}
.story{border-top:3px solid var(--c);padding-top:10px}
footer{border-top:3px solid var(--ink);padding-top:16px;color:var(--muted);font-size:13px}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:18px}.row{grid-template-columns:1fr;gap:14px;padding:28px 0}}
"""


def page_swiss(b, t, payload):
    """Option 1: Swiss grid."""
    rows = "".join(f'<section class="row"><div><h2><span>{i:02d}</span>{escape(title)}</h2><p class="dek">{escape(t[key])}</p></div>'
                   f'<div>{content(b, keys)}</div></section>' for i, (title, key, keys) in enumerate(SECTIONS, 1))
    body = (f'<main class="wrap">{b["back"]}<header><p class="q">Nasdaq 100 vs bond yields</p><h1>{escape(t["verdict"])}</h1>'
            f'<p class="lead">{escape(t["verdict_line"])}</p></header><div class="kpis">{b["kpis"]}</div>{rows}'
            f'<footer>{b["footer"]}</footer></main>')
    # returns a str, the full page
    return doc(SWISS_CSS, "Inter+Tight:wght@400;500;600;700", body, payload)


# ---------------------------------------------------------------------------
# Option 2 · Serif: warm paper, one narrow reading column, oxblood accent
# ---------------------------------------------------------------------------
SERIF_CSS = """
:root{color-scheme:light dark;--page:#f7f5f0;--surface:#f7f5f0;--ink:#1b1a17;--ink-2:#5d5a52;--muted:#8d897f;--grid:#e0dcd1;--axis:#c9c4b6;
  --accent:#8a2d1c;--nq:#2a5db0;--bd:#2f8a62;--y10:#c2622d;--zone-rot:rgba(47,138,98,.08);--zone-fear:rgba(194,98,45,.08)}
@media (prefers-color-scheme:dark){:root{--page:#141311;--surface:#141311;--ink:#f1eee6;--ink-2:#b4afa3;--muted:#8a857a;--grid:#2e2c28;
  --axis:#46433d;--accent:#e08a74;--nq:#6d9be0;--bd:#4fb487;--y10:#e0844f;--zone-rot:rgba(79,180,135,.12);--zone-fear:rgba(224,132,79,.12)}}
body{font:16px/1.65 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
.serif,h1,h2,.kpi b{font-family:"Source Serif 4",Georgia,serif}
.wrap{max-width:760px;margin:0 auto;padding:8px 20px 48px}
header{padding:32px 0 8px}
.q{margin:0 0 12px;font-size:12px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
h1{margin:0;font-size:clamp(32px,5.5vw,46px);line-height:1.12;font-weight:600;letter-spacing:-.01em}
.lead{margin:14px 0 0;color:var(--ink-2);font-size:17px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin:32px 0 8px;padding:20px 0;border-top:1px solid var(--ink);border-bottom:1px solid var(--grid)}
.kpi b{display:block;font-size:28px;font-weight:600;font-variant-numeric:tabular-nums}
.kpi span{font-size:13px;color:var(--ink-2)}
section{padding:44px 0 0}
.num{margin:0;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
h2{margin:6px 0 4px;font-size:28px;font-weight:600;line-height:1.2}
.dek{margin:0 0 18px;color:var(--ink-2);font-family:"Source Serif 4",Georgia,serif;font-style:italic;font-size:18px}
section .kpis{margin:0 0 4px;border-top:0;padding-top:0}
.story{border-left:3px solid var(--c);padding-left:14px}
.story h3{font-family:"Source Serif 4",Georgia,serif;font-size:20px}
footer{margin-top:48px;padding-top:16px;border-top:1px solid var(--grid);color:var(--muted);font-size:13px}
@media (max-width:640px){.kpis{grid-template-columns:1fr 1fr}h2{font-size:24px}}
"""
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]             # section numbers in this design


def page_serif(b, t, payload):
    """Option 2: one elegant reading column."""
    secs = "".join(f'<section><p class="num">{ROMAN[i]}</p><h2>{escape(title)}</h2><p class="dek">{escape(t[key])}</p>{content(b, keys)}</section>'
                   for i, (title, key, keys) in enumerate(SECTIONS))
    body = (f'<main class="wrap">{b["back"]}<header><p class="q">Nasdaq 100 vs bond yields</p><h1>{escape(t["verdict"])}</h1>'
            f'<p class="lead">{escape(t["verdict_line"])}</p></header><div class="kpis">{b["kpis"]}</div>{secs}'
            f'<footer>{b["footer"]}</footer></main>')
    # returns a str, the full page
    return doc(SERIF_CSS, "Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@400;500;600", body, payload)


# ---------------------------------------------------------------------------
# Option 3 · Lab: the homepage's green band and brass, white panels
# ---------------------------------------------------------------------------
LAB_CSS = """
:root{color-scheme:light dark;--band:#0f3d2e;--brass:#c49a45;--page:#f6f3ec;--surface:#fff;--ink:#13201b;--ink-2:#55625c;--muted:#87918c;
  --grid:#e6e1d5;--axis:#cbc5b6;--nq:#2a5db0;--bd:#1f7a55;--y10:#c27a2c;--zone-rot:rgba(31,122,85,.08);--zone-fear:rgba(194,122,44,.09);--r:999px}
@media (prefers-color-scheme:dark){:root{--band:#0a2a20;--brass:#d8b26a;--page:#0f1513;--surface:#17201c;--ink:#e9efe9;--ink-2:#a5b2ab;
  --muted:#7d8a84;--grid:#26332d;--axis:#3a4842;--nq:#6d9be0;--bd:#3fa37c;--y10:#d99a52;--zone-rot:rgba(63,163,124,.13);--zone-fear:rgba(217,154,82,.13)}}
body{font:16px/1.6 "DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
h1,h2,.kpi b{font-family:"DM Serif Display",Georgia,serif;font-weight:400}
.in{max-width:1000px;margin:0 auto;padding:0 20px}
.band{background:var(--band);color:#d9e6df;padding:8px 0 96px}
.band a.back{color:#d9e6df}
.q{margin:24px 0 12px;color:var(--brass);font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}
h1{margin:0;color:#fff;font-size:clamp(34px,6vw,54px);line-height:1.06;max-width:18ch}
.lead{margin:16px 0 0;max-width:60ch}
.top{margin-top:-64px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.kpi{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:16px 18px}
.top .kpi{box-shadow:0 14px 34px rgba(0,0,0,.10)}
.kpi b{display:block;font-size:30px;font-variant-numeric:tabular-nums}
.kpi span{font-size:13px;color:var(--ink-2)}
.panel{background:var(--surface);border:1px solid var(--grid);border-radius:14px;padding:28px;margin-top:20px}
.panel .tag{margin:0;color:var(--brass);font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
h2{margin:4px 0 2px;font-size:28px;line-height:1.15}
.dek{margin:0 0 18px;color:var(--ink-2)}
.panel .kpi{background:var(--page);border:0}
.story{border-top:3px solid var(--c);padding-top:12px}
footer{margin-top:40px;background:var(--band);color:#d9e6df;font-size:13px}
footer .in{padding:20px}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
"""


def page_lab(b, t, payload):
    """Option 3: same look as the homepage."""
    panels = "".join(f'<section class="panel"><p class="tag">{i:02d}</p><h2>{escape(title)}</h2><p class="dek">{escape(t[key])}</p>{content(b, keys)}</section>'
                     for i, (title, key, keys) in enumerate(SECTIONS, 1))
    body = (f'<header class="band"><div class="in">{b["back"]}<p class="q">Nasdaq 100 vs bond yields</p><h1>{escape(t["verdict"])}</h1>'
            f'<p class="lead">{escape(t["verdict_line"])}</p></div></header>'
            f'<main class="in"><div class="kpis top">{b["kpis"]}</div>{panels}</main>'
            f'<footer><div class="in">{b["footer"]}</div></footer>')
    # returns a str, the full page
    return doc(LAB_CSS, "DM+Serif+Display&family=DM+Sans:wght@400;500;700", body, payload)


# ---------------------------------------------------------------------------
# Option 4 · Dashboard: everything on one screen, two-column grid of panels
# ---------------------------------------------------------------------------
DASH_CSS = """
:root{color-scheme:light dark;--page:#f4f5f7;--surface:#fff;--ink:#111827;--ink-2:#4b5563;--muted:#8b93a1;--grid:#e5e7eb;--axis:#cbd0d8;
  --nq:#2563eb;--bd:#0f9f6e;--y10:#ea6a2a;--zone-rot:rgba(15,159,110,.08);--zone-fear:rgba(234,106,42,.08)}
@media (prefers-color-scheme:dark){:root{--page:#0b0d12;--surface:#14171f;--ink:#e5e7eb;--ink-2:#a3aab6;--muted:#6f7785;--grid:#232834;
  --axis:#363c4a;--nq:#5b8ff5;--bd:#2fbf8a;--y10:#f0844a;--zone-rot:rgba(47,191,138,.12);--zone-fear:rgba(240,132,74,.12)}}
body{font:15px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:4px 20px 32px}
.bar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:4px 16px;border-bottom:1px solid var(--grid);margin-bottom:20px}
.bar .t{font-weight:600}
.bar .d{color:var(--muted);font-size:13px;font-family:"IBM Plex Mono",ui-monospace,monospace}
h1{margin:0;font-size:clamp(22px,3vw,30px);line-height:1.2;letter-spacing:-.01em;font-weight:600}
.lead{margin:6px 0 18px;color:var(--ink-2)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.kpi{background:var(--surface);border:1px solid var(--grid);border-radius:10px;padding:14px 16px}
.kpi b{display:block;font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--muted)}
.dash{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
.panel{background:var(--surface);border:1px solid var(--grid);border-radius:10px;padding:18px 20px;min-width:0}
.panel.wide{grid-column:1 / -1}
.panel h2{margin:0;font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.dek{margin:4px 0 14px;font-size:16px;font-weight:600}
.panel .kpi{border:0;background:var(--page);padding:10px 12px}
.panel .kpi b{font-size:20px}
.chart{height:300px}
.story{border-left:3px solid var(--c);padding-left:12px}
footer{margin-top:20px;color:var(--muted);font-size:12px}
@media (min-width:901px){#roll{height:540px}}   /* side by side with the two stacked performance charts: same height, no empty panel */
@media (max-width:900px){.dash{grid-template-columns:1fr}}
@media (max-width:640px){.kpis{grid-template-columns:1fr 1fr}.chart{height:420px}.panel{padding:16px 14px}}
"""
DASH_ORDER = [0, 2, 3, 4, 1, 6, 5]        # charts first, then stories and press side by side, the full table last


def page_dashboard(b, t, payload):
    """Option 4: compact dashboard."""
    panels = ""
    for i in DASH_ORDER:                                       # walk the sections in dashboard order
        title, key, keys = SECTIONS[i]
        wide = " wide" if key == "window" else ""              # the big table spans both columns
        panels += f'<section class="panel{wide}"><h2>{escape(title)}</h2><p class="dek">{escape(t[key])}</p>{content(b, keys)}</section>'
    body = (f'<main class="wrap"><div class="bar">{b["back"]}<span class="d">Nasdaq 100 · 10y yield · TLT</span></div>'
            f'<h1>{escape(t["verdict"])}</h1><p class="lead">{escape(t["verdict_line"])}</p>'
            f'<div class="kpis">{b["kpis"]}</div><div class="dash">{panels}</div><footer>{b["footer"]}</footer></main>')
    # returns a str, the full page
    return doc(DASH_CSS, "IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500", body, payload)


# ---------------------------------------------------------------------------
# Option 5 · Statement: each section opens with its finding in large type
# ---------------------------------------------------------------------------
STATEMENT_CSS = """
:root{color-scheme:light dark;--page:#fafafa;--surface:#fafafa;--ink:#0e0e10;--ink-2:#55555c;--muted:#8e8e96;--grid:#e6e6ea;--axis:#c9c9d0;
  --nq:#3b5bdb;--bd:#12a37a;--y10:#e8590c;--zone-rot:rgba(18,163,122,.07);--zone-fear:rgba(232,89,12,.07);--r:999px}
@media (prefers-color-scheme:dark){:root{--page:#0e0e10;--surface:#0e0e10;--ink:#f2f2f4;--ink-2:#b0b0b8;--muted:#7a7a83;--grid:#232327;
  --axis:#3a3a40;--nq:#7b93f0;--bd:#38c99c;--y10:#ff8a4c;--zone-rot:rgba(56,201,156,.11);--zone-fear:rgba(255,138,76,.11)}}
body{font:16px/1.6 Manrope,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:8px 20px 48px}
header{padding:56px 0 40px}
.q{margin:0 0 18px;color:var(--muted);font-size:14px;font-weight:600}
h1{margin:0;font-size:clamp(36px,7vw,68px);line-height:1;letter-spacing:-.04em;font-weight:800;max-width:15ch}
.lead{margin:20px 0 0;color:var(--ink-2);font-size:17px;max-width:56ch}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:28px}
.kpi b{display:block;font-size:34px;font-weight:700;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.kpi span{font-size:13px;color:var(--muted)}
section{padding:80px 0 0}
.eyebrow{margin:0 0 10px;color:var(--muted);font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase}
h2{margin:0 0 28px;font-size:clamp(24px,4vw,36px);line-height:1.15;letter-spacing:-.025em;font-weight:700;max-width:24ch}
section .kpis{margin-bottom:8px}
section .kpi b{font-size:28px}
.story h3{font-size:19px}
.story{padding-top:12px;border-top:2px solid var(--c)}
footer{margin-top:80px;padding-top:18px;border-top:1px solid var(--grid);color:var(--muted);font-size:13px}
@media (max-width:640px){header{padding:32px 0 28px}.kpis{grid-template-columns:1fr 1fr;gap:20px}section{padding-top:56px}h2{margin-bottom:20px}}
"""


def page_statement(b, t, payload):
    """Option 5: the finding is the heading."""
    secs = "".join(f'<section><p class="eyebrow">{i:02d} · {escape(title)}</p><h2>{escape(t[key])}</h2>{content(b, keys)}</section>'
                   for i, (title, key, keys) in enumerate(SECTIONS, 1))
    body = (f'<main class="wrap">{b["back"]}<header><p class="q">Nasdaq 100 vs bond yields</p><h1>{escape(t["verdict"])}</h1>'
            f'<p class="lead">{escape(t["verdict_line"])}</p></header><div class="kpis">{b["kpis"]}</div>{secs}'
            f'<footer>{b["footer"]}</footer></main>')
    # returns a str, the full page
    return doc(STATEMENT_CSS, "Manrope:wght@400;600;700;800", body, payload)


PAGES = {                                 # output file -> function that builds it
    "option_1_swiss.html": page_swiss,
    "option_2_serif.html": page_serif,
    "option_3_lab.html": page_lab,
    "option_4_dashboard.html": page_dashboard,
    "option_5_statement.html": page_statement,
}

if __name__ == "__main__":
    main()
