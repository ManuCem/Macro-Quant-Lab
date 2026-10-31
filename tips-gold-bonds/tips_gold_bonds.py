"""
What drives bond prices and gold prices? Real yields.
------------------------------------------------------
A learning page (no data download, no API) that explains, with two sliders:

    nominal yield  = real yield + expected inflation (the "breakeven")
    TIPS           = Treasury bonds whose principal grows with CPI, so the REAL return is locked in
    gold           = pays no coupon, so the real yield is what you give up by holding it

Reference values (October 2026, illustrative, typed in by hand - nothing is downloaded):
    US 10-year nominal yield ~5.1%, 10-year TIPS (real) yield ~2.65%,
    10-year breakeven ~2.3%, US CPI 3.7%.

Run:
    python tips_gold_bonds.py
    (needs only the Python standard library) -> writes tips_gold_bonds.html next to this file

Layout of this file (see CLAUDE.md):
    1. python / data code  -> reference values, the maths, and def main()
    2. html / chart code   -> builds the web page in the Lab design (inline CSS + JS + SVG, fonts from Google Fonts)

Not investment advice. All worked examples are illustrative.
"""

import json                               # turns the Python numbers into text the page's JavaScript can read
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

# ---------------------------------------------------------------
# python / data code
# ---------------------------------------------------------------

NOMINAL = 5.1        # US 10-year Treasury nominal yield, in % (October 2026 reference value)
REAL = 2.65          # US 10-year TIPS yield = the real yield, in % (October 2026 reference value)
BREAKEVEN = 2.3      # 10-year breakeven = market's expected inflation, in % (October 2026 reference value)
CPI = 3.7            # latest US CPI inflation, in % per year (October 2026 reference value)
GOLD_EXAMPLE = 1000  # dollars used in every worked example (illustrative)
AS_OF = "October 2026"   # label shown next to every reference value
OUT_FILE = Path(__file__).with_name("tips_gold_bonds.html")   # where the page is saved (same folder as this script)


def real_return(nominal_pct, inflation_pct):
    """Real return of a plain bond held one year: what the coupon buys after prices rose."""
    nominal = nominal_pct / 100                    # 5.1 -> 0.051 so we can multiply
    inflation = inflation_pct / 100                # 3.7 -> 0.037
    result = ((1 + nominal) / (1 + inflation) - 1) * 100   # exact real return, back in %
    # returns a float (percent), e.g. real_return(5.1, 3.7) -> 1.3499...
    return result


def tips_nominal_return(real_pct, inflation_pct):
    """Nominal (dollar) return of a TIPS held one year: principal grows with CPI AND the real coupon is paid."""
    real = real_pct / 100                          # 2.65 -> 0.0265
    inflation = inflation_pct / 100                # 3.7 -> 0.037
    result = ((1 + real) * (1 + inflation) - 1) * 100      # dollar return in %
    # returns a float (percent), e.g. tips_nominal_return(2.65, 3.7) -> 6.4480...
    return result


def tips_worked_example(principal=GOLD_EXAMPLE, real_pct=REAL, inflation_pct=CPI):
    """Walk one year of a TIPS: the principal is re-scaled by CPI, then the coupon is paid on the new principal."""
    new_principal = principal * (1 + inflation_pct / 100)      # CPI adjusts the principal upward
    coupon = new_principal * real_pct / 100                    # fixed real coupon rate paid on the adjusted principal
    inflation_gain = new_principal - principal                 # dollars added by the CPI adjustment
    total_dollars = inflation_gain + coupon                    # all dollars earned in the year
    result = {                                                 # keep every step so the page can show it
        "principal": principal,
        "new_principal": round(new_principal, 2),
        "inflation_gain": round(inflation_gain, 2),
        "coupon": round(coupon, 2),
        "total_dollars": round(total_dollars, 2),
        "nominal_pct": round(total_dollars / principal * 100, 2),
        "real_pct": round(real_return(tips_nominal_return(real_pct, inflation_pct), inflation_pct), 2),
    }
    # returns a dict with 7 keys, e.g.:
    # {'principal': 1000, 'new_principal': 1037.0, 'inflation_gain': 37.0, 'coupon': 27.48,
    #  'total_dollars': 64.48, 'nominal_pct': 6.45, 'real_pct': 2.65}
    return result


def crossover_inflation(nominal_pct=NOMINAL, real_pct=REAL):
    """Inflation rate at which a plain bond and a TIPS earn the same real return (actual inflation = this)."""
    result = ((1 + nominal_pct / 100) / (1 + real_pct / 100) - 1) * 100   # solve (1+N)/(1+pi) = 1+R for pi
    # returns a float (percent), e.g. crossover_inflation() -> 2.3915...
    return result


def build_model():
    """Gather every number the page needs into one dictionary (it is pasted into the page as JSON)."""
    result = {
        "asOf": AS_OF,
        "nominal": NOMINAL,
        "real": REAL,
        "breakeven": BREAKEVEN,
        "cpi": CPI,
        "amount": GOLD_EXAMPLE,
        "gap": round(NOMINAL - REAL - BREAKEVEN, 2),           # rounding gap in the identity N = R + B
        "crossover": round(crossover_inflation(), 2),
        "tipsExample": tips_worked_example(),
        "nomMinusReal": round(NOMINAL - REAL, 2),              # nominal minus real yield: the breakeven implied by these two quotes
        "bondRealAtCpi": round(real_return(NOMINAL, CPI), 2),  # plain bond's real return if inflation stays at today's CPI
        "goldCostYear": round(GOLD_EXAMPLE * REAL / 100, 2),   # real dollars a year given up by holding gold instead of TIPS
    }
    # returns a dict with 12 keys, e.g.:
    # {'asOf': 'October 2026', 'nominal': 5.1, 'real': 2.65, 'breakeven': 2.3, 'cpi': 3.7,
    #  'amount': 1000, 'gap': 0.15, 'crossover': 2.39, 'tipsExample': {...},
    #  'nomMinusReal': 2.45, 'bondRealAtCpi': 1.35, 'goldCostYear': 26.5}
    return result


def main():
    model = build_model()                                       # step 1: compute every number
    page = build_page(model)                                    # step 2: pour them into the HTML template
    OUT_FILE.write_text(page, encoding="utf-8")                 # step 3: save the page
    print(f"Saved {OUT_FILE.name} ({len(page) / 1024:.1f} KB)")  # step 4: confirm
    print(f"  Plain bond vs TIPS cross at {model['crossover']}% actual inflation")
    print(f"  Identity gap (nominal - real - breakeven) = {model['gap']} points")
    print("Reminder: illustrative only, not investment advice.")
    # main returns nothing: it prints text like
    #   Saved tips_gold_bonds.html (23.3 KB)
    #     Plain bond vs TIPS cross at 2.39% actual inflation
    #     Identity gap (nominal - real - breakeven) = 0.15 points
    #   Reminder: illustrative only, not investment advice.


# ---------------------------------------------------------------
# html / chart code
# ---------------------------------------------------------------

FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"

# Look: the "Lab" design every project page uses (see CLAUDE.md): green header band, brass accents, white panels,
# the same fonts as the homepage. Colours: one fixed hue per idea, plain bond / inflation = blue, TIPS / real yield = orange,
# gold = gold. Text always names the thing in words, never colour alone.
CSS = """
:root{color-scheme:light dark;--band:#3a2b10;--band-ink:#e4e6ea;--brass:#c49a45;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--bond:#2a5db0;--tips:#b85a18;--gold:#a8841c;--good:#1f7a55;--bad:#b23a3a;--on-color:#fff}
@media (prefers-color-scheme:dark){:root{--band:#281d0a;--brass:#d8b26a;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--bond:#6d9be0;--tips:#e08a4c;--gold:#d9b54a;--good:#3fa37c;--bad:#e07b7b;--on-color:#0f1513}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 "DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
h1,h2,.kpi b{font-family:"DM Serif Display",Georgia,serif;font-weight:400}
a{color:inherit}
p{margin:0 0 12px}
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
.kpis.two{grid-template-columns:1fr 1fr;margin:12px 0}
.kpi{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:16px 18px}
.top .kpi{box-shadow:0 14px 34px rgba(0,0,0,.10)}
.kpi b{display:block;font-size:30px;font-variant-numeric:tabular-nums}
.kpi span{font-size:13px;color:var(--ink-2)}
.kpi b.pos{color:var(--good)}.kpi b.neg{color:var(--bad)}
.panel{background:var(--surface);border:1px solid var(--grid);border-radius:14px;padding:28px;margin-top:20px}
.panel .tag{margin:0;color:var(--brass);font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
h2{margin:4px 0 2px;font-size:28px;line-height:1.15}
.dek{margin:0 0 18px;font-weight:700}
.how{background:var(--page);border-radius:10px;padding:12px 16px;margin:0 0 18px;font-size:15px;color:var(--ink-2)}
.how b,.so b{color:var(--ink)}
.so{border-left:3px solid var(--brass);padding:2px 0 2px 16px;margin:20px 0 0}
.so p{margin:0 0 8px}
.panel .kpi{background:var(--page);border:0}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle}
.eq{font-family:"DM Serif Display",Georgia,serif;font-size:21px;margin:0 0 6px}
.stack{display:flex;height:48px;border-radius:8px;overflow:hidden;gap:2px;margin:10px 0 6px}
.stack div{display:flex;align-items:center;justify-content:center;color:var(--on-color);font-weight:700;font-size:15px;min-width:0;white-space:nowrap}
.ctl{margin:14px 0 6px}
.ctl label{display:flex;justify-content:space-between;gap:10px;font-weight:700}
.ctl output{color:var(--tips);font-variant-numeric:tabular-nums}
input[type=range]{display:block;width:100%;height:44px;margin:0;accent-color:var(--tips);touch-action:pan-y;cursor:pointer}
.verdict{border-left:3px solid var(--tips);background:var(--page);padding:10px 14px;border-radius:0 10px 10px 0;margin:12px 0;min-height:3.2em;font-size:15px}
.chart{width:100%;margin-top:8px}
.chart svg{display:block;width:100%;height:auto}
.chart svg text{fill:var(--muted);font-family:inherit}
.legend{display:flex;flex-wrap:wrap;gap:4px 22px;margin:6px 0 0;font-size:14px;color:var(--ink-2)}
.legend span{display:flex;align-items:center;gap:8px;min-height:28px}
.legend i{width:24px;height:0;border-top:3px solid}
.bars{margin:8px 0}
.bar{display:grid;grid-template-columns:140px 1fr 76px;align-items:center;gap:10px;margin:10px 0;font-size:15px}
.bar .track{background:var(--page);border-radius:6px;height:22px;position:relative;overflow:hidden}
.bar .fill{position:absolute;left:0;top:0;bottom:0;border-radius:0 4px 4px 0}
.bar .val{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.gloss{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;margin:24px 0 0;padding-top:20px;border-top:1px solid var(--grid)}
.gloss div{margin:0}
.gloss dt{font-weight:700}
.gloss dd{margin:2px 0 0;color:var(--ink-2);font-size:15px}
.take{margin:0;padding-left:1.2rem}
.take li{margin:0 0 12px}
.take li::marker{color:var(--brass)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;max-width:640px;font-variant-numeric:tabular-nums;font-size:15px}
td{padding:9px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
td:first-child{text-align:left;position:sticky;left:0;background:var(--surface);padding-left:0}
tr.sum td{font-weight:700}
.refs{margin:28px 0 0;padding:0 4px;color:var(--muted);font-size:13px;line-height:1.45}
.refs .refs-h{margin:0 0 2px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:12px}
.refs ul{list-style:none;padding:0;margin:0}
.refs a{display:flex;align-items:center;min-height:44px;padding:4px 0;color:var(--ink-2);text-decoration:underline;
  text-decoration-color:var(--axis);text-underline-offset:3px}
.refs a:hover{color:var(--ink);text-decoration-color:currentColor}
.refs b{font-weight:700}
.refs .refs-note{margin:6px 0 0}
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
@media (max-width:640px){
  .gloss{grid-template-columns:1fr;gap:18px}
  .kpi{padding:14px}.kpi b{font-size:26px}
  .legend{flex-direction:column;gap:0}
  td{padding:8px 4px;white-space:normal}td:first-child{position:static}td:last-child{white-space:nowrap}
  .bar{grid-template-columns:1fr 70px;grid-template-areas:"name val" "track track";gap:4px 10px}
  .bar .nm{grid-area:name}.bar .track{grid-area:track}.bar .val{grid-area:val}
}
"""

# The page's JavaScript: the two sliders, the line chart (hand-drawn SVG) and the opportunity-cost bars.
# (JS comments play the role of the per-line "#" comments.)
JS = """
// numbers computed in Python and pasted in here
const M = __MODEL__;
// shortcuts to find elements by id, and a money/percent formatter with a real minus sign
const $ = id => document.getElementById(id);
const pct = (x, d = 2) => (x >= 0 ? "" : "\\u2212") + Math.abs(x).toFixed(d) + "%";
const usd = x => (x < 0 ? "\\u2212$" : "$") + Math.abs(x).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
// the same return formula as the Python file, so the sliders match the worked numbers
const realRet = (n, i) => ((1 + n / 100) / (1 + i / 100) - 1) * 100;
// phone layout flag (<=640px), re-read whenever the chart is drawn
const narrowMQ = window.matchMedia("(max-width: 640px)");

// ---- panel 3: line chart of real return against actual inflation ----
function drawChart1() {
  const infl = parseFloat($("infl").value);                // current slider value, %
  const small = narrowMQ.matches;                          // phone gets a taller, simpler chart
  const W = Math.max(240, $("chart1").clientWidth || 720); // draw at the box's real width, so 1 SVG unit = 1 pixel
  const H = small ? 340 : 360;                             // the chart box is taller than wide on a phone
  const L = small ? 42 : 54, R = small ? 12 : 20, T = 16, B = 44;   // margins: room for axis labels
  const xmax = 8, ymin = -4, ymax = 6;                     // axes: inflation 0-8%, real return -4..+6% (bond starts at the nominal yield)
  const X = v => L + (v / xmax) * (W - L - R);             // data -> pixel (x)
  const Y = v => T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B);   // data -> pixel (y)
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="Real return of a plain bond and a TIPS against actual inflation">';
  for (let g = ymin; g <= ymax; g += 2) {                  // horizontal grid + y labels
    s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(g) + '" y2="' + Y(g) + '" stroke="var(' + (g === 0 ? "--axis" : "--grid") + ')" stroke-width="' + (g === 0 ? 1.5 : 1) + '"/>';
    s += '<text x="' + (L - 8) + '" y="' + (Y(g) + 4) + '" text-anchor="end" font-size="13">' + (g < 0 ? "\\u2212" + (-g) : g) + '%</text>';
  }
  for (let g = 0; g <= xmax; g += 2) {                     // x labels (first and last stay inside the box)
    s += '<text x="' + X(g) + '" y="' + (H - 22) + '" text-anchor="' + (g === 0 ? "start" : g === xmax ? "end" : "middle") + '" font-size="13">' + g + '%</text>';
  }
  s += '<text x="' + ((L + W - R) / 2) + '" y="' + (H - 4) + '" text-anchor="middle" font-size="13">Actual inflation</text>';
  // plain bond line (solid) sampled every 0.1%
  let pb = "";
  for (let i = 0; i <= xmax + 1e-9; i += 0.1) pb += (pb ? "L" : "M") + X(i).toFixed(1) + " " + Y(realRet(M.nominal, i)).toFixed(1);
  s += '<path d="' + pb + '" fill="none" stroke="var(--bond)" stroke-width="2.5"/>';
  // TIPS line (dashed): real return stays at the real yield
  s += '<line x1="' + X(0) + '" x2="' + X(xmax) + '" y1="' + Y(M.real) + '" y2="' + Y(M.real) + '" stroke="var(--tips)" stroke-width="2.5" stroke-dasharray="7 5"/>';
  // crossover marker: a dotted vertical line and its label
  s += '<line x1="' + X(M.crossover) + '" x2="' + X(M.crossover) + '" y1="' + T + '" y2="' + (H - B) + '" stroke="var(--muted)" stroke-dasharray="2 4"/>';
  s += '<text x="' + (X(M.crossover) + 6) + '" y="' + (T + 24) + '" font-size="13">equal at ' + M.crossover + '%</text>';
  // current slider position: ring dots on each line
  s += '<circle cx="' + X(infl) + '" cy="' + Y(realRet(M.nominal, infl)) + '" r="6" fill="var(--bond)" stroke="var(--surface)" stroke-width="2"/>';
  s += '<circle cx="' + X(infl) + '" cy="' + Y(M.real) + '" r="6" fill="var(--tips)" stroke="var(--surface)" stroke-width="2"/>';
  $("chart1").innerHTML = s + "</svg>";
}
function update1() {
  const infl = parseFloat($("infl").value);                // current actual inflation
  const b = realRet(M.nominal, infl), t = M.real;          // real returns: plain bond falls, TIPS stays put
  $("inflout").textContent = pct(infl, 1);
  $("bondreal").textContent = pct(b);
  $("bondreal").className = b >= 0 ? "pos" : "neg";
  $("tipsreal").textContent = pct(t);
  $("tipsreal").className = t >= 0 ? "pos" : "neg";
  const diff = Math.abs(t - b).toFixed(2);
  $("verdict1").textContent = infl > M.crossover
    ? "Inflation is above the crossover (" + M.crossover + "%): the TIPS wins by " + diff + " points. The plain bond's fixed dollars buy less than expected."
    : infl < M.crossover
      ? "Inflation is below the crossover (" + M.crossover + "%): the plain bond wins by " + diff + " points. TIPS pay for inflation that did not arrive."
      : "Inflation equals the crossover: both give the same real return.";
  drawChart1();
}
$("infl").addEventListener("input", update1);

// ---- panel 4: slider 2 and opportunity-cost bars ----
function update2() {
  const r = parseFloat($("ry").value);                     // real yield chosen on the slider, %
  const A = M.amount;                                      // $1,000 example
  const tipsReal = A * r / 100;                            // real dollars a TIPS earns in a year
  const goldReal = 0;                                      // gold earns no coupon
  const nomBreak = ((1 + r / 100) * (1 + M.cpi / 100) - 1) * 100;   // gold's nominal gain needed to match, at reference CPI
  const tenYear = A * (Math.pow(1 + r / 100, 10) - 1);     // real dollars forgone after 10 years of compounding
  $("ryout").textContent = pct(r);
  const scale = 4;                                         // bar track is 4% wide at most
  const w = v => Math.min(100, Math.abs(v) / scale * 100) + "%";
  const bar = (name, v, color) => '<div class="bar"><span class="nm">' + name + '</span><span class="track"><span class="fill" style="width:' + w(v) +
    ';background:' + color + '"></span></span><span class="val">' + pct(v) + '</span></div>';
  $("bars").innerHTML = bar("TIPS real income", r, "var(--tips)") + bar("Gold real income", goldReal, "var(--gold)");
  $("verdict2").innerHTML = r > 0
    ? "Holding $" + A.toLocaleString("en-US") + " of gold instead of TIPS gives up about <b>" + usd(tipsReal) + " a year</b> of real income (" + usd(tenYear) +
      " over 10 years). To break even, gold must rise about <b>" + pct(r) + "</b> in real terms, or <b>" + pct(nomBreak) + "</b> in dollars at " + M.cpi + "% CPI."
    : r === 0
      ? "At a zero real yield, holding gold costs nothing versus TIPS."
      : "With a <b>negative</b> real yield, TIPS lose " + usd(Math.abs(tipsReal)) + " a year in purchasing power. Gold's lack of income is no longer a handicap, which is the classic bullish setting for gold.";
}
$("ry").addEventListener("input", update2);

// ---- start up, and redraw the chart when the phone is rotated across the 640px line or the window is resized ----
update1(); update2();
narrowMQ.addEventListener("change", drawChart1);
let lastW = 0;                                             // only redraw when the width really changed (phones fire resize on scroll)
window.addEventListener("resize", () => { const w = $("chart1").clientWidth; if (w !== lastW) { lastW = w; drawChart1(); } });
"""

SOURCES = [                               # (source, what it gives, link): one quiet line each in the References block at the end
    ("FRED", "10-year Treasury yield, nominal (DGS10)", "https://fred.stlouisfed.org/series/DGS10"),        # St. Louis Fed: the nominal yield
    ("FRED", "10-year TIPS yield, real (DFII10)", "https://fred.stlouisfed.org/series/DFII10"),            # the real yield
    ("FRED", "10-year breakeven inflation (T10YIE)", "https://fred.stlouisfed.org/series/T10YIE"),         # expected inflation
    ("BLS", "Consumer Price Index, actual inflation (CPI)", "https://www.bls.gov/cpi/"),                   # US Bureau of Labor Statistics
    ("TreasuryDirect", "how TIPS work", "https://www.treasurydirect.gov/marketable-securities/tips/"),     # US Treasury explainer
]

GLOSSARY = [                              # (term, plain-language meaning): the four yields and prices the page is built on
    ("Nominal yield", "The interest a normal Treasury pays, in dollars, ignoring inflation."),
    ("Real yield", "The interest after inflation. Markets read it from TIPS (Treasury Inflation-Protected Securities)."),
    ("Expected inflation (breakeven)", "What the market expects inflation to average. It is the nominal yield minus the TIPS yield."),
    ("CPI", "Consumer Price Index: the measured rise in prices over the past year. That is actual inflation, not the expectation."),
]


def usd(value, cents=True):
    """Format dollars with a thousands separator, e.g. 1037 -> '$1,037.00' (or '$1,037' with cents=False)."""
    text = f"${value:,.2f}" if cents else f"${value:,.0f}"    # comma every three digits; cents only where they matter
    # returns a str, e.g. usd(1037) -> '$1,037.00', usd(26.5) -> '$26.50', usd(1000, cents=False) -> '$1,000'
    return text


def tile(value, label, color=None, value_id=None):
    """One headline number with its label; an optional dot names the series by its chart colour."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # identity is in the text too, never colour alone
    idattr = f' id="{value_id}"' if value_id else ""           # sliders rewrite the number through this id
    # returns a str of HTML, e.g. '<div class="kpi"><b><i class="dot" ...></i>2.65%</b><span>10-year TIPS yield (real)</span></div>'
    return f'<div class="kpi"><b{idattr}>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def panel(number, question, finding, how, body, so=""):
    """One numbered section: a question, its one-line finding, how to read it, the chart or table, and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""          # optional reading guide
    so_html = f'<div class="so">{so}</div>' if so else ""                                  # optional takeaway
    # returns a str of HTML, e.g. '<section class="panel"><p class="tag">01</p><h2>What is a real yield?</h2><p class="dek">Nominal ...'
    return (f'<section class="panel"><p class="tag">{number:02d}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def answer_text(m):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    text = (f"<b>The real yield.</b> A bond is a promise of future money. Gold is a metal that promises nothing. Both prices are "
            f"pulled around by one number: the <b>real yield</b>, the interest you earn <i>after</i> inflation has taken its cut. "
            f"With the 10-year TIPS at {m['real']}%, holding {usd(m['amount'], False)} of gold instead gives up about "
            f"{usd(m['goldCostYear'])} a year of real income.")
    # returns a str of HTML, about 380 characters, e.g.
    # '<b>The real yield.</b> A bond is a promise of future money. ... gives up about $26.50 a year of real income.'
    return text


def tips_table(m):
    """The one-year TIPS walk-through as a two-column table (step, dollars or percent)."""
    e = m["tipsExample"]                                       # the worked example computed in tips_worked_example()
    rows = [                                                   # (step, value, is it a total line?)
        ("Starting principal", usd(e["principal"]), False),
        (f"CPI adjusts it to ({m['cpi']}%)", usd(e["new_principal"]), False),
        ("+ Inflation gain", usd(e["inflation_gain"]), False),
        (f"+ Coupon ({m['real']}% of new principal)", usd(e["coupon"]), False),
        ("= Dollars earned", usd(e["total_dollars"]), True),
        ("Nominal return", f"{e['nominal_pct']:.2f}%", False),
        (f"Real return (after {m['cpi']}% inflation)", f"{e['real_pct']:.2f}%", True),
    ]
    body = "".join(f'<tr{" class=sum" if bold else ""}><td>{escape(a)}</td><td>{escape(b)}</td></tr>' for a, b, bold in rows)
    # returns a str of HTML: 7 rows, e.g. <tr><td>Starting principal</td><td>$1,000.00</td></tr> ... <tr class=sum><td>Real return ...</td><td>2.65%</td></tr>
    return f'<div class="scroll"><table><tbody>{body}</tbody></table></div>'


def conclusions(m):
    """The 'What did we learn?' list, written from the numbers."""
    e = m["tipsExample"]                                       # the one-year TIPS example
    winner = ("the TIPS wins" if m["cpi"] > m["crossover"]     # which bond does better if inflation stays at today's CPI
              else "the plain bond wins" if m["cpi"] < m["crossover"] else "they tie")
    items = [
        (f"<b>Nominal yield &asymp; real yield + expected inflation.</b> In {m['asOf']}: {m['nominal']}% &asymp; {m['real']}% + "
         f"{m['breakeven']}%, with a gap of {m['gap']} points because quoted yields come from different markets and rounding."),
        (f"<b>A TIPS locks in the real return.</b> CPI re-scales the principal, so {usd(e['principal'], False)} earned "
         f"{usd(e['total_dollars'])} in a year at {m['cpi']}% CPI: {e['nominal_pct']:.2f}% in dollars, {e['real_pct']:.2f}% after inflation."),
        (f"<b>Plain bond or TIPS is a bet on inflation.</b> Both give the same real return at {m['crossover']}% actual inflation. "
         f"If inflation stays at {m['cpi']}% CPI, {winner}: the plain bond earns {m['bondRealAtCpi']:.2f}% real, the TIPS {m['real']}%."),
        (f"<b>For gold, the real yield is an opportunity cost.</b> Gold pays no coupon, so at a {m['real']}% real yield "
         f"{usd(m['amount'], False)} of gold gives up about {usd(m['goldCostYear'])} a year. When real yields fall toward zero or below, "
         f"that cost vanishes and gold becomes easier to hold."),
        (f"<b>Limits.</b> The reference values are typed in by hand for {m['asOf']}, not downloaded, and every worked example is "
         f"illustrative. Real yields are the main story for gold, not the only one: the US dollar, central-bank buying and fear in "
         f"markets also move it, and the link has been loose in some years. A mental model, not a forecast."),
    ]
    # returns a list of 5 HTML strings, e.g.
    # ['<b>Nominal yield &asymp; real yield + expected inflation.</b> In October 2026: 5.1% &asymp; 2.65% + 2.3%, ...', ...]
    return items


def references(m):
    """The quiet 'References' block after the last panel: muted small lines with links, no panel box, no question heading."""
    lines = "".join(                                           # one list item per source; the whole line is the (44px tall) link
        f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><span><b>{escape(src)}</b> · {escape(what)}</span></a></li>'
        for src, what, u in SOURCES)
    note = (f'<p class="refs-note">The values on this page are reference values for {escape(m["asOf"])}, '   # where the numbers come from
            "typed into the script by hand (nothing is downloaded).</p>")
    # returns a str of HTML, e.g.
    # '<aside class="refs" aria-label="References"><p class="refs-h">References</p><ul><li><a href="https://fred.stlouisfed.org/series/DGS10" ...>
    #  <span><b>FRED</b> · 10-year Treasury yield, nominal (DGS10)</span></a></li>... (5 links)</ul>
    #  <p class="refs-note">The values on this page are reference values for October 2026, typed into the script by hand ...</p></aside>'
    return f'<aside class="refs" aria-label="References"><p class="refs-h">References</p><ul>{lines}</ul>{note}</aside>'


def build_page(model):
    """Assemble the standalone HTML page in the Lab design and return it as text (main() saves it)."""
    m = model                                                  # short name: it is used in almost every line below
    e = m["tipsExample"]                                       # the one-year TIPS walk-through

    kpis = "".join([                                           # the four reference numbers under the header
        tile(f"{m['nominal']}%", "10-year Treasury yield (nominal)", "--bond"),
        tile(f"{m['real']}%", "10-year TIPS yield (real)", "--tips"),
        tile(f"{m['breakeven']}%", "10-year breakeven (expected inflation)"),
        tile(f"{m['cpi']}%", "US CPI inflation, past year"),
    ])
    stack = ('<p class="eq">Nominal yield &asymp; Real yield + Expected inflation</p>'
             '<div class="stack" role="img" aria-label="Nominal yield split into real yield and expected inflation">'
             f'<div style="flex:{m["real"]};background:var(--tips)">Real {m["real"]}%</div>'
             f'<div style="flex:{m["breakeven"]};background:var(--bond)">Inflation {m["breakeven"]}%</div></div>')
    gloss = '<dl class="gloss">' + "".join(f"<div><dt>{escape(t)}</dt><dd>{escape(d)}</dd></div>" for t, d in GLOSSARY) + "</dl>"
    slider1 = ('<div class="ctl"><label for="infl">Actual inflation <output id="inflout"></output></label>'
               f'<input id="infl" type="range" min="0" max="8" step="0.1" value="{m["cpi"]}"></div>'
               '<div class="kpis two">' + tile("", "Plain bond, real return", value_id="bondreal")
               + tile("", "TIPS, real return", value_id="tipsreal") + "</div>"
               '<div class="verdict" id="verdict1" aria-live="polite"></div>'
               '<div id="chart1" class="chart"></div>'
               f'<div class="legend"><span><i style="border-color:var(--bond)"></i>Plain bond ({m["nominal"]}% nominal)</span>'
               f'<span><i style="border-color:var(--tips);border-top-style:dashed"></i>TIPS ({m["real"]}% real, plus CPI)</span></div>')
    slider2 = ("<p>Gold pays no coupon and no dividend. Holding it means giving up the real yield you could have earned on a TIPS. "
               "The higher that real yield, the more expensive it is to hold gold, so buyers demand a better reason, and the gold "
               "price tends to come under pressure. When real yields fall toward zero or below, that cost vanishes and gold becomes "
               "easier to hold.</p>"
               '<p class="note"><b>Opportunity cost</b> = the best alternative you gave up. Here: the real yield on a TIPS.</p>'
               '<div class="ctl"><label for="ry">Real yield (10-year TIPS) <output id="ryout"></output></label>'
               f'<input id="ry" type="range" min="-1" max="4" step="0.05" value="{m["real"]}"></div>'
               '<div class="bars" id="bars"></div><div class="verdict" id="verdict2" aria-live="polite"></div>')
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in conclusions(m)) + "</ol>"

    panels = "".join([
        panel(1, "What is a real yield?",
              f"Nominal yield &asymp; real yield + expected inflation: {m['nominal']}% &asymp; {m['real']}% + {m['breakeven']}%.",
              "The bar is the 10-year nominal yield split into its two parts, drawn to scale: the real yield read from TIPS (orange) "
              "and the inflation the market expects, the breakeven (blue). Below it, the four terms the page is built on.",
              stack + gloss,
              f"<p>Reference ({m['asOf']}): nominal {m['nominal']}% vs real {m['real']}% + breakeven {m['breakeven']}% = "
              f"{m['real'] + m['breakeven']:.2f}% (rounding gap {m['gap']} points). Realised CPI is {m['cpi']}%, above the "
              f"{m['breakeven']}% the market expects.</p>"),
        panel(2, "How does a TIPS keep up with inflation?",
              f"{usd(e['principal'], False)} becomes {usd(e['new_principal'])}, plus a {usd(e['coupon'])} coupon: "
              f"{e['nominal_pct']:.2f}% in dollars, {e['real_pct']:.2f}% after inflation.",
              "A TIPS pays a <b>fixed real coupon</b>, but on a principal that is re-scaled by CPI. Read the table top to bottom: "
              "one year of a TIPS, first the CPI adjustment, then the coupon paid on the new, larger principal.",
              tips_table(m)
              + f'<p class="note">Illustrative: {usd(e["principal"], False)} bought at par with a {m["real"]}% real coupon, held one year '
                f'while CPI runs at the reference rate.</p>',
              "<p>If prices rise, the principal rises, and so does the coupon in dollars. That locks in the real return.</p>"),
        panel(3, "When does a TIPS beat a plain bond?",
              f"It depends on actual inflation: above {m['crossover']}% the TIPS wins, below it the plain bond does.",
              "A plain bond's yield is fixed in dollars, so higher inflation eats its real return. A TIPS keeps its real yield. "
              "Move the slider to change <b>actual</b> inflation over the next year. In the chart, the solid blue line is the plain "
              "bond's real return, the dashed orange line the TIPS; the dots follow the slider and the dotted line marks where they are equal.",
              slider1,
              f"<p>Why the crossover is not exactly {m['breakeven']}%: {m['nominal']}% &minus; {m['real']}% = {m['nomMinusReal']:.2f}%, "
              f"a touch above the quoted {m['breakeven']}% breakeven. Quoted yields come from different markets and rounding, so a "
              "small gap is normal. Real returns here use the exact formula (1+nominal) / (1+inflation) &minus; 1.</p>"),
        panel(4, "Why does gold compete with real yields?",
              f"At a {m['real']}% real yield, {usd(m['amount'], False)} of gold gives up about {usd(m['goldCostYear'])} a year versus TIPS.",
              f"Move the slider to set the 10-year TIPS real yield. The bars compare one year of real income from "
              f"{usd(m['amount'], False)} in TIPS and in gold (which pays none); the box below turns the gap into dollars.",
              slider2,
              "<p>Real yields are the <i>main</i> story, not the only one. The US dollar, central-bank buying and fear in markets also "
              "move gold, and the link between gold and real yields has been loose in some years. Treat this as a mental model, "
              "not a forecast.</p>"),
        panel(5, "What did we learn?", "Five takeaways.", "", take),   # always the last panel
    ]) + references(m)                                         # then the quiet References block (no panel box)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Real Yields, Bonds and Gold</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="band"><div class="in">
<a class="back" href="../index.html">&larr; Macro Quant Lab</a>
<p class="eyebrow">Real yields · TIPS · Gold</p>
<h1>What quietly drives bonds and gold?</h1>
<p class="answer">{answer_text(m)}</p>
<p class="meta">Reference values for {m['asOf']}, typed in by hand (nothing downloaded) · All worked examples are illustrative · Not investment advice</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{panels}
</main>
<footer><div class="in">Illustrative learning page, not investment advice. Reference values for {m['asOf']}: US 10-year nominal about
{m['nominal']}%, 10-year TIPS about {m['real']}%, 10-year breakeven about {m['breakeven']}%, US CPI {m['cpi']}%. Generated by
tips_gold_bonds.py; no data download and no chart library.</div></footer>
<script>{JS.replace("__MODEL__", json.dumps(m))}</script>
</body>
</html>
"""
    # returns a str of about 25,000 characters starting:
    # '<!doctype html>\\n<html lang="en">\\n<head>\\n<meta charset="utf-8">...'
    return html


if __name__ == "__main__":
    main()
