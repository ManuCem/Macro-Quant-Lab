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
    2. html / chart code   -> builds the standalone web page (inline CSS + JS + SVG)

Not investment advice. All worked examples are illustrative.
"""

import json                               # turns the Python numbers into text the page's JavaScript can read
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
    }
    # returns a dict with 9 keys, e.g.:
    # {'asOf': 'October 2026', 'nominal': 5.1, 'real': 2.65, 'breakeven': 2.3, 'cpi': 3.7,
    #  'amount': 1000, 'gap': 0.15, 'crossover': 2.39, 'tipsExample': {...}}
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
    #   Saved tips_gold_bonds.html (21.3 KB)
    #     Plain bond vs TIPS cross at 2.39% actual inflation
    #     Identity gap (nominal - real - breakeven) = 0.15 points
    #   Reminder: illustrative only, not investment advice.


# ---------------------------------------------------------------
# html / chart code
# ---------------------------------------------------------------

# The whole page lives in one string. The token __MODEL__ is replaced by the numbers above.
# (HTML/CSS/JS comments below play the role of the per-line "#" comments.)
PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Real yields, bonds and gold</title>
<style>
/* colour tokens: light by default, dark when the phone/computer is in dark mode */
:root{--bg:#fafaf7;--card:#ffffff;--ink:#1c1f24;--ink2:#515862;--muted:#7a818c;--line:#dcdfe4;
--bond:#2a6fdb;--tips:#d9730d;--gold:#b8860b;--good:#1f8a4c;--bad:#c23a3a;--soft:#eef1f6}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1c1f25;--ink:#eceff3;--ink2:#b4bac4;--muted:#8b929d;--line:#343942;
--bond:#6ea3ff;--tips:#f0a050;--gold:#e0b84a;--good:#4cc582;--bad:#ef7b7b;--soft:#262a32}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
padding:0 max(16px,env(safe-area-inset-right)) 40px max(16px,env(safe-area-inset-left))}
main{max-width:860px;margin:0 auto}
h1{font-size:1.7rem;line-height:1.2;margin:28px 0 8px}
h2{font-size:1.25rem;margin:0 0 8px}
p{margin:0 0 12px}
.lead{color:var(--ink2);font-size:1.05rem}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 18px;margin:18px 0}
.tag{display:inline-block;font-size:.78rem;color:var(--ink2);background:var(--soft);border-radius:999px;padding:3px 10px}
.def{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.def div{background:var(--soft);border-radius:10px;padding:10px 12px;font-size:.93rem}
.def .t{display:block;font-weight:700;margin-bottom:2px}
.stack{display:flex;height:48px;border-radius:8px;overflow:hidden;gap:2px;margin:14px 0 6px}
.stack div{display:flex;align-items:center;justify-content:center;color:#fff;font-weight:600;font-size:.92rem;min-width:0}
.eq{font-size:1.05rem;font-weight:600;margin:6px 0}
.note{color:var(--ink2);font-size:.9rem}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:right;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--card)}
.ctl{margin:14px 0 6px}
.ctl label{display:flex;justify-content:space-between;gap:10px;font-weight:600}
.ctl output{color:var(--tips);font-variant-numeric:tabular-nums}
input[type=range]{width:100%;height:44px;margin:0;accent-color:var(--tips);touch-action:pan-y}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.tile{background:var(--soft);border-radius:10px;padding:10px 12px}
.tile .v{font-size:1.45rem;font-weight:700;font-variant-numeric:tabular-nums}
.tile .l{font-size:.82rem;color:var(--ink2)}
.pos{color:var(--good)}.neg{color:var(--bad)}
.verdict{border-left:4px solid var(--tips);padding:8px 12px;background:var(--soft);border-radius:0 8px 8px 0;margin:10px 0 4px;min-height:3.2em}
svg{display:block;width:100%;height:auto}
svg text{fill:var(--ink2);font-family:inherit}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:6px;font-size:.9rem}
.legend span{display:flex;align-items:center;gap:6px;min-height:28px}
.legend i{width:22px;height:0;border-top:3px solid}
.bars{margin:8px 0}
.bar{display:grid;grid-template-columns:96px 1fr 76px;align-items:center;gap:8px;margin:8px 0;font-size:.92rem}
.bar .track{background:var(--soft);border-radius:6px;height:22px;position:relative;overflow:hidden}
.bar .fill{position:absolute;left:0;top:0;bottom:0;border-radius:0 4px 4px 0}
.bar .val{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
footer{color:var(--muted);font-size:.85rem;margin-top:24px}
a.back{display:inline-flex;align-items:center;min-height:44px;color:var(--bond)}
@media (max-width:640px){
h1{font-size:1.45rem}
.def,.tiles{grid-template-columns:1fr}
th,td{white-space:normal}
th:first-child,td:first-child{position:static}
td:last-child{white-space:nowrap}
.bar{grid-template-columns:1fr 70px;grid-template-areas:"name val" "track track"}
.bar .nm{grid-area:name}.bar .track{grid-area:track}.bar .val{grid-area:val}
}
</style>
</head>
<body>
<main>
<a class="back" href="../index.html">&larr; Macro-Quant-Lab</a>
<h1>Real yields: the quiet driver of bonds and gold</h1>
<p class="lead">A bond is a promise of future money. Gold is a metal that promises nothing. Both prices are pulled around by one number: the <b>real yield</b>, the interest you earn <i>after</i> inflation has taken its cut.</p>
<p><span class="tag" id="asof"></span> <span class="tag">All worked examples are illustrative</span></p>

<section id="s1">
<h2>1. Three yields, one identity</h2>
<div class="def">
<div><span class="t">Nominal yield</span>The interest a normal Treasury pays, in dollars, ignoring inflation.</div>
<div><span class="t">Real yield</span>The interest after inflation. Markets read it from <b>TIPS</b> (Treasury Inflation-Protected Securities).</div>
<div><span class="t">Expected inflation (breakeven)</span>What the market expects inflation to average. It is the nominal yield minus the TIPS yield.</div>
<div><span class="t">CPI</span>Consumer Price Index: the measured rise in prices over the past year. That is <i>actual</i> inflation, not the expectation.</div>
</div>
<p class="eq">Nominal yield &asymp; Real yield + Expected inflation</p>
<div class="stack" id="stack" role="img" aria-label="Nominal yield split into real yield and expected inflation"></div>
<p class="note" id="stacknote"></p>
</section>

<section id="s2">
<h2>2. How a TIPS adjusts with CPI</h2>
<p>A TIPS pays a <b>fixed real coupon</b>, but on a principal that is re-scaled by CPI. If prices rise, the principal rises, and so does the coupon in dollars. That locks in the real return.</p>
<div class="scroll"><table id="tipstable"></table></div>
<p class="note">Illustrative: $1,000 bought at par with a 2.65% real coupon, held one year while CPI runs at the reference rate.</p>
</section>

<section id="s3">
<h2>3. Slider 1: plain bond or TIPS, depending on actual inflation</h2>
<p>A plain bond's yield is fixed in dollars, so higher inflation eats its real return. A TIPS keeps its real yield. Move the slider to change <b>actual</b> inflation over the next year.</p>
<div class="ctl"><label for="infl">Actual inflation <output id="inflout"></output></label>
<input id="infl" type="range" min="0" max="8" step="0.1" value="3.7"></div>
<div class="tiles">
<div class="tile"><div class="v" id="bondreal"></div><div class="l">Plain bond, real return</div></div>
<div class="tile"><div class="v" id="tipsreal"></div><div class="l">TIPS, real return</div></div>
</div>
<div class="verdict" id="verdict1"></div>
<div id="chart1"></div>
<div class="legend"><span><i style="border-color:var(--bond)"></i>Plain bond (5.1% nominal)</span><span><i style="border-color:var(--tips);border-top-style:dashed"></i>TIPS (2.65% real, plus CPI)</span></div>
<p class="note">Why the crossover is not exactly 2.3%: 5.1% &minus; 2.65% = 2.45%, a touch above the quoted 2.3% breakeven. Quoted yields come from different markets and rounding, so a small gap is normal. Real returns here use the exact formula (1+nominal) / (1+inflation) &minus; 1.</p>
</section>

<section id="s4">
<h2>4. Why gold competes with real yields</h2>
<p>Gold pays no coupon and no dividend. Holding it means giving up the real yield you could have earned on a TIPS. The higher that real yield, the more expensive it is to hold gold, so buyers demand a better reason, and the gold price tends to come under pressure. When real yields fall toward zero or below, that cost vanishes and gold becomes easier to hold.</p>
<p class="note"><b>Opportunity cost</b> = the best alternative you gave up. Here: the real yield on a TIPS.</p>
<div class="ctl"><label for="ry">Real yield (10-year TIPS) <output id="ryout"></output></label>
<input id="ry" type="range" min="-1" max="4" step="0.05" value="2.65"></div>
<div class="bars" id="bars"></div>
<div class="verdict" id="verdict2"></div>
<p class="note">Real yields are the <i>main</i> story, not the only one. The US dollar, central-bank buying and fear in markets also move gold, and the link between gold and real yields has been loose in some years. Treat this as a mental model, not a forecast.</p>
</section>

<footer>Illustrative learning page, not investment advice. Reference values for <span id="asof2"></span>: US 10-year nominal about 5.1%, 10-year TIPS about 2.65%, 10-year breakeven about 2.3%, US CPI 3.7%. Generated by tips_gold_bonds.py; no external data or libraries.</footer>
</main>

<script>
// numbers computed in Python and pasted in here
const M = __MODEL__;
// shortcuts to find elements by id, and a money/percent formatter
const $ = id => document.getElementById(id);
const pct = (x, d = 2) => (x >= 0 ? "" : "−") + Math.abs(x).toFixed(d) + "%";
const usd = x => (x < 0 ? "−$" : "$") + Math.abs(x).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
// the same two return formulas as the Python file, so the sliders match the worked numbers
const realRet = (n, i) => ((1 + n / 100) / (1 + i / 100) - 1) * 100;
// phone layout flag (<=640px), re-read whenever the chart is drawn
const phone = () => window.matchMedia("(max-width: 640px)").matches;

// ---- header tags ----
$("asof").textContent = "Reference values: " + M.asOf;
$("asof2").textContent = M.asOf;

// ---- section 1: stacked bar nominal = real + breakeven ----
(function () {
  const total = M.real + M.breakeven;                     // bar is as wide as the two parts together
  $("stack").innerHTML =
    '<div style="flex:' + M.real + ';background:var(--tips)">Real ' + M.real + '%</div>' +
    '<div style="flex:' + M.breakeven + ';background:var(--bond)">Inflation ' + M.breakeven + '%</div>';
  $("stacknote").textContent = "Reference (" + M.asOf + "): nominal " + M.nominal + "% vs real " + M.real + "% + breakeven " +
    M.breakeven + "% = " + total.toFixed(2) + "% (rounding gap " + M.gap + " points). Realised CPI is " + M.cpi +
    "%, above the " + M.breakeven + "% the market expects.";
})();

// ---- section 2: TIPS worked example table ----
(function () {
  const e = M.tipsExample;
  const rows = [
    ["Starting principal", usd(e.principal)],
    ["CPI adjusts it to (" + M.cpi + "%)", usd(e.new_principal)],
    ["+ Inflation gain", usd(e.inflation_gain)],
    ["+ Coupon (" + M.real + "% of new principal)", usd(e.coupon)],
    ["= Dollars earned", usd(e.total_dollars)],
    ["Nominal return", pct(e.nominal_pct)],
    ["Real return (after " + M.cpi + "% inflation)", pct(e.real_pct)]
  ];
  $("tipstable").innerHTML = "<tbody>" + rows.map(r => "<tr><td>" + r[0] + "</td><td>" + r[1] + "</td></tr>").join("") + "</tbody>";
})();

// ---- section 3: slider 1 and line chart ----
function drawChart1() {
  const infl = parseFloat($("infl").value);                // current slider value, %
  const small = phone();                                   // phone gets a taller, simpler chart
  const W = small ? 290 : 720, H = small ? 330 : 340;      // SVG units; phone is ~1:1 with pixels so text stays readable
  const L = small ? 42 : 54, R = 20, T = 16, B = 40;       // margins: room for axis labels
  const xmax = 8, ymin = -4, ymax = 6;                     // axes: inflation 0-8%, real return -4..+6% (bond starts at 5.1%)
  const X = v => L + (v / xmax) * (W - L - R);             // data -> pixel (x)
  const Y = v => T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B);   // data -> pixel (y)
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Real return of a plain bond and a TIPS against actual inflation">';
  for (let g = ymin; g <= ymax; g += 2) {                  // horizontal grid + y labels
    s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(g) + '" y2="' + Y(g) + '" stroke="var(--line)" stroke-width="' + (g === 0 ? 1.5 : 1) + '"/>';
    s += '<text x="' + (L - 8) + '" y="' + (Y(g) + 4) + '" text-anchor="end" font-size="13">' + g + '%</text>';
  }
  for (let g = 0; g <= xmax; g += 2) {                     // x labels (first and last stay inside the box)
    s += '<text x="' + X(g) + '" y="' + (H - 16) + '" text-anchor="' + (g === 0 ? "start" : g === xmax ? "end" : "middle") + '" font-size="13">' + g + '%</text>';
  }
  s += '<text x="' + ((L + W - R) / 2) + '" y="' + (H - 1) + '" text-anchor="middle" font-size="12">Actual inflation</text>';
  // plain bond line (solid) sampled every 0.1%
  let pb = "";
  for (let i = 0; i <= xmax + 1e-9; i += 0.1) pb += (pb ? "L" : "M") + X(i).toFixed(1) + " " + Y(realRet(M.nominal, i)).toFixed(1);
  s += '<path d="' + pb + '" fill="none" stroke="var(--bond)" stroke-width="2.5"/>';
  // TIPS line (dashed): real return stays at the real yield
  s += '<line x1="' + X(0) + '" x2="' + X(xmax) + '" y1="' + Y(M.real) + '" y2="' + Y(M.real) + '" stroke="var(--tips)" stroke-width="2.5" stroke-dasharray="7 5"/>';
  // crossover marker
  s += '<line x1="' + X(M.crossover) + '" x2="' + X(M.crossover) + '" y1="' + T + '" y2="' + (H - B) + '" stroke="var(--muted)" stroke-dasharray="2 4"/>';
  s += '<text x="' + (X(M.crossover) + 6) + '" y="' + (T + 24) + '" font-size="12">equal at ' + M.crossover + '%</text>';
  // current slider position: ring dots on each line
  s += '<circle cx="' + X(infl) + '" cy="' + Y(realRet(M.nominal, infl)) + '" r="6" fill="var(--bond)" stroke="var(--card)" stroke-width="2"/>';
  s += '<circle cx="' + X(infl) + '" cy="' + Y(M.real) + '" r="6" fill="var(--tips)" stroke="var(--card)" stroke-width="2"/>';
  $("chart1").innerHTML = s + "</svg>";
}
function update1() {
  const infl = parseFloat($("infl").value);                // current actual inflation
  const b = realRet(M.nominal, infl), t = M.real;          // real returns: plain bond falls, TIPS stays put
  $("inflout").textContent = pct(infl, 1);
  $("bondreal").textContent = pct(b);
  $("bondreal").className = "v " + (b >= 0 ? "pos" : "neg");
  $("tipsreal").textContent = pct(t);
  $("tipsreal").className = "v pos";
  const diff = Math.abs(t - b).toFixed(2);
  $("verdict1").textContent = infl > M.crossover
    ? "Inflation is above the crossover (" + M.crossover + "%): the TIPS wins by " + diff + " points. The plain bond's fixed dollars buy less than expected."
    : infl < M.crossover
      ? "Inflation is below the crossover (" + M.crossover + "%): the plain bond wins by " + diff + " points. TIPS pay for inflation that did not arrive."
      : "Inflation equals the crossover: both give the same real return.";
  drawChart1();
}
$("infl").addEventListener("input", update1);

// ---- section 4: slider 2 and opportunity-cost bars ----
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

// ---- start up, and redraw the chart when the phone is rotated across the 640px line ----
update1(); update2();
window.matchMedia("(max-width: 640px)").addEventListener("change", drawChart1);
</script>
</body>
</html>
"""


def build_page(model):
    """Insert the numbers into the page template and return the finished HTML text."""
    html = PAGE.replace("__MODEL__", json.dumps(model))     # paste the dictionary in as JSON
    # returns a str of about 20,000 characters starting:
    # '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">...'
    return html


if __name__ == "__main__":
    main()
