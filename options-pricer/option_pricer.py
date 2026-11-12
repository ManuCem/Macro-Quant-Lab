"""
What should an S&P 500 option cost today?
-----------------------------------------
Prices a 30-day European call and put on the S&P 500 with the Black-Scholes formula, using today's
market data, then checks the answer two ways:

    1. Put-call parity: call - put must equal S - K * exp(-r * T), whatever the model says.
    2. The market: one real S&P 500 call from Yahoo's option chain (about 30 days to expiry,
       strike closest to ours, price = middle of bid and ask).

The five inputs (Yahoo Finance via yfinance, free, no key):
    S     = S&P 500 index level (^GSPC)
    K     = strike: S rounded to the nearest 5, so the option is "at the money"
    r     = 13-week US Treasury bill yield (^IRX), quoted in %, so divided by 100
    sigma = VIX (^VIX), the market's expected volatility for the next 30 days, in %, divided by 100
    T     = 30 / 365 years (30 calendar days)
    No dividends.

The maths, kept as basic as possible (math.erf, no scipy):
    N(x)  = 0.5 * (1 + erf(x / sqrt(2)))                 area under the bell curve left of x
    d1    = (ln(S / K) + (r + sigma^2 / 2) * T) / (sigma * sqrt(T))
    d2    = d1 - sigma * sqrt(T)
    call  = S * N(d1) - K * exp(-r * T) * N(d2)
    put   = K * exp(-r * T) * N(-d2) - S * N(-d1)
    delta = N(d1) for the call, N(d1) - 1 for the put

Output: options-pricer/option_pricer.html (one standalone page, one chart drawn with Apache ECharts).
The same maths in C++: options-pricer/option_pricer.cpp (copy the 5 inputs the page shows).

Run:
    pip install yfinance pandas
    python options-pricer/option_pricer.py

Layout of this file (see CLAUDE.md):
    1. python / data code  -> settings, download, calculations, and def main()
    2. html / chart code   -> builds the web page and the chart

Not investment advice.
"""

import json                               # turns Python lists/dicts into text the browser's JavaScript can read
import math                               # log, sqrt, exp and erf: everything Black-Scholes needs
from datetime import date                 # dates, to count the days until an option expires
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import pandas as pd                       # tables (DataFrames) and the current time in New York
import yfinance as yf                     # free prices and option chains from Yahoo Finance


# ===========================================================================
# python / data code
# ===========================================================================

HERE = Path(__file__).parent                                   # the options-pricer folder
OUTPUT_PATH = HERE / "option_pricer.html"                      # the web page we write
DAYS = 30                                 # life of our option, in calendar days
STRIKE_STEP = 5                           # S&P 500 option strikes come in steps of 5 index points
CURVE_RANGE = 0.10                        # the chart shows the S&P 500 from 10% below to 10% above today
CURVE_POINTS = 61                         # how many S&P levels the chart line is drawn through
NY = "America/New_York"                   # Wall Street's time zone: "today" means today in New York


def last_price(ticker):
    """The latest price Yahoo Finance has for one ticker (today's close, or the live price during the session)."""
    history = yf.Ticker(ticker).history(period="5d")           # the last 5 trading days (5, not 1, so a holiday never leaves it empty)
    if history.empty:                                          # Yahoo sent nothing back (bad ticker or no connection)
        raise RuntimeError(f"Yahoo Finance returned no prices for {ticker}")   # stop with a clear message
    value = float(history["Close"].iloc[-1])                   # the last row's price, as a plain Python number
    # returns a float, the raw Yahoo number (not rounded yet), e.g.
    # last_price("^GSPC") -> 7630.61           (S&P 500 index points)
    # last_price("^IRX")  -> 4.125             (13-week T-bill yield, in %)
    # last_price("^VIX")  -> 17.479999542236328 (VIX, in %)
    return value


def get_inputs():
    """Download S, r and sigma, then fix K and T: the five numbers Black-Scholes needs."""
    S = round(last_price("^GSPC"), 2)                          # S&P 500 level, 2 decimals (Yahoo adds float noise beyond that)
    irx = round(last_price("^IRX"), 3)                         # T-bill yield in %, 3 decimals as Yahoo quotes it (e.g. 4.12)
    vix = round(last_price("^VIX"), 2)                         # VIX in %, 2 decimals as Cboe quotes it (e.g. 17.53)
    K = round(S / STRIKE_STEP) * STRIKE_STEP                   # nearest multiple of 5: 7630.61 / 5 = 1526.12 -> 1526 -> 7630
    now = pd.Timestamp.now(tz=NY)                              # the time the prices were downloaded, on Wall Street's clock
    inputs = {
        "S": S,                                                # S&P 500 level, index points
        "K": float(K),                                         # strike, index points
        "r": round(irx / 100, 5),                              # 4.12% -> 0.0412 (round removes float noise like 0.041200000000000005)
        "sigma": round(vix / 100, 4),                          # 17.53% -> 0.1753
        "T": DAYS / 365,                                       # 30 days as a fraction of a year: 0.0822
        "days": DAYS,                                          # the same, in days (for the text)
        "irx": irx,                                            # the T-bill yield as quoted, in %
        "vix": vix,                                            # the VIX as quoted, in %
        "today": now.date().isoformat(),                       # today's date in New York, e.g. '2026-11-12'
        "asof": now.strftime("%d %b %Y, %H:%M"),               # download time for the page, e.g. '12 Nov 2026, 13:01'
    }
    # returns a dict of 10 values (real output, 12 Nov 2026 during the session):
    # {'S': 7630.61, 'K': 7630.0, 'r': 0.04125, 'sigma': 0.1748, 'T': 0.0821917808219178, 'days': 30,
    #  'irx': 4.125, 'vix': 17.48, 'today': '2026-11-12', 'asof': '12 Nov 2026, 13:01'}
    return inputs


def normal_cdf(x):
    """N(x): the share of the standard bell curve to the left of x (a probability between 0 and 1)."""
    area = 0.5 * (1 + math.erf(x / math.sqrt(2)))              # the textbook identity linking N(x) to the error function erf
    # returns a float between 0 and 1, e.g. normal_cdf(0) -> 0.5, normal_cdf(1.96) -> 0.9750, normal_cdf(-1) -> 0.1587
    return area


def black_scholes(S, K, r, sigma, T):
    """Black-Scholes price of a European call and put, plus their deltas and the intermediate steps."""
    vol_t = sigma * math.sqrt(T)                               # sigma * sqrt(T): the typical move over the option's life, as a fraction
    d1 = (math.log(S / K) + (r + sigma ** 2 / 2) * T) / vol_t  # how far today's level is above the strike, measured in typical moves (plus a drift term)
    d2 = d1 - vol_t                                            # d1 shifted down by one typical move
    discount = math.exp(-r * T)                                # what $1 paid at expiry is worth today
    call = S * normal_cdf(d1) - K * discount * normal_cdf(d2)  # call: what you expect to get (S*N(d1)) minus what you expect to pay (K*e^-rT*N(d2))
    put = K * discount * normal_cdf(-d2) - S * normal_cdf(-d1) # put: the mirror image, using the left side of the bell curve
    result = {
        "vol_t": vol_t,                                        # sigma * sqrt(T)
        "d1": d1,                                              # first step of the formula
        "d2": d2,                                              # second step
        "N_d1": normal_cdf(d1),                                # N(d1)
        "N_d2": normal_cdf(d2),                                # N(d2): in the model, the chance the call ends above the strike
        "discount": discount,                                  # e^(-rT)
        "call": call,                                          # call price, index points (= dollars per unit of the index)
        "put": put,                                            # put price
        "delta_call": normal_cdf(d1),                          # call delta: price change per 1-point rise in the S&P 500
        "delta_put": normal_cdf(d1) - 1,                       # put delta: always the call delta minus 1 (a negative number)
    }
    # returns a dict of 10 floats (real output for S=7630.61, K=7630, r=0.04125, sigma=0.1748, T=30/365, rounded here):
    # {'vol_t': 0.0501, 'd1': 0.0943, 'd2': 0.0442, 'N_d1': 0.5376, 'N_d2': 0.5176, 'discount': 0.996616,
    #  'call': 165.8567, 'put': 139.4217, 'delta_call': 0.5376, 'delta_put': -0.4624}
    return result


def parity_check(inputs, prices):
    """Put-call parity: call - put should equal S - K * exp(-rT) exactly."""
    left = prices["call"] - prices["put"]                      # what the formulas give: call minus put
    right = inputs["S"] - inputs["K"] * math.exp(-inputs["r"] * inputs["T"])   # what parity says it must be: S minus the strike's value today
    parity = {
        "call_minus_put": left,                                # left side
        "s_minus_pv_k": right,                                 # right side
        "gap": left - right,                                   # should be 0, apart from the computer's rounding (around 1e-13)
        "level_part": inputs["S"] - inputs["K"],               # part of the gap due to S being above or below K (index points)
        "interest_part": inputs["K"] * (1 - math.exp(-inputs["r"] * inputs["T"])),  # part due to interest on K over 30 days
    }
    # returns a dict of 5 floats (real output, rounded here):
    # {'call_minus_put': 26.435, 's_minus_pv_k': 26.435, 'gap': 0.0, 'level_part': 0.61, 'interest_part': 25.825}
    return parity


def price_curve(inputs):
    """Call and put value today if the S&P 500 stood at other levels (everything else unchanged): the data for the chart."""
    low = inputs["S"] * (1 - CURVE_RANGE)                      # 10% below today's level
    high = inputs["S"] * (1 + CURVE_RANGE)                     # 10% above
    step = (high - low) / (CURVE_POINTS - 1)                   # gap between two points on the line
    rows = []                                                  # one dict per S&P level
    for i in range(CURVE_POINTS):                              # i = 0, 1, ..., 60
        level = low + i * step                                 # the S&P level for this point
        p = black_scholes(level, inputs["K"], inputs["r"], inputs["sigma"], inputs["T"])   # same formula, only S changes
        rows.append({"sp500": round(level, 2), "call": round(p["call"], 2), "put": round(p["put"], 2)})   # keep 2 decimals
    curve = pd.DataFrame(rows).set_index("sp500")              # one row per S&P level
    # returns a DataFrame, 61 rows x 2 columns, prices in index points (real output, first and last rows):
    #              call     put
    # sp500
    # 6867.55      2.81  739.44
    # 6892.98      3.43  714.62
    # ...
    # 8393.67    793.17    3.67
    return curve


def fetch_market_option(inputs):
    """One real S&P 500 call: expiry closest to 30 days, strike closest to K, price = middle of bid and ask."""
    try:                                                       # the chain sometimes fails or is empty: never crash the page
        spx = yf.Ticker("^SPX")                                # Yahoo lists S&P 500 options under ^SPX (^GSPC has no chain)
        expiries = spx.options                                 # every listed expiry date, as text: ('2026-11-12', '2026-11-13', ...)
        today = date.fromisoformat(inputs["today"])            # today in New York, as a date
        expiry = min(expiries, key=lambda e: abs((date.fromisoformat(e) - today).days - DAYS))   # the expiry nearest to 30 days away
        calls = spx.option_chain(expiry).calls                 # all calls for that expiry: one row per strike
        row = calls.loc[(calls["strike"] - inputs["K"]).abs().idxmin()]   # the row whose strike is closest to our K
        bid = float(row["bid"])                                # best price a buyer offers right now
        ask = float(row["ask"])                                # best price a seller asks
        if not (bid > 0 and ask > 0):                          # zero or missing quotes (e.g. weekend): no fair price to compare with
            raise ValueError("Yahoo returned no bid and ask for this option (the market may be closed)")
        market = {
            "ok": True,                                        # the comparison can be shown
            "contract": str(row["contractSymbol"]),            # e.g. 'SPXW261211C07630000' = SPX weekly, 11 Dec 2026, Call, strike 7630
            "expiry": expiry,                                  # expiry date as text
            "days": (date.fromisoformat(expiry) - today).days, # calendar days left
            "strike": float(row["strike"]),                    # its strike
            "bid": bid,                                        # bid
            "ask": ask,                                        # ask
            "mid": (bid + ask) / 2,                            # the market price we use: halfway between bid and ask
        }
    except Exception as error:                                 # any failure: network, empty chain, no quotes...
        market = {"ok": False, "error": str(error)}            # keep the reason, the page shows it in one line
    # returns a dict, 8 values when it worked (real output, 12 Nov 2026):
    # {'ok': True, 'contract': 'SPXW261211C07630000', 'expiry': '2026-12-11', 'days': 29, 'strike': 7630.0,
    #  'bid': 130.9, 'ask': 131.5, 'mid': 131.2}
    # or 2 values when it failed, e.g. {'ok': False, 'error': 'Yahoo returned no bid and ask for this option (the market may be closed)'}
    return market


def compare_with_market(inputs, market):
    """Price the real option with Black-Scholes (its own strike and days) and compare with its market price."""
    comparison = dict(market)                                  # a copy, so the downloaded dict is left as it was
    if market["ok"]:                                           # only when we got a real price
        T_real = market["days"] / 365                          # its own time to expiry, in years (e.g. 29 days, not 30)
        model = black_scholes(inputs["S"], market["strike"], inputs["r"], inputs["sigma"], T_real)["call"]   # same S, r, sigma
        comparison["model"] = model                            # model price of the same contract
        comparison["diff"] = model - market["mid"]             # model minus market, index points
        comparison["diff_pct"] = (model / market["mid"] - 1) * 100   # the same, in % of the market price
    # returns a dict: the market dict plus 3 values (real output, rounded here):
    # {'ok': True, 'contract': 'SPXW261211C07630000', 'expiry': '2026-12-11', 'days': 29, 'strike': 7630.0,
    #  'bid': 130.9, 'ask': 131.5, 'mid': 131.2, 'model': 162.86, 'diff': 31.66, 'diff_pct': 24.1}
    # or, if the download failed, the same 2 values as fetch_market_option: {'ok': False, 'error': '...'}
    return comparison


def print_summary(inputs, prices, parity, comparison):
    """Print the key numbers in the terminal."""
    print(f"Prices downloaded {inputs['asof']} New York time")
    print(f"Inputs: S={inputs['S']}  K={inputs['K']:g}  r={inputs['r']:g}  sigma={inputs['sigma']:g}  T={inputs['days']}/365={inputs['T']:.6f}")
    print(f"d1={prices['d1']:.4f}  d2={prices['d2']:.4f}  N(d1)={prices['N_d1']:.4f}  N(d2)={prices['N_d2']:.4f}")
    print(f"Call price: {prices['call']:.4f}")
    print(f"Put price:  {prices['put']:.4f}")
    print(f"Call delta: {prices['delta_call']:.4f}   Put delta: {prices['delta_put']:.4f}")
    print(f"Parity: call - put = {parity['call_minus_put']:.4f}   S - K*exp(-rT) = {parity['s_minus_pv_k']:.4f}   gap = {parity['gap']:.1e}")
    if comparison["ok"]:                                       # the market comparison worked
        print(f"Market: {comparison['contract']} ({comparison['days']} days, strike {comparison['strike']:g})  "
              f"bid {comparison['bid']}  ask {comparison['ask']}  mid {comparison['mid']:.2f}")
        print(f"Model {comparison['model']:.2f}  vs market {comparison['mid']:.2f}: "
              f"{comparison['diff']:+.2f} ({comparison['diff_pct']:+.1f}%)")
    else:                                                      # it failed: say why, the page says the same
        print(f"Market comparison skipped: {comparison['error']}")
    # returns nothing; prints 8 lines (real output, 12 Nov 2026):
    # Prices downloaded 12 Nov 2026, 13:01 New York time
    # Inputs: S=7630.61  K=7630  r=0.04125  sigma=0.1748  T=30/365=0.082192
    # d1=0.0943  d2=0.0442  N(d1)=0.5376  N(d2)=0.5176
    # Call price: 165.8567
    # Put price:  139.4217
    # Call delta: 0.5376   Put delta: -0.4624
    # Parity: call - put = 26.4350   S - K*exp(-rT) = 26.4350   gap = 0.0e+00
    # Market: SPXW261211C07630000 (29 days, strike 7630)  bid 130.9  ask 131.5  mid 131.20
    # Model 162.86  vs market 131.20: +31.66 (+24.1%)
    return None


def main():
    inputs = get_inputs()                                      # step 1: download S, r, sigma and set K, T
    prices = black_scholes(inputs["S"], inputs["K"], inputs["r"], inputs["sigma"], inputs["T"])   # step 2: call, put, deltas
    parity = parity_check(inputs, prices)                      # step 3: call - put against S - K*e^(-rT)
    curve = price_curve(inputs)                                # step 4: call and put at other S&P levels, for the chart
    market = fetch_market_option(inputs)                       # step 5: one real option from the chain (or the reason it failed)
    comparison = compare_with_market(inputs, market)           # step 6: model price of that same option, and the gap
    print_summary(inputs, prices, parity, comparison)          # step 7: print the numbers
    build_page(inputs, prices, parity, curve, comparison)      # step 8: write the web page (code below)
    print(f"Saved {OUTPUT_PATH}")                              # tell the user where the page is


# ===========================================================================
# html / chart code
# ===========================================================================

ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"  # Apache ECharts, a fixed version
FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"
UPDATED = "9 Nov 2026"                   # the date this study was last changed (new, not committed yet); after a commit, re-read it with
                                          # git log -1 --format=%cs -- options-pricer
CPP_URL = "https://github.com/ManuCem/Macro-Quant-Lab/blob/main/options-pricer/option_pricer.cpp"   # the C++ file on GitHub

# Look: the "Lab" design every project page uses (see CLAUDE.md), in this project's own colour:
# plum header band, orchid accent. Chart colours: call = blue, put = orange (a pair colour-blind readers can tell apart),
# and the text always names the series in words too.
CSS = """
:root{color-scheme:light dark;--band:#3b1840;--band-ink:#e4e6ea;--brass:#b45fc4;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--call:#2f6fc0;--put:#c8662f}
@media (prefers-color-scheme:dark){:root{--band:#29102d;--brass:#d690e0;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--call:#6fa3e6;--put:#e58e62}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 "DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
h1,h2,.kpi b{font-family:"DM Serif Display",Georgia,serif;font-weight:400}
a{color:inherit}
.in{max-width:1000px;margin:0 auto;padding:0 max(20px,env(safe-area-inset-right)) 0 max(20px,env(safe-area-inset-left))}
.band{background:var(--band);color:var(--band-ink);padding:8px 0 96px}
a.back{display:inline-flex;align-items:center;min-height:44px;color:var(--band-ink);text-decoration:none;font-size:14px}
/* back link on the left, the date this study was last updated on the right */
.toprow{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.upd{display:inline-flex;align-items:center;min-height:44px;font-size:13px;color:var(--band-ink);opacity:.72;white-space:nowrap}
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
.panel .kpi{background:var(--page);border:0}
.panel .kpis{margin:0 0 18px}
.chart{width:100%;height:340px}
.label{margin:22px 0 6px;font-size:13px;font-weight:600;color:var(--ink-2)}
.label a{display:inline-flex;align-items:center;min-height:44px;color:var(--brass)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;vertical-align:middle}
.small{display:block;font-size:12px;color:var(--muted)}
/* the C++ copy box: the only block allowed to scroll sideways, inside its own frame */
pre.code{margin:0;padding:12px 16px;background:var(--page);border:1px solid var(--grid);border-radius:10px;overflow-x:auto;
  -webkit-overflow-scrolling:touch;font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;color:var(--ink)}
.cpp{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.cpp .label{display:flex;flex-wrap:wrap;align-items:center;gap:0 .3em;min-height:44px;margin:12px 0 4px}   /* both labels the same height, so the two boxes line up */
.kpi b{white-space:nowrap}                /* the colour dot never wraps away from its number */
/* Black-Scholes, step by step: formula on the left, today's number on the right; wraps on a phone */
.steps{margin:0 0 18px;border-top:1px solid var(--grid)}
.steps div{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 16px;padding:10px 0;border-bottom:1px solid var(--grid)}
.steps span{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:14px}
.steps b{font-variant-numeric:tabular-nums}
.gloss{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;margin:24px 0 0;padding-top:20px;border-top:1px solid var(--grid)}
.gloss div{margin:0}
.gloss dt{font-weight:700}
.gloss dd{margin:2px 0 0;color:var(--ink-2);font-size:15px}
.take{margin:0;padding-left:1.2rem}
.take li{margin:0 0 12px}
.take li::marker{color:var(--brass)}
.warn{margin:0;padding:12px 16px;border:1px dashed var(--axis);border-radius:10px;color:var(--ink-2)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--grid);text-align:right}
th:first-child,td:first-child{text-align:left;padding-left:0}
th{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.refs{margin:32px 0 0;padding:0 4px;font-size:13px;line-height:1.5;color:var(--muted)}
.refs h3{margin:0 0 2px;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.refs ul{list-style:none;padding:0;margin:0}
.refs a{display:flex;align-items:center;min-height:44px;padding:6px 0;color:var(--muted);text-decoration:none}
.refs b{font-weight:600;color:var(--ink-2);text-decoration:underline;text-decoration-color:var(--axis);text-underline-offset:3px}
.refs a:hover span{text-decoration:underline}
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}}
@media (max-width:640px){
  .chart{height:420px}
  .gloss,.cpp{grid-template-columns:1fr;gap:18px}
  th,td{padding:8px 4px;font-size:13px}
  .kpi{padding:14px}.kpi b{font-size:24px}
}
"""

JS = """
const DATA = __DATA__;                                          // everything Python computed, as JSON
const narrowMQ = window.matchMedia("(max-width: 640px)");       // true on a phone-width screen
const darkMQ = window.matchMedia("(prefers-color-scheme: dark)");   // true in dark mode
const isTouch = window.matchMedia("(pointer: coarse)").matches; // a finger instead of a mouse
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();  // read a colour token
const money = v => "$" + v.toFixed(2);                          // 165.8567 -> "$165.86"
const level = v => Math.round(v).toLocaleString("en-US");       // 7630.61 -> "7,631"
let chart = null;                                               // the ECharts instance, created once

function tipStyle() {                                           // tooltip look from the page tokens, never ECharts' default white box
  return {
    backgroundColor: css("--surface"),                          // white in light mode, near-black in dark mode
    borderColor: css("--grid"), borderWidth: 1,                 // the same thin border as the panels
    textStyle: {color: css("--ink"), fontFamily: "DM Sans, system-ui, sans-serif", fontSize: 13},  // readable text in both modes
    extraCssText: "box-shadow: 0 6px 20px rgba(0,0,0,.18); border-radius: 8px;",                    // a soft shadow lifts it off the chart
    axisPointer: {label: {backgroundColor: css("--ink-2"), color: css("--surface")}},              // any axis-pointer label uses the tokens too
  };
}

function curveOptions(narrow) {                                 // call and put value against the S&P 500 level
  const C = DATA.curve;
  const line = (name, key, color) => ({name, type: "line", data: C.sp500.map((x, i) => [x, C[key][i]]), showSymbol: false,
    lineStyle: {color, width: 2.5}, itemStyle: {color}});
  const axisStyle = {axisLine: {lineStyle: {color: css("--axis")}}, splitLine: {lineStyle: {color: css("--grid")}}};
  const series = [line("Call (right to buy)", "call", css("--call")), line("Put (right to sell)", "put", css("--put"))];
  series[0].markLine = {silent: true, symbol: "none", lineStyle: {color: css("--muted"), type: "dashed"},   // today's S&P level
    label: {color: css("--ink-2"), formatter: "Today " + level(DATA.S), position: "end"}, data: [{xAxis: DATA.S}]};
  return {
    animation: false, backgroundColor: "transparent", textStyle: {color: css("--ink-2"), fontFamily: "DM Sans, system-ui, sans-serif"},
    legend: narrow ? {bottom: 4, left: 8, orient: "vertical", itemGap: 6, textStyle: {color: css("--ink-2")}}   // below the plot on a phone
                   : {top: 6, left: 64, textStyle: {color: css("--ink-2")}},                                    // one row above it on desktop
    grid: narrow ? {left: 52, right: 22, top: 20, bottom: 104} : {left: 64, right: 32, top: 48, bottom: 54},
    tooltip: Object.assign(tipStyle(), {trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click", confine: true,
      formatter: ps => "S&amp;P 500 at " + level(ps[0].value[0]) + ps.map(p => "<br>" + p.marker + p.seriesName.split(" (")[0] + " " + money(p.value[1])).join("")}),
    xAxis: Object.assign({type: "value", min: C.sp500[0], max: C.sp500[C.sp500.length - 1], splitNumber: narrow ? 3 : 6,
      name: "S&P 500 level", nameLocation: "middle", nameGap: 30, nameTextStyle: {color: css("--muted")},
      axisLabel: {color: css("--muted"), hideOverlap: true, showMinLabel: false, showMaxLabel: false, formatter: level}}, axisStyle),  // no labels at the very edges: they were cut off
    yAxis: Object.assign({type: "value", axisLabel: {color: css("--muted"), formatter: v => "$" + v}}, axisStyle),
    series,
  };
}

function draw() {                                               // (re)build the chart: on load, phone rotation and theme change
  const div = document.getElementById("curve");
  if (!chart) chart = echarts.init(div);
  chart.setOption(curveOptions(narrowMQ.matches), true);
  chart.resize();
}
if (isTouch) document.querySelectorAll(".hint").forEach(h => h.textContent = "Tap");  // say "tap", not "hover", to touch users
narrowMQ.addEventListener("change", draw);                      // rebuild when a phone is rotated
darkMQ.addEventListener("change", draw);                        // rebuild in the new colours (tooltip included)
window.addEventListener("resize", () => chart && chart.resize());
draw();
"""

SOURCES = [                               # (who, what it gave us, link): one quiet line each after the last panel
    ("Yahoo Finance", "S&P 500 index (^GSPC), 13-week Treasury bill yield (^IRX), VIX (^VIX) and the S&P 500 option chain (^SPX), "
     "downloaded with yfinance", "https://finance.yahoo.com/quote/%5ESPX/options/"),
    ("Black and Scholes (1973)", "The Pricing of Options and Corporate Liabilities, Journal of Political Economy, the paper behind the formula",
     "https://www.jstor.org/stable/1831029"),
    ("Cboe", "how the VIX is calculated from a whole range of S&P 500 option prices", "https://www.cboe.com/tradable_products/vix/"),
]

GLOSSARY = [                              # (term, plain-language meaning): the ideas a reader needs for the panels below
    ("Call option", "The right, not the obligation, to buy the index at the strike on the expiry date. Worth something only if the index ends above the strike."),
    ("Put option", "The right to sell at the strike. Worth something only if the index ends below the strike: it works like insurance against a fall."),
    ("Strike (K) and expiry (T)", "The agreed price and the date. Here K is today's level rounded to the nearest 5 (\"at the money\") and T is 30 days, written in years."),
    ("Volatility (σ) and the VIX", "How much the index typically moves in a year, in %. The VIX is the market's own estimate for the next 30 days, worked out from option prices."),
    ("Risk-free rate (r)", "The interest on a safe 3-month US Treasury bill. Money due at expiry is worth a little less today: K × e^(−rT)."),
    ("N(x), the bell curve", "The share of a normal (bell-shaped) distribution to the left of x: a probability between 0 and 1. N(0) = 0.5."),
    ("Delta", "How much the option price moves when the index moves 1 point. A call delta of 0.5 means about 50 cents per point."),
    ("Bid, ask and mid", "The best prices buyers offer (bid) and sellers ask (ask). The mid, halfway between, is a fair estimate of the market price."),
]


def money(value):
    """Format a price in index points as dollars, e.g. 165.8567 -> '$165.86'."""
    # returns a str, e.g. money(165.8567) -> '$165.86', money(7640) -> '$7,640.00'
    return f"${value:,.2f}"


def signed(value, digits=2, prefix=""):
    """A number with an explicit sign and a real minus sign, e.g. -1.5 -> '−1.50', 31.66 with prefix '$' -> '+$31.66'."""
    text = f"{prefix}{abs(value):,.{digits}f}"                 # the size of the number, without its sign
    # returns a str, e.g. signed(-1.5) -> '−1.50', signed(31.66, 2, '$') -> '+$31.66', signed(0) -> '0.00'
    return ("+" if value > 0 else "−" if value < 0 else "") + text


def tile(value, label, color=None):
    """One headline number with its label; an optional dot names the series by its chart colour."""
    dot = f'<i class="dot" style="background:var({color})"></i>' if color else ""   # identity is in the text too, never colour alone
    # returns a str of HTML, e.g. '<div class="kpi"><b>$165.86</b><span>30-day call, strike 7,630</span></div>'
    return f'<div class="kpi"><b>{dot}{escape(value)}</b><span>{escape(label)}</span></div>'


def model_vs_market_words(c):
    """One phrase saying whether the model is above or below the market, e.g. 'the model is $31.66 (24.1%) above it'."""
    side = "above" if c["diff"] > 0 else "below"               # which side of the market the model lands
    # returns a str, e.g. 'the model is $31.66 (24.1%) above it'
    return f"the model is {money(abs(c['diff']))} ({abs(c['diff_pct']):.1f}%) {side} it"


def answer_text(inputs, prices, comparison):
    """The short answer at the top of the page, written from the numbers so it stays true after a re-run."""
    lead = (f"<b>About {money(prices['call'])} for a call and {money(prices['put'])} for a put.</b> With the S&amp;P 500 at "
            f"{inputs['S']:,.2f}, Black-Scholes prices {inputs['days']}-day options with a strike of {inputs['K']:,.0f} at those "
            f"values, using the VIX ({inputs['vix']:.2f}%) as volatility and the 3-month T-bill ({inputs['irx']:.2f}%) as the interest rate. ")
    if comparison["ok"]:                                       # we have a real price to compare with
        market = (f"The real call closest to ours (strike {comparison['strike']:,.0f}, {comparison['days']} days) trades at "
                  f"{money(comparison['mid'])}, so {model_vs_market_words(comparison)}.")
    else:                                                      # no market price this run
        market = "The real market price could not be downloaded on this run."
    # returns a str of HTML, about 400 characters, e.g.
    # '<b>About $165.86 for a call and $139.42 for a put.</b> With the S&amp;P 500 at 7,630.61, Black-Scholes prices 30-day options ...
    #  The real call closest to ours (strike 7,630, 29 days) trades at $131.20, so the model is $31.66 (24.1%) above it.'
    return lead + market


def why_gap_text(c):
    """Interpret the model-vs-market gap for the 'What it tells us' box."""
    if c["diff"] > 0:                                          # the model is too expensive
        text = ("<p><b>The model is too expensive, and the volatility input is the main suspect.</b> The VIX is not the volatility "
                "of this one option: it is an average over many strikes, and it leans on puts far below today's level, which are "
                "expensive because investors pay up for crash protection. So the VIX usually sits above the volatility traders "
                "price into an at-the-money option. A lower σ would bring the model down to the market.</p>"
                "<p>Leaving out dividends pushes the same way: the companies in the index pay dividends, which lower the expected "
                "future level of the index, and so make calls cheaper and puts dearer than this simple version says.</p>")
    else:                                                      # the model is too cheap
        text = ("<p><b>The model is too cheap.</b> The market is pricing more movement for this option than the VIX suggests, "
                "for example ahead of an event traders are worried about. A higher σ would bring the model up to the market.</p>"
                "<p>Dividends cannot explain this side of the gap: leaving them out makes the model call too expensive, not too cheap.</p>")
    # returns a str of HTML, two short paragraphs, e.g. '<p><b>The model is too expensive, and the volatility input is the main suspect.</b> ...'
    return text


def parity_words(parity):
    """How closely the two sides of parity agree, in words: 'to 9 decimal places' (it is a rounding error) or the gap itself."""
    if abs(parity["gap"]) < 1e-9:                              # smaller than 0.000000001: only the computer's rounding
        words = "to 9 decimal places"
    else:                                                      # a real gap (should never happen with these formulas)
        words = f"only up to a gap of {abs(parity['gap']):.6f}"
    # returns a str, e.g. 'to 9 decimal places'
    return words


def conclusions(inputs, prices, parity, comparison):
    """The 'What did we learn?' list, written from the numbers."""
    items = [
        (f"<b>Five numbers set the price.</b> S&amp;P 500 {inputs['S']:,.2f}, strike {inputs['K']:,.0f}, rate {inputs['r']:g}, "
         f"volatility {inputs['sigma']:g} and {inputs['days']} days give a call of {money(prices['call'])} and a put of "
         f"{money(prices['put'])}: about {prices['call'] / inputs['S'] * 100:.1f}% and {prices['put'] / inputs['S'] * 100:.1f}% "
         f"of the index for a month of protection."),
        (f"<b>Delta is the slope of the price line.</b> The call moves about {prices['delta_call']:.2f} and the put "
         f"{signed(prices['delta_put'])} for each point the index moves. The two always differ by exactly 1."),
        (f"<b>Parity holds {parity_words(parity)}.</b> Call − put equals S − K·e<sup>−rT</sup>, as it must for any "
         f"pricing that leaves no free money on the table. It is a check on the formulas, not on the market."),
    ]
    if comparison["ok"]:                                       # the market lesson, only when we had a market price
        items.append(f"<b>The market disagrees.</b> For the closest real call {model_vs_market_words(comparison)}. "
                     f"The model is only as good as its volatility input.")
    items.append("<b>Limits.</b> One snapshot on one day, with Yahoo's quotes, which can be delayed by about 15 minutes. "
                 "Black-Scholes assumes volatility and interest rates stay constant and that the index never jumps; real "
                 "markets break all three. The VIX is used as a proxy for this option's volatility, dividends are left "
                 "out, and the T-bill rate is used as quoted, without converting it to continuous compounding.")
    # returns a list of 5 HTML strings (4 if the market price failed), e.g.
    # ['<b>Five numbers set the price.</b> S&amp;P 500 7,630.61, strike 7,630, ...', '<b>Delta is the slope of the price line.</b> ...', ...,
    #  '<b>Limits.</b> One snapshot on one day, ...']
    return items


def inputs_table(inputs):
    """The five inputs: what they are, today's value, and the number that goes into the formula."""
    rows = [                                                   # (name, where it comes from, today's value, value in the formula)
        ("S · S&P 500 level", "Yahoo ^GSPC", f"{inputs['S']:,.2f}", f"{inputs['S']:g}"),
        ("K · Strike", f"S rounded to the nearest {STRIKE_STEP}", f"{inputs['K']:,.0f}", f"{inputs['K']:g}"),
        ("r · Interest rate", "13-week T-bill, Yahoo ^IRX", f"{inputs['irx']:.2f}%", f"{inputs['r']:g}"),
        ("σ · Volatility", "VIX, Yahoo ^VIX", f"{inputs['vix']:.2f}%", f"{inputs['sigma']:g}"),
        ("T · Time to expiry", f"{inputs['days']} days ÷ 365", f"{inputs['days']} days", f"{inputs['T']:.4f}"),
    ]
    head = "<tr><th>Input</th><th>Today</th><th>In the formula</th></tr>"   # 3 columns fit a 360px phone; the source sits under the name
    body = "".join(f'<tr><td>{escape(n)}<span class="small">{escape(src)}</span></td><td>{escape(v)}</td><td>{escape(f)}</td></tr>'
                   for n, src, v, f in rows)
    # returns a str of HTML: a header and 5 rows, e.g. <tr><td>σ · Volatility<span class="small">VIX, Yahoo ^VIX</span></td><td>17.48%</td><td>0.1748</td></tr>
    return f'<div class="scroll"><table>{head}{body}</table></div>'


def cpp_box(inputs, prices):
    """The five lines to paste at the top of option_pricer.cpp, and what the program should then print."""
    code = (f"double S = {inputs['S']:g};\n"                   # :g writes 7630.61, not 7630.610000
            f"double K = {inputs['K']:g};\n"
            f"double r = {inputs['r']:g};\n"
            f"double sigma = {inputs['sigma']:g};\n"
            f"double T = {inputs['days']}.0 / 365.0;")        # the same fraction Python uses, so both see the same number
    output = (f"Call price: {prices['call']:.4f}\n"            # the C++ program prints these exact lines
              f"Put price:  {prices['put']:.4f}\n"
              f"Call delta: {prices['delta_call']:.4f}")
    # returns a str of HTML: two labelled code boxes side by side (stacked on a phone), e.g.
    # '<div class="cpp"><div><p class="label">Paste at the top of ...</p><pre class="code">double S = 7630.61;\ndouble K = 7630; ...</pre></div> ...'
    return ('<div class="cpp">'
            f'<div><p class="label">Paste at the top of <a href="{CPP_URL}" target="_blank" rel="noopener">option_pricer.cpp</a></p>'
            f'<pre class="code">{escape(code)}</pre></div>'
            f'<div><p class="label">It should print</p><pre class="code">{escape(output)}</pre></div></div>'
            '<p class="note">Compile and run: <code>g++ option_pricer.cpp -o option_pricer</code>, then <code>./option_pricer</code>.</p>')


def steps_block(inputs, prices):
    """Black-Scholes in four lines, each with today's number."""
    rows = [                                                   # (formula, today's value)
        ("σ√T", f"{prices['vol_t']:.4f}"),
        ("d1 = [ln(S/K) + (r + σ²/2)·T] / σ√T", f"{prices['d1']:.4f}"),
        ("d2 = d1 − σ√T", f"{prices['d2']:.4f}"),
        ("N(d1), N(d2)", f"{prices['N_d1']:.4f}, {prices['N_d2']:.4f}"),
        ("Call = S·N(d1) − K·e^(−rT)·N(d2)", money(prices["call"])),
        ("Put = K·e^(−rT)·N(−d2) − S·N(−d1)", money(prices["put"])),
    ]
    items = "".join(f"<div><span>{escape(f)}</span><b>{escape(v)}</b></div>" for f, v in rows)
    # returns a str of HTML: 6 rows, e.g. <div><span>d2 = d1 − σ√T</span><b>0.0442</b></div>
    return f'<div class="steps">{items}</div>'


def parity_table(parity):
    """The two sides of put-call parity and the gap between them."""
    rows = [("Call − put", f"{parity['call_minus_put']:.4f}"),
            ("S − K·e^(−rT)", f"{parity['s_minus_pv_k']:.4f}"),
            ("Gap", f"{parity['gap']:.1e}")]                   # scientific notation: the gap is around 0.00000000000003
    body = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td></tr>" for a, b in rows)
    # returns a str of HTML: 3 rows, e.g. <tr><td>Call − put</td><td>26.4350</td></tr>
    return f'<div class="scroll"><table><tr><th>Side</th><th>Value</th></tr>{body}</table></div>'


def market_table(c):
    """The real option against the model: contract, quotes, the two prices and the gap."""
    expiry = date.fromisoformat(c["expiry"]).strftime("%d %b %Y")   # '2026-12-11' -> '11 Dec 2026'
    rows = [("Contract", c["contract"]),
            ("Strike · expiry", f"{c['strike']:,.0f} · {expiry} ({c['days']} days)"),
            ("Bid · ask", f"{money(c['bid'])} · {money(c['ask'])}"),
            ("Market price (mid)", money(c["mid"])),
            ("Model price (same strike and days)", money(c["model"])),
            ("Model − market", f"{signed(c['diff'], 2, '$')} ({signed(c['diff_pct'], 1)}%)")]
    body = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td></tr>" for a, b in rows)
    # returns a str of HTML: 6 rows, e.g. <tr><td>Market price (mid)</td><td>$131.20</td></tr>
    return f'<div class="scroll"><table><tr><th>Real call</th><th>Value</th></tr>{body}</table></div>'


def panel(number, question, finding, how, body, so=""):
    """One numbered section: a question, its one-line finding, how to read it, the chart or table, and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""          # optional reading guide
    so_html = f'<div class="so">{so}</div>' if so else ""                                  # optional takeaway
    # returns a str of HTML, e.g. '<section class="panel"><p class="tag">01</p><h2>What goes into the price today?</h2><p class="dek">...'
    return (f'<section class="panel"><p class="tag">{number:02d}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def references():
    """The quiet 'References' list after the last panel: no panel box, no question, one muted line per source."""
    items = "".join(                                           # one <li> per source; the whole line is the link (big tap target)
        f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><span><b>{escape(who)}</b>: {escape(what)}.</span></a></li>'
        for who, what, u in SOURCES)
    # returns a str of HTML: a small heading and 3 links, e.g.
    # '<aside class="refs" aria-label="References"><h3>References</h3><ul><li><a href="https://finance.yahoo.com/..." ...>...</a></li> ...</ul></aside>'
    return f'<aside class="refs" aria-label="References"><h3>References</h3><ul>{items}</ul></aside>'


def build_page(inputs, prices, parity, curve, comparison):
    """Assemble the standalone HTML page and write it to disk."""
    payload = {                                                # everything the page's JavaScript needs
        "S": inputs["S"],                                      # today's level, for the dashed "Today" line
        "curve": {"sp500": curve.index.tolist(), "call": curve["call"].tolist(), "put": curve["put"].tolist()},
    }
    c = comparison                                             # short name
    move = inputs["S"] * prices["vol_t"]                       # one typical move over 30 days, in index points
    gap_words = "above" if parity["level_part"] >= 0 else "below"   # is today's level above or below the strike?

    kpis = "".join([                                           # the four headline numbers under the header
        tile(money(prices["call"]), f"{inputs['days']}-day call, strike {inputs['K']:,.0f}", "--call"),
        tile(money(prices["put"]), f"{inputs['days']}-day put, strike {inputs['K']:,.0f}", "--put"),
        tile(f"{prices['delta_call']:.2f}", f"Call delta · put {signed(prices['delta_put'])}"),
        tile(signed(c["diff"], 2, "$"), f"Model − market, real call ({signed(c['diff_pct'], 1)}%)") if c["ok"]
        else tile(f"{inputs['vix']:.2f}%", "VIX, the volatility input"),
    ])
    gloss = '<dl class="gloss">' + "".join(f"<div><dt>{escape(t)}</dt><dd>{escape(d)}</dd></div>" for t, d in GLOSSARY) + "</dl>"
    value_tiles = ('<div class="kpis">'
                   + tile(money(prices["call"]), "Call price", "--call") + tile(money(prices["put"]), "Put price", "--put")
                   + tile(f"{prices['delta_call']:.4f}", "Call delta") + tile(signed(prices["delta_put"], 4), "Put delta") + "</div>")
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in conclusions(inputs, prices, parity, c)) + "</ol>"

    if c["ok"]:                                                # panel 5 with a real comparison
        p5 = panel(5, "Does the model match the market?",
                   f"Model {money(c['model'])}, market {money(c['mid'])}: {model_vs_market_words(c)}.",
                   f"The real option closest to ours: the S&amp;P 500 call with strike {c['strike']:,.0f}, {c['days']} days "
                   "from expiry. Its market price is the middle of the best bid and ask. The model is run again for this exact "
                   "strike and number of days, with the same S, r and σ, so the two prices describe the same contract.",
                   market_table(c), why_gap_text(c))
    else:                                                      # the chain failed: one short message, no crash
        p5 = panel(5, "Does the model match the market?", "No market price on this run.", "",
                   f'<p class="warn">The option chain could not be used: {escape(c["error"])}. Run the script again during '
                   "US market hours (9:30 to 16:00 New York time).</p>")

    panels = "".join([
        panel(1, "What goes into the price today?",
              f"S&amp;P 500 {inputs['S']:,.2f}, VIX {inputs['vix']:.2f}%, T-bill {inputs['irx']:.2f}%, {inputs['days']} days.",
              "Black-Scholes needs exactly five numbers. Three come from the market today (S, r and σ); two we choose: the strike "
              f"(today's level rounded to the nearest {STRIKE_STEP}, so the option is \"at the money\") and the time "
              f"({inputs['days']} days). The right column is each number as the formula uses it: percentages become decimals, "
              "days become years.",
              inputs_table(inputs) + cpp_box(inputs, prices),
              f"<p>Four of the five inputs are known for sure today. Only volatility is a guess about the future, and we borrow "
              f"the market's own guess: the VIX. That makes σ the input that matters most, as panel 5 shows.</p>"),
        panel(2, "How does Black-Scholes turn five numbers into a price?",
              "Measure the distance to the strike in typical moves, then read probabilities off the bell curve.",
              f"Each line is one step of the formula, with today's number on the right. σ√T = {prices['vol_t']:.4f} is the "
              f"typical move over {inputs['days']} days: {prices['vol_t'] * 100:.1f}%, or about {move:,.0f} index points. d1 and "
              "d2 say how many of those moves today's level sits above the strike; N() turns them into probabilities.",
              steps_block(inputs, prices) + gloss,
              f"<p>The call is what you expect to receive, S·N(d1), minus what you expect to pay, the strike's value today times "
              f"the chance of paying it, N(d2) = {prices['N_d2']:.2f}. With the index right at the strike these chances sit near "
              f"one half, so the call and the put land close to each other; the gap that remains is mostly interest "
              f"(panels 3 and 4).</p>"),
        panel(3, "What are a call and a put worth?",
              f"Call {money(prices['call'])}, put {money(prices['put'])}: about {prices['call'] / inputs['S'] * 100:.1f}% and "
              f"{prices['put'] / inputs['S'] * 100:.1f}% of the index.",
              "The two lines show what the call and the put would be worth today if the S&amp;P 500 stood at another level, with "
              "every other input unchanged. The dashed line is today's level. The steepness of each line there is its delta. "
              'Prices are in index points, which are dollars per unit of the index (one real contract covers 100 units). '
              '<span class="hint">Hover over or click</span> the chart to read the values.',
              value_tiles + '<div id="curve" class="chart" role="img" aria-label="Call and put value against the S&amp;P 500 level"></div>',
              f"<p>The call delta is {prices['delta_call']:.2f}: if the index rose 10 points the call would gain about "
              f"{money(10 * prices['delta_call'])} and the put would lose about {money(-10 * prices['delta_put'])}. The call "
              f"costs {money(prices['call'] - prices['put'])} more than the put: today's level is {abs(parity['level_part']):.2f} "
              f"points {gap_words} the strike, and holding the strike's cash for {inputs['days']} days is worth "
              f"{money(parity['interest_part'])} of interest. The next panel shows why that sum is not a coincidence.</p>"),
        panel(4, "Do the call and the put agree with each other?",
              f"Yes: call − put = {parity['call_minus_put']:.4f} and S − K·e<sup>−rT</sup> = {parity['s_minus_pv_k']:.4f}.",
              "Put-call parity. Buying a call and selling a put with the same strike and expiry pays exactly (index − strike) at "
              "expiry, whatever happens: the same as owning the index and owing the strike. Two positions that always pay the same "
              "must cost the same today, so call − put has to equal S − K·e<sup>−rT</sup>. No volatility is involved.",
              parity_table(parity),
              f"<p>The two sides match {parity_words(parity)}: any gap left is only the computer's rounding, so the call and put "
              f"formulas are consistent with each other. If real prices broke this rule, a trader could buy the cheap side, sell the dear side and lock in "
              f"a riskless profit, which is why markets keep it close (apart from dividends, which this simple version leaves out).</p>"),
        p5,
        panel(6, "What did we learn?", "Takeaways, then the limits.", "", take),
    ]) + references()                                          # the sources follow the last panel as a quiet list, not a panel

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>S&amp;P 500 Option Pricer</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
<script src="{ECHARTS_URL}"></script>
</head>
<body>
<header class="band"><div class="in">
<div class="toprow"><a class="back" href="../index.html">&larr; Macro Quant Lab</a><span class="upd">Updated {UPDATED}</span></div>
<p class="eyebrow">Derivatives</p>
<h1>What should an S&amp;P 500 option cost today?</h1>
<p class="answer">{answer_text(inputs, prices, c)}</p>
<p class="meta">Prices downloaded {inputs['asof']} New York time · Yahoo Finance · Not investment advice</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{panels}
</main>
<footer><div class="in">Generated by option_pricer.py from Yahoo Finance data (S&amp;P 500 ^GSPC, 13-week T-bill ^IRX, VIX ^VIX,
S&amp;P 500 options ^SPX). The same Black-Scholes maths is in option_pricer.cpp. Learning project, not investment advice.</div></footer>
<script>{JS.replace("__DATA__", json.dumps(payload))}</script>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # save the page
    # returns nothing; writes option_pricer.html (~25 KB: the HTML text plus 183 numbers for the chart as JSON)
    return None


if __name__ == "__main__":
    main()
