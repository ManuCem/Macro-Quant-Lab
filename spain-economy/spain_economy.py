"""
What drove Spain's economy from the euro boom to today?
-------------------------------------------------------
A data-only tour of the Spanish economy since 1995, split into six periods (one tab each):

    1995-2007  Euro boom            interest rates fall to German levels, credit and housing boom
    2008-2009  The bubble bursts    global financial crisis, construction collapses, jobs lost
    2010-2013  Euro debt crisis     borrowing costs jump, second recession, unemployment peaks
    2014-2019  Recovery             exports and the current account turn around
    2020-2022  Covid and inflation  lockdowns hit tourism, then the energy-price shock
    2023-today Since 2023           growth, where it comes from, and what still lags

The page shows numbers and the economic mechanism behind them. It does not judge governments
or policies: every period also shows what was fragile, with the data that measures it.

Key terms (explained again on the page):
    real (vs nominal)   with inflation removed, so it measures quantities, not prices
    real interest rate  interest rate minus inflation: what borrowing really costs
    current account     what a country earns from abroad minus what it pays abroad (% of GDP)
    unit labour cost    wage cost of producing one unit of output
    spread              extra yield Spain pays over Germany on 10-year bonds, in basis points
    1 basis point (bp)  0.01 percentage point; 100 bp = 1 percentage point

Data (all free, no key):
    Eurostat API   GDP, investment, exports, GDP per person, unemployment, inflation (HICP),
                   government debt and balance, construction, unit labour costs, productivity,
                   population, migration, tourism, temporary contracts, current account
    FRED           10-year bond yields (OECD), 3-month interbank rate (OECD), ECB policy rates,
                   house prices and private credit (BIS)

Output: spain-economy/spain_economy.html (one standalone page with tabs, drawn with Apache ECharts)
        spain-economy/csv/annual.csv, quarterly.csv, monthly.csv (the tables behind the charts)

Run:
    pip install pandas numpy requests
    python spain-economy/spain_economy.py            # download everything and build the page
    python spain-economy/spain_economy.py --cached   # rebuild the page from the saved CSVs (no download)

Layout of this file (see CLAUDE.md):
    1. python / data code  -> settings, downloads, calculations, and def main()
    2. html / chart code   -> builds the web page and the charts
"""

import json                               # turns Python lists/dicts into text the browser's JavaScript can read
import sys                                # reads the optional --cached flag from the command line
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import numpy as np                        # maths on arrays (strides when decoding Eurostat replies)
import pandas as pd                       # tables (DataFrames) and time series
import requests                           # downloads the Eurostat JSON replies


# ===========================================================================
# python / data code
# ===========================================================================

HERE = Path(__file__).parent                                   # the spain-economy folder
OUTPUT_PATH = HERE / "spain_economy.html"                      # the web page we write
CSV_DIR = HERE / "csv"                                         # where the three data tables are saved
EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{}"   # {} = dataset code
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"                          # {} = FRED series id
FIRST_YEAR = 1995                         # Eurostat national accounts start in 1995: the start of the study
START = "1995-01-01"                      # the same start as a date, for monthly and quarterly data
UPDATED = "22 Nov 2026"                   # shown as "Updated ..." in the header (first build of this study)

COUNTRIES = {"ES": "es", "EA": "ea", "DE": "de", "FR": "fr", "IT": "it"}   # Eurostat geo code -> short column suffix
EURO_AREA_CODES = ["EA20", "EA21"]       # euro-area aggregates with fixed members over time; tables differ in which they have
NAMES = {"es": "Spain", "ea": "Euro area", "de": "Germany", "fr": "France", "it": "Italy"}   # suffix -> name on the page

PERIODS = [                               # the six tabs: key, years shown, name, short name (chart bands), first and last day (None = latest data)
    {"key": "boom", "years": "1995–2007", "name": "Euro boom", "short": "Boom", "start": "1995-01-01", "end": "2007-12-31"},
    {"key": "bust", "years": "2008–2009", "name": "The bubble bursts", "short": "Bust", "start": "2008-01-01", "end": "2009-12-31"},
    {"key": "debt", "years": "2010–2013", "name": "Euro debt crisis", "short": "Debt crisis", "start": "2010-01-01", "end": "2013-12-31"},
    {"key": "recovery", "years": "2014–2019", "name": "Recovery", "short": "Recovery", "start": "2014-01-01", "end": "2019-12-31"},
    {"key": "covid", "years": "2020–2022", "name": "Covid and inflation", "short": "Covid", "start": "2020-01-01", "end": "2022-12-31"},
    {"key": "today", "years": "2023–today", "name": "Since 2023", "short": "Since 2023", "start": "2023-01-01", "end": None},
]


def fetch_eurostat(dataset, euro_area=EURO_AREA_CODES, **filters):
    """Download one Eurostat table through its JSON API; one column per country, one row per period.
    euro_area = which euro-area codes to try, in order of preference, when geo includes "EA"."""
    geo = filters.pop("geo")                                   # the countries asked for, e.g. ["ES", "EA"] or "ES"
    geo = [geo] if isinstance(geo, str) else list(geo)         # always a list
    if "EA" in geo:                                            # "EA" here means "the euro area", whatever code this table uses
        geo += [c for c in euro_area if c != "EA"]             # also ask for the preferred aggregates (by default EA20, EA21)
    params = {"format": "JSON", "lang": "EN", "geo": geo, **filters}   # every filter fixes one dimension (unit, item, ...)
    reply = requests.get(EUROSTAT_URL.format(dataset), params=params, timeout=120).json()   # JSON-stat reply
    if "value" not in reply:                                   # Eurostat answers errors with an "error" field instead of data
        raise RuntimeError(f"Eurostat {dataset}: {reply.get('error')}")   # stop with a readable message
    dims, sizes = reply["id"], reply["size"]                   # dimension names in order, and how many categories each has
    strides = [int(np.prod(sizes[i + 1:])) for i in range(len(sizes))]   # position step of each dimension in the flat value list
    names = {d: {pos: code for code, pos in reply["dimension"][d]["category"]["index"].items()} for d in ("geo", "time")}  # position -> code
    rows = []                                                  # one (period, country, value) tuple per number
    for flat, value in reply["value"].items():                 # values come as {"flat position": number}, missing ones are skipped
        flat = int(flat)                                       # the key is text, e.g. "17"
        country = names["geo"][(flat // strides[dims.index("geo")]) % sizes[dims.index("geo")]]   # which country this number is for
        time = names["time"][(flat // strides[dims.index("time")]) % sizes[dims.index("time")]]   # which period
        rows.append((time, country, value))                    # keep it
    table = pd.DataFrame(rows, columns=["period", "geo", "value"]).pivot(index="period", columns="geo", values="value")  # wide
    table.index = [period_to_date(p) for p in table.index]     # "2007", "2007-Q3", "2007-09" -> dates
    table = table.sort_index()                                 # oldest first
    if "EA" in geo:                                            # keep ONE euro-area column, named "EA"
        code = next(c for c in list(euro_area) + ["EA"] if c in table)   # the first preferred code this table has
        table["EA"] = table[code]                              # e.g. EA20 -> "EA" (the same members over the whole history)
        table = table.drop(columns=[c for c in EURO_AREA_CODES if c in table])   # drop the other codes
    # returns a DataFrame, one row per period, one column per country code, e.g.
    # fetch_eurostat("nama_10_gdp", unit="CLV_PCH_PRE", na_item="B1GQ", geo=["ES", "EA"]) -> 51 rows x 2 columns:
    #               EA   ES
    # 2024-01-01   1.3  3.7
    # 2025-01-01   1.2  2.6
    return table


def period_to_date(text):
    """Turn a Eurostat period label into the date it starts on."""
    if "-Q" in text:                                           # quarterly, e.g. "2007-Q3"
        year, quarter = text.split("-Q")                       # "2007", "3"
        date = pd.Timestamp(int(year), 3 * int(quarter) - 2, 1)   # Q3 starts in month 7
    elif len(text) == 4:                                       # annual, e.g. "2007"
        date = pd.Timestamp(int(text), 1, 1)                   # 1 January
    else:                                                      # monthly, e.g. "2007-09"
        date = pd.Timestamp(text + "-01")                      # first day of the month
    # returns a pandas Timestamp, e.g. period_to_date("2007-Q3") -> Timestamp('2007-07-01'), period_to_date("2007") -> Timestamp('2007-01-01')
    return date


def fetch_fred(series_id):
    """Download one FRED series as a pandas Series indexed by date."""
    table = pd.read_csv(FRED_URL.format(series_id), index_col=0, parse_dates=True)   # CSV: date (index) + value
    series = pd.to_numeric(table.iloc[:, 0], errors="coerce").dropna()   # numbers only; "." (missing) is dropped
    # returns a pandas Series, e.g. fetch_fred("IRLTLT01ESM156N") (Spain 10-year yield, monthly, %, 1980 -> Oct 2026):
    # observation_date
    # 2026-09-01    3.93
    # 2026-10-01    4.07
    return series


def to_years(table):
    """Annual Eurostat table: dates (1 January) become plain year numbers, from 1995 on."""
    table = table.copy()                                       # do not change the caller's table
    table.index = table.index.year                             # 2007-01-01 -> 2007
    table = table.loc[FIRST_YEAR:]                             # the study starts in 1995
    # returns the same DataFrame with an int index, e.g.
    #           EA   ES
    # 2024     1.3  3.7
    # 2025     1.2  2.6
    return table


def build_annual():
    """One table, one row per year since 1995: growth, debt, construction, costs, people and tourism."""
    geos = list(COUNTRIES)                                     # ["ES", "EA", "DE", "FR", "IT"]
    col = {}                                                   # column name -> Series, joined into one table at the end
    growth = to_years(fetch_eurostat("nama_10_gdp", unit="CLV_PCH_PRE", na_item="B1GQ", geo=geos))   # real GDP, % change on the year before
    for geo, key in COUNTRIES.items():                         # one growth column per country
        col[f"growth_{key}"] = growth[geo]                     # e.g. growth_es
    inv = to_years(fetch_eurostat("nama_10_gdp", unit="PC_GDP", na_item="P51G", geo=["ES", "EA"]))   # investment (gross fixed capital formation), % of GDP
    col["inv_es"], col["inv_ea"] = inv["ES"], inv["EA"]      # Spain and euro area
    exports = to_years(fetch_eurostat("nama_10_gdp", unit="PC_GDP", na_item="P6", geo=["ES", "EA"]))   # exports of goods and services, % of GDP
    col["exports_es"], col["exports_ea"] = exports["ES"], exports["EA"]
    pps = to_years(fetch_eurostat("nama_10_pc", unit="PC_EU27_2020_HAB_MPPS_CP", na_item="B1GQ", geo=["ES", "EA"]))   # GDP per person in PPS, EU = 100
    col["pps_es"], col["pps_ea"] = pps["ES"], pps["EA"]
    gdppc = to_years(fetch_eurostat("nama_10_pc", unit="CLV10_EUR_HAB", na_item="B1GQ", geo=["ES", "EA"]))   # real GDP per person, euros at 2010 prices
    col["gdppc_es"], col["gdppc_ea"] = gdppc["ES"], gdppc["EA"]
    debt = to_years(fetch_eurostat("gov_10dd_edpt1", na_item="GD", unit="PC_GDP", sector="S13", geo=["ES", "EA", "DE"]))   # government debt, % of GDP
    col["debt_es"], col["debt_ea"], col["debt_de"] = debt["ES"], debt["EA"], debt["DE"]
    balance = to_years(fetch_eurostat("gov_10dd_edpt1", na_item="B9", unit="PC_GDP", sector="S13", geo=["ES", "EA"]))   # budget balance (+ surplus / - deficit), % of GDP
    col["balance_es"], col["balance_ea"] = balance["ES"], balance["EA"]
    gva_f = to_years(fetch_eurostat("nama_10_a10", unit="CP_MEUR", na_item="B1G", nace_r2="F", geo=["ES", "EA"]))       # construction value added, million euros
    gva_all = to_years(fetch_eurostat("nama_10_a10", unit="CP_MEUR", na_item="B1G", nace_r2="TOTAL", geo=["ES", "EA"]))  # all industries
    col["constr_gva_es"] = gva_f["ES"] / gva_all["ES"] * 100   # construction's share of the Spanish economy, %
    col["constr_gva_ea"] = gva_f["EA"] / gva_all["EA"] * 100   # same for the euro area
    jobs_f = to_years(fetch_eurostat("nama_10_a10_e", unit="THS_PER", na_item="EMP_DC", nace_r2="F", geo="ES"))        # people working in construction, thousands
    jobs_all = to_years(fetch_eurostat("nama_10_a10_e", unit="THS_PER", na_item="EMP_DC", nace_r2="TOTAL", geo="ES"))  # people working in all industries, thousands
    col["constr_jobs_es"], col["jobs_es"] = jobs_f["ES"], jobs_all["ES"]   # national-accounts employment (consistent with GDP)
    col["constr_jobs_share_es"] = jobs_f["ES"] / jobs_all["ES"] * 100      # construction's share of all jobs, %
    ulc = to_years(fetch_eurostat("nama_10_lp_ulc", unit="I15", na_item="NULC_PER", geo=["ES", "DE", "EA"]))   # nominal unit labour cost, 2015 = 100
    for geo, key in [("ES", "es"), ("DE", "de"), ("EA", "ea")]:   # rebase to 1999 = 100, the year the euro started
        col[f"ulc_{key}"] = ulc[geo] / ulc.loc[1999, geo] * 100
    prod = to_years(fetch_eurostat("nama_10_lp_ulc", unit="I15", na_item="RLPR_HW", geo=["ES", "EA"]))   # real output per hour worked, 2015 = 100
    for geo, key in [("ES", "es"), ("EA", "ea")]:            # rebase to 2007 = 100, the last year before the crisis
        col[f"prod_{key}"] = prod[geo] / prod.loc[2007, geo] * 100
    level = to_years(fetch_eurostat("nama_10_lp_ulc", unit="PC_EU27_2020_MPPS_CP", na_item="NLPR_HW", geo=["ES", "EA"]))   # output per hour in PPS, EU = 100
    col["prodlvl_es"], col["prodlvl_ea"] = level["ES"], level["EA"]   # the LEVEL of productivity, comparable across countries
    pop = to_years(fetch_eurostat("demo_pjan", age="TOTAL", sex="T", unit="NR", geo="ES"))   # population on 1 January
    col["pop_es"] = pop["ES"] / 1e6                            # in millions
    netmig = to_years(fetch_eurostat("demo_gind", indic_de="CNMIGRATRT", geo="ES"))          # net migration per 1,000 residents
    col["netmig_es"] = netmig["ES"]
    nights = to_years(fetch_eurostat("tour_occ_ninat", c_resid="FOR", nace_r2="I551-I553", unit="NR", geo="ES"))   # nights spent by foreign tourists
    col["nights_es"] = nights["ES"] / 1e6                      # in millions
    temp = to_years(fetch_eurostat("lfsa_etpgan", unit="PC", sex="T", age="Y15-64", citizen="TOTAL", geo=["ES", "EA"]))   # temporary employees, % of employees
    col["temp_es"], col["temp_ea"] = temp["ES"], temp["EA"]
    table = pd.DataFrame(col).loc[FIRST_YEAR:]                 # one table, matched by year
    table["emp_growth_es"] = table["jobs_es"].pct_change() * 100   # % change in the number of people working
    table["perworker_growth_es"] = ((1 + table["growth_es"] / 100) / (1 + table["emp_growth_es"] / 100) - 1) * 100   # growth of output per worker, %
    table.index.name = "year"                                  # header of the first CSV column
    # returns a DataFrame, one row per year (1995 -> 2025, 31 rows x 37 columns), e.g. a few columns of the last rows:
    #       growth_es  growth_ea  debt_es  temp_es  pop_es  emp_growth_es
    # year
    # 2024        3.7        1.3    101.4     16.0   48.62           3.01
    # 2025        2.6        1.2    100.5     15.4   49.13           2.61
    return table


def build_quarterly():
    """One table, one row per quarter since 1995: real GDP, house prices, private credit, current account."""
    geos = list(COUNTRIES)                                     # ["ES", "EA", "DE", "FR", "IT"]
    col = {}                                                   # column name -> Series
    gdp = fetch_eurostat("namq_10_gdp", unit="CLV10_MEUR", s_adj="SCA", na_item="B1GQ", geo=geos)   # real GDP, million euros at 2010 prices, seasonally adjusted
    for geo, key in COUNTRIES.items():                         # one GDP column per country
        col[f"gdp_{key}"] = gdp[geo]
    col["house_real_es"] = fetch_fred("QESR628BIS")            # BIS real residential property prices, Spain (index, inflation removed)
    col["credit_es"] = fetch_fred("QESPAM770A")                # BIS credit to the private non-financial sector, % of GDP
    col["credit_hh_es"] = fetch_fred("QESHAM770A")             # ... to households, % of GDP
    col["credit_nfc_es"] = fetch_fred("QESNAM770A")            # ... to non-financial companies, % of GDP
    ca = fetch_eurostat("bop_gdp6_q", freq="Q", bop_item="CA", partner="WRL_REST", stk_flow="BAL", unit="PC_GDP", s_adj="NSA", geo="ES")   # current account, % of GDP (freq="Q": the table also holds yearly rows)
    col["ca_es"] = ca["ES"]                                    # one quarter at a time (jumps with the tourist season)
    table = pd.DataFrame(col).loc[START:]                      # one table, matched by quarter start date
    table["ca4_es"] = table["ca_es"].rolling(4).mean()         # average of the last 4 quarters: removes the seasonal swing
    table.index.name = "date"                                  # header of the first CSV column
    # returns a DataFrame, one row per quarter (1995-Q1 -> 2026-Q3, 127 rows x 11 columns), e.g. (rounded; BIS credit ends earlier):
    #               gdp_es     gdp_ea  house_real_es  credit_es  ca_es  ca4_es
    # date
    # 2026-04-01  336755.8  2939830.6         107.06        NaN    2.0    2.72
    # 2026-07-01  338893.0  2951900.6            NaN        NaN    NaN     NaN
    return table


def build_monthly():
    """One table, one row per month since 1995: unemployment, inflation, interest rates and yields."""
    col = {}                                                   # column name -> Series
    unemp = fetch_eurostat("une_rt_m", s_adj="SA", age="TOTAL", sex="T", unit="PC_ACT", geo=["ES", "EA"])   # unemployment rate, %
    col["unemp_es"], col["unemp_ea"] = unemp["ES"], unemp["EA"]
    youth = fetch_eurostat("une_rt_m", s_adj="SA", age="Y_LT25", sex="T", unit="PC_ACT", geo="ES")   # unemployment of under-25s, %
    col["youth_es"] = youth["ES"]
    # inflation: consumer prices vs a year earlier, %. For the euro area we use the official series ("EA": the members of
    # each month), which starts in 1997 and is the inflation the ECB aimed at; the fixed 20-member series only starts in 2000
    hicp = fetch_eurostat("prc_hicp_minr", euro_area=["EA"], unit="RCH_A", coicop18="TOTAL", geo=["ES", "EA"])
    col["infl_es"], col["infl_ea"] = hicp["ES"], hicp["EA"]
    energy = fetch_eurostat("prc_hicp_minr", euro_area=["EA"], unit="RCH_A", coicop18="NRG", geo=["ES", "EA"])   # energy prices only, % vs a year earlier
    col["infl_nrg_es"], col["infl_nrg_ea"] = energy["ES"], energy["EA"]
    col["y10_es"] = fetch_fred("IRLTLT01ESM156N")              # Spain 10-year government bond yield, %
    col["y10_de"] = fetch_fred("IRLTLT01DEM156N")              # Germany 10-year government bond yield, %
    col["rate3m_es"] = fetch_fred("IR3TIB01ESM156N")           # Spain 3-month interbank rate (Euribor from 1999), %
    col["ecb_mro"] = fetch_fred("ECBMRRFR").resample("MS").last()   # ECB main refinancing rate, daily -> last value of each month
    col["ecb_dfr"] = fetch_fred("ECBDFR").resample("MS").last()     # ECB deposit facility rate, daily -> last value of each month
    table = pd.DataFrame(col).loc[START:]                      # one table, matched by month
    table["spread_bp"] = (table["y10_es"] - table["y10_de"]) * 100   # Spain minus Germany, in basis points
    table["real_rate_es"] = table["rate3m_es"] - table["infl_es"]    # real short-term rate: interest rate minus inflation
    table.index.name = "date"                                  # header of the first CSV column
    # returns a DataFrame, one row per month (Jan 1995 -> Nov 2026, 383 rows x 14 columns), e.g. (rounded):
    #             unemp_es  unemp_ea  infl_es  infl_ea  y10_es  y10_de  rate3m_es  ecb_dfr  spread_bp  real_rate_es
    # date
    # 2026-09-01      10.3       6.5      5.0      3.8    3.93    3.47       2.64      2.5      45.73         -2.37
    # 2026-10-01       NaN       NaN      4.9      4.0    4.07    3.42       2.63      2.5      65.55         -2.27
    return table


def save_tables(annual, quarterly, monthly):
    """Save the three tables as CSV next to this script."""
    CSV_DIR.mkdir(parents=True, exist_ok=True)                 # create the csv folder if missing
    annual.round(4).to_csv(CSV_DIR / "annual.csv")             # one row per year
    quarterly.round(4).to_csv(CSV_DIR / "quarterly.csv")       # one row per quarter
    monthly.round(4).to_csv(CSV_DIR / "monthly.csv")           # one row per month
    # returns nothing; writes csv/annual.csv (31 rows), csv/quarterly.csv (127 rows), csv/monthly.csv (383 rows), e.g.
    # year,growth_es,growth_ea,growth_de,growth_fr,growth_it,inv_es,inv_ea,...
    # 1995,,,1.5,2.3,,21.9,21.6,...        (Spain's yearly growth starts in 1996)
    return None


def load_tables():
    """Read the three tables back from the CSVs (for --cached runs, no download)."""
    annual = pd.read_csv(CSV_DIR / "annual.csv", index_col="year")                              # int year index
    quarterly = pd.read_csv(CSV_DIR / "quarterly.csv", index_col="date", parse_dates=True)     # date index
    monthly = pd.read_csv(CSV_DIR / "monthly.csv", index_col="date", parse_dates=True)         # date index
    # returns a tuple of 3 DataFrames, the same tables build_annual / build_quarterly / build_monthly return:
    # (annual 31 x 37, quarterly 127 x 11, monthly 383 x 14)
    return annual, quarterly, monthly


def value_at(series, when):
    """The last available value on or before a date (or year)."""
    clean = series.loc[:when].dropna()                         # everything up to that point, gaps removed
    # returns a float, e.g. value_at(monthly["unemp_es"], "2007-12-01") -> 8.8
    return float(clean.iloc[-1])


def extreme(series, start, end, lowest=False):
    """The highest (or lowest) value between two dates (or years), and when it happened."""
    window = series.loc[start:end].dropna()                    # only that window, gaps removed
    when = window.idxmin() if lowest else window.idxmax()      # date (or year) of the extreme; the first one if it repeats
    # returns a tuple (float, Timestamp or int), e.g. extreme(monthly["unemp_es"], "2008", "2016") -> (26.4, Timestamp('2013-02-01'))
    return float(window.loc[when]), when


def mean_between(series, start, end):
    """The average value between two dates (or years)."""
    # returns a float, e.g. mean_between(annual["growth_es"], 1995, 2007) -> 3.66 (1996-2007: the 1995 value is missing)
    return float(series.loc[start:end].dropna().mean())


def change_pct(old, new):
    """Percentage change from old to new."""
    # returns a float, e.g. change_pct(100, 112.5) -> 12.5
    return (new / old - 1) * 100


def month_label(ts):
    """A date as 'Jul 2012'."""
    # returns a str, e.g. month_label(Timestamp('2012-07-01')) -> 'Jul 2012'
    return pd.Timestamp(ts).strftime("%b %Y")


def quarter_label(ts):
    """A date as 'Q3 2012'."""
    ts = pd.Timestamp(ts)                                      # accept text or Timestamp
    # returns a str, e.g. quarter_label(Timestamp('2012-07-01')) -> 'Q3 2012'
    return f"Q{ts.quarter} {ts.year}"


def period_bounds(period, monthly):
    """First and last date of a period; the open-ended last period runs to the latest month of data."""
    start = pd.Timestamp(period["start"])                      # first day
    end = pd.Timestamp(period["end"]) if period["end"] else monthly.dropna(how="all").index[-1]   # last day, or latest month
    # returns a tuple of 2 Timestamps, e.g. period_bounds(PERIODS[0], monthly) -> (Timestamp('1995-01-01'), Timestamp('2007-12-31'))
    return start, end


def rebased(series, base):
    """A series divided by its value at a base date (or year), times 100, so it reads 100 at the base."""
    # returns a Series, e.g. rebased(quarterly["gdp_es"], "2019-10-01") -> ... 2020-04-01 78.0 ... 2026-07-01 112.6
    return series / value_at(series, base) * 100


def period_table(annual, quarterly, monthly):
    """The key averages of each period: growth, inflation, unemployment, spread, current account, debt, house prices."""
    rows = []                                                  # one dict per period
    for p in PERIODS:                                          # e.g. the boom: 1995-01-01 -> 2007-12-31
        start, end = period_bounds(p, monthly)                 # dates of the period
        y0, y1 = start.year, min(end.year, int(annual["growth_es"].dropna().index[-1]))   # years with annual data in it
        q = quarterly.loc[start:end]                           # the quarters of the period
        m = monthly.loc[start:end]                             # the months of the period
        house = q["house_real_es"].dropna()                    # real house prices in the period
        u = m["unemp_es"].dropna()                             # Spanish unemployment in the period
        rows.append({
            "key": p["key"],                                   # tab key
            "label": f"{p['name']} ({y0}–{end.year})",         # e.g. 'Euro boom (1995–2007)'
            "growth_es": mean_between(annual["growth_es"], y0, y1),   # average yearly real GDP growth, Spain, %
            "growth_ea": mean_between(annual["growth_ea"], y0, y1),   # same for the euro area
            "infl_es": float(m["infl_es"].mean()),             # average inflation, Spain, %
            "infl_ea": float(m["infl_ea"].mean()),             # average inflation, euro area, %
            "unemp_start": float(u.iloc[0]),                   # unemployment in the first month
            "unemp_end": float(u.iloc[-1]),                    # unemployment in the last month
            "unemp_ea_end": float(m["unemp_ea"].dropna().iloc[-1]),   # euro-area unemployment in the last month
            "spread_bp": float(m["spread_bp"].mean()),         # average 10-year spread over Germany, bp
            "ca": float(q["ca_es"].mean()),                    # average current account, % of GDP
            "debt_end": value_at(annual["debt_es"], y1),       # public debt in the last year, % of GDP
            "house": change_pct(house.iloc[0], house.iloc[-1]),   # real house prices, % change over the period
        })
    table = pd.DataFrame(rows).set_index("key")               # periods as rows
    # returns a DataFrame, 6 rows x 12 columns (rounded here), e.g. the first 2 rows:
    #           label                          growth_es growth_ea infl_es infl_ea unemp_start unemp_end ... spread_bp    ca debt_end  house
    # key
    # boom      Euro boom (1995–2007)                3.7       2.4     2.9     1.9        21.4       8.8 ...      70.9  -4.2     35.7  119.2
    # bust      The bubble bursts (2008–2009)       -1.5      -2.0     2.0     1.8         9.1      18.9 ...      56.6  -6.4     53.1  -11.1
    return table


def headline_facts(annual, quarterly, monthly):
    """The numbers for the header: the credit boom, the unemployment peak, the spread peak and output since 2008."""
    credit_peak, credit_peak_q = extreme(quarterly["credit_es"], "1995", "2015")   # household + company debt at its highest
    u_low, u_low_d = extreme(monthly["unemp_es"], "2005", "2008", lowest=True)     # unemployment at its pre-crisis low
    u_peak, u_peak_d = extreme(monthly["unemp_es"], "2008", "2016")                # unemployment at its crisis high
    s_peak, s_peak_d = extreme(monthly["spread_bp"], "2008", "2016")               # 10-year spread at its crisis high
    pre_es, _ = extreme(quarterly["gdp_es"], "2007", "2009")   # Spain's pre-crisis peak of real GDP
    pre_ea, _ = extreme(quarterly["gdp_ea"], "2007", "2009")   # the euro area's
    gdp_last_q = quarterly["gdp_es"].dropna().index[-1]        # latest quarter with GDP
    last_u = monthly["unemp_es"].dropna()                      # Spanish unemployment, gaps removed
    facts = {
        "rate_1995": value_at(monthly["rate3m_es"], "1995-01-01"),   # 3-month rate in Jan 1995, %
        "rate_1999": value_at(monthly["rate3m_es"], "1999-01-01"),   # ... in Jan 1999, when the euro started
        "credit_1995": value_at(quarterly["credit_es"], "1995-01-01"),   # household + company debt, % of GDP, 1995
        "credit_2007": value_at(quarterly["credit_es"], "2007-10-01"),   # ... end of 2007
        "credit_peak": credit_peak, "credit_peak_q": quarter_label(credit_peak_q),
        "u_low": u_low, "u_low_d": month_label(u_low_d),
        "u_peak": u_peak, "u_peak_d": month_label(u_peak_d),
        "u_ea_at_peak": value_at(monthly["unemp_ea"], u_peak_d),   # euro-area unemployment in the same month
        "s_peak": s_peak, "s_peak_d": month_label(s_peak_d),
        "gdp_vs_peak_es": change_pct(pre_es, value_at(quarterly["gdp_es"], gdp_last_q)),   # real GDP now vs its 2007-08 peak, %
        "gdp_vs_peak_ea": change_pct(pre_ea, value_at(quarterly["gdp_ea"], gdp_last_q)),   # same for the euro area
        "gdp_last_q": quarter_label(gdp_last_q),
        "exports_last": float(annual["exports_es"].dropna().iloc[-1]),   # exports, % of GDP, latest year
        "u_last": float(last_u.iloc[-1]), "u_last_d": month_label(last_u.index[-1]),
        "u_ea_last": float(monthly["unemp_ea"].dropna().iloc[-1]),
        "last_month": month_label(monthly["infl_es"].dropna().index[-1]),   # latest month of the monthly indicators (inflation)
        "last_year": int(annual["growth_es"].dropna().index[-1]),         # latest year with annual GDP
    }
    # returns a dict of 22 values (rounded here), e.g.
    # {'rate_1995': 8.94, 'rate_1999': 3.13, 'credit_1995': 85.2, 'credit_2007': 216.4, 'credit_peak': 233.8, 'credit_peak_q': 'Q2 2010',
    #  'u_low': 7.9, 'u_low_d': 'May 2007', 'u_peak': 26.4, 'u_peak_d': 'Feb 2013', 'u_ea_at_peak': 12.3, 's_peak': 555.27,
    #  's_peak_d': 'Jul 2012', 'gdp_vs_peak_es': 20.61, 'gdp_vs_peak_ea': 18.18, 'gdp_last_q': 'Q3 2026', 'u_last': 10.3, ...}
    return facts


def boom_facts(annual, quarterly, monthly):
    """1995-2007: cheap money, credit, housing, construction, and the imbalances that built up."""
    m, q, a = monthly, quarterly, annual                       # short names
    rr = m.loc["1999":"2007", "real_rate_es"].dropna()         # real 3-month rate in the euro years before the crisis
    rr_ea = (m["rate3m_es"] - m["infl_ea"]).loc["1999":"2007"].dropna()   # the same Euribor rate minus EURO-AREA inflation
    hp_peak, hp_peak_q = extreme(q["house_real_es"], "1995", "2010")   # real house prices at their top
    cg_peak, cg_year = extreme(a["constr_gva_es"], 1995, 2010)         # construction share of the economy at its top
    inv_peak, inv_year = extreme(a["inv_es"], 1995, 2010)              # investment share of GDP at its top
    ca_low, ca_low_q = extreme(q["ca4_es"], "1995", "2012", lowest=True)   # current account at its most negative (4-quarter average)
    facts = {
        "growth_es": mean_between(a["growth_es"], 1995, 2007), "growth_ea": mean_between(a["growth_ea"], 1995, 2007),
        "real_rate_avg": float(rr.mean()),                     # average real short-term rate, 1999-2007, %
        "real_rate_neg": float((rr < 0).mean() * 100),         # % of those months with a negative real rate
        "real_rate_ea": float(rr_ea.mean()),                   # what the same rate meant for the average euro-area country, %
        "infl_es": mean_between(m["infl_es"], "1999", "2007"), "infl_ea": mean_between(m["infl_ea"], "1999", "2007"),
        "hh_1995": value_at(q["credit_hh_es"], "1995-01-01"), "hh_2007": value_at(q["credit_hh_es"], "2007-10-01"),
        "nfc_1995": value_at(q["credit_nfc_es"], "1995-01-01"), "nfc_2007": value_at(q["credit_nfc_es"], "2007-10-01"),
        "hp_rise": change_pct(value_at(q["house_real_es"], "1995-01-01"), hp_peak), "hp_peak_q": quarter_label(hp_peak_q),
        "pop_1998": value_at(a["pop_es"], 1998), "pop_2008": value_at(a["pop_es"], 2008),   # population, millions (1 January)
        "cg_peak": cg_peak, "cg_year": int(cg_year), "cg_ea": value_at(a["constr_gva_ea"], cg_year),
        "cj_peak": extreme(a["constr_jobs_share_es"], 1995, 2010)[0],   # construction's share of all jobs at its top, %
        "inv_peak": inv_peak, "inv_year": int(inv_year), "inv_ea": value_at(a["inv_ea"], inv_year),
        "ca_low": ca_low, "ca_low_q": quarter_label(ca_low_q),
        "ulc_es": value_at(a["ulc_es"], 2008) - 100, "ulc_de": value_at(a["ulc_de"], 2008) - 100,   # % rise 1999-2008 (index 1999 = 100)
        "ulc_ea": value_at(a["ulc_ea"], 2008) - 100,
        "debt_2007": value_at(a["debt_es"], 2007), "debt_ea_2007": value_at(a["debt_ea"], 2007),
        "balance_2007": value_at(a["balance_es"], 2007),
        "u_1995": value_at(m["unemp_es"], "1995-01-01"), "u_2007": value_at(m["unemp_es"], "2007-12-01"),
    }
    # returns a dict of 32 values (rounded here), e.g.
    # {'growth_es': 3.66, 'growth_ea': 2.38, 'real_rate_avg': 0.1, 'real_rate_neg': 48.15, 'real_rate_ea': 1.16, 'infl_es': 3.12,
    #  'infl_ea': 2.06, 'hh_1995': 31.4, 'hh_2007': 81.9, 'nfc_1995': 53.8, 'nfc_2007': 134.4, 'hp_rise': 125.56, 'hp_peak_q': 'Q3 2007',
    #  'cg_peak': 12.42, 'cg_year': 2006, 'cg_ea': 6.22, 'ca_low': -9.9, 'ca_low_q': 'Q2 2008', 'ulc_es': 35.12, 'ulc_de': 2.98, ...}
    return facts


def bust_facts(annual, quarterly, monthly):
    """2008-2009: how far output and jobs fell, why jobs fell so much, and what happened to the budget."""
    m, q, a = monthly, quarterly, annual                       # short names
    out = {}                                                   # filled below
    for key in ["es", "ea", "de"]:                             # peak-to-trough fall of real GDP per country
        top, top_q = extreme(q[f"gdp_{key}"], "2007", "2009")  # pre-crisis peak
        low, low_q = extreme(q[f"gdp_{key}"], top_q, "2010-12-31", lowest=True)   # the lowest quarter after it
        out[f"drop_{key}"] = change_pct(top, low)              # % fall, negative
        out[f"top_q_{key}"], out[f"low_q_{key}"] = quarter_label(top_q), quarter_label(low_q)
    jobs_lost = value_at(a["jobs_es"], 2007) - value_at(a["jobs_es"], 2009)              # thousands of jobs lost, 2007 -> 2009
    constr_lost = value_at(a["constr_jobs_es"], 2007) - value_at(a["constr_jobs_es"], 2009)   # of which in construction
    mro_hi, mro_hi_d = extreme(m["ecb_mro"], "2008", "2008")   # ECB main rate at its 2008 high
    mro_lo, mro_lo_d = extreme(m["ecb_mro"], "2009", "2010", lowest=True)   # ... and its 2009-10 low
    out.update({
        "u_low": extreme(m["unemp_es"], "2007", "2008", lowest=True)[0],   # unemployment at its low before the jump
        "u_2009": value_at(m["unemp_es"], "2009-12-01"), "u_ea_2009": value_at(m["unemp_ea"], "2009-12-01"),
        "u_ea_2007": value_at(m["unemp_ea"], "2007-12-01"),
        "jobs_lost": jobs_lost, "constr_lost": constr_lost, "constr_share": constr_lost / jobs_lost * 100,
        "temp_es_2007": value_at(a["temp_es"], 2007), "temp_ea_2007": value_at(a["temp_ea"], 2007),
        "balance_2007": value_at(a["balance_es"], 2007), "balance_2009": value_at(a["balance_es"], 2009),
        "balance_ea_2009": value_at(a["balance_ea"], 2009),
        "debt_2007": value_at(a["debt_es"], 2007), "debt_2009": value_at(a["debt_es"], 2009), "debt_ea_2009": value_at(a["debt_ea"], 2009),
        "mro_hi": mro_hi, "mro_hi_d": month_label(mro_hi_d), "mro_lo": mro_lo, "mro_lo_d": month_label(mro_lo_d),
        "growth_2009": value_at(a["growth_es"], 2009), "growth_ea_2009": value_at(a["growth_ea"], 2009),
    })
    # returns a dict of 30 values (rounded here), e.g.
    # {'drop_es': -4.39, 'top_q_es': 'Q2 2008', 'low_q_es': 'Q1 2009', 'drop_ea': -5.73, 'drop_de': -7.03, 'jobs_lost': 1328.9,
    #  'constr_lost': 869.5, 'constr_share': 65.43, 'temp_es_2007': 31.6, 'temp_ea_2007': 16.1, 'balance_2007': 1.9, 'balance_2009': -11.2,
    #  'mro_hi': 3.75, 'mro_hi_d': 'Oct 2008', 'mro_lo': 1.0, 'mro_lo_d': 'May 2009', ...}
    return out


def debt_facts(annual, quarterly, monthly):
    """2010-2013: the spread, the second recession, the shift of debt from private to public, the labour market."""
    m, q, a = monthly, quarterly, annual                       # short names
    s_peak, s_peak_d = extreme(m["spread_bp"], "2010", "2014")   # spread at its peak
    y_peak, y_peak_d = extreme(m["y10_es"], "2010", "2014")      # Spain's 10-year yield at its peak
    u_peak, u_peak_d = extreme(m["unemp_es"], "2010", "2016")    # unemployment peak
    yo_peak, yo_peak_d = extreme(m["youth_es"], "2010", "2016")  # youth unemployment peak
    c_peak, c_peak_q = extreme(q["credit_es"], "2007", "2014")   # private debt at its peak
    d_peak, d_peak_y = extreme(a["debt_es"], 2010, 2019)         # public debt at its peak before Covid
    hp_top, _ = extreme(q["house_real_es"], "2005", "2010")      # real house prices at the 2007 top
    hp_low, hp_low_q = extreme(q["house_real_es"], "2010", "2018", lowest=True)   # ... and the bottom after it
    facts = {
        "s_2007": mean_between(m["spread_bp"], "2007", "2007"),   # average spread in 2007, bp
        "s_2010": value_at(m["spread_bp"], "2010-01-01"),
        "s_peak": s_peak, "s_peak_d": month_label(s_peak_d), "s_2013": value_at(m["spread_bp"], "2013-12-01"),
        "y_peak": y_peak, "y_peak_d": month_label(y_peak_d),
        "y_de_at_peak": value_at(m["y10_de"], y_peak_d),         # Germany's yield in the same month
        "g_2012": value_at(a["growth_es"], 2012), "g_2013": value_at(a["growth_es"], 2013),
        "g_ea_2012": value_at(a["growth_ea"], 2012), "g_ea_2013": value_at(a["growth_ea"], 2013),
        "g_2010": value_at(a["growth_es"], 2010), "g_2011": value_at(a["growth_es"], 2011),
        "b_2009": value_at(a["balance_es"], 2009), "b_2012": value_at(a["balance_es"], 2012), "b_2013": value_at(a["balance_es"], 2013),
        "c_peak": c_peak, "c_peak_q": quarter_label(c_peak_q), "c_2019": value_at(q["credit_es"], "2019-10-01"),
        "d_2007": value_at(a["debt_es"], 2007), "d_2013": value_at(a["debt_es"], 2013),
        "d_peak": d_peak, "d_peak_y": int(d_peak_y), "d_ea_2013": value_at(a["debt_ea"], 2013),
        "u_peak": u_peak, "u_peak_d": month_label(u_peak_d), "u_ea_at_peak": value_at(m["unemp_ea"], u_peak_d),
        "yo_peak": yo_peak, "yo_peak_d": month_label(yo_peak_d),
        "hp_fall": change_pct(hp_top, hp_low), "hp_low_q": quarter_label(hp_low_q),
    }
    # returns a dict of 32 values (rounded here), e.g.
    # {'s_2007': 8.97, 's_peak': 555.27, 's_peak_d': 'Jul 2012', 's_2013': 234.08, 'y_peak': 6.79, 'g_2012': -2.9, 'g_2013': -1.4,
    #  'b_2009': -11.2, 'b_2012': -11.5, 'b_2013': -7.5, 'c_peak': 233.8, 'c_2019': 151.9, 'd_2007': 35.7, 'd_peak': 104.4,
    #  'd_peak_y': 2014, 'u_peak': 26.4, 'yo_peak': 56.2, 'yo_peak_d': 'Jul 2013', 'hp_fall': -44.5, 'hp_low_q': 'Q4 2013', ...}
    return facts


def recovery_facts(annual, quarterly, monthly):
    """2014-2019: exports, the current account, costs, and what was still fragile."""
    m, q, a = monthly, quarterly, annual                       # short names
    ca_low, ca_low_q = extreme(q["ca4_es"], "2005", "2012", lowest=True)   # current account at its most negative
    yearly_ca = q["ca_es"].groupby(q.index.year).mean()        # current account, average of each year's 4 quarters
    surplus_years = yearly_ca.loc[2009:][yearly_ca.loc[2009:] > 0]   # years after 2008 with a surplus
    ulc_top, ulc_top_y = extreme(a["ulc_es"], 2007, 2013)      # Spain's unit labour costs at their top
    ulc_low, ulc_low_y = extreme(a["ulc_es"], ulc_top_y, 2019, lowest=True)   # ... and their low afterwards
    facts = {
        "growth_es": mean_between(a["growth_es"], 2014, 2019), "growth_ea": mean_between(a["growth_ea"], 2014, 2019),
        "u_2014": value_at(m["unemp_es"], "2014-01-01"), "u_2019": value_at(m["unemp_es"], "2019-12-01"),
        "u_ea_2019": value_at(m["unemp_ea"], "2019-12-01"),
        "x_2009": value_at(a["exports_es"], 2009), "x_2019": value_at(a["exports_es"], 2019), "x_ea_2019": value_at(a["exports_ea"], 2019),
        "ca_low": ca_low, "ca_low_q": quarter_label(ca_low_q),
        "first_surplus": int(surplus_years.index[0]),          # first year with a current-account surplus after the crisis
        "ca_2019": float(yearly_ca.loc[2019]),
        "ulc_top_y": int(ulc_top_y), "ulc_low_y": int(ulc_low_y), "ulc_fall": change_pct(ulc_top, ulc_low),
        "ulc_de_same": change_pct(value_at(a["ulc_de"], ulc_top_y), value_at(a["ulc_de"], ulc_low_y)),   # Germany over the same years
        "d_2007": value_at(a["debt_es"], 2007), "d_2019": value_at(a["debt_es"], 2019), "d_ea_2019": value_at(a["debt_ea"], 2019),
        "temp_2019": value_at(a["temp_es"], 2019), "temp_ea_2019": value_at(a["temp_ea"], 2019),
        "prod_2019": value_at(a["prod_es"], 2019) - 100, "prod_ea_2019": value_at(a["prod_ea"], 2019) - 100,   # % since 2007
        "n_2013": value_at(a["nights_es"], 2013), "n_2019": value_at(a["nights_es"], 2019),
    }
    # returns a dict of 25 values (rounded here), e.g.
    # {'growth_es': 2.63, 'growth_ea': 1.97, 'u_2014': 25.5, 'u_2019': 13.8, 'x_2009': 23.0, 'x_2019': 34.7, 'ca_low': -9.9,
    #  'first_surplus': 2012, 'ulc_top_y': 2009, 'ulc_low_y': 2016, 'ulc_fall': -6.84, 'ulc_de_same': 10.35, 'd_2019': 97.7,
    #  'temp_2019': 26.3, 'prod_2019': 13.34, 'prod_ea_2019': 9.33, ...}
    return facts


def covid_facts(annual, quarterly, monthly):
    """2020-2022: the fall in output, tourism, inflation and interest rates."""
    m, q, a = monthly, quarterly, annual                       # short names
    out = {}                                                   # filled below
    for key in COUNTRIES.values():                             # es, ea, de, fr, it
        g = rebased(q[f"gdp_{key}"], "2019-10-01")             # real GDP, Q4 2019 = 100
        out[f"q2_{key}"] = float(g.loc["2020-04-01"]) - 100    # % below end-2019 in Q2 2020
        back = g.loc["2020-07-01":][g.loc["2020-07-01":] >= 100]   # quarters back at or above the end-2019 level
        out[f"back_{key}"] = quarter_label(back.index[0]) if len(back) else "not yet"   # first such quarter
        out[f"back_n_{key}"] = int((back.index[0] - pd.Timestamp("2019-10-01")).days / 91.3) if len(back) else None   # quarters it took
    i_pk, i_pk_d = extreme(m["infl_es"], "2021", "2023")       # Spanish inflation peak
    iea_pk, iea_pk_d = extreme(m["infl_ea"], "2021", "2023")   # euro-area inflation peak
    e_pk, e_pk_d = extreme(m["infl_nrg_es"], "2021", "2023")   # Spanish energy inflation peak
    eea_pk, eea_pk_d = extreme(m["infl_nrg_ea"], "2021", "2023")   # euro-area energy inflation peak
    after = m.loc[i_pk_d:"2023-12-01"]                         # months after the Spanish peak
    below = after[after["infl_es"] < after["infl_ea"]]         # months Spanish inflation was under the euro area's
    neg_nrg = m.loc[e_pk_d:"2023-12-01", "infl_nrg_es"]        # Spanish energy inflation after its peak
    neg_nrg_ea = m.loc[eea_pk_d:"2024-12-01", "infl_nrg_ea"]   # euro-area energy inflation after its peak
    dfr = m["ecb_dfr"].dropna()                                # ECB deposit rate, monthly
    hikes = dfr.loc["2022":][dfr.loc["2022":].diff() > 0]      # months the rate went up
    dfr_hi, dfr_hi_d = extreme(dfr, "2022", "2024")            # its peak
    out.update({
        "g_2020": value_at(a["growth_es"], 2020), "g_ea_2020": value_at(a["growth_ea"], 2020),
        "n_2019": value_at(a["nights_es"], 2019), "n_2020": value_at(a["nights_es"], 2020),
        "n_drop": change_pct(value_at(a["nights_es"], 2019), value_at(a["nights_es"], 2020)),
        "n_2022": value_at(a["nights_es"], 2022),
        "i_pk": i_pk, "i_pk_d": month_label(i_pk_d), "iea_pk": iea_pk, "iea_pk_d": month_label(iea_pk_d),
        "e_pk": e_pk, "e_pk_d": month_label(e_pk_d), "eea_pk": eea_pk, "eea_pk_d": month_label(eea_pk_d),
        "first_below": month_label(below.index[0]) if len(below) else None,   # first month Spain's inflation was below the euro area's
        "nrg_neg": month_label(neg_nrg[neg_nrg < 0].index[0]) if (neg_nrg < 0).any() else None,   # first month energy prices fell on the year
        "nrg_neg_ea": month_label(neg_nrg_ea[neg_nrg_ea < 0].index[0]) if (neg_nrg_ea < 0).any() else None,   # same, euro area
        "dfr_lo": value_at(dfr, hikes.index[0] - pd.offsets.MonthBegin(1)),   # deposit rate just before the first rise
        "first_hike": month_label(hikes.index[0]), "dfr_hi": dfr_hi, "dfr_hi_d": month_label(dfr_hi_d),
        "y10_2021": value_at(m["y10_es"], "2021-12-01"),
        "y10_hi": extreme(m["y10_es"], "2022", "2024")[0], "y10_hi_d": month_label(extreme(m["y10_es"], "2022", "2024")[1]),
        "rate3m_hi": extreme(m["rate3m_es"], "2022", "2024")[0],
        "d_2019": value_at(a["debt_es"], 2019), "d_2020": value_at(a["debt_es"], 2020), "d_2022": value_at(a["debt_es"], 2022),
    })
    # returns a dict of 43 values (rounded here), e.g.
    # {'q2_es': -22.05, 'back_es': 'Q2 2022', 'back_n_es': 10, 'q2_ea': -13.96, 'back_ea': 'Q3 2021', 'back_n_ea': 6, 'g_2020': -10.9,
    #  'n_drop': -79.64, 'i_pk': 10.7, 'i_pk_d': 'Jul 2022', 'iea_pk': 10.6, 'iea_pk_d': 'Oct 2022', 'e_pk': 60.3, 'first_below': 'Sep 2022',
    #  'nrg_neg': 'Dec 2022', 'nrg_neg_ea': 'Mar 2023', 'dfr_lo': -0.5, 'first_hike': 'Jul 2022', 'dfr_hi': 4.0, 'dfr_hi_d': 'Sep 2023', ...}
    return out


def today_facts(annual, quarterly, monthly):
    """2023 to today: growth, where it comes from, and the measures that still lag."""
    m, q, a = monthly, quarterly, annual                       # short names
    ly = int(a["growth_es"].dropna().index[-1])                # latest year with annual GDP, e.g. 2025
    u = m["unemp_es"].dropna()                                 # Spanish unemployment, gaps removed
    low12, low12_d = extreme(u.iloc[-12:], u.index[-12], u.index[-1], lowest=True)   # lowest rate of the last 12 months
    lower_before = u.loc[:u.index[-13]][u.loc[:u.index[-13]] <= low12]   # months before that year with a rate this low
    hp_low, hp_low_q = extreme(q["house_real_es"], "2010", "2018", lowest=True)   # real house prices at the post-crisis bottom
    hp_top, hp_top_q = extreme(q["house_real_es"], "2005", "2010")                # ... at the 2007 top
    hp = q["house_real_es"].dropna()                           # real house prices, gaps removed
    infl = m["infl_es"].dropna()                               # Spanish inflation, gaps removed
    facts = {"ly": ly}                                         # filled below
    for key in COUNTRIES.values():                             # average growth 2023 -> latest year, per country
        facts[f"g_{key}"] = mean_between(a[f"growth_{key}"], 2023, ly)
    facts.update({
        "emp": mean_between(a["emp_growth_es"], 2023, ly),     # average yearly growth of the number of people working, %
        "perworker": mean_between(a["perworker_growth_es"], 2023, ly),   # average yearly growth of output per worker, %
        "pop_2022": value_at(a["pop_es"], 2022), "pop_last": float(a["pop_es"].dropna().iloc[-1]),
        "pop_last_y": int(a["pop_es"].dropna().index[-1]),
        "netmig": mean_between(a["netmig_es"], 2023, ly),      # average net migration per 1,000 residents
        "n_last": value_at(a["nights_es"], ly), "n_2019": value_at(a["nights_es"], 2019),
        "pps": value_at(a["pps_es"], ly), "pps_2007": value_at(a["pps_es"], 2007), "pps_ea": value_at(a["pps_ea"], ly),
        "gdppc": change_pct(value_at(a["gdppc_es"], 2007), value_at(a["gdppc_es"], ly)),       # real GDP per person, % since 2007
        "gdppc_ea": change_pct(value_at(a["gdppc_ea"], 2007), value_at(a["gdppc_ea"], ly)),
        "prod": value_at(a["prod_es"], ly) - 100, "prod_ea": value_at(a["prod_ea"], ly) - 100,   # output per hour, % since 2007
        "u": float(u.iloc[-1]), "u_d": month_label(u.index[-1]), "u_ea": float(m["unemp_ea"].dropna().iloc[-1]),
        "low12": low12, "low12_d": month_label(low12_d),       # lowest unemployment of the last 12 months, and when
        "u_since": int(lower_before.index[-1].year) if len(lower_before) else None,   # last year before that it was this low
        "prodlvl": value_at(a["prodlvl_es"], ly), "prodlvl_ea": value_at(a["prodlvl_ea"], ly),   # output per hour, PPS, EU = 100
        "prodlvl_2007": value_at(a["prodlvl_es"], 2007),
        "prod_19": change_pct(value_at(a["prod_es"], 2019), value_at(a["prod_es"], ly)),        # output per hour, % since 2019
        "prod_19_ea": change_pct(value_at(a["prod_ea"], 2019), value_at(a["prod_ea"], ly)),
        "youth": float(m["youth_es"].dropna().iloc[-1]),
        "hp_from_low": change_pct(hp_low, hp.iloc[-1]), "hp_low_y": int(hp_low_q.year),
        "hp_vs_top": change_pct(hp_top, hp.iloc[-1]), "hp_last_q": quarter_label(hp.index[-1]),
        "infl": float(infl.iloc[-1]), "infl_d": month_label(infl.index[-1]), "infl_ea": float(m["infl_ea"].dropna().iloc[-1]),
        "dfr": float(m["ecb_dfr"].dropna().iloc[-1]),
        "debt": value_at(a["debt_es"], ly), "debt_ea": value_at(a["debt_ea"], ly),
        "temp": float(a["temp_es"].dropna().iloc[-1]), "temp_ea": float(a["temp_ea"].dropna().iloc[-1]),
        "temp_2021": value_at(a["temp_es"], 2021), "temp_y": int(a["temp_es"].dropna().index[-1]),
        "ca": float(q["ca4_es"].dropna().iloc[-1]),
    })
    # returns a dict of 48 values (rounded here), e.g.
    # {'ly': 2025, 'g_es': 2.9, 'g_ea': 0.97, 'emp': 2.91, 'perworker': -0.01, 'pop_2022': 47.49, 'pop_last': 49.13, 'pps': 91.4,
    #  'pps_2007': 104.1, 'pps_ea': 103.8, 'prod': 15.57, 'prod_ea': 11.43, 'prodlvl': 95.3, 'prodlvl_ea': 107.1, 'u': 10.3,
    #  'u_ea': 6.5, 'low12': 10.1, 'low12_d': 'Nov 2025', 'u_since': 2008, 'hp_from_low': 62.54, 'infl': 4.9, 'infl_ea': 4.0, ...}
    return facts


def print_summary(table, facts):
    """Print the period table and a few headline numbers in the terminal."""
    show = table.drop(columns="label").round(1)                # numbers only, 1 decimal
    print(show.to_string())                                    # the period table
    h = facts["head"]                                          # header numbers
    print(f"Credit peak {h['credit_peak']:.0f}% of GDP ({h['credit_peak_q']}); unemployment {h['u_low']:.1f}% ({h['u_low_d']}) -> "
          f"{h['u_peak']:.1f}% ({h['u_peak_d']}); spread peak {h['s_peak']:.0f} bp ({h['s_peak_d']}); "
          f"real GDP vs 2008 peak {h['gdp_vs_peak_es']:+.1f}% (euro area {h['gdp_vs_peak_ea']:+.1f}%)")
    # returns nothing; prints the 6-row period table and one line, e.g.
    #           growth_es  growth_ea  infl_es  infl_ea  unemp_start  unemp_end  unemp_ea_end  spread_bp   ca  debt_end  house
    # key
    # boom            3.7        2.4      2.9      1.9         21.4        8.8           7.4       70.9 -4.2      35.7  119.2
    # ...
    # today           2.9        1.0      3.2      3.2         13.1       10.3           6.5       75.4  3.0     100.5   26.1
    # Credit peak 234% of GDP (Q2 2010); unemployment 7.9% (May 2007) -> 26.4% (Feb 2013); spread peak 555 bp (Jul 2012);
    # real GDP vs 2008 peak +20.6% (euro area +18.2%)
    return None


def main():
    if "--cached" in sys.argv:                                 # rebuild the page from the saved tables
        annual, quarterly, monthly = load_tables()             # step 1 (cached): read the three CSVs
    else:                                                      # normal run: download everything
        annual = build_annual()                                # step 1a: yearly table (Eurostat)
        quarterly = build_quarterly()                          # step 1b: quarterly table (Eurostat + BIS via FRED)
        monthly = build_monthly()                              # step 1c: monthly table (Eurostat + FRED)
        save_tables(annual, quarterly, monthly)                # step 2: keep a copy of the data
    table = period_table(annual, quarterly, monthly)           # step 3: the key averages of each period
    facts = {                                                  # step 4: every number the text uses, one dict per tab
        "head": headline_facts(annual, quarterly, monthly),
        "boom": boom_facts(annual, quarterly, monthly),
        "bust": bust_facts(annual, quarterly, monthly),
        "debt": debt_facts(annual, quarterly, monthly),
        "recovery": recovery_facts(annual, quarterly, monthly),
        "covid": covid_facts(annual, quarterly, monthly),
        "today": today_facts(annual, quarterly, monthly),
    }
    print_summary(table, facts)                                # step 5: print the key numbers
    build_page(annual, quarterly, monthly, table, facts)       # step 6: write the web page (code below)
    print(f"Saved {OUTPUT_PATH}")                              # tell the user where the page is


# ===========================================================================
# html / chart code
# ===========================================================================

ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"  # Apache ECharts, a fixed version
FONTS_URL = "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap"

# Look: the "Lab" design every project page uses (see CLAUDE.md), in this project's own colours: an olive header band
# with a saffron accent. Series colours follow the entity everywhere on the page and come from the validated default
# palette: Spain = orange, euro area = blue, Germany = aqua, France = yellow, Italy = magenta. On a Spain-only chart
# with two measures, the second measure is violet. Text always uses the ink tokens, never a series colour.
CSS = """
:root{color-scheme:light dark;--band:#283318;--band-ink:#e6e7e2;--brass:#d6a419;--page:#f6f5f2;--surface:#fff;--ink:#16181d;--ink-2:#555a63;
  --muted:#868b94;--grid:#e4e2dc;--axis:#c9c7c0;--zone:rgba(120,120,120,.10);--zone-2:rgba(120,120,120,.045);
  --es:#eb6834;--ea:#2a78d6;--de:#1baf7a;--fr:#eda100;--it:#e87ba4;--s2:#6250d6;--ref:#868b94}
@media (prefers-color-scheme:dark){:root{--band:#1b2210;--brass:#eec455;--page:#0f1012;--surface:#18191d;--ink:#ececee;--ink-2:#aaadb5;
  --muted:#80848c;--grid:#2a2c31;--axis:#3f4248;--zone:rgba(200,200,200,.09);--zone-2:rgba(200,200,200,.035);
  --es:#d95926;--ea:#3987e5;--de:#199e70;--fr:#c98500;--it:#d55181;--s2:#9085e9;--ref:#80848c}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 "DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
h1,h2,.kpi b{font-family:"DM Serif Display",Georgia,serif;font-weight:400}
a{color:inherit}
.in{max-width:1000px;margin:0 auto;padding:0 max(20px,env(safe-area-inset-right)) 0 max(20px,env(safe-area-inset-left))}
.band{background:var(--band);color:var(--band-ink);padding:8px 0 96px}
a.back{display:inline-flex;align-items:center;min-height:44px;color:var(--band-ink);text-decoration:none;font-size:14px}
.toprow{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.upd{display:inline-flex;align-items:center;min-height:44px;font-size:13px;color:var(--band-ink);opacity:.72;white-space:nowrap}
a.back:hover{color:#fff}
.eyebrow{margin:24px 0 12px;color:var(--brass);font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}
h1{margin:0;color:#fff;font-size:clamp(32px,5.5vw,50px);line-height:1.08;max-width:20ch}
.answer{margin:18px 0 0;max-width:70ch}
.answer b{color:#fff}
.meta{margin:14px 0 0;font-size:13px;opacity:.75}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.kpis.top{margin-top:-64px}
.kpi{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:16px 18px}
.top .kpi{box-shadow:0 14px 34px rgba(0,0,0,.10)}
.kpi b{display:block;font-size:30px;font-variant-numeric:tabular-nums;line-height:1.2}
.kpi span{display:block;font-size:13px;color:var(--ink-2);line-height:1.4;margin-top:4px}
/* period tabs: a grid of large buttons, wrapping to two columns on a phone */
.tabs{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin:28px 0 0;scroll-margin-top:12px}
.tabs button{min-height:60px;padding:8px 10px;border:1px solid var(--grid);border-radius:10px;background:var(--surface);color:var(--ink-2);
  font:inherit;text-align:left;cursor:pointer;display:flex;flex-direction:column;justify-content:center;gap:1px}
.tabs button b{font-size:14px;line-height:1.25;color:var(--ink);font-weight:700}
.tabs button span{font-size:12px;line-height:1.3}
.tabs button[aria-selected=true]{background:var(--band);border-color:var(--band);color:var(--band-ink);box-shadow:inset 0 -3px 0 var(--brass)}
.tabs button[aria-selected=true] b{color:#fff}
.tabs button[aria-selected=true] span{color:var(--brass)}
.tabs button:focus-visible,.next:focus-visible{outline:3px solid var(--brass);outline-offset:2px}
@media (hover:hover){.tabs button:not([aria-selected=true]):hover{border-color:var(--brass)}}
.panel{background:var(--surface);border:1px solid var(--grid);border-radius:14px;padding:28px;margin-top:20px}
.panel .tag{margin:0;color:var(--brass);font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
h2{margin:4px 0 2px;font-size:28px;line-height:1.15}
.dek{margin:0 0 18px;font-weight:700}
.intro{border-top:4px solid var(--brass)}
.intro .sum{margin:0 0 18px;color:var(--ink-2);max-width:70ch}
.how{background:var(--page);border-radius:10px;padding:12px 16px;margin:0 0 18px;font-size:15px;color:var(--ink-2)}
.how b,.so b{color:var(--ink)}
.so{border-left:3px solid var(--brass);padding:2px 0 2px 16px;margin:20px 0 0}
.so p{margin:0 0 8px}
.panel .kpi{background:var(--page);border:0}
.panel .kpi b{font-size:26px}
.chart{width:100%;height:340px}
.chart.short{height:260px}
.label{margin:18px 0 4px;font-size:13px;font-weight:600;color:var(--ink-2)}
.note{color:var(--muted);font-size:13px;margin:6px 0 0}
.gloss{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px;margin:0}
.gloss div{margin:0}
.gloss dt{font-weight:700}
.gloss dd{margin:2px 0 0;color:var(--ink-2);font-size:15px}
.take{margin:0;padding-left:1.2rem}
.take li{margin:0 0 12px}
.take li::marker{color:var(--brass)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.swipe{display:none;color:var(--muted);font-size:13px;margin:0 0 6px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--surface);padding-left:0}
th{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em;white-space:normal;vertical-align:bottom}
td small{color:var(--muted)}
.next{display:flex;align-items:center;justify-content:center;width:100%;min-height:52px;margin:20px 0 0;padding:10px 16px;
  border:1px solid var(--grid);border-radius:12px;background:var(--surface);color:var(--ink);font:inherit;font-weight:700;cursor:pointer;text-align:center}
@media (hover:hover){.next:hover{border-color:var(--brass)}}
.shared{margin-top:36px}
.refs{margin:32px 0 0;padding:0 4px;font-size:13px;line-height:1.5;color:var(--muted)}
.refs h3{margin:0 0 2px;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.refs ul{list-style:none;padding:0;margin:0}
.refs a{display:flex;align-items:center;min-height:44px;padding:6px 0;color:var(--muted);text-decoration:none}
.refs b{font-weight:600;color:var(--ink-2);text-decoration:underline;text-decoration-color:var(--axis);text-underline-offset:3px}
.refs a:hover span{text-decoration:underline}
footer{margin-top:40px;background:var(--band);color:var(--band-ink);font-size:13px}
footer .in{padding-top:20px;padding-bottom:20px}
@media (max-width:900px){.tabs{grid-template-columns:repeat(4,1fr)}}
@media (max-width:720px){.kpis{grid-template-columns:1fr 1fr;gap:10px}.panel{padding:20px 16px}.band{padding-bottom:84px}h2{font-size:24px}
  .kpi{padding:14px}.kpi b{font-size:26px}.panel .kpi b{font-size:22px}}
@media (max-width:640px){
  .tabs{grid-template-columns:1fr 1fr}.tabs button:first-child{grid-column:1/-1}
  .chart{height:400px}.chart.short{height:320px}
  .gloss{grid-template-columns:1fr;gap:14px}
  th,td{padding:8px 6px;font-size:13px}
  .swipe{display:block}
  .periods td:first-child{white-space:normal;min-width:118px;max-width:130px}
}
"""

JS = r"""
const DATA = __DATA__;                                          // everything Python computed, as JSON
const narrowMQ = window.matchMedia("(max-width: 640px)");       // true on a phone-width screen
const darkMQ = window.matchMedia("(prefers-color-scheme: dark)");
const isTouch = window.matchMedia("(pointer: coarse)").matches; // a finger instead of a mouse
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();  // read a colour token
const INSTANCES = {};                                           // chart div id -> ECharts instance
const MINUS = "−";                                         // a real minus sign
const num = (v, d) => (v < 0 ? MINUS : "") + Math.abs(v).toFixed(d);
const sign = (v, d) => (v > 0 ? "+" : "") + num(v, d);

function tipStyle() {                                           // tooltip look from the page tokens, never ECharts' default white box
  return {
    backgroundColor: css("--surface"), borderColor: css("--grid"), borderWidth: 1,
    textStyle: {color: css("--ink"), fontFamily: "DM Sans, system-ui, sans-serif", fontSize: 13},
    extraCssText: "box-shadow: 0 6px 20px rgba(0,0,0,.18); border-radius: 8px;",
    axisPointer: {label: {backgroundColor: css("--ink-2"), color: css("--surface")}},
  };
}

function dateLabel(v, freq) {                                   // tooltip header: "2007", "Q3 2007" or "Sep 2007"
  const d = new Date(v);
  if (freq === "A") return String(d.getFullYear());
  if (freq === "Q") return "Q" + (Math.floor(d.getMonth() / 3) + 1) + " " + d.getFullYear();
  return d.toLocaleDateString("en-GB", {month: "short", year: "numeric"});
}

function valueText(v, spec) {                                   // one value with its unit, e.g. "−3.2%", "563 bp", "104.5"
  if (v == null || isNaN(v)) return "–";
  const t = spec.signed ? sign(v, spec.dec) : num(v, spec.dec);
  return t + (spec.unit === "bp" ? " bp" : spec.unit === "m" ? " m" : spec.unit);
}

function axisText(v, spec) {                                    // y-axis labels: whole numbers where possible
  const d = Number.isInteger(v) ? 0 : 1;
  return num(v, d) + (spec.unit === "%" ? "%" : "");
}

function build(spec, narrow) {                                  // one chart's ECharts options from its spec
  const n = spec.series.length;
  const ends = !narrow && spec.kind === "line" && n <= 5;           // direct labels at the line ends on desktop (same plot width for all)
  const legendH = n < 2 ? 0 : (narrow ? n * 21 + 10 : 0);
  const o = {animation: false, backgroundColor: "transparent", textStyle: {color: css("--ink-2"), fontFamily: "DM Sans, system-ui, sans-serif"}};
  o.legend = n < 2 ? {show: false}
    : narrow ? {bottom: 2, left: 4, orient: "vertical", itemGap: 5, textStyle: {color: css("--ink-2"), fontSize: 13}}   // one entry per line, below the plot
             : {top: 2, left: 8, itemGap: 16, textStyle: {color: css("--ink-2"), fontSize: 13}};                    // one row above the plot
  o.grid = narrow ? {left: 4, right: 14, top: 22, bottom: legendH + 6, containLabel: true}
                  : {left: 8, right: ends ? 112 : 18, top: (n < 2 ? 22 : 46) + (spec.events && spec.events.length ? 18 : 0), bottom: 6, containLabel: true};
  const axisCommon = {axisLine: {lineStyle: {color: css("--axis")}}, axisTick: {lineStyle: {color: css("--axis")}},
                      splitLine: {lineStyle: {color: css("--grid")}}};
  const cut = narrow && spec.narrowFrom ? Math.max(0, (spec.years || []).indexOf(spec.narrowFrom)) : 0;   // phone: fewer years
  if (cut) spec = Object.assign({}, spec, {years: spec.years.slice(cut), series: spec.series.map(s => Object.assign({}, s, {d: s.d.slice(cut)}))});
  if (spec.x === "year") {
    o.xAxis = Object.assign({type: "category", data: spec.years, axisTick: {alignWithLabel: true, lineStyle: {color: css("--axis")}},
      axisLabel: {color: css("--muted"), hideOverlap: true}}, {axisLine: axisCommon.axisLine});
  } else {
    o.xAxis = Object.assign({}, axisCommon, {type: "time", min: Date.parse(spec.xmin), max: Date.parse(spec.xmax),
      minInterval: 365 * 24 * 3600 * 1000, splitNumber: narrow ? 4 : 8, splitLine: {show: false},
      axisLabel: {color: css("--muted"), hideOverlap: true, formatter: "{yyyy}", showMinLabel: true, showMaxLabel: false},
      axisPointer: {label: {formatter: p => dateLabel(p.value, spec.freq)}}});
  }
  o.yAxis = Object.assign({}, axisCommon, {type: "value", scale: !!spec.scale, min: spec.min, max: spec.max,
    axisLabel: {color: css("--muted"), formatter: v => axisText(v, spec)}});
  o.series = spec.series.map(s => {
    const c = css(s.c);
    if (s.dot) return {name: s.name, type: "line", data: s.d, symbol: "circle", symbolSize: 9, lineStyle: {opacity: 0},
                       itemStyle: {color: css("--ink"), borderColor: css("--surface"), borderWidth: 2}, z: 5};
    if (spec.kind === "line") return {name: s.name, type: "line", data: s.d, showSymbol: false, connectNulls: true,
      lineStyle: {color: c, width: s.w || 2, type: s.dash ? "dashed" : "solid"}, itemStyle: {color: c},
      endLabel: {show: ends, color: css("--ink"), fontSize: 12, formatter: () => s.short || s.name},
      labelLayout: {moveOverlap: "shiftY"}, z: s.z || 2};
    return {name: s.name, type: "bar", data: s.d, stack: spec.kind === "stack" ? "a" : undefined, barMaxWidth: 16, barGap: "15%",
            itemStyle: {color: c, borderRadius: 2, borderColor: css("--surface"), borderWidth: spec.kind === "stack" ? 1 : 0}};
  });
  // shaded period(s), event lines and the zero line all hang on the first series
  const first = o.series[0];
  const areas = [];
  const xv = d => spec.x === "year" ? d : Date.parse(d);
  if (spec.bands) DATA.periods.forEach((p, i) => areas.push([
    {xAxis: xv(p.start), name: narrow ? "" : p.short, itemStyle: {color: i % 2 ? css("--zone-2") : css("--zone")}}, {xAxis: xv(p.end)}]));
  if (spec.band) areas.push([{xAxis: xv(spec.band[0]), name: spec.band[2], itemStyle: {color: css("--zone")}}, {xAxis: xv(spec.band[1])}]);
  if (areas.length) first.markArea = {silent: true, data: areas,
    label: {color: css("--muted"), fontSize: 11, position: "insideTop", distance: 4}};
  const lines = [];
  if (spec.zero) lines.push({yAxis: 0, label: {show: false}, lineStyle: {color: css("--axis"), type: "solid", width: 1}});
  (spec.events || []).forEach(e => lines.push({xAxis: Date.parse(e[0]),
    label: {show: !narrow, formatter: e[1], color: css("--ink-2"), fontSize: 11, position: "end", distance: 4},
    lineStyle: {color: css("--muted"), type: "dashed", width: 1}}));
  if (lines.length) first.markLine = {silent: true, symbol: "none", data: lines};
  o.tooltip = Object.assign(tipStyle(), {trigger: "axis", triggerOn: isTouch ? "click" : "mousemove|click", confine: true,
    valueFormatter: v => valueText(v, spec)});
  return o;
}

function drawPanel(panel) {                                     // (re)build every chart inside one visible tab panel
  const narrow = narrowMQ.matches;
  panel.querySelectorAll(".chart").forEach(div => {
    if (!INSTANCES[div.id]) INSTANCES[div.id] = echarts.init(div);
    INSTANCES[div.id].setOption(build(DATA.charts[div.id], narrow), true);
    INSTANCES[div.id].resize();
  });
}
const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
function current() { return document.querySelector('[role="tabpanel"]:not([hidden])'); }
function show(key, focusTab) {                                  // switch tab: show its panel, draw its charts, remember it in the URL
  tabs.forEach(t => {
    const on = t.dataset.tab === key;
    t.setAttribute("aria-selected", on); t.tabIndex = on ? 0 : -1;
    document.getElementById("p-" + t.dataset.tab).hidden = !on;
    if (on && focusTab) t.focus();
  });
  if (history.replaceState) history.replaceState(null, "", "#" + key);
  drawPanel(current());
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => show(t.dataset.tab));
  t.addEventListener("keydown", e => {                          // arrow keys move between tabs (keyboard users)
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (step) { e.preventDefault(); show(tabs[(i + step + tabs.length) % tabs.length].dataset.tab, true); }
  });
});
document.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => {   // "Next period" buttons
  show(b.dataset.go);
  document.getElementById("tabs").scrollIntoView({behavior: "smooth", block: "start"});
}));
if (isTouch) document.querySelectorAll(".hint").forEach(h => h.textContent = "Tap");   // say "tap", not "hover", to touch users
const startKey = location.hash.slice(1);
show(tabs.some(t => t.dataset.tab === startKey) ? startKey : "overview");
const redraw = () => drawPanel(current());
narrowMQ.addEventListener("change", redraw);                    // rebuild when a phone is rotated
darkMQ.addEventListener("change", redraw);                      // rebuild in the new colours (tooltips too)
window.addEventListener("resize", () => Object.values(INSTANCES).forEach(c => c.resize()));
"""

SOURCES = [                               # (who, what it gave us, link): one quiet line each
    ("Eurostat", "national accounts (GDP, investment, exports, GDP per person, construction, employment), unemployment, "
     "HICP inflation, government debt and balance, unit labour costs, productivity, population, migration, tourism, "
     "temporary contracts and the current account", "https://ec.europa.eu/eurostat/data/database"),
    ("FRED, St. Louis Fed (OECD data)", "10-year government bond yields of Spain and Germany and the Spanish 3-month interbank rate",
     "https://fred.stlouisfed.org/series/IRLTLT01ESM156N"),
    ("FRED (ECB data)", "ECB main refinancing and deposit facility rates", "https://fred.stlouisfed.org/series/ECBDFR"),
    ("FRED (BIS data)", "real residential property prices and credit to households and non-financial companies, Spain",
     "https://fred.stlouisfed.org/series/QESR628BIS"),
    ("ECB", "the July 2012 London speech (\"whatever it takes\")",
     "https://www.ecb.europa.eu/press/key/date/2012/html/sp120726.en.html"),
    ("European Stability Mechanism", "the 2012 euro-area financial assistance for the recapitalisation of Spanish banks",
     "https://www.esm.europa.eu/financial-assistance/spain"),
]

GLOSSARY = [                              # (term, plain-language meaning)
    ("Real vs nominal", "Nominal figures are in today's euros. Real figures remove inflation, so they measure quantities "
                        "(how much was produced) rather than prices."),
    ("Real interest rate", "The interest rate minus inflation. If a loan costs 3% and prices rise 4%, the real rate is −1%: "
                           "the debt shrinks in real terms, so borrowing is very attractive."),
    ("Current account", "What a country earns from the rest of the world (exports, tourism, income) minus what it pays. "
                        "A deficit has to be financed by borrowing from abroad or selling assets to foreigners."),
    ("Unit labour cost", "Wages paid per unit of output. It rises when wages grow faster than productivity, which makes "
                         "a country's goods more expensive compared with its trading partners."),
    ("Spread and basis point", "The spread is the extra yield Spain pays over Germany on 10-year bonds. One basis point (bp) "
                               "is 0.01 percentage point, so 100 bp = 1 percentage point."),
    ("Internal devaluation", "Inside the euro a country cannot make its currency cheaper. It can only regain price "
                             "competitiveness by letting wages and prices grow more slowly than its partners."),
    ("Deleveraging", "Households, firms or banks reducing their debt by repaying it, which means spending less "
                     "than their income for a while."),
    ("Automatic stabilisers", "Taxes fall and unemployment benefits rise by themselves in a recession, so the budget "
                              "deficit grows without any new decision."),
    ("Temporary contract", "A fixed-term job contract. It is cheaper to end than a permanent one, so in a downturn "
                           "firms cut these jobs first."),
    ("PPS (purchasing power standard)", "An artificial currency that removes price-level differences between countries, "
                                        "so GDP per person can be compared fairly. EU average = 100."),
    ("HICP", "The harmonised index of consumer prices: the inflation measure used by Eurostat and the ECB, built the "
             "same way in every EU country."),
    ("Percent vs percentage point", "Unemployment going from 10% to 12% is a rise of 2 percentage points, or 20%."),
]


def pct(value, digits=1):
    """Format a number with an explicit sign and a real minus sign, e.g. -3.85 -> '−3.9'."""
    text = f"{abs(value):.{digits}f}"                          # the size of the number, without its sign
    value = round(value, digits)                               # -0.01 shown with 1 decimal is 0.0: no sign then
    # returns a str, e.g. pct(-2.04) -> '−2.0', pct(4.49) -> '+4.5', pct(-0.01) -> '0.0'
    return ("+" if value > 0 else "−" if value < 0 else "") + text


def neg(value, digits=1):
    """A number with a real minus sign when negative and no plus sign, e.g. -0.6 -> '−0.6'."""
    # returns a str, e.g. neg(-0.64) -> '−0.6', neg(2.3) -> '2.3', neg(-0.01) -> '0.0'
    return ("−" if round(value, digits) < 0 else "") + f"{abs(value):.{digits}f}"


def tile(value, label):
    """One headline number with its label."""
    # returns a str of HTML, e.g. '<div class="kpi"><b>26.3%</b><span>Unemployment peak, Feb 2013</span></div>'
    return f'<div class="kpi"><b>{escape(value)}</b><span>{escape(label)}</span></div>'


def chart(cid, label, short=False):
    """An empty div the page's JavaScript fills with chart `cid`."""
    cls = "chart short" if short else "chart"                  # short charts sit under a taller one in the same panel
    # returns a str of HTML, e.g. '<div id="ov_gdp" class="chart" role="img" aria-label="Real GDP, 1995 = 100"></div>'
    return f'<div id="{cid}" class="{cls}" role="img" aria-label="{escape(label)}"></div>'


def caption(text):
    """A small label above a chart, naming what it shows."""
    # returns a str of HTML, e.g. '<p class="label">Current account, % of GDP</p>'
    return f'<p class="label">{text}</p>'


def panel(tag, question, finding, how, body, so=""):
    """One section: a question, its one-line finding, how to read it, the chart(s), and what it tells us."""
    how_html = f'<p class="how"><b>How to read it.</b> {how}</p>' if how else ""
    so_html = f'<div class="so">{so}</div>' if so else ""
    # returns a str of HTML, e.g. '<section class="panel"><p class="tag">1995–2007 · 01</p><h2>What happened to interest rates ...'
    return (f'<section class="panel"><p class="tag">{tag}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p>{how_html}{body}{so_html}</section>')


def intro(number, period, question, finding, summary, tiles):
    """The opening card of a period tab: which period, its question, the finding, a short summary and 4 numbers."""
    kp = '<div class="kpis">' + "".join(tile(v, l) for v, l in tiles) + "</div>"
    # returns a str of HTML, e.g. '<section class="panel intro"><p class="tag">Period 1 of 6 · 1995–2007</p><h2>Why did Spain ...'
    return (f'<section class="panel intro"><p class="tag">Period {number} of 6 · {escape(period)}</p><h2>{escape(question)}</h2>'
            f'<p class="dek">{finding}</p><p class="sum">{summary}</p>{kp}</section>')


# ---- chart specs: plain dicts the JavaScript turns into ECharts options ----

def pts(series, start, end):
    """Monthly or quarterly points [date, value] between two dates, for a time axis."""
    s = series.loc[start:end].dropna()                         # the window, gaps removed
    # returns a list of [str, float], e.g. [['2007-01-01', 8.4], ['2007-02-01', 8.3], ...]
    return [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in s.items()]


def ypts(series, y0, y1):
    """Annual points placed in the middle of each year, for a time axis shared with monthly data."""
    s = series.loc[y0:y1].dropna()                             # the years, gaps removed
    # returns a list of [str, float], e.g. [['2007-07-01', 35.8], ['2008-07-01', 39.7], ...]
    return [[f"{int(y)}-07-01", round(float(v), 2)] for y, v in s.items()]


def ser(name, color, data, **extra):
    """One series of a chart: its name, colour token and points."""
    # returns a dict, e.g. {'name': 'Spain', 'c': '--es', 'd': [['2007-01-01', 8.4], ...]}
    return {"name": name, "c": color, "d": data, **extra}


def tchart(series, start, end, unit, freq, dec=1, band=None, events=None, zero=False, scale=False, bands=False, signed=False):
    """A line chart on a time axis."""
    # returns a dict, e.g. {'kind': 'line', 'x': 'time', 'xmin': '2006-01-01', 'xmax': '2011-12-31', 'unit': '%', 'freq': 'M', ...}
    end = str(end)[:10]                                        # e.g. '2009-12-31'
    if end.endswith("-12-31"):                                 # end on the next 1 January, where the axis has a year tick
        end = f"{int(end[:4]) + 1}-01-01"
    return {"kind": "line", "x": "time", "series": series, "xmin": str(start)[:10], "xmax": end, "unit": unit,
            "freq": freq, "dec": dec, "band": band, "events": events or [], "zero": zero, "scale": scale, "bands": bands,
            "signed": signed}


def ychart(items, y0, y1, unit, dec=1, band=None, kind="bar", zero=True, signed=False, narrow_from=None):
    """A bar (or stacked bar) chart with one category per year; items = [(name, colour, Series, extra), ...]."""
    years = list(range(y0, y1 + 1))                            # the categories
    series = []                                                # one dict per bar series
    for name, color, s, extra in items:
        vals = s.reindex(years)                                # aligned on the years, missing -> NaN
        series.append(ser(name, color, [None if pd.isna(v) else round(float(v), 2) for v in vals], **extra))
    # returns a dict, e.g. {'kind': 'bar', 'x': 'year', 'years': ['2008', ...], 'series': [...], 'unit': '%', ...}
    return {"kind": kind, "x": "year", "years": [str(y) for y in years], "series": series, "unit": unit, "dec": dec,
            "band": [str(band[0]), str(band[1]), band[2]] if band else None, "events": [], "zero": zero, "signed": signed,
            "freq": "A", "narrowFrom": str(narrow_from) if narrow_from else None}   # first year shown on a phone


def band_of(key, monthly):
    """The shaded band of one period: [start, end, label]."""
    p = next(x for x in PERIODS if x["key"] == key)            # the period dict
    start, end = period_bounds(p, monthly)                     # its dates
    # returns a list, e.g. ['2008-01-01', '2009-12-31', 'The bubble bursts']
    return [str(start)[:10], str(end)[:10], p["name"]]


def chart_specs(a, q, m, f):
    """Every chart on the page, by div id."""
    end = m.dropna(how="all").index[-1]                        # latest month with data
    last = str(end + pd.offsets.MonthEnd(0))[:10]              # the end of that month, for axis limits
    ly = f["head"]["last_year"]                                # latest year with annual data
    EV_EURO = [["1999-01-01", "Euro launched"]]
    EV_LEH = [["2008-09-15", "Lehman fails"]]
    EV_DEBT = [["2010-05-02", "Greek rescue"], ["2012-07-26", "Jul 2012"]]
    EV_COVID = [["2020-03-14", "Lockdown"], ["2022-02-24", "Ukraine war"]]
    g95 = {k: rebased(q[f"gdp_{k}"], "1995-01-01") for k in ["es", "ea"]}   # real GDP, Q1 1995 = 100
    g08 = {k: rebased(q[f"gdp_{k}"], "2008-01-01") for k in ["es", "ea", "de"]}   # real GDP, Q1 2008 = 100
    g19 = {k: rebased(q[f"gdp_{k}"], "2019-10-01") for k in COUNTRIES.values()}   # real GDP, Q4 2019 = 100
    house = rebased(q["house_real_es"], "1995-01-01")         # real house prices, Q1 1995 = 100
    specs = {
        # ---- overview ----
        "ov_gdp": tchart([ser("Spain", "--es", pts(g95["es"], START, last)), ser("Euro area", "--ea", pts(g95["ea"], START, last))],
                         START, last, "", "Q", dec=1, bands=True, scale=True),
        "ov_unemp": tchart([ser("Spain", "--es", pts(m["unemp_es"], START, last)), ser("Euro area", "--ea", pts(m["unemp_ea"], START, last))],
                           START, last, "%", "M", bands=True),
        "ov_infl": tchart([ser("Spain", "--es", pts(m["infl_es"], START, last)), ser("Euro area", "--ea", pts(m["infl_ea"], START, last))],
                          START, last, "%", "M", bands=True, zero=True),
        # ---- 1995-2007 boom ----
        "b_rates": tchart([ser("3-month interest rate", "--s2", pts(m["rate3m_es"], START, "2009-12-31"), short="3-month rate"),
                           ser("Spanish inflation", "--ref", pts(m["infl_es"], START, "2009-12-31"), dash=True, short="Inflation"),
                           ser("Real rate (rate − inflation)", "--es", pts(m["real_rate_es"], START, "2009-12-31"), w=2.5, short="Real rate")],
                          START, "2009-12-31", "%", "M", band=band_of("boom", m), events=EV_EURO, zero=True),
        "b_credit": tchart([ser("Households", "--es", pts(q["credit_hh_es"], START, "2010-12-31")),
                            ser("Non-financial companies", "--s2", pts(q["credit_nfc_es"], START, "2010-12-31"), short="Companies")],
                           START, "2010-12-31", "%", "Q", dec=0, band=band_of("boom", m)),
        "b_house": tchart([ser("Real house prices (1995 = 100)", "--es", pts(house, START, "2010-12-31"), short="House prices")],
                          START, "2010-12-31", "", "Q", dec=0, band=band_of("boom", m), scale=True),
        "b_constr": tchart([ser("Spain", "--es", ypts(a["constr_gva_es"], 1995, 2013)), ser("Euro area", "--ea", ypts(a["constr_gva_ea"], 1995, 2013))],
                           START, "2013-12-31", "%", "A", band=band_of("boom", m), scale=True),
        "b_inv": tchart([ser("Spain", "--es", ypts(a["inv_es"], 1995, 2013)), ser("Euro area", "--ea", ypts(a["inv_ea"], 1995, 2013))],
                        START, "2013-12-31", "%", "A", band=band_of("boom", m), scale=True),
        "b_ca": tchart([ser("Current account, last 4 quarters", "--es", pts(q["ca4_es"], START, "2013-12-31"), short="Current account")],
                       START, "2013-12-31", "%", "Q", band=band_of("boom", m), zero=True),
        "b_ulc": tchart([ser("Spain", "--es", ypts(a["ulc_es"], 1999, 2013)), ser("Euro area", "--ea", ypts(a["ulc_ea"], 1999, 2013)),
                         ser("Germany", "--de", ypts(a["ulc_de"], 1999, 2013))],
                        "1999-01-01", "2013-12-31", "", "A", band=band_of("boom", m), scale=True),
        # ---- 2008-2009 bust ----
        "g_gdp": tchart([ser("Spain", "--es", pts(g08["es"], "2006-01-01", "2011-12-31")), ser("Euro area", "--ea", pts(g08["ea"], "2006-01-01", "2011-12-31")),
                         ser("Germany", "--de", pts(g08["de"], "2006-01-01", "2011-12-31"))],
                        "2006-01-01", "2011-12-31", "", "Q", band=band_of("bust", m), events=EV_LEH, scale=True),
        "g_unemp": tchart([ser("Spain", "--es", pts(m["unemp_es"], "2006-01-01", "2011-12-31")), ser("Euro area", "--ea", pts(m["unemp_ea"], "2006-01-01", "2011-12-31"))],
                          "2006-01-01", "2011-12-31", "%", "M", band=band_of("bust", m), events=EV_LEH),
        "g_temp": tchart([ser("Spain", "--es", ypts(a["temp_es"], 1995, ly)), ser("Euro area", "--ea", ypts(a["temp_ea"], 1995, ly))],
                         START, f"{ly}-12-31", "%", "A", band=band_of("bust", m)),
        "g_balance": ychart([("Spain", "--es", a["balance_es"], {}), ("Euro area", "--ea", a["balance_ea"], {})], 2000, 2013, "%",
                            band=(2008, 2009, "Bust"), signed=True),
        # ---- 2010-2013 debt crisis ----
        "d_y10": tchart([ser("Spain", "--es", pts(m["y10_es"], "2007-01-01", "2015-12-31")), ser("Germany", "--de", pts(m["y10_de"], "2007-01-01", "2015-12-31"))],
                        "2007-01-01", "2015-12-31", "%", "M", dec=2, band=band_of("debt", m), events=EV_DEBT),
        "d_spread": tchart([ser("Spread Spain − Germany", "--es", pts(m["spread_bp"], "2007-01-01", "2015-12-31"), short="Spread")],
                           "2007-01-01", "2015-12-31", "bp", "M", dec=0, band=band_of("debt", m), events=EV_DEBT, zero=True),
        "d_growth": ychart([("Spain", "--es", a["growth_es"], {}), ("Euro area", "--ea", a["growth_ea"], {})], 2007, 2016, "%",
                           band=(2010, 2013, "Debt crisis"), signed=True),
        "d_shift": tchart([ser("Household + company debt", "--s2", pts(q["credit_es"], "2000-01-01", last), short="Private debt"),
                           ser("Public debt", "--es", ypts(a["debt_es"], 2000, ly))],
                          "2000-01-01", last, "%", "Q", dec=0, band=band_of("debt", m)),
        "d_unemp": tchart([ser("All ages", "--es", pts(m["unemp_es"], "2007-01-01", "2016-12-31")), ser("Under 25", "--s2", pts(m["youth_es"], "2007-01-01", "2016-12-31"))],
                          "2007-01-01", "2016-12-31", "%", "M", band=band_of("debt", m)),
        # ---- 2014-2019 recovery ----
        "r_exp": tchart([ser("Spain", "--es", ypts(a["exports_es"], 1995, ly)), ser("Euro area", "--ea", ypts(a["exports_ea"], 1995, ly))],
                        START, f"{ly}-12-31", "%", "A", band=band_of("recovery", m), scale=True),
        "r_ca": tchart([ser("Current account, last 4 quarters", "--es", pts(q["ca4_es"], "2000-01-01", last), short="Current account")],
                       "2000-01-01", last, "%", "Q", band=band_of("recovery", m), zero=True),
        "r_ulc": tchart([ser("Spain", "--es", ypts(a["ulc_es"], 1999, 2019)), ser("Euro area", "--ea", ypts(a["ulc_ea"], 1999, 2019)),
                         ser("Germany", "--de", ypts(a["ulc_de"], 1999, 2019))],
                        "1999-01-01", "2019-12-31", "", "A", band=band_of("recovery", m), scale=True),
        "r_debt": tchart([ser("Spain", "--es", ypts(a["debt_es"], 1995, ly)), ser("Euro area", "--ea", ypts(a["debt_ea"], 1995, ly)),
                          ser("Germany", "--de", ypts(a["debt_de"], 1995, ly))],
                         START, f"{ly}-12-31", "%", "A", dec=0, band=band_of("recovery", m)),
        # ---- 2020-2022 covid and inflation ----
        "c_gdp": tchart([ser(NAMES[k], f"--{k}", pts(g19[k], "2019-01-01", last)) for k in ["ea", "es", "de", "fr", "it"]],
                        "2019-01-01", last, "", "Q", band=band_of("covid", m), events=EV_COVID[:1], scale=True),
        "c_tour": ychart([("Foreign tourists' nights", "--es", a["nights_es"], {})], 2005, ly, "m", dec=0, band=(2020, 2022, "Covid")),
        "c_infl": tchart([ser("Spain", "--es", pts(m["infl_es"], "2019-01-01", last)), ser("Euro area", "--ea", pts(m["infl_ea"], "2019-01-01", last))],
                         "2019-01-01", last, "%", "M", band=band_of("covid", m), events=EV_COVID[1:], zero=True),
        "c_nrg": tchart([ser("Spain", "--es", pts(m["infl_nrg_es"], "2019-01-01", last)), ser("Euro area", "--ea", pts(m["infl_nrg_ea"], "2019-01-01", last))],
                        "2019-01-01", last, "%", "M", band=band_of("covid", m), events=EV_COVID[1:], zero=True),
        "c_rates": tchart([ser("ECB deposit rate", "--s2", pts(m["ecb_dfr"], "2019-01-01", last), short="ECB deposit"),
                           ser("3-month rate (Euribor)", "--ref", pts(m["rate3m_es"], "2019-01-01", last), dash=True, short="3-month"),
                           ser("Spain 10-year yield", "--es", pts(m["y10_es"], "2019-01-01", last), short="Spain 10y")],
                          "2019-01-01", last, "%", "M", dec=2, band=band_of("covid", m), zero=True),
        # ---- 2023-today ----
        "t_growth": ychart([(NAMES[k], f"--{k}", a[f"growth_{k}"], {}) for k in ["ea", "es", "de", "fr", "it"]], 2015, ly, "%",
                           band=(2023, ly, "Since 2023"), signed=True, narrow_from=2019),
        "t_sources": ychart([("More people working", "--es", a["emp_growth_es"], {}),
                             ("More output per worker", "--s2", a["perworker_growth_es"], {}),
                             ("Real GDP growth", "--ink", a["growth_es"], {"dot": True})], 2015, ly, "%",
                            band=(2023, ly, "Since 2023"), kind="stack", signed=True),
        "t_pps": tchart([ser("Spain", "--es", ypts(a["pps_es"], 1995, ly)), ser("Euro area", "--ea", ypts(a["pps_ea"], 1995, ly))],
                        START, f"{ly}-12-31", "", "A", dec=0, band=band_of("today", m), scale=True),
        "t_prod": tchart([ser("Spain", "--es", ypts(a["prodlvl_es"], 1995, ly)), ser("Euro area", "--ea", ypts(a["prodlvl_ea"], 1995, ly))],
                         START, f"{ly}-12-31", "", "A", dec=0, band=band_of("today", m), scale=True),
        "t_house": tchart([ser("Real house prices (1995 = 100)", "--es", pts(house, START, last), short="House prices")],
                          START, last, "", "Q", dec=0, band=band_of("today", m), scale=True),
    }
    # returns a dict of ~33 chart specs keyed by div id, e.g. {'ov_gdp': {'kind': 'line', 'x': 'time', 'series': [...], ...}, ...}
    return specs


# ---- text: every number comes from the facts dicts, so it stays true after a re-run ----

def header_answer(h):
    """The short answer under the title."""
    # returns a str of HTML, ~600 characters, e.g. '<b>Six periods, each with a different driver.</b> After joining the euro ...'
    return (f"<b>Six periods, each with a different driver.</b> As Spain joined the euro, its 3-month interest rate fell from "
            f"{h['rate_1995']:.1f}% (1995) to {h['rate_1999']:.1f}% (1999), and household and company debt rose from "
            f"{h['credit_1995']:.0f}% to {h['credit_2007']:.0f}% of GDP by 2007. The bust and the euro debt crisis took "
            f"unemployment from {h['u_low']:.1f}% ({h['u_low_d']}) to {h['u_peak']:.1f}% ({h['u_peak_d']}). By {h['gdp_last_q']} "
            f"real GDP was {pct(h['gdp_vs_peak_es'], 0)}% above its 2008 peak (euro area {pct(h['gdp_vs_peak_ea'], 0)}%), "
            f"while unemployment, at {h['u_last']:.1f}%, was still above the euro area's {h['u_ea_last']:.1f}%.")


def overview_tab(t, h):
    """Overview: the whole period at a glance."""
    best = t["growth_es"].idxmax(); worst = t["growth_es"].idxmin()   # periods with the fastest and slowest average growth
    name = {p["key"]: p["name"] for p in PERIODS}              # key -> period name
    rows = "".join(
        f"<tr><td>{escape(r['label'])}</td><td>{pct(r['growth_es'])}% <small>/ {pct(r['growth_ea'])}%</small></td>"
        f"<td>{neg(r['infl_es'])}% <small>/ {neg(r['infl_ea'])}%</small></td>"
        f"<td>{r['unemp_start']:.1f}% → {r['unemp_end']:.1f}%</td><td>{r['spread_bp']:.0f} bp</td><td>{pct(r['ca'])}%</td>"
        f"<td>{r['debt_end']:.0f}%</td><td>{pct(r['house'], 0)}%</td></tr>" for _, r in t.iterrows())
    table = ('<p class="swipe">Swipe the table sideways to see every column.</p><div class="scroll"><table class="periods">'
             "<tr><th>Period</th><th>Real GDP growth, avg / yr<br><small>Spain / euro area</small></th>"
             "<th>Inflation, avg<br><small>Spain / euro area</small></th><th>Unemployment<br><small>start → end</small></th>"
             "<th>10-year spread over Germany, avg</th><th>Current account, avg % of GDP</th><th>Public debt at end, % of GDP</th>"
             f"<th>Real house prices, change</th></tr>{rows}</table></div>"
             f'<p class="note">Growth averages use yearly data (Spain from 1996, to {h["last_year"]}); the other columns use '
             f"monthly or quarterly data to the latest release. Euro-area unemployment starts in 2000 and euro-area inflation "
             f"in 1997.</p>")
    u_es = t.loc["debt", "unemp_end"] - t.loc["bust", "unemp_start"]   # rise in Spanish unemployment 2008 -> 2013, points
    return "".join([
        panel("Overview · 01", "How did output move through the six periods?",
              f"Average growth ranged from {pct(t.loc[worst, 'growth_es'])}% a year ({name[worst].lower()}) to "
              f"{pct(t.loc[best, 'growth_es'])}% ({name[best].lower()}).",
              "Real GDP (total output with inflation removed) as an index: 1995 = 100, so 150 means 50% more output than in 1995. "
              "The shaded bands are the six periods, one per tab above.",
              chart("ov_gdp", "Real GDP of Spain and the euro area, 1995 = 100") +
              '<p class="note"><span class="hint">Hover over or click</span> a chart to read the values.</p>',
              "<p>Real GDP grows when more people work and when each worker produces more. Spain's population grew from "
              f"{h['pop_1995']:.1f} million in 1995 to {h['pop_last']:.1f} million in {h['pop_last_y']}, so part of its faster "
              "growth is simply more people. The <b>Since 2023</b> tab separates the two.</p>"),
        panel("Overview · 02", "What were the key numbers in each period?",
              f"Unemployment rose by {u_es:.1f} percentage points between 2008 and 2013.",
              "One row per period. Growth and inflation are yearly averages. Unemployment shows the first and last month of the period. "
              "The spread is the extra interest Spain paid over Germany on 10-year bonds (100 bp = 1 percentage point). "
              "The current account is what Spain earned from abroad minus what it paid (below zero = borrowing from abroad).",
              table,
              "<p>No period was good on every measure. The boom combined fast growth with a large external deficit and a "
              "house-price bubble. The recovery fixed the external deficit, but it started with very high unemployment and "
              "public debt. The tabs explain each row.</p>"),
        panel("Overview · 03", "How did unemployment and inflation move?",
              f"Spanish unemployment ranged from {h['u_low']:.1f}% to {h['u_peak']:.1f}%; the euro area's moved much less.",
              "Top: unemployment rate, % of the labour force. Bottom: inflation, the yearly rise in consumer prices (HICP). "
              "Spain and the euro area.",
              caption("Unemployment rate, %") + chart("ov_unemp", "Unemployment rate, Spain and euro area") +
              caption("Inflation (HICP), % over 12 months") + chart("ov_infl", "Inflation, Spain and euro area", short=True),
              "<p>Spanish unemployment swings far more than the euro area's, in both directions. Two reasons come back in "
              "several tabs: construction and tourism are large and move with the cycle, and many jobs were on temporary "
              "contracts, which are cheap to end (see <b>2008–2009</b>).</p>"),
    ])


def boom_tab(f, t):
    """1995-2007: the euro boom."""
    tag = "1995–2007 · "
    tiles = [(f"{pct(f['growth_es'])}%", f"Real GDP growth a year (euro area {pct(f['growth_ea'])}%)"),
             (f"{f['u_1995']:.0f}% → {f['u_2007']:.1f}%", "Unemployment, Jan 1995 → Dec 2007"),
             (f"{f['hh_1995'] + f['nfc_1995']:.0f}% → {f['hh_2007'] + f['nfc_2007']:.0f}%", "Household + company debt, % of GDP"),
             (f"{neg(f['ca_low'])}%", f"Current account at its lowest, % of GDP ({f['ca_low_q']})")]
    return "".join([
        intro(1, "1995–2007", "Why did Spain grow so fast after joining the euro?",
              f"Real GDP grew {pct(f['growth_es'])}% a year on average, against {pct(f['growth_ea'])}% in the euro area.",
              "Joining the euro brought German-level interest rates to an economy with higher inflation. Borrowing became very "
              "cheap in real terms, credit flowed into housing, and construction became a much larger part of the economy. "
              "Spending grew faster than income, and the difference was borrowed from abroad.", tiles),
        panel(tag + "01", "What happened to interest rates when Spain joined the euro?",
              f"The real short-term rate averaged {neg(f['real_rate_avg'])}% in Spain in 1999–2007 (below zero in "
              f"{f['real_rate_neg']:.0f}% of months); for the euro area as a whole the same rate meant {neg(f['real_rate_ea'])}%.",
              "Three lines, all in %. The <b>3-month interest rate</b> is what banks charge each other for 3-month loans "
              "(Euribor from 1999, the same in the whole euro area); mortgages and business loans are priced off it. "
              "<b>Inflation</b> is the yearly rise in Spanish consumer prices. The <b>real rate</b> is the first minus the second: "
              "what borrowing costs once inflation is removed.",
              chart("b_rates", "Spain: 3-month interest rate, inflation and real rate, 1995-2009"),
              f"<p>To join the euro, Spain had to bring inflation and interest rates down to the level of the core countries. "
              f"After 1999 the ECB set one interest rate for the whole euro area, based on average euro-area inflation. Spanish "
              f"inflation was higher ({f['infl_es']:.1f}% a year in 1999–2007 against {f['infl_ea']:.1f}% for the euro area), so "
              f"the same rate was a lower real rate in Spain: about {f['real_rate_ea'] - f['real_rate_avg']:.1f} points lower "
              f"than for the euro area on average. A real rate near or below zero makes borrowing to buy a house "
              f"or to build very attractive: this is where the credit boom starts.</p>"),
        panel(tag + "02", "Where did the borrowed money go?",
              f"Household debt rose from {f['hh_1995']:.0f}% to {f['hh_2007']:.0f}% of GDP; real house prices rose "
              f"{f['hp_rise']:.0f}% to their peak in {f['hp_peak_q']}.",
              "Top: loans and bonds owed by households and by non-financial companies, as a % of a year's GDP (BIS data). "
              "Bottom: house prices with general inflation removed, 1995 = 100.",
              caption("Debt of households and companies, % of GDP") + chart("b_credit", "Spain: household and company debt, % of GDP") +
              caption("Real house prices, 1995 = 100") + chart("b_house", "Spain: real house prices, 1995 = 100", short=True),
              f"<p>Company debt rose from {f['nfc_1995']:.0f}% to {f['nfc_2007']:.0f}% of GDP, much of it in construction "
              f"and real estate. Rising prices made housing look like a safe investment, which brought in more borrowing: "
              f"credit and prices pushed each other up. Demand was also real: the population grew from {f['pop_1998']:.1f} "
              f"million (1998) to {f['pop_2008']:.1f} million (2008), mostly through immigration.</p>"),
        panel(tag + "03", "How much of the economy was construction?",
              f"Construction reached {f['cg_peak']:.1f}% of the economy in {f['cg_year']} (euro area {f['cg_ea']:.1f}%) "
              f"and {f['cj_peak']:.1f}% of all jobs.",
              "Top: construction's share of everything the economy produces (gross value added). Bottom: investment in "
              "buildings, homes, infrastructure and machines, as a % of GDP. Spain and the euro area.",
              caption("Construction, % of value added") + chart("b_constr", "Construction share of value added, Spain and euro area", short=True) +
              caption("Investment, % of GDP") + chart("b_inv", "Investment, % of GDP, Spain and euro area", short=True),
              f"<p>In {f['inv_year']} investment was {f['inv_peak']:.0f}% of GDP in Spain against {f['inv_ea']:.0f}% in the "
              f"euro area. Building homes counts as output while it happens, but homes built for buyers who are no longer "
              f"there add little future output. With so much activity and so many jobs in one sector, the whole economy "
              f"depended on one price: the price of housing.</p>"),
        panel(tag + "04", "What was fragile?",
              f"The current account deficit reached {abs(f['ca_low']):.1f}% of GDP ({f['ca_low_q']}); unit labour costs rose "
              f"{f['ulc_es']:.0f}% in 1999–2008, against {pct(f['ulc_de'], 0)}% in Germany.",
              "Top: the current account, what Spain earns from abroad minus what it pays, as the average of the last 4 quarters "
              "(% of GDP). Below zero, Spain spends more than it earns and borrows the difference from abroad. Bottom: unit labour "
              "costs, the wage cost of producing one unit of output, 1999 = 100.",
              caption("Current account, % of GDP") + chart("b_ca", "Spain: current account, % of GDP", short=True) +
              caption("Unit labour costs, 1999 = 100") + chart("b_ulc", "Unit labour costs, Spain, euro area and Germany, 1999 = 100", short=True),
              f"<p>Three weak spots grew during the boom. <b>Foreign borrowing:</b> Spanish banks financed part of the credit by "
              f"borrowing abroad, and that kind of funding can stop suddenly. <b>Competitiveness:</b> wages and prices rose faster "
              f"than productivity ({f['ulc_es']:.0f}% against {f['ulc_ea']:.0f}% for the euro area), and inside the euro there is "
              f"no currency to devalue. <b>One sector:</b> growth leaned on construction. Public finances looked solid: debt fell "
              f"to {f['debt_2007']:.0f}% of GDP in 2007 (euro area {f['debt_ea_2007']:.0f}%) with a surplus of "
              f"{f['balance_2007']:.1f}% of GDP. But part of that tax revenue came from the housing boom itself.</p>"),
    ])


def bust_tab(f):
    """2008-2009: the bubble bursts."""
    tag = "2008–2009 · "
    tiles = [(f"{neg(f['drop_es'])}%", f"Real GDP, {f['top_q_es']} → {f['low_q_es']}"),
             (f"{f['u_low']:.1f}% → {f['u_2009']:.1f}%", "Unemployment, 2007 low → Dec 2009"),
             (f"{f['jobs_lost'] / 1000:.1f} m", "Jobs lost, 2007 → 2009"),
             (f"{pct(f['balance_2007'])}% → {pct(f['balance_2009'])}%", "Budget balance, % of GDP, 2007 → 2009")]
    return "".join([
        intro(2, "2008–2009", "What happened when the bubble burst?",
              f"Real GDP fell {abs(f['drop_es']):.1f}% from {f['top_q_es']} to {f['low_q_es']}, and unemployment rose from "
              f"{f['u_low']:.1f}% to {f['u_2009']:.1f}% in two years.",
              "House prices stopped rising in 2007, and in 2008 the global financial crisis cut off the cheap funding Spanish "
              "banks relied on. Building stopped, construction workers lost their jobs, and households and firms with large "
              "debts cut their spending.", tiles),
        panel(tag + "01", "How fast did output fall?",
              f"Peak to bottom: Spain {neg(f['drop_es'])}%, euro area {neg(f['drop_ea'])}%, Germany {neg(f['drop_de'])}%.",
              "Real GDP, Q1 2008 = 100. A value of 96 means output 4% below its early-2008 level. The dashed line marks the "
              "failure of the US bank Lehman Brothers (Sep 2008), when the global crisis became acute.",
              chart("g_gdp", "Real GDP, Q1 2008 = 100, Spain, euro area and Germany"),
              f"<p>Spain's fall in output was {'smaller than' if f['drop_es'] > f['drop_ea'] else 'larger than'} the euro area's, "
              f"and Germany, an exporter, fell most when world trade collapsed. Spain's big difference was in jobs, as the "
              f"next panel shows. The ECB cut its main rate from "
              f"{f['mro_hi']:.2f}% ({f['mro_hi_d']}) to {f['mro_lo']:.2f}% ({f['mro_lo_d']}), but with banks and borrowers "
              f"loaded with property debt, cheaper money did not restart lending.</p>"),
        panel(tag + "02", "Why did unemployment rise so much more than in the euro area?",
              f"{f['jobs_lost'] / 1000:.1f} million jobs were lost in 2007–2009, {f['constr_share']:.0f}% of them in construction.",
              "Top: unemployment rate, % of the labour force. Bottom: employees on temporary (fixed-term) contracts, % of all "
              "employees, 1995 to today.",
              caption("Unemployment rate, %") + chart("g_unemp", "Unemployment, Spain and euro area, 2006-2011", short=True) +
              caption("Temporary contracts, % of employees") + chart("g_temp", "Temporary contracts, Spain and euro area", short=True),
              f"<p>Unemployment rose from {f['u_low']:.1f}% to {f['u_2009']:.1f}% in Spain, against {f['u_ea_2007']:.1f}% to "
              f"{f['u_ea_2009']:.1f}% in the euro area. Two features explain the gap. <b>Construction</b> alone accounted for "
              f"{f['constr_share']:.0f}% of the jobs lost. <b>Temporary contracts:</b> in 2007 {f['temp_es_2007']:.0f}% of Spanish "
              f"employees had one ({f['temp_ea_2007']:.0f}% in the euro area). Ending them is cheap, so firms adjusted by cutting "
              f"staff rather than hours or wages, while in Germany many firms kept workers on reduced hours. Young workers, who "
              f"held most temporary contracts, were hit first.</p>"),
        panel(tag + "03", "What happened to public finances?",
              f"The budget went from a surplus of {f['balance_2007']:.1f}% of GDP in 2007 to a deficit of "
              f"{abs(f['balance_2009']):.1f}% in 2009.",
              "Government revenue minus spending, % of GDP, each year. Above zero is a surplus, below zero a deficit.",
              chart("g_balance", "Government budget balance, % of GDP, Spain and euro area, 2000-2013"),
              f"<p>Most of the swing happened by itself: taxes linked to property sales and construction collapsed, and spending "
              f"on unemployment benefits rose with unemployment (automatic stabilisers). Public debt rose from "
              f"{f['debt_2007']:.0f}% to {f['debt_2009']:.0f}% of GDP in two years, still below the euro area's "
              f"{f['debt_ea_2009']:.0f}%. But a deficit of {abs(f['balance_2009']):.1f}% of GDP (euro area "
              f"{abs(f['balance_ea_2009']):.1f}%) is what investors started to watch in 2010.</p>"),
    ])


def debt_tab(f):
    """2010-2013: the euro debt crisis."""
    tag = "2010–2013 · "
    tiles = [(f"{f['s_peak']:.0f} bp", f"10-year spread over Germany, peak ({f['s_peak_d']})"),
             (f"{f['u_peak']:.1f}%", f"Unemployment peak ({f['u_peak_d']})"),
             (f"{f['yo_peak']:.1f}%", f"Under-25 unemployment peak ({f['yo_peak_d']})"),
             (f"{neg(f['hp_fall'], 0)}%", f"Real house prices, 2007 peak → {f['hp_low_q']}")]
    return "".join([
        intro(3, "2010–2013", "Why did Spain fall into a second recession?",
              f"Real GDP shrank again in 2012 ({pct(f['g_2012'])}%) and 2013 ({pct(f['g_2013'])}%), and unemployment peaked "
              f"at {f['u_peak']:.1f}% in {f['u_peak_d']}.",
              "From 2010 doubts about Greece spread to other euro countries with large deficits or weak banks. Spain's borrowing "
              "costs rose, the deficit was cut through spending cuts and tax rises, banks with property losses needed new capital, "
              "and households and firms kept paying down debt. All of these reduced spending at the same time.", tiles),
        panel(tag + "01", "Why did Spain's borrowing costs jump?",
              f"The 10-year spread over Germany went from {f['s_2007']:.0f} bp on average in 2007 to {f['s_peak']:.0f} bp in "
              f"{f['s_peak_d']} (monthly average).",
              "Top: the yield on 10-year government bonds of Spain and Germany, %. Bottom: the difference, in basis points "
              "(100 bp = 1 percentage point): the extra return investors asked for holding Spanish rather than German debt. "
              "Dashed lines: the first Greek rescue (May 2010), and in July 2012 the euro-area loan to recapitalise Spanish banks "
              "followed by the ECB's pledge to do \"whatever it takes\" to preserve the euro.",
              caption("10-year government bond yields, %") + chart("d_y10", "10-year bond yields, Spain and Germany, 2007-2015", short=True) +
              caption("Spread, Spain minus Germany, basis points") + chart("d_spread", "Spain-Germany 10-year spread, bp, 2007-2015", short=True),
              f"<p>Before 2008 markets treated all euro government debt almost the same. Greece's rescue showed that a euro "
              f"country might not repay, and investors started to price that risk. In Spain the fear centred on the banks: if "
              f"property losses forced the state to rescue them, public debt would jump, and the banks themselves held much of "
              f"that public debt. Spain's 10-year yield reached {f['y_peak']:.2f}% in {f['y_peak_d']} (Germany "
              f"{f['y_de_at_peak']:.2f}%). After July 2012 the risk of a break-up of the euro faded, and by December 2013 the "
              f"spread was {f['s_2013']:.0f} bp.</p>"),
        panel(tag + "02", "Why did the economy shrink again in 2012–2013?",
              f"Spain's GDP fell {abs(f['g_2012']):.1f}% in 2012 and {abs(f['g_2013']):.1f}% in 2013; the euro area's "
              f"{pct(f['g_ea_2012'])}% and {pct(f['g_ea_2013'])}%.",
              "Yearly change in real GDP, %. Bars below zero are years in which output shrank.",
              chart("d_growth", "Real GDP growth, Spain and euro area, 2007-2016"),
              f"<p>Three forces pulled spending down together. <b>Fiscal consolidation:</b> the deficit went from "
              f"{abs(f['b_2009']):.1f}% of GDP in 2009 to {abs(f['b_2013']):.1f}% in 2013 (2012, at {abs(f['b_2012']):.1f}%, "
              f"includes the one-off cost of recapitalising banks), aiming to keep investors willing to lend. "
              f"<b>Deleveraging:</b> households and firms used their income to repay debt instead of spending. <b>Scarce credit:</b> "
              f"while the spread was high, banks paid more for funding and lent less. With all three pulling in the same "
              f"direction, domestic demand fell for a second time.</p>"),
        panel(tag + "03", "Where did the debt go?",
              f"Household and company debt fell from {f['c_peak']:.0f}% of GDP ({f['c_peak_q']}) to {f['c_2019']:.0f}% in 2019; "
              f"public debt rose from {f['d_2007']:.0f}% (2007) to {f['d_peak']:.0f}% ({f['d_peak_y']}).",
              "Both lines are Spanish debt as a % of GDP. Private = households and non-financial companies (BIS, quarterly). "
              "Public = general government debt (Eurostat, yearly).",
              chart("d_shift", "Spain: private and public debt, % of GDP, 2000 to today"),
              "<p>Private debt came down through repayments, defaults and write-offs. Public debt went up through deficits, "
              "support for banks and a shrinking GDP (the same debt is a larger share of a smaller economy). The debt did not "
              "disappear: part of it moved from private balance sheets to the state's. After a credit boom this is a common "
              "pattern.</p>"),
        panel(tag + "04", "How deep did the labour market fall?",
              f"Unemployment peaked at {f['u_peak']:.1f}% ({f['u_peak_d']}), and at {f['yo_peak']:.1f}% for under-25s "
              f"({f['yo_peak_d']}).",
              "Unemployment rate for all ages and for people under 25, % of the labour force.",
              chart("d_unemp", "Spain: unemployment, all ages and under 25, 2007-2016"),
              f"<p>At the peak more than one in four people looking for work had none (euro area {f['u_ea_at_peak']:.1f}%). "
              f"Long spells without work erode skills and make it harder to find a job later, a cost that lasts after the "
              f"recession ends. House prices kept falling until {f['hp_low_q']}: in real terms they ended {abs(f['hp_fall']):.0f}% "
              f"below the 2007 peak, adding losses for banks and for households.</p>"),
    ])


def recovery_tab(f):
    """2014-2019: recovery."""
    tag = "2014–2019 · "
    tiles = [(f"{pct(f['growth_es'])}%", f"Real GDP growth a year (euro area {pct(f['growth_ea'])}%)"),
             (f"{f['u_2014']:.1f}% → {f['u_2019']:.1f}%", "Unemployment, Jan 2014 → Dec 2019"),
             (f"{f['x_2009']:.0f}% → {f['x_2019']:.0f}%", "Exports, % of GDP, 2009 → 2019"),
             (f"{pct(f['ca_2019'])}%", "Current account, % of GDP, 2019")]
    return "".join([
        intro(4, "2014–2019", "What drove the recovery?",
              f"Growth averaged {pct(f['growth_es'])}% a year ({pct(f['growth_ea'])}% in the euro area) and unemployment fell "
              f"from {f['u_2014']:.1f}% to {f['u_2019']:.1f}%.",
              "Lower borrowing costs after 2012, ECB rates near zero, cheaper oil from 2014 and a gain in cost competitiveness all "
              "helped. The biggest change was in the external accounts: Spain started to sell more abroad than it bought.", tiles),
        panel(tag + "01", "Did Spain start selling more abroad?",
              f"Exports rose from {f['x_2009']:.0f}% of GDP in 2009 to {f['x_2019']:.0f}% in 2019; the current account went "
              f"from {neg(f['ca_low'])}% ({f['ca_low_q']}) to a surplus from {f['first_surplus']}.",
              "Top: exports of goods and services (including foreign tourists' spending in Spain), % of GDP. Bottom: the current "
              "account, average of the last 4 quarters, % of GDP.",
              caption("Exports, % of GDP") + chart("r_exp", "Exports, % of GDP, Spain and euro area", short=True) +
              caption("Current account, % of GDP") + chart("r_ca", "Spain: current account, % of GDP, 2000 to today", short=True),
              f"<p>Part of the turnaround came from weaker imports while home demand was low; part came from firms that started "
              f"to export when the home market shrank. Spain's export share is still below the euro area's ({f['x_ea_2019']:.0f}% "
              f"in 2019), partly because large countries trade less relative to their size. A surplus means Spain lends to the "
              f"rest of the world instead of borrowing from it, which reduces the dependence on foreign funding that made 2010–2012 "
              f"so dangerous.</p>"),
        panel(tag + "02", "Did costs come back in line with the euro area?",
              f"Spain's unit labour costs fell {abs(f['ulc_fall']):.0f}% from {f['ulc_top_y']} to {f['ulc_low_y']}, while "
              f"Germany's rose {f['ulc_de_same']:.0f}%.",
              "Unit labour costs, 1999 = 100: the wage cost of producing one unit of output. A rising line means each unit costs "
              "more to make.",
              chart("r_ulc", "Unit labour costs, Spain, euro area and Germany, 1999 = 100"),
              "<p>Inside the euro a country cannot make its currency cheaper. It can only regain price competitiveness by letting "
              "costs grow more slowly than its partners: an internal devaluation. Part of Spain's improvement came from the loss "
              "of low-productivity jobs, mainly in construction. Output per worker rises when the least productive jobs disappear, "
              "which is not the same as each worker becoming more productive.</p>"),
        panel(tag + "03", "What was still fragile?",
              f"In 2019 unemployment was {f['u_2019']:.1f}% (euro area {f['u_ea_2019']:.1f}%) and public debt {f['d_2019']:.0f}% "
              f"of GDP (euro area {f['d_ea_2019']:.0f}%).",
              "General government debt, % of GDP, for Spain, the euro area and Germany.",
              chart("r_debt", "Public debt, % of GDP, Spain, euro area and Germany"),
              f"<p>Public debt stopped rising but barely came down, so Spain entered the next crisis with debt near "
              f"{f['d_2019']:.0f}% of GDP, against {f['d_2007']:.0f}% in 2007. {f['temp_2019']:.0f}% of employees were again on "
              f"temporary contracts ({f['temp_ea_2019']:.0f}% in the euro area), so jobs could still be cut quickly in a downturn. "
              f"Output per hour worked was {pct(f['prod_2019'])}% above 2007 (euro area {pct(f['prod_ea_2019'])}%).</p>"),
    ])


def covid_tab(f):
    """2020-2022: Covid and inflation."""
    tag = "2020–2022 · "
    tiles = [(f"{pct(f['g_2020'])}%", f"Real GDP in 2020 (euro area {pct(f['g_ea_2020'])}%)"),
             (f['back_es'], f"Back to the end-2019 level of GDP (euro area {f['back_ea']})"),
             (f"{f['i_pk']:.1f}%", f"Inflation peak ({f['i_pk_d']})"),
             (f"{neg(f['dfr_lo'])}% → {f['dfr_hi']:.1f}%", f"ECB deposit rate before the first rise ({f['first_hike']}) → peak ({f['dfr_hi_d']})")]
    later = f["back_n_es"] - f["back_n_ea"] if f["back_n_es"] is not None and f["back_n_ea"] is not None else 0   # quarters later than the euro area
    later_txt = (f"Spain got back to its end-2019 output in {f['back_es']}, {later} quarters after the euro area, "
                 f"because international travel took longer to return.") if later > 0 else \
                (f"Spain got back to its end-2019 output in {f['back_es']} (euro area {f['back_ea']}).")
    below = f" From {f['first_below']} Spanish inflation was below the euro area's." if f["first_below"] else ""
    return "".join([
        intro(5, "2020–2022", "Why did Covid hit Spain harder, and what happened to inflation?",
              f"Real GDP fell {abs(f['g_2020']):.1f}% in 2020 (euro area {abs(f['g_ea_2020']):.1f}%); inflation peaked at "
              f"{f['i_pk']:.1f}% in {f['i_pk_d']}.",
              "Lockdowns stopped tourism, hospitality and leisure, which are a larger part of Spain's economy than of most of its "
              "neighbours. When economies reopened, energy prices jumped, first with the reopening and then with the war in "
              "Ukraine, and in 2022 the ECB raised rates for the first time in eleven years.", tiles),
        panel(tag + "01", "Why did output fall more than in the rest of the euro area?",
              f"In Q2 2020 Spain's GDP was {abs(f['q2_es']):.1f}% below end-2019 (euro area {abs(f['q2_ea']):.1f}%, Germany "
              f"{abs(f['q2_de']):.1f}%, France {abs(f['q2_fr']):.1f}%, Italy {abs(f['q2_it']):.1f}%).",
              "Top: real GDP, Q4 2019 = 100, for Spain and the largest euro-area economies. Bottom: nights spent in Spanish hotels "
              "and other tourist accommodation by visitors living abroad, millions a year.",
              caption("Real GDP, Q4 2019 = 100") + chart("c_gdp", "Real GDP, Q4 2019 = 100, Spain, euro area, Germany, France, Italy") +
              caption("Nights spent by foreign tourists, millions") + chart("c_tour", "Nights spent by foreign tourists in Spain, millions", short=True),
              f"<p>Foreign tourists' nights fell {abs(f['n_drop']):.0f}% in 2020, from {f['n_2019']:.0f} million to "
              f"{f['n_2020']:.0f} million. Hotels, restaurants and leisure need people to travel and meet, so unlike much of "
              f"industry and office work they could not carry on under lockdown or from home. {later_txt}</p>"),
        panel(tag + "02", "How high did inflation go, and why did it turn earlier in Spain?",
              f"Spain peaked at {f['i_pk']:.1f}% in {f['i_pk_d']}, the euro area at {f['iea_pk']:.1f}% in {f['iea_pk_d']}.",
              "Yearly change in consumer prices (HICP), %. Top: all items. Bottom: energy only (electricity, gas, fuels). Dashed "
              "line: Russia's invasion of Ukraine (Feb 2022), which pushed gas prices up.",
              caption("Inflation, all items, %") + chart("c_infl", "Inflation, Spain and euro area, 2019 to today", short=True) +
              caption("Energy inflation, %") + chart("c_nrg", "Energy inflation, Spain and euro area, 2019 to today", short=True),
              f"<p>Energy explains most of the timing. Spanish energy inflation peaked at {f['e_pk']:.0f}% in {f['e_pk_d']}, the "
              f"euro area's at {f['eea_pk']:.0f}% in {f['eea_pk_d']}. Many Spanish households had electricity tariffs linked to the "
              f"daily wholesale price, so higher gas prices reached their bills within weeks, and so did the later fall. From June "
              f"2022 Spain and Portugal also capped the gas price used to set electricity prices (the \"Iberian exception\"). In "
              f"most of the euro area fixed-price contracts passed the rise on later.{below}"
              + (f" Energy prices were already falling on the year in Spain by {f['nrg_neg']}, and in the euro area by "
                 f"{f['nrg_neg_ea']}." if f["nrg_neg"] and f["nrg_neg_ea"] else "") + "</p>"),
        panel(tag + "03", "How fast did interest rates rise?",
              f"The ECB deposit rate went from {neg(f['dfr_lo'], 2)}% to {f['dfr_hi']:.2f}% between {f['first_hike']} and "
              f"{f['dfr_hi_d']}.",
              "All in %. The ECB deposit rate is what banks earn on money left at the ECB, the rate that steers the others. The "
              "3-month rate is Euribor. The Spanish 10-year yield is what the state pays to borrow for ten years.",
              chart("c_rates", "ECB deposit rate, 3-month rate and Spain 10-year yield, 2019 to today"),
              f"<p>Most Spanish mortgages have variable rates reset to Euribor every 6 or 12 months, so rate rises passed quickly "
              f"into household budgets; where fixed-rate mortgages dominate the effect is slower. The 3-month rate peaked at "
              f"{f['rate3m_hi']:.2f}% and the state's 10-year yield went from {f['y10_2021']:.2f}% (Dec 2021) to "
              f"{f['y10_hi']:.2f}% ({f['y10_hi_d']}). With public debt at {f['d_2022']:.0f}% of GDP in 2022, higher yields raise "
              f"the state's interest bill over time as old debt is refinanced.</p>"),
    ])


def today_tab(f):
    """2023 to today."""
    ly = f["ly"]                                               # latest year with yearly data (averages use 2023 -> ly)
    span = f"2023–{f['u_d'][-4:]}"                             # the tab covers 2023 to the latest month of data, e.g. '2023–2026'
    tag = "Since 2023 · "
    since = f"its lowest since {f['u_since']}" if f["u_since"] else "its lowest on record"
    tiles = [(f"{pct(f['g_es'])}%", f"Real GDP growth a year, 2023–{ly} (euro area {pct(f['g_ea'])}%)"),
             (f"{pct(f['emp'])}%", f"Growth in the number of people working, a year, 2023–{ly}"),
             (f"{f['u']:.1f}%", f"Unemployment, {f['u_d']} (euro area {f['u_ea']:.1f}%)"),
             (f"{f['pps']:.0f}", f"GDP per person in PPS, EU = 100 ({ly}; euro area {f['pps_ea']:.0f})")]
    return "".join([
        intro(6, span, "How has Spain grown since 2023, and what still lags?",
              f"Growth averaged {pct(f['g_es'])}% a year in 2023–{ly}, against {pct(f['g_ea'])}% in the euro area.",
              "This tab splits growth into more people working and more output per worker, then looks at the measures that "
              "decide living standards: output per person, output per hour, jobs and housing.", tiles),
        panel(tag + "01", "How fast is Spain growing compared with its neighbours?",
              f"Average 2023–{ly}: Spain {pct(f['g_es'])}%, euro area {pct(f['g_ea'])}%, Germany {pct(f['g_de'])}%, "
              f"France {pct(f['g_fr'])}%, Italy {pct(f['g_it'])}%.",
              "Yearly change in real GDP, %, grouped by year.",
              chart("t_growth", "Real GDP growth, Spain, euro area, Germany, France and Italy, 2015 to latest year"),
              f"<p>Tourism had its strongest years on record: {f['n_last']:.0f} million nights by foreign visitors in {ly}, against "
              f"{f['n_2019']:.0f} million in 2019. Spain also has a smaller share of energy-intensive manufacturing than Germany, "
              f"so the 2022–2023 rise in gas prices weighed on it less. The current account stayed in surplus "
              f"({pct(f['ca'])}% of GDP over the last 4 quarters).</p>"),
        panel(tag + "02", "Where does the growth come from?",
              f"In 2023–{ly} the number of people working grew {pct(f['emp'])}% a year and output per worker "
              f"{pct(f['perworker'])}%.",
              "Each year's bar splits real GDP growth into two parts: more people working and more output per worker. The dot is "
              "total real GDP growth (the two parts add up to it, approximately).",
              chart("t_sources", "Spain: real GDP growth split into employment and output per worker, 2015 to latest year"),
              f"<p>{'Almost all' if f['perworker'] < 0.3 else 'Most'} of the growth since 2023 comes from more people working; "
              f"output per worker {'barely changed' if abs(f['perworker']) < 0.3 else 'grew ' + pct(f['perworker']) + '% a year'}. "
              f"The population rose from {f['pop_2022']:.1f} million (2022) to {f['pop_last']:.1f} million ({f['pop_last_y']}), "
              f"mainly through net migration (about {f['netmig']:.0f} people per 1,000 residents a year). More workers raise "
              f"total GDP, but income per person grows only if output per worker grows too.</p>"),
        panel(tag + "03", "Is output per person catching up?",
              f"GDP per person is {f['pps']:.0f} and output per hour {f['prodlvl']:.0f} (EU average = 100); for the euro area "
              f"{f['pps_ea']:.0f} and {f['prodlvl_ea']:.0f}.",
              "Both charts adjust for price differences between countries (PPS), with the EU average = 100. Top: GDP per person. "
              "Bottom: output per hour worked. Spain and the euro area.",
              caption("GDP per person in PPS, EU = 100") + chart("t_pps", "GDP per person in PPS, Spain and euro area, EU = 100", short=True) +
              caption("Output per hour worked in PPS, EU = 100") + chart("t_prod", "Output per hour worked in PPS, Spain and euro area, EU = 100", short=True),
              f"<p>GDP per person in PPS was {f['pps_2007']:.0f} in 2007, a level lifted by the construction boom, and "
              f"{f['pps']:.0f} in {ly}; poorer EU members growing fast have also raised the EU average. In real terms GDP per "
              f"person is {pct(f['gdppc'], 0)}% above 2007 (euro area {pct(f['gdppc_ea'], 0)}%).</p>"
              f"<p>Output per hour has grown {pct(f['prod'], 0)}% since 2007, more than the euro area's {pct(f['prod_ea'], 0)}%, "
              f"but much of that came from losing low-productivity construction jobs in 2008–2013; since 2019 it has grown "
              f"{pct(f['prod_19'], 0)}% (euro area {pct(f['prod_19_ea'], 0)}%). In level it is still "
              f"{f['prodlvl_ea'] - f['prodlvl']:.0f} points below the euro area. Small firms, a large share of low-productivity "
              f"services and low spending on research are the usual explanations.</p>"),
        panel(tag + "04", "What is fragile today?",
              f"Unemployment is {f['u'] - f['u_ea']:.1f} points above the euro area, and real house prices are "
              f"{pct(f['hp_from_low'], 0)}% above their {f['hp_low_y']} low.",
              "House prices with general inflation removed, 1995 = 100: the boom of 1995–2007, the fall to 2013 and the rise since.",
              chart("t_house", "Spain: real house prices, 1995 = 100", short=True),
              f"<p><b>Jobs.</b> Unemployment reached {f['low12']:.1f}% in {f['low12_d']}, {since}, and is {f['u']:.1f}% in "
              f"{f['u_d']} (euro area {f['u_ea']:.1f}%); for under-25s it is {f['youth']:.1f}%. Temporary contracts fell from "
              f"{f['temp_2021']:.0f}% of employees in 2021 to {f['temp']:.0f}% in {f['temp_y']} (euro area {f['temp_ea']:.0f}%) "
              f"after the 2022 change in contract rules; part of that is a reclassification into permanent seasonal "
              f"(\"fijo discontinuo\") contracts.</p>"
              f"<p><b>Housing.</b> Real house prices are {pct(f['hp_vs_top'], 0)}% compared with the 2007 peak "
              f"({f['hp_last_q']}). This time the rise comes with much less household and company debt (see <b>2010–2013</b>), "
              f"but the population is growing faster than the number of homes, which makes housing harder to afford, "
              f"especially for the young.</p>"
              f"<p><b>Prices and debt.</b> Inflation was {f['infl']:.1f}% in {f['infl_d']} (euro area {f['infl_ea']:.1f}%), with "
              f"the ECB deposit rate at {f['dfr']:.2f}%. Public debt is {f['debt']:.0f}% of GDP (euro area {f['debt_ea']:.0f}%), "
              f"so higher interest rates weigh on the budget for longer.</p>"),
    ])


def learned(facts, t):
    """The 'What did we learn?' list, written from the numbers."""
    h, b, g, d, r, c, n = (facts[k] for k in ["head", "boom", "bust", "debt", "recovery", "covid", "today"])
    items = [
        (f"<b>One interest rate, different inflation.</b> Inside the euro Spain's real short-term rate averaged "
         f"{neg(b['real_rate_avg'])}% in 1999–2007. Cheap real credit took household and company debt from "
         f"{h['credit_1995']:.0f}% to {h['credit_2007']:.0f}% of GDP and real house prices up {b['hp_rise']:.0f}%."),
        (f"<b>The imbalances of the boom were private and external.</b> Public debt was {b['debt_2007']:.0f}% of GDP in 2007, "
         f"but the current account deficit reached {abs(b['ca_low']):.1f}% of GDP and unit labour costs rose {b['ulc_es']:.0f}% "
         f"against {pct(b['ulc_de'], 0)}% in Germany."),
        (f"<b>Spain's labour market amplifies shocks.</b> Unemployment went from {h['u_low']:.1f}% to {h['u_peak']:.1f}%, with "
         f"construction behind {g['constr_share']:.0f}% of the jobs lost in 2007–2009 and {g['temp_es_2007']:.0f}% of employees "
         f"on temporary contracts."),
        (f"<b>Without its own currency, the adjustment came through costs and exports.</b> Unit labour costs fell "
         f"{abs(r['ulc_fall']):.0f}% from {r['ulc_top_y']} to {r['ulc_low_y']}, exports rose from {r['x_2009']:.0f}% to "
         f"{r['x_2019']:.0f}% of GDP, and the current account has been in surplus since {r['first_surplus']}."),
        (f"<b>Structure decides how a shock spreads.</b> A large tourism sector made the Covid fall deeper ({pct(c['q2_es'])}% "
         f"in Q2 2020), and electricity prices linked to the wholesale market made inflation rise and fall earlier."),
        (f"<b>Recent growth comes mostly from more workers.</b> Since 2023 employment grew {pct(n['emp'])}% a year and output per "
         f"worker {pct(n['perworker'])}%. GDP per person is {n['pps']:.0f}% of the EU average and unemployment "
         f"{n['u']:.1f}% (euro area {n['u_ea']:.1f}%)."),
        ("<b>Limits.</b> Period averages hide what happens inside each period, and recent years will be revised. The euro-area "
         "figures are for today's 20 members, calculated back in time. The mechanisms on this page are the standard economic "
         "explanations; the charts show that the numbers moved together, not proof of what caused what. The page describes "
         "what happened and does not judge the policies chosen."),
    ]
    # returns a list of 7 HTML strings, e.g. ['<b>One interest rate, different inflation.</b> Inside the euro ...', ...]
    return items


def references():
    """The quiet 'References' list after the last panel: no panel box, no question, one muted line per source."""
    items = "".join(
        f'<li><a href="{escape(u)}" target="_blank" rel="noopener"><span><b>{escape(who)}</b>: {escape(what)}.</span></a></li>'
        for who, what, u in SOURCES)
    # returns a str of HTML: a small heading and 6 links, e.g. '<aside class="refs" aria-label="References"><h3>References</h3><ul><li>...'
    return f'<aside class="refs" aria-label="References"><h3>References</h3><ul>{items}</ul></aside>'


def build_page(annual, quarterly, monthly, table, facts):
    """Assemble the standalone HTML page and write it to disk."""
    h = facts["head"]                                          # header numbers
    h = {**h, "pop_1995": value_at(annual["pop_es"], 1995), "pop_last": float(annual["pop_es"].dropna().iloc[-1]),
         "pop_last_y": int(annual["pop_es"].dropna().index[-1])}   # population for the overview text
    end = monthly.dropna(how="all").index[-1]                  # latest month with data
    periods_js = []                                            # the six bands for the overview charts
    for p in PERIODS:
        s, e = period_bounds(p, monthly)
        periods_js.append({"start": str(s)[:10], "end": str(e + pd.offsets.MonthEnd(0))[:10] if not p["end"] else str(e)[:10],
                           "short": p["short"]})
    payload = {"charts": chart_specs(annual, quarterly, monthly, facts), "periods": periods_js}   # everything the JavaScript needs

    kpis = "".join([
        tile(f"{h['credit_peak']:.0f}%", f"Household + company debt at its peak, % of GDP ({h['credit_peak_q']})"),
        tile(f"{h['u_peak']:.1f}%", f"Unemployment peak, {h['u_peak_d']} (euro area {h['u_ea_at_peak']:.1f}%)"),
        tile(f"{h['s_peak']:.0f} bp", f"10-year spread over Germany at its peak ({h['s_peak_d']})"),
        tile(f"{pct(h['gdp_vs_peak_es'], 0)}%", f"Real GDP vs its 2008 peak, {h['gdp_last_q']} (euro area {pct(h['gdp_vs_peak_ea'], 0)}%)"),
    ])
    tab_list = [("overview", "Overview", f"1995–{end.year}")] + \
               [(p["key"], p["name"], p["years"].replace("today", str(end.year))) for p in PERIODS]
    tabs = ('<nav class="tabs" id="tabs" role="tablist" aria-label="Periods">' + "".join(
        f'<button type="button" role="tab" id="tab-{k}" data-tab="{k}" aria-controls="p-{k}" aria-selected="false">'
        f"<b>{escape(name)}</b><span>{escape(years)}</span></button>" for k, name, years in tab_list) + "</nav>")
    bodies = {
        "overview": overview_tab(table, h),
        "boom": boom_tab(facts["boom"], table),
        "bust": bust_tab(facts["bust"]),
        "debt": debt_tab(facts["debt"]),
        "recovery": recovery_tab(facts["recovery"]),
        "covid": covid_tab(facts["covid"]),
        "today": today_tab(facts["today"]),
    }
    panels = ""
    for i, (k, name, years) in enumerate(tab_list):            # one tab panel each, with a "next" button at the bottom
        nxt = tab_list[i + 1] if i + 1 < len(tab_list) else None
        button = (f'<button type="button" class="next" data-go="{nxt[0]}">Next: {escape(nxt[2])} · {escape(nxt[1])} →</button>' if nxt
                  else '<button type="button" class="next" data-go="overview">Back to the overview ↑</button>')
        panels += (f'<section class="tabpanel" id="p-{k}" role="tabpanel" aria-labelledby="tab-{k}" tabindex="-1">'
                   f"{bodies[k]}{button}</section>")
    gloss = '<dl class="gloss">' + "".join(f"<div><dt>{escape(t)}</dt><dd>{escape(d)}</dd></div>" for t, d in GLOSSARY) + "</dl>"
    take = '<ol class="take">' + "".join(f"<li>{x}</li>" for x in learned(facts, table)) + "</ol>"
    shared = ('<div class="shared">'
              + panel("Key ideas", "What do the terms on this page mean?", "Twelve ideas used across the tabs, in plain language.", "", gloss)
              + panel("Summary", "What did we learn?", "Seven takeaways, ending with the limits.", "", take)
              + "</div>" + references())

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Spanish Economy Since 1995</title>
<meta name="description" content="A data-only tour of the Spanish economy from the euro boom to today, in six periods.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
<script src="{ECHARTS_URL}"></script>
</head>
<body>
<header class="band"><div class="in">
<div class="toprow"><a class="back" href="../index.html">&larr; Macro Quant Lab</a><span class="upd">Updated {UPDATED}</span></div>
<p class="eyebrow">Spanish economy · Euro boom to today</p>
<h1>What drove Spain's economy from the euro boom to today?</h1>
<p class="answer">{header_answer(h)}</p>
<p class="meta">Monthly data to {h['last_month']}, quarterly to {h['gdp_last_q']}, yearly to {h['last_year']} · Eurostat, OECD, ECB and BIS (via FRED) · Data only, no policy judgements</p>
</div></header>
<main class="in">
<div class="kpis top">{kpis}</div>
{tabs}
{panels}
{shared}
</main>
<footer><div class="in">Generated by spain_economy.py from Eurostat and FRED data (OECD, ECB and BIS series). Learning project.</div></footer>
<script>{JS.replace("__DATA__", json.dumps(payload, ensure_ascii=False))}</script>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")             # save the page
    # returns nothing; writes spain_economy.html (~300 KB: the HTML text plus the chart data as JSON)
    return None


if __name__ == "__main__":
    main()
