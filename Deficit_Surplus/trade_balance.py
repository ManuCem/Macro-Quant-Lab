"""
Who sells more to the world than it buys? A world map of trade surpluses and deficits.

For every country we take its trade in GOODS for one year from UN Comtrade (free,
no API key) and compute:

    trade balance = exports - imports
        > 0  -> SURPLUS  (the country sells more than it buys, e.g. China, Germany)
        < 0  -> DEFICIT  (the country buys more than it sells, e.g. the US, the UK)

Comtrade also splits each country's trade by partner, so for every country we
keep its top 5 export destinations and its top 5 import sources. On the map,
tapping a country draws arrows to those 5 partners.

Countries that did not send their own data to Comtrade (Russia, Vietnam, UAE, Iran,
many small economies) get a MIRROR estimate: what Russia exported is estimated
from what everyone else says they imported from Russia, and vice versa.

Output: Deficit_Surplus/trade_balance.html (one standalone page, drawn with D3).
        Deficit_Surplus/csv/trade_balance.csv (one row per country, a copy of the table).

Layout of this file (see CLAUDE.md):
    1. python / data code  -> settings, downloads, calculations, and def main()
    2. html / chart code   -> builds the web page with the map
"""

import json                               # reads the API answers and turns Python data into text for the browser
import re                                 # finds the waiting time inside Comtrade's "quota" message
import time                               # time.sleep() to stay under Comtrade's rate limit
from html import escape                   # makes text safe inside HTML (turns "<" into "&lt;", etc.)
from pathlib import Path                  # builds file paths that work on Windows, Mac and Linux

import pandas as pd                       # tables (DataFrames)
import requests                           # downloads data from web APIs


# ===========================================================================
# python / data code
# ===========================================================================

YEAR = 2024                               # the year we map: the latest one most countries have reported (2025 is still incomplete)
TOP_N = 10                                # how many partners to keep per country (the list; the map draws arrows to the top 3)

HERE = Path(__file__).parent                              # the Deficit_Surplus folder
OUTPUT_PATH = HERE / "trade_balance.html"                 # the web page we write
CSV_PATH = HERE / "csv" / "trade_balance.csv"             # a copy of the country table
CACHE_DIR = HERE / "cache"                                # raw API answers, so a second run does not download again (git-ignored)

COMTRADE_DATA_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"           # C = commodities, A = annual, HS = product classification
COMTRADE_AVAILABLE_URL = "https://comtradeapi.un.org/public/v1/getDA/C/A/HS"        # "data availability": which countries reported which year
COMTRADE_PARTNERS_URL = "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"  # code -> country name / ISO code
WORLD_BANK_COUNTRIES_URL = "https://api.worldbank.org/v2/country?format=json&per_page=400"     # capital city + its latitude/longitude
WORLD_MAP_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json"           # country borders (Natural Earth, 1:50 million)

SECONDS_BETWEEN_CALLS = 1.6               # Comtrade's free endpoint answers "429 Too Many Requests" if called faster than ~1 per second
MAX_RECORDS = 500                         # the free endpoint returns at most 500 rows per call

# Comtrade uses its own numeric codes for a few countries; the map uses the ISO 3166 numeric code.
COMTRADE_TO_ISO_NUMERIC = {
    842: 840,                             # USA (Comtrade's 842 also covers Puerto Rico and the US Virgin Islands)
    251: 250,                             # France (Comtrade's 251 includes Monaco)
    699: 356,                             # India
    757: 756,                             # Switzerland (Comtrade's 757 includes Liechtenstein)
    579: 578,                             # Norway (Comtrade's 579 includes Svalbard)
    490: 158,                             # "Other Asia, nes" = Taiwan in Comtrade's naming
}
ISO3_FIXES = {490: "TWN"}                 # Comtrade gives Taiwan the made-up ISO code "S19"; use the real one
COMTRADE_ALIASES = {840: 842, 250: 251, 756: 757, 578: 579}  # second codes for the same country (e.g. 840 "United States of America"):
                                          # their rows are counted under the main code that countries report with

EXTRA_CAPITALS = {                        # capitals the World Bank list does not have (it skips Taiwan)
    "TWN": ("Taipei", 25.03, 121.57),     # (capital name, latitude, longitude)
    "HKG": ("Hong Kong", 22.30, 114.17),  # a city-territory: the "capital" is the city itself
    "MAC": ("Macao", 22.19, 113.54),
}

UNINHABITED = {"ATA", "ATF", "HMD", "BVT", "SGS", "IOT", "ATB", "UMI"}  # Antarctica, French Southern Lands, Heard Is., Bouvet Is.,
                                          # S. Georgia, Br. Indian Ocean Terr., Br. Antarctic Terr., US Minor Outlying Is.: no real
                                          # economy, only noise in the mirror data (ships and research stations), so they are left out

MAP_ALIASES = {                           # map shapes that Comtrade counts inside another country: paint them in that country's colour
    "630": "USA", "850": "USA",           # Puerto Rico, US Virgin Islands (inside Comtrade's "USA")
    "492": "FRA",                         # Monaco (inside "France")
    "438": "CHE",                         # Liechtenstein (inside "Switzerland")
}

SHORT_NAMES = {                           # the map file's names are short and clean; a few still need a nicer label
    "USA": "United States",               # map file says "United States of America"
    "BIH": "Bosnia & Herz.",
    "CAF": "Central African Rep.",
    "COD": "DR Congo",
    "COG": "Congo",
    "DOM": "Dominican Rep.",
    "SWZ": "Eswatini",
    "GNQ": "Eq. Guinea",
    "SSD": "South Sudan",
}


def fetch_json(url, cache_file, params=None):
    """Download a JSON answer, or read it from the cache if we already downloaded it."""
    cache_path = CACHE_DIR / cache_file                       # where this answer is (or will be) saved
    if cache_path.exists():                                   # already downloaded on an earlier run?
        return json.loads(cache_path.read_text(encoding="utf-8"))  # yes: read it from disk, no internet needed
    for attempt in range(1, 7):                               # try up to 6 times
        time.sleep(SECONDS_BETWEEN_CALLS)                     # pause first, so we never call the API too fast
        response = requests.get(url, params=params, timeout=90)  # ask the API
        if response.status_code == 429:                       # 429 = "too many requests": the API wants us to slow down
            time.sleep(5 * attempt)                           # wait longer each time (5 s, 10 s, 15 s...)
            continue                                          # and try again
        if response.status_code == 403 and "quota" in response.text.lower():  # 403 + "quota": the free hourly allowance is used up
            wait = re.search(r"(\d+):(\d+):(\d+)", response.text)  # the answer says when it refills, e.g. "replenished in 00:08:15"
            seconds = int(wait[1]) * 3600 + int(wait[2]) * 60 + int(wait[3]) if wait else 600  # hh:mm:ss -> seconds (10 min if not given)
            print(f"\n  Comtrade quota used up: waiting {seconds // 60} min {seconds % 60} s for it to refill...")  # say why it pauses
            time.sleep(seconds + 10)                          # wait until it refills, plus a little margin
            continue                                          # and try again
        response.raise_for_status()                           # any other error (404, 500...) stops the script with a clear message
        answer = response.json()                              # turn the text answer into Python lists/dicts
        CACHE_DIR.mkdir(parents=True, exist_ok=True)          # create the cache folder if missing
        cache_path.write_text(json.dumps(answer), encoding="utf-8")  # save it for next time
        # returns whatever the API sent, as Python objects; e.g. for one Comtrade call a dict:
        # {"elapsedTime": "0.3 secs", "count": 448, "error": "",
        #  "data": [{"reporterCode": 842, "flowCode": "X", "partnerCode": 124, "primaryValue": 348.4e9, ...}, ...]}
        return answer
    raise RuntimeError(f"{url} kept refusing (too many requests / quota); run the script again later")


def load_partner_codes():
    """Comtrade's list of country codes: numeric code -> ISO3 code and name."""
    answer = fetch_json(COMTRADE_PARTNERS_URL, "partnerAreas.json")  # one small reference file
    rows = []                                                 # we collect one dict per code here
    for item in answer["results"]:                            # each item is one country or group ("World", "Areas nes"...)
        code = item["PartnerCode"]                            # Comtrade's numeric code, e.g. 842
        if item.get("entryExpiredDate") or code in COMTRADE_ALIASES:  # old codes ("Fed. Rep. of Germany (...1990)") and second codes: skip
            continue
        iso3 = ISO3_FIXES.get(code, item.get("PartnerCodeIsoAlpha3", ""))  # ISO3 code, e.g. "USA" (Taiwan fixed by hand)
        rows.append({
            "code": code,                                     # Comtrade code
            "iso3": iso3,                                     # 3-letter ISO code
            "comtrade_name": item["PartnerDesc"].strip(),     # Comtrade's name, e.g. "USA", "Rep. of Korea"
            "map_id": f"{COMTRADE_TO_ISO_NUMERIC.get(code, code):03d}",  # the map's id: ISO numeric, 3 digits, e.g. "840"
            "is_group": bool(item.get("isGroup")),            # True for "World", "EU" and other non-countries
        })
    codes = pd.DataFrame(rows)                                # list of dicts -> table
    is_country = (~codes["is_group"]) & codes["iso3"].str.fullmatch(r"[A-Z]{3}")  # real countries have a proper 3-letter code
    codes = codes[is_country].drop_duplicates("iso3").set_index("code")  # keep countries only, one row each
    # returns a DataFrame, ~240 rows (one per country), indexed by Comtrade code:
    #       iso3  comtrade_name  map_id  is_group
    # code
    # 4      AFG    Afghanistan     004     False
    # 842    USA            USA     840     False
    # 490    TWN  Other Asia, nes   158     False
    return codes


def load_capitals():
    """Capital city and its coordinates for every country, from the World Bank."""
    answer = fetch_json(WORLD_BANK_COUNTRIES_URL, "worldbank_countries.json")  # [page info, list of countries]
    rows = []                                                 # one dict per country
    for item in answer[1]:                                    # answer[0] is page info, answer[1] the countries
        if not item["capitalCity"] or not item["latitude"]:   # regions like "Euro area" have no capital: skip them
            continue
        rows.append({
            "iso3": item["id"],                               # e.g. "USA"
            "capital": item["capitalCity"],                   # e.g. "Washington D.C."
            "lat": float(item["latitude"]),                   # latitude in degrees (north is positive)
            "lon": float(item["longitude"]),                  # longitude in degrees (east is positive)
        })
    for row in rows:                                          # spelling fixes
        if row["iso3"] == "UKR":                              # the World Bank still writes "Kiev"
            row["capital"] = "Kyiv"                           # Ukraine's official English spelling
    for iso3, (capital, lat, lon) in EXTRA_CAPITALS.items():  # add the ones the World Bank lacks
        rows.append({"iso3": iso3, "capital": capital, "lat": lat, "lon": lon})
    capitals = pd.DataFrame(rows).set_index("iso3")           # list of dicts -> table indexed by ISO3
    # returns a DataFrame, ~215 rows, indexed by ISO3:
    #               capital      lat       lon
    # iso3
    # ESP            Madrid  40.4167   -3.7033
    # USA   Washington D.C.  38.8895  -77.0320
    return capitals


def load_world_map():
    """The country borders (TopoJSON) and the name the map file uses for each country id."""
    world = fetch_json(WORLD_MAP_URL, "countries-50m.json")   # ~750 KB of borders
    countries = world["objects"]["countries"]["geometries"]   # one entry per country shape
    names = {}                                                # map id -> name
    for g in countries:                                       # one shape at a time
        if "id" in g:                                         # a few disputed areas have no id: skip them
            names.setdefault(g["id"], g["properties"]["name"])  # keep the FIRST name: id "036" is Australia and also Ashmore Is.
    # returns a tuple (world, names):
    #   world: dict, the TopoJSON file as-is (passed untouched to the browser)
    #   names: dict with ~240 items, e.g. {"840": "United States of America", "724": "Spain", "156": "China"}
    return world, names


def list_reporters(year, codes):
    """Comtrade codes of the countries that sent their own trade data for this year."""
    answer = fetch_json(COMTRADE_AVAILABLE_URL, f"available_{year}.json", params={"period": year})  # one row per reporter
    size = {}                                                 # reporter code -> number of data rows it sent (a rough measure of how much it trades)
    for row in answer["data"]:                                # a reporter can appear twice (two product classifications)
        if row["reporterCode"] not in codes.index:            # skip groups that report as one, like the EU (code 97)
            continue
        size[row["reporterCode"]] = max(size.get(row["reporterCode"], 0), row["totalRecords"])  # keep the bigger count
    reporters = sorted(size, key=size.get, reverse=True)      # biggest first, so the big economies download before any quota pause
    # returns a list of ints, ~148 Comtrade codes for 2024, biggest traders first, e.g.:
    # [276, 842, 156, 251, 380, 528, 56, 392, 826, 724, ..., 20, 28]
    return reporters


def download_one_reporter(code, year):
    """Exports and imports of one country to/from every partner, for one year."""
    params = {                                                # what we ask Comtrade for
        "reporterCode": code,                                 # the country that reports
        "period": year,                                       # the year
        "flowCode": "X,M",                                    # X = exports, M = imports
        "cmdCode": "TOTAL",                                   # all goods together (not product by product)
        "partner2Code": 0,                                    # no "second partner" split
        "customsCode": "C00",                                 # all customs procedures together
        "motCode": 0,                                         # all modes of transport together
    }
    rows = fetch_json(COMTRADE_DATA_URL, f"comtrade_{year}_{code}_XM.json", params)["data"]  # both flows in one call
    if len(rows) >= MAX_RECORDS:                              # hit the 500-row cap? then the answer may be cut off...
        rows = []                                             # ...so throw it away and ask for each flow separately
        for flow in ("X", "M"):                               # one call for exports, one for imports
            one_flow = dict(params, flowCode=flow)            # same question, a single flow
            rows += fetch_json(COMTRADE_DATA_URL, f"comtrade_{year}_{code}_{flow}.json", one_flow)["data"]  # add its rows to the list
    table = pd.DataFrame([{
        "reporter": row["reporterCode"],                      # who reports, e.g. 842 (USA)
        "partner": row["partnerCode"],                        # trade partner, e.g. 124 (Canada); 0 means "World" = the total
        "flow": row["flowCode"],                              # "X" or "M"
        "value": row["primaryValue"],                         # US dollars (exports valued FOB, imports CIF = including freight)
    } for row in rows])
    # returns a DataFrame, ~450 rows (2 flows x ~225 partners), e.g. download_one_reporter(842, 2024):
    #      reporter  partner flow         value
    # 0         842        0    M  3.356813e+12
    # 1         842      124    M  4.215240e+11
    # 2         842      124    X  3.484050e+11
    return table


def download_all_flows(year, codes):
    """Exports and imports by partner for every country that reported this year."""
    reporters = list_reporters(year, codes)                   # which countries have data
    tables = []                                               # one small table per country
    for number, code in enumerate(reporters, start=1):        # loop over them, counting from 1
        print(f"  {number:3d}/{len(reporters)}  Comtrade reporter {code}", end="\r")  # progress on one line
        tables.append(download_one_reporter(code, year))      # download (or read from cache)
    print()                                                   # finish the progress line
    flows = pd.concat(tables, ignore_index=True)              # stack all countries into one long table
    flows["partner"] = flows["partner"].replace(COMTRADE_ALIASES)  # 840 -> 842 etc., so each country has a single code
    flows = flows.groupby(["reporter", "partner", "flow"], as_index=False)["value"].max()  # safety: one row per (reporter, partner, flow)
    # returns a DataFrame, ~60,000 rows: every (reporter, partner, flow) with its value in US$:
    #        reporter  partner flow         value
    # 0             8        0    M  7.912345e+09
    # 1             8        0    X  4.123456e+09
    # 2             8       40    M  1.234567e+08
    return flows


def build_country_table(flows, codes, capitals, map_names):
    """One row per country: exports, imports, balance, top partners, capital, map id."""
    reported = set(flows["reporter"])                         # Comtrade codes of countries with their own data
    totals = flows[flows["partner"] == 0]                     # partner 0 = "World": each reporter's total exports/imports
    by_partner = flows[flows["partner"].isin(codes.index) & flows["reporter"].isin(codes.index)]  # both sides real countries (drops "Areas nes", "Bunkers"...)
    by_partner = by_partner[by_partner["reporter"] != by_partner["partner"]]  # drop "trade with itself" (re-imports) if any

    rows = []                                                 # one dict per country goes here
    for code, info in codes.iterrows():                       # loop over every real country
        if code in reported:                                  # CASE 1: the country reported its own data
            mine = totals[totals["reporter"] == code]         # its two total rows (X and M)
            exports = mine.loc[mine["flow"] == "X", "value"].sum()   # total exports, US$
            imports = mine.loc[mine["flow"] == "M", "value"].sum()   # total imports, US$
            own = by_partner[by_partner["reporter"] == code]  # its rows by partner
            top_x = own[own["flow"] == "X"].nlargest(TOP_N, "value")  # biggest 10 export destinations
            top_m = own[own["flow"] == "M"].nlargest(TOP_N, "value")  # biggest 10 import sources
            top_x = list(zip(top_x["partner"], top_x["value"]))       # -> [(partner code, US$), ...]
            top_m = list(zip(top_m["partner"], top_m["value"]))       # same for imports
            source = "reported"                               # flag: own data
        else:                                                 # CASE 2: no own data -> MIRROR estimate from the partners
            seen_by_others = by_partner[by_partner["partner"] == code]  # every row where SOMEONE ELSE names this country as partner
            bought_from_it = seen_by_others[seen_by_others["flow"] == "M"]  # others' imports FROM it = its exports
            sold_to_it = seen_by_others[seen_by_others["flow"] == "X"]      # others' exports TO it = its imports
            exports = bought_from_it["value"].sum()           # mirror exports, US$
            imports = sold_to_it["value"].sum()               # mirror imports, US$
            top_x = bought_from_it.nlargest(TOP_N, "value")   # the 10 countries that buy most from it
            top_m = sold_to_it.nlargest(TOP_N, "value")       # the 10 countries that sell most to it
            top_x = list(zip(top_x["reporter"], top_x["value"]))  # here the partner is the REPORTER column
            top_m = list(zip(top_m["reporter"], top_m["value"]))      # same for imports
            source = "mirror"                                 # flag: estimated
        if exports == 0 and imports == 0:                     # nobody has any number for it (tiny territories): skip
            continue
        iso3 = info["iso3"]                                   # e.g. "USA"
        if iso3 in UNINHABITED:                               # no people, no economy: skip
            continue
        capital = capitals.loc[iso3] if iso3 in capitals.index else None  # its capital row, if known
        if capital is None and info["map_id"] not in map_names:  # no shape on the map and no capital (Bouvet Island...): nothing to draw
            continue
        name = SHORT_NAMES.get(iso3) or map_names.get(info["map_id"]) or info["comtrade_name"]  # nicest short name available
        rows.append({
            "iso3": iso3,                                     # 3-letter code, used as the key in the browser
            "map_id": info["map_id"],                         # id of its shape in the map file
            "name": name,                                     # e.g. "United States"
            "capital": capital["capital"] if capital is not None else "",  # e.g. "Washington D.C."
            "lat": capital["lat"] if capital is not None else None,        # where the arrows start/end
            "lon": capital["lon"] if capital is not None else None,
            "exports_bn": exports / 1e9,                      # US$ -> billions of US$
            "imports_bn": imports / 1e9,
            "balance_bn": (exports - imports) / 1e9,          # the number the map is coloured by
            "source": source,                                 # "reported" or "mirror"
            "top_exports": [(codes.loc[p, "iso3"], v / 1e9) for p, v in top_x],  # partner codes -> ISO3, US$ -> bn
            "top_imports": [(codes.loc[p, "iso3"], v / 1e9) for p, v in top_m],
        })
    table = pd.DataFrame(rows).set_index("iso3").sort_values("balance_bn")  # biggest deficit first
    # returns a DataFrame, ~210 rows (one per country), indexed by ISO3, sorted by balance:
    #      map_id           name          capital    lat     lon  exports_bn  imports_bn  balance_bn    source  top_exports                         top_imports
    # iso3
    # USA     840  United States  Washington D.C.  38.89  -77.03     2063.80     3356.81    -1293.01  reported  [(MEX, 334.0), (CAN, 348.4), ...]  [(MEX, 509.8), (CHN, 438.9), ...]
    # ...
    # CHN     156          China          Beijing  40.05  116.08     3577.10     2587.95      989.15  reported  [(USA, 525.6), (HKG, 291.6), ...]  [(TWN, 215.2), (KOR, 182.0), ...]
    return table


def summarise(table):
    """Headline numbers: total surplus, total deficit, and how far the world is from adding up to zero."""
    surplus = table[table["balance_bn"] > 0]                  # countries in surplus
    deficit = table[table["balance_bn"] < 0]                  # countries in deficit
    summary = {
        "year": YEAR,                                         # the data year (float() below turns numpy numbers into plain Python ones)
        "surplus_total_bn": round(float(surplus["balance_bn"].sum()), 1),   # sum of all surpluses
        "surplus_count": len(surplus),                        # how many countries
        "deficit_total_bn": round(float(deficit["balance_bn"].sum()), 1),   # sum of all deficits (a negative number)
        "deficit_count": len(deficit),
        "net_bn": round(float(table["balance_bn"].sum()), 1),        # in theory ~0 (one country's export is another's import)
        "mirror_count": int((table["source"] == "mirror").sum()),    # how many countries are estimates
    }
    # returns a dict, e.g.:
    # {"year": 2024, "surplus_total_bn": 2650.3, "surplus_count": 64,
    #  "deficit_total_bn": -3120.8, "deficit_count": 146, "net_bn": -470.5, "mirror_count": 62}
    return summary


def save_csv(table):
    """Save the country table as CSV (partners written as text like 'MEX:334.0; CAN:348.4')."""
    out = table.copy()                                        # do not change the table the page uses
    for col in ("top_exports", "top_imports"):                # the two list columns
        out[col] = out[col].apply(lambda pairs: "; ".join(f"{iso}:{v:.1f}" for iso, v in pairs))  # list -> readable text
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)        # create the csv folder if missing
    out.round(3).to_csv(CSV_PATH)                             # write it
    # returns nothing; writes Deficit_Surplus/csv/trade_balance.csv, which starts like:
    # iso3,map_id,name,capital,lat,lon,exports_bn,imports_bn,balance_bn,source,top_exports,top_imports
    # USA,840,United States,Washington D.C.,38.8895,-77.032,2063.803,3356.813,-1293.01,reported,CAN:348.4; MEX:334.0; ...
    return None


def main():
    print(f"Downloading reference lists and the {YEAR} trade data (first run: ~8 min, later runs use the cache)...")
    codes = load_partner_codes()                              # step 1: Comtrade code -> ISO3 / map id
    capitals = load_capitals()                                # step 2: capital cities and their coordinates
    world, map_names = load_world_map()                       # step 3: country borders for the map
    flows = download_all_flows(YEAR, codes)                   # step 4: exports & imports by partner, every reporter
    table = build_country_table(flows, codes, capitals, map_names)  # step 5: one row per country
    summary = summarise(table)                                # step 6: headline totals
    save_csv(table)                                           # step 7: CSV copy
    html = build_page(table, summary, world)                  # step 8: the web page
    OUTPUT_PATH.write_text(html, encoding="utf-8")            # step 9: save it
    print(summary)                                            # show the headline numbers
    print(table[["name", "balance_bn", "source"]].head(5))    # 5 biggest deficits
    print(table[["name", "balance_bn", "source"]].tail(5))    # 5 biggest surpluses
    print(f"Saved {OUTPUT_PATH}")


# ===========================================================================
# html / chart code
# ===========================================================================

def page_data(table, summary):
    """Shrink the country table into the small JSON object the browser reads."""
    countries = {}                                            # iso3 -> short dict (short keys keep the page small)
    for iso3, row in table.iterrows():                        # one country at a time
        has_capital = pd.notna(row["lat"])                    # do we know where its capital is?
        countries[iso3] = {
            "n": row["name"],                                 # name
            "c": row["capital"],                              # capital name
            "ll": [round(row["lon"], 3), round(row["lat"], 3)] if has_capital else None,  # [lon, lat]: D3 wants longitude first
            "x": round(row["exports_bn"], 3),                 # exports, $ bn
            "m": round(row["imports_bn"], 3),                 # imports, $ bn
            "b": round(row["balance_bn"], 3),                 # balance, $ bn
            "s": row["source"][0],                            # "r" = reported, "m" = mirror estimate
            "tx": [[p, round(v, 3)] for p, v in row["top_exports"]],  # top 5 export destinations
            "tm": [[p, round(v, 3)] for p, v in row["top_imports"]],  # top 5 import sources
        }
    by_map_id = {row["map_id"]: iso3 for iso3, row in table.iterrows()}  # map shape id -> iso3, to colour each shape
    by_map_id.update(MAP_ALIASES)                             # Puerto Rico -> USA, Monaco -> FRA...
    data = {"summary": summary, "countries": countries, "byMapId": by_map_id, "aliasIds": list(MAP_ALIASES)}
    # returns a dict ready for json.dumps, e.g.:
    # {"summary": {"year": 2024, "surplus_total_bn": 2650.3, ...},
    #  "countries": {"ESP": {"n": "Spain", "c": "Madrid", "ll": [-3.703, 40.417], "x": 412.3, "m": 470.1,
    #                        "b": -57.8, "s": "r", "tx": [["FRA", 64.1], ...], "tm": [["DEU", 51.2], ...]}, ...},
    #  "byMapId": {"724": "ESP", "840": "USA", "630": "USA", ...}, "aliasIds": ["630", "850", "492", "438"]}
    return data


def build_page(table, summary, world):
    """Fill the HTML template below with the data and the map borders."""
    data_json = json.dumps(page_data(table, summary), separators=(",", ":"))  # compact JSON text (no spaces)
    world_json = json.dumps(world, separators=(",", ":"))     # the borders, also compact
    html = PAGE_TEMPLATE                                      # start from the template
    html = html.replace("__YEAR__", escape(str(summary["year"])))           # the year in titles
    html = html.replace("__MIRROR_COUNT__", str(summary["mirror_count"]))   # used in the notes
    html = html.replace("__DATA__", data_json.replace("</", "<\\/"))        # "<\/" so a name can never close the <script> early
    html = html.replace("__WORLD__", world_json.replace("</", "<\\/"))
    # returns a str: the whole web page (~850 KB, most of it the map borders), e.g.
    # '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n...'
    return html


# The page. Placeholders like __DATA__ are replaced by build_page(); everything else is plain HTML/CSS/JS.
PAGE_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trade Surplus Map</title>
<meta name="description" content="World map of trade surpluses and deficits in goods, __YEAR__, with each country's top 5 trading partners.">
<style>
  /* ---------- colour tokens: light by default, dark when the viewer's system is dark ---------- */
  :root {
    color-scheme: light dark;
    --page: #f9f9f7;  --surface: #fcfcfb;  --ink: #0b0b0b;  --ink-2: #52514e;  --ink-3: #898781;
    --border: #e1e0d9;  --hover: #c3c2b7;
    --land-off: #e6e5e0;                       /* countries not highlighted by the filter, or without data */
    /* deficit arm (red) and surplus arm (blue): step 0 = smallest amount, step 4 = largest */
    --neg-0: #fbd0cc; --neg-1: #f4a19b; --neg-2: #e5605c; --neg-3: #bf3534; --neg-4: #87201f;
    --pos-0: #cde2fb; --pos-1: #9ec5f4; --pos-2: #5598e7; --pos-3: #256abf; --pos-4: #104281;
    --arrow: #0b0b0b;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --page: #0d0d0d;  --surface: #1a1a19;  --ink: #f0efec;  --ink-2: #c3c2b7;  --ink-3: #898781;
      --border: #2c2c2a;  --hover: #4a4a46;  --land-off: #2f2f2c;
      /* in dark mode small amounts sit close to the dark surface and big ones glow */
      --neg-0: #4a1f1e; --neg-1: #7d2b2a; --neg-2: #c63b3a; --neg-3: #e5605c; --neg-4: #f4a19b;
      --pos-0: #173459; --pos-1: #1c4f8f; --pos-2: #2a78d6; --pos-3: #5598e7; --pos-4: #9ec5f4;
      --arrow: #f0efec;
    }
  }
  :root[data-theme="dark"] {
    --page: #0d0d0d;  --surface: #1a1a19;  --ink: #f0efec;  --ink-2: #c3c2b7;  --ink-3: #898781;
    --border: #2c2c2a;  --hover: #4a4a46;  --land-off: #2f2f2c;
    --neg-0: #4a1f1e; --neg-1: #7d2b2a; --neg-2: #c63b3a; --neg-3: #e5605c; --neg-4: #f4a19b;
    --pos-0: #173459; --pos-1: #1c4f8f; --pos-2: #2a78d6; --pos-3: #5598e7; --pos-4: #9ec5f4;
    --arrow: #f0efec;
  }

  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink);
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1320px; margin: 0 auto; padding: 28px 20px 48px; }
  .back { display: inline-block; padding: 10px 0; margin: -10px 0 4px; color: var(--ink-2); font-size: 14px; text-decoration: none; }
  .back:hover { color: var(--ink); }
  h1 { font-size: 24px; line-height: 1.2; margin: 0; letter-spacing: -0.01em; }
  h1 span { color: var(--ink-3); font-weight: 500; }
  .head-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin-bottom: 12px; }
  /* tabs: "Map" and "How to read it" */
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); }
  .tabs button { min-height: 44px; padding: 0 14px; border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px;
                 background: transparent; color: var(--ink-2); font: inherit; font-size: 15px; cursor: pointer; }
  .tabs button:hover { color: var(--ink); }
  .tabs button[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--ink); font-weight: 600; }
  [hidden] { display: none !important; }

  /* ---------- controls: filter buttons + country picker, in one row above the map ---------- */
  .controls { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin-bottom: 14px; }
  .seg { display: inline-flex; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 3px; }
  .seg button { min-height: 40px; padding: 0 16px; border: 0; border-radius: 7px; background: transparent;
                color: var(--ink-2); font: inherit; font-size: 15px; cursor: pointer; }
  .seg button:hover { color: var(--ink); }
  .seg button[aria-pressed="true"] { background: var(--ink); color: var(--surface); font-weight: 600; }
  .seg button:focus-visible, .pick select:focus-visible { outline: 2px solid var(--pos-2); outline-offset: 2px; }
  .pick select { min-height: 44px; min-width: 220px; padding: 0 12px; border: 1px solid var(--border); border-radius: 10px;
                 background: var(--surface); color: var(--ink); font: inherit; font-size: 15px; }

  /* ---------- map (full width) with the country details below it ---------- */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
  .map-card { padding: 10px 10px 8px; min-width: 0; }
  .map-top { display: flex; justify-content: space-between; align-items: flex-end; gap: 10px 16px; flex-wrap: wrap; margin-bottom: 4px; }
  .total { margin-left: auto; text-align: right; font-size: 13px; color: var(--ink-2); }   /* the corner box with the total */
  .total .big { display: block; font-size: 26px; font-weight: 700; color: var(--ink); line-height: 1.15; }
  .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; flex: none; }

  .map-wrap { position: relative; }
  #map { display: block; width: 100%; user-select: none; -webkit-user-select: none; }
  .country { stroke: var(--surface); stroke-width: 0.6px; vector-effect: non-scaling-stroke; cursor: pointer;
             transition: fill .25s; }
  .country.partner { stroke: var(--ink-2); stroke-width: 1px; }
  .country.sel { stroke: var(--ink); stroke-width: 1.6px; }
  .dot { fill: var(--ink-3); opacity: .75; pointer-events: none; }
  .dot.on { fill: var(--ink); opacity: 1; }
  .hit { fill: transparent; cursor: pointer; }
  .lbl { font-size: 10.5px; fill: var(--ink); paint-order: stroke; stroke: var(--surface); stroke-width: 2.5px; stroke-opacity: .8;
         stroke-linejoin: round; pointer-events: none; }
  .lbl.cap { font-size: 9px; fill: var(--ink-3); }
  .lbl.key { font-size: 12px; font-weight: 650; fill: var(--ink); }
  .arc { fill: none; stroke: var(--arrow); stroke-linecap: round; opacity: .85; pointer-events: none; }
  .arc-halo { fill: none; stroke: var(--surface); stroke-linecap: round; opacity: .9; pointer-events: none; }
  .head { fill: var(--arrow); opacity: .9; pointer-events: none; }
  /* arrows draw themselves from start to end when a country is picked */
  .arc.grow, .arc-halo.grow { stroke-dasharray: 1; animation: grow .7s ease-out both; }
  .head.grow { animation: fadein .3s ease-out .55s both; }
  @keyframes grow { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
  @keyframes fadein { from { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .arc.grow, .arc-halo.grow, .head.grow { animation: none; } }

  .zoom { position: absolute; right: 8px; bottom: 8px; display: flex; flex-direction: column; gap: 6px; }
  .zoom button { width: 40px; height: 40px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface);
                 color: var(--ink); font: 600 18px/1 system-ui, sans-serif; cursor: pointer; }
  .zoom button:hover { border-color: var(--hover); }
  .tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--border);
         border-radius: 8px; padding: 8px 10px; font-size: 13px; line-height: 1.4; box-shadow: 0 4px 14px rgba(0,0,0,.12);
         max-width: 240px; opacity: 0; transition: opacity .1s; }
  .tip b { font-size: 14px; }
  .tip .muted { color: var(--ink-3); }

  /* legend: 10 swatches (5 red + 5 blue) with the $ bn boundaries under them */
  .legend { flex: 1 1 240px; max-width: 360px; font-size: 12px; color: var(--ink-2); }
  .ramp-box { width: 100%; }
  .ramp { display: grid; grid-template-columns: repeat(10, 1fr); gap: 2px; }
  .ramp span { height: 12px; transition: opacity .25s; }
  .ramp span:first-child { border-radius: 3px 0 0 3px; }
  .ramp span:last-child { border-radius: 0 3px 3px 0; }
  .ramp span.dim { opacity: .18; }
  .ticks { position: relative; height: 16px; font-size: 11px; color: var(--ink-3); }
  .ticks span { position: absolute; top: 1px; transform: translateX(-50%); font-variant-numeric: tabular-nums; }
  .ends { display: flex; justify-content: space-between; font-weight: 600; color: var(--ink-2); }

  /* ---------- country details, below the map: summary on the left, top 10 on the right (stacked on a phone) ---------- */
  .panel { margin-top: 14px; padding: 18px 18px 20px; display: grid; grid-template-columns: minmax(0, 320px) minmax(0, 1fr);
           gap: 8px 40px; align-items: start; }
  .panel h2 { margin: 0; font-size: 22px; line-height: 1.2; }
  .panel h3 { margin: 18px 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-3); }
  .panel p { margin: 6px 0; color: var(--ink-2); font-size: 14px; }
  .p-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
  .close { width: 40px; height: 40px; flex: none; margin: -6px -6px 0 0; border: 0; border-radius: 8px; background: transparent;
           color: var(--ink-2); font-size: 20px; cursor: pointer; }
  .close:hover { background: var(--page); color: var(--ink); }
  .bal { display: flex; align-items: center; gap: 10px; margin: 10px 0 4px; }
  .bal .big { font-size: 30px; font-weight: 700; line-height: 1.1; }
  .tag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); }
  .xm { display: flex; gap: 24px; margin: 6px 0 2px; font-size: 14px; }
  .xm div span { display: block; color: var(--ink-3); font-size: 12px; }
  .est { font-size: 13px !important; padding: 8px 10px; border-radius: 8px; background: var(--page); }
  .seg.small { margin-top: 14px; width: 100%; }
  .seg.small button { flex: 1; padding: 0 10px; }
  ol.top { list-style: none; margin: 4px 0 0; padding: 0; }
  ol.top li + li { margin-top: 2px; }
  .prow { display: grid; grid-template-columns: 22px 1fr auto; gap: 2px 8px; align-items: center; width: 100%;
          min-height: 44px; padding: 6px 6px; border: 0; border-radius: 8px; background: transparent; color: inherit;
          font: inherit; font-size: 14px; text-align: left; cursor: pointer; }
  .prow:hover { background: var(--page); }
  .prow .rk { grid-row: span 2; width: 20px; height: 20px; border-radius: 50%; color: var(--ink-2); border: 1px solid var(--border);
              font-size: 11px; font-weight: 700; display: grid; place-items: center; }
  .prow .rk.on { background: var(--ink); color: var(--surface); border-color: var(--ink); }   /* the 3 partners drawn on the map */
  .prow .v { font-variant-numeric: tabular-nums; }
  .prow .bar { grid-column: 2 / 4; height: 4px; border-radius: 2px; background: var(--border); overflow: hidden; }
  .prow .bar i { display: block; height: 100%; background: var(--ink-3); border-radius: 2px; }
  .prow small { color: var(--ink-3); }

  /* ---------- notes and table ---------- */
  .notes { max-width: 78ch; color: var(--ink-2); font-size: 15px; }
  .notes h2 { color: var(--ink); font-size: 18px; margin: 24px 0 8px; }
  .notes h2:first-child { margin-top: 8px; }
  .notes li + li { margin-top: 6px; }
  .table-box { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); max-height: 520px; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; font-variant-numeric: tabular-nums; }
  th:first-child, td:first-child { text-align: left; position: sticky; left: 0; background: var(--surface); white-space: normal; }
  thead th { position: sticky; top: 0; background: var(--surface); color: var(--ink-3); font-weight: 600; font-size: 12px; z-index: 1; }
  thead th:first-child { z-index: 2; }
  footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--ink-3); font-size: 13px; }
  footer a { color: inherit; display: inline-block; padding: 12px 4px; margin: -12px -4px; }  /* bigger tap area, same look */

  @media (max-width: 900px) { .panel { grid-template-columns: 1fr; } }
  /* ---------- phone ---------- */
  @media (max-width: 640px) {
    main { padding: 18px 16px 40px; }
    h1 { font-size: 21px; }
    .tabs { width: 100%; }
    .tabs button { flex: 1; }
    .controls { gap: 10px; }
    .seg { width: 100%; }
    .seg button { flex: 1; padding: 0 8px; }
    .pick, .pick select { width: 100%; }
    .map-card { padding: 8px 6px 8px; }
    .panel { padding: 16px 14px 18px; }
    .total { margin-left: 0; text-align: left; width: 100%; }
    .zoom { right: 6px; bottom: 6px; }
    .col-src { display: none; }            /* the least useful table column goes on a phone */
  }
  /* touch screens: one finger scrolls the page, two fingers move the map (handled in JS) */
  @media (pointer: coarse) { #map { touch-action: pan-x pan-y; } }
</style>
</head>
<body>
<main>
  <a class="back" href="../index.html">&larr; Macro Quant Lab</a>
  <div class="head-row">
    <h1>Who sells more than it buys? <span>__YEAR__</span></h1>
    <div class="tabs" role="tablist" aria-label="Sections">
      <button type="button" role="tab" id="tab-map" aria-controls="view-map" aria-selected="true">Map</button>
      <button type="button" role="tab" id="tab-notes" aria-controls="view-notes" aria-selected="false">How to read it</button>
    </div>
  </div>

  <!-- tab 1: the map, with the picked country's details below it -->
  <div id="view-map" role="tabpanel" aria-labelledby="tab-map">
    <div class="controls">
      <div class="seg" role="group" aria-label="Show countries">
        <button type="button" data-filter="surplus" aria-pressed="true">Surpluses</button>
        <button type="button" data-filter="deficit" aria-pressed="false">Deficits</button>
      </div>
      <label class="pick"><select id="pick" aria-label="Pick a country"></select></label>
    </div>
    <section class="card map-card" aria-label="World map">
      <div class="map-top">
        <div class="legend" id="legend"></div>
        <div class="total" id="total" aria-live="polite"></div>
      </div>
      <div class="map-wrap" id="wrap">
        <svg id="map" role="img" aria-label="World map coloured by trade balance"></svg>
        <div class="zoom">
          <button type="button" id="zin" aria-label="Zoom in">+</button>
          <button type="button" id="zout" aria-label="Zoom out">&minus;</button>
          <button type="button" id="zreset" aria-label="Reset the view">&#8634;</button>
        </div>
        <div class="tip" id="tip" role="tooltip"></div>
      </div>
    </section>
    <section class="card panel" id="panel" aria-live="polite"></section>
  </div>

  <!-- tab 2: how to read it + every country as a table -->
  <div id="view-notes" role="tabpanel" aria-labelledby="tab-notes" hidden>
    <section class="notes">
      <h2>How to read it</h2>
      <ul>
        <li><b>Trade balance = exports &minus; imports</b> of goods in __YEAR__. <b>Blue</b> countries sold more than they bought
            (surplus), <b>red</b> ones bought more than they sold (deficit). The darker the colour, the bigger the amount.</li>
        <li><b>Pick a country</b> on the map or in the list. Arrows point to its top 3 partners (from the exporter to the
            importer, between capital cities; thicker = bigger flow). Its top 10 partners are listed under the map.</li>
        <li><b>Goods only.</b> Services (tourism, finance, software) are not counted. The UK, for example, has a big deficit
            in goods but a surplus in services.</li>
        <li><b>Estimated countries.</b> __MIRROR_COUNT__ countries did not send their own __YEAR__ data to UN Comtrade (Russia,
            Vietnam, the UAE and Iran among them). For them we use <i>mirror data</i>: their exports are what every other country
            says it bought from them, and their imports are what every other country says it sold to them.</li>
        <li><b>Why surpluses and deficits do not cancel out.</b> In theory one country's export is another's import, so the world
            should add up to zero. It does not: imports include freight and insurance (CIF) while exports do not (FOB), goods
            in transit are counted in different years, and hubs such as Hong Kong, Singapore and the Netherlands re-export
            goods made elsewhere.</li>
        <li>Source: UN Comtrade (all goods, HS total), capitals from the World Bank, borders from Natural Earth. The US includes
            Puerto Rico, France includes Monaco, Switzerland includes Liechtenstein (and its large gold trade).</li>
      </ul>
      <h2>All countries</h2>
    </section>
    <div class="table-box"><table id="table"></table></div>
  </div>

  <footer>Made in the <a href="../index.html">Macro Quant Lab</a>. Data: UN Comtrade, __YEAR__.</footer>
</main>

<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js"></script>
<script>
// =====================================================================
// 1. Data (written into the page by trade_balance.py)
// =====================================================================
const DATA = __DATA__;                    // {summary, countries: {ISO3: {...}}, byMapId: {"840": "USA", ...}}
const WORLD = __WORLD__;                  // country borders (TopoJSON)
const C = DATA.countries;                 // shortcut: C.ESP = {n: "Spain", b: -57.8, ...}
const BINS = [1, 10, 50, 200];            // $ bn boundaries of the 5 colour steps: <1, 1-10, 10-50, 50-200, 200+
const ARROWS = 3;                         // arrows drawn on the map (the list below the map shows the top 10)
const phoneQuery = matchMedia("(max-width: 640px)");   // the phone layout switch
const touchQuery = matchMedia("(pointer: coarse)");    // a finger, not a mouse
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {
  filter: "surplus",                      // "surplus" | "deficit": which side is coloured
  selected: null,                         // ISO3 of the picked country, or null
  flow: "x",                              // "x" = show export destinations, "m" = import sources
  t: d3.zoomIdentity,                     // current zoom (scale k, shift x/y)
  drawKey: "",                            // changes when arrows must animate again
};

// =====================================================================
// 2. Small helpers
// =====================================================================
function money(bn, signed) {              // 1234.5 -> "$1.23 tn", -57.8 -> "−$57.8 bn", 0.4 -> "$400 m"
  const sign = bn < 0 ? "−" : (signed && bn > 0 ? "+" : "");
  const a = Math.abs(bn);
  let txt;
  if (a >= 1000) txt = (a / 1000).toFixed(2) + " tn";
  else if (a >= 100) txt = a.toFixed(0) + " bn";
  else if (a >= 1) txt = a.toFixed(1) + " bn";
  else txt = Math.round(a * 1000) + " m";
  return sign + "$" + txt;
}
function step(bn) {                       // which of the 5 colour steps a balance falls in (0..4)
  const a = Math.abs(bn); let i = 0;
  while (i < BINS.length && a >= BINS[i]) i++;
  return i;
}
function shown(c) {                       // is this country highlighted by the current filter?
  if (!c) return false;
  return state.filter === "surplus" ? c.b > 0 : c.b < 0;
}
function fillFor(iso) {                   // the colour of a country on the map
  const c = C[iso];
  if (!shown(c)) return "var(--land-off)";
  return `var(--${c.b >= 0 ? "pos" : "neg"}-${step(c.b)})`;
}
function swatch(bn) { return `<span class="sw" style="background:var(--${bn >= 0 ? "pos" : "neg"}-${step(bn)})"></span>`; }
function esc(s) { return String(s).replace(/[&<>"]/g, ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[ch])); }
function partnersOf(iso) { const c = C[iso]; return c ? (state.flow === "x" ? c.tx : c.tm) : []; }   // the top 10
function arrowPartners(iso) { return partnersOf(iso).slice(0, ARROWS); }                                  // the top 3, drawn as arrows

// =====================================================================
// 3. Geometry: country shapes, and a label anchor in each country's biggest piece
// =====================================================================
const features = topojson.feature(WORLD, WORLD.objects.countries).features
  .filter(f => f.id !== "010" && f.geometry);   // drop Antarctica (no trade, lots of space)
const featureByIso = {};
features.forEach(f => {
  f.iso = DATA.byMapId[f.id] || null;           // which country of our data this shape is
  f.alias = DATA.aliasIds.includes(f.id);       // e.g. Puerto Rico: coloured as the USA but keeps its own name
  f.area = d3.geoArea(f);                       // a country can have 2 shapes with one id (Australia + Ashmore Is.): keep the bigger
  if (f.iso && !f.alias && (!featureByIso[f.iso] || f.area > featureByIso[f.iso].area)) featureByIso[f.iso] = f;
  f.label = f.iso && !f.alias ? C[f.iso].n : f.properties.name;
  const polys = f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : [f.geometry.coordinates];
  let best = null, bestArea = -1;               // the biggest piece (mainland France, not French Guiana)
  polys.forEach(p => { const g = {type: "Polygon", coordinates: p}; const a = d3.geoArea(g); if (a > bestArea) { bestArea = a; best = g; } });
  f.main = best;
  f.anchor = d3.geoCentroid(best);              // [lon, lat] where the country name goes
});
function geoPoint(iso) {                        // where arrows start/end: the capital, or the shape's centre
  const c = C[iso];
  if (c && c.ll) return c.ll;
  return featureByIso[iso] ? featureByIso[iso].anchor : null;
}

// =====================================================================
// 4. The SVG layers
// =====================================================================
const wrap = document.getElementById("wrap");
const svg = d3.select("#map");
const gWorld = svg.append("g");                 // shapes: moved/zoomed as one group
const gBack = gWorld.append("rect").attr("fill", "transparent");  // click on the sea = clear the selection
const gCountries = gWorld.append("g");
const gOverlay = svg.append("g");               // dots, arrows, labels: redrawn in screen pixels so they stay crisp
const gDots = gOverlay.append("g");
const gArrows = gOverlay.append("g");
const gLabels = gOverlay.append("g");
const gHits = gOverlay.append("g");             // invisible bigger tap targets for tiny countries
let W = 0, H = 0, projection, path, home = d3.zoomIdentity;   // home = the starting view, also used by the reset button

const zoom = d3.zoom()
  .scaleExtent([1, 14])
  .filter(e => !e.type.startsWith("touch") && (!e.ctrlKey || e.type === "wheel") && !e.button)  // touch handled below
  .on("zoom", e => { state.t = e.transform; gWorld.attr("transform", e.transform); scheduleOverlay(); });
svg.call(zoom).on("dblclick.zoom", null);

// two-finger pinch/pan on touch screens; one finger keeps scrolling the page
let pinch = null;
function fingers(e) {
  const [a, b] = d3.pointers(e, svg.node());
  return { mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], dist: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1 };
}
svg.node().addEventListener("touchstart", e => {
  if (e.touches.length === 2) { e.preventDefault(); pinch = { ...fingers(e), t: state.t }; }
}, { passive: false });
svg.node().addEventListener("touchmove", e => {
  if (!pinch || e.touches.length !== 2) return;
  e.preventDefault();
  const now = fingers(e);
  const k = Math.max(1, Math.min(14, pinch.t.k * now.dist / pinch.dist));       // new scale (1 = the whole world)
  const wx = (pinch.mid[0] - pinch.t.x) / pinch.t.k, wy = (pinch.mid[1] - pinch.t.y) / pinch.t.k;  // map point under the fingers
  let t = d3.zoomIdentity.translate(now.mid[0] - wx * k, now.mid[1] - wy * k).scale(k);
  t = zoom.constrain()(t, [[0, 0], [W, H]], [[0, 0], [W, H]]);                    // do not leave the map
  svg.call(zoom.transform, t);
}, { passive: false });
svg.node().addEventListener("touchend", e => { if (e.touches.length < 2) pinch = null; });

function focusPoint() {                         // zoom buttons zoom around the picked country, or the middle
  const ll = state.selected && geoPoint(state.selected);
  if (ll) { const p = state.t.apply(projection(ll)); if (p[0] >= 0 && p[0] <= W && p[1] >= 0 && p[1] <= H) return p; }
  return [W / 2, H / 2];
}
const dur = reduceMotion ? 0 : 350;
document.getElementById("zin").onclick = () => svg.transition().duration(dur).call(zoom.scaleBy, 1.8, focusPoint());
document.getElementById("zout").onclick = () => svg.transition().duration(dur).call(zoom.scaleBy, 1 / 1.8, focusPoint());
document.getElementById("zreset").onclick = () => svg.transition().duration(dur).call(zoom.transform, home);

// =====================================================================
// 5. Build (and rebuild on resize / phone rotation)
// =====================================================================
function build() {
  const phone = phoneQuery.matches;
  W = wrap.clientWidth;
  if (!W) return;                               // the map tab is hidden: nothing to draw
  // as big as the screen allows: on a computer the height left under the title; on a phone a near-square box
  H = Math.round(phone ? Math.min(W * 1.05, window.innerHeight * 0.62) : Math.max(380, Math.min(W * 0.52, window.innerHeight - 190)));
  svg.attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
  projection = d3.geoNaturalEarth1().fitExtent([[4, 4], [W - 4, H - 4]], { type: "FeatureCollection", features });
  path = d3.geoPath(projection);
  features.forEach(f => { f.baseArea = path.area(f.main); });   // size on screen at zoom 1, decides which names fit
  sortByArea();                                 // biggest countries get their names first
  gBack.attr("width", W).attr("height", H);
  gCountries.selectAll("path").data(features, f => f.id + f.properties.name).join("path")
    .attr("class", "country").attr("d", path)
    .on("click", (e, f) => { if (f.iso) select(f.iso === state.selected ? null : f.iso); })
    .on("mousemove", (e, f) => showTip(e, f.iso, f.properties.name))
    .on("mouseleave", hideTip);
  zoom.extent([[0, 0], [W, H]]).translateExtent([[0, 0], [W, H]]);
  const [[, y0], [, y1]] = path.bounds({ type: "FeatureCollection", features });   // top and bottom of the world at zoom 1
  const k0 = phone ? Math.min(1.7, (H - 8) / (y1 - y0)) : 1;   // phone: zoom in until the world fills the box's height
  const centre = projection([12, 20]);                         // ...centred on Europe/Africa (the − button shows the whole world)
  home = k0 > 1 ? d3.zoomIdentity.translate(W / 2 - centre[0] * k0, (y0 + y1) / 2 * (1 - k0) + (H / 2 - (y0 + y1) / 2)).scale(k0) : d3.zoomIdentity;
  home = zoom.constrain()(home, [[0, 0], [W, H]], [[0, 0], [W, H]]);
  svg.call(zoom.transform, home);
  paint();
}
gBack.on("click", () => select(null));

// =====================================================================
// 6. Paint: country colours and outlines (filter + selection)
// =====================================================================
function paint() {
  const partners = new Set(arrowPartners(state.selected).map(p => p[0]));
  gCountries.selectAll("path")
    .style("fill", f => f.iso ? fillFor(f.iso) : "var(--land-off)")
    .classed("partner", f => partners.has(f.iso))
    .classed("sel", f => f.iso && f.iso === state.selected);
  gCountries.selectAll(".partner").raise();     // outlines on top of neighbours
  gCountries.selectAll(".sel").raise();
  renderTotal(); renderLegend(); renderPanel(); renderTable();
  overlay();
}

// =====================================================================
// 7. Overlay: capital dots, arrows to the top 3 partners, labels that never overlap
// =====================================================================
let overlayQueued = false;
function scheduleOverlay() {                    // redraw at most once per animation frame while zooming
  if (overlayQueued) return;
  overlayQueued = true;
  requestAnimationFrame(() => { overlayQueued = false; overlay(); });
}
function toScreen(ll) { const p = projection(ll); return p ? state.t.apply(p) : null; }

function arrowGeometry(a, b, width, rank) {     // a curved arrow from screen point a to b, bending "north"
  const dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy);
  const ux = dx / d, uy = dy / d;
  const [px, py] = ux >= 0 ? [uy, -ux] : [-uy, ux];      // the perpendicular that points up the screen
  const bend = Math.min(d * (0.1 + 0.07 * rank), 60 + 35 * rank);  // each rank its own curve, so arrows to the same region do not overlap
  const c = [(a[0] + b[0]) / 2 + px * bend, (a[1] + b[1]) / 2 + py * bend];   // control point of the curve
  let tx = b[0] - c[0], ty = b[1] - c[1]; const tl = Math.hypot(tx, ty) || 1; tx /= tl; ty /= tl;  // direction at the tip
  const tip = [b[0] - tx * 4, b[1] - ty * 4];            // stop just before the capital dot
  const hl = 6 + width * 1.6, hw = 3 + width * 0.9;      // arrow head length and half width
  const end = [tip[0] - tx * hl * 0.7, tip[1] - ty * hl * 0.7];
  const head = [tip, [tip[0] - tx * hl - ty * hw, tip[1] - ty * hl + tx * hw], [tip[0] - tx * hl + ty * hw, tip[1] - ty * hl - tx * hw]];
  return { d: `M${a[0]},${a[1]}Q${c[0]},${c[1]} ${end[0]},${end[1]}`, head: "M" + head.join("L") + "Z" };
}

function overlay() {
  if (!projection) return;
  const k = state.t.k, phone = phoneQuery.matches, sel = state.selected;
  const list = arrowPartners(sel);
  const key = new Set(sel ? [sel, ...list.map(p => p[0])] : []);   // countries that get a bold name

  // capital dots
  const dots = Object.keys(C).filter(iso => C[iso].ll).map(iso => ({ iso, p: toScreen(C[iso].ll) }));
  gDots.selectAll("circle").data(dots, d => d.iso).join("circle")
    .attr("class", d => "dot" + (key.has(d.iso) ? " on" : ""))
    .attr("cx", d => d.p[0]).attr("cy", d => d.p[1])
    .attr("r", d => key.has(d.iso) ? 3.2 : (k > 3 ? 1.8 : 1.1))
    .style("opacity", d => shown(C[d.iso]) || key.has(d.iso) ? null : 0.3);   // null = the CSS value

  // bigger invisible tap targets for countries too small to hit (or missing from the map)
  const hits = Object.keys(C).filter(iso => {
    const f = featureByIso[iso];
    return geoPoint(iso) && (!f || f.baseArea * k * k < 160);
  }).map(iso => ({ iso, p: toScreen(geoPoint(iso)) }));
  gHits.selectAll("circle").data(hits, d => d.iso).join("circle")
    .attr("class", "hit").attr("r", 11).attr("cx", d => d.p[0]).attr("cy", d => d.p[1])
    .on("click", (e, d) => select(d.iso === state.selected ? null : d.iso))
    .on("mousemove", (e, d) => showTip(e, d.iso))
    .on("mouseleave", hideTip);

  // arrows: exports go from the picked country to the partner, imports from the partner to it
  let arrows = [];
  const from = sel && geoPoint(sel);
  if (from) {
    const s = toScreen(from), maxV = list.length ? list[0][1] : 1;
    arrows = list.map(([iso, v], i) => {
      const ll = geoPoint(iso); if (!ll) return null;
      const p = toScreen(ll), width = (phone ? 1.2 : 1.6) + (phone ? 2.6 : 4) * v / maxV;  // thicker = bigger flow
      if (Math.hypot(p[0] - s[0], p[1] - s[1]) < 14) return null;   // neighbours too close for an arrow at this zoom (its name is still bold)
      const g = state.flow === "x" ? arrowGeometry(s, p, width, i) : arrowGeometry(p, s, width, i);
      return { iso, rank: i + 1, width, ...g };
    }).filter(Boolean).reverse();                 // draw #1 last so it sits on top
  }
  const ak = state.drawKey;
  gArrows.selectAll("g.arrow").data(arrows, d => ak + d.iso).join(
      enter => { const g = enter.append("g").attr("class", "arrow");
                 g.append("path").attr("class", "arc-halo grow").attr("pathLength", 1);
                 g.append("path").attr("class", "arc grow").attr("pathLength", 1);
                 g.append("path").attr("class", "head grow");
                 return g; })
    .each(function (d) {
      const g = d3.select(this);
      g.select(".arc-halo").attr("d", d.d).attr("stroke-width", d.width + 3);
      g.select(".arc").attr("d", d.d).attr("stroke-width", d.width);
      g.select(".head").attr("d", d.head);
    });

  // labels: most important first; a label is skipped if it would overlap one already placed
  const fs = phone ? 10 : 10.5;
  const cands = [];
  key.forEach(iso => { const ll = geoPoint(iso); if (ll) { const p = toScreen(ll); cands.push({ id: "k" + iso, text: C[iso].n, x: p[0], y: p[1] - 10, size: 12, cls: "key", anchor: "middle" }); } });
  const minArea = 1000;                          // a country name needs this many square pixels of land
  const showCapitals = k >= (phone ? 2.5 : 2.2);  // capital names only once zoomed in
  byArea.forEach(f => {
    if (key.has(f.iso) || f.baseArea * k * k < minArea) return;
    const p = toScreen(f.anchor);
    cands.push({ id: "n" + f.id + f.properties.name, text: f.label, x: p[0], y: p[1], size: fs, cls: "", anchor: "middle" });
    const c = showCapitals && !f.alias && f.iso && C[f.iso];   // its capital comes right after it: never a capital without its country
    if (c && c.ll && c.c) {
      const q = toScreen(c.ll);
      cands.push({ id: "c" + f.iso, text: c.c, x: q[0] + 4, y: q[1], size: 9, cls: "cap", anchor: "start", needs: "n" + f.id + f.properties.name });
    }
  });
  const placed = [], boxes = [];
  const placedIds = new Set();
  cands.forEach(l => {
    if (l.needs && !placedIds.has(l.needs)) return;                     // its country name did not fit: skip the capital too
    const w = l.text.length * l.size * 0.56 + 4, h = l.size + 3;
    const x0 = l.anchor === "middle" ? l.x - w / 2 : l.x, y0 = l.y - h / 2;
    const box = [x0, y0, x0 + w, y0 + h];
    if (box[0] < 0 || box[2] > W || box[1] < 0 || box[3] > H) return;      // off the visible map
    if (boxes.some(b => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) return;  // overlaps
    boxes.push(box); placed.push(l); placedIds.add(l.id);
  });
  gLabels.selectAll("text").data(placed, d => d.id).join("text")
    .attr("class", d => "lbl " + d.cls).attr("x", d => d.x).attr("y", d => d.y)
    .attr("text-anchor", d => d.anchor).attr("dominant-baseline", "central").text(d => d.text);
}
const byArea = features.filter(f => f.label).slice();   // sorted biggest first once the projection exists
function sortByArea() { byArea.sort((a, b) => b.baseArea - a.baseArea); }

// =====================================================================
// 8. Tooltip (mouse only; on a phone the panel below shows the same and more)
// =====================================================================
const tip = document.getElementById("tip");
function showTip(e, iso, fallbackName) {
  if (touchQuery.matches) return;
  const c = C[iso];
  tip.innerHTML = c
    ? `<b>${esc(c.n)}</b><br>${swatch(c.b)} ${money(c.b, true)} ${c.b >= 0 ? "surplus" : "deficit"}<br>` +
      `<span class="muted">Exports ${money(c.x)} · Imports ${money(c.m)}${c.s === "m" ? "<br>Estimated from partners' data" : ""}</span>`
    : `<b>${esc(fallbackName || "")}</b><br><span class="muted">No data</span>`;
  const [x, y] = d3.pointer(e, wrap);
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  tip.style.left = Math.min(x + 14, W - tw - 4) + "px";
  tip.style.top = (y + 14 + th > H ? y - th - 10 : y + 14) + "px";
  tip.style.opacity = 1;
}
function hideTip() { tip.style.opacity = 0; }

// =====================================================================
// 9. Corner total, legend, side panel, table
// =====================================================================
const all = Object.entries(C).map(([iso, c]) => ({ iso, ...c }));
const surplus = all.filter(c => c.b > 0).sort((a, b) => b.b - a.b);
const deficit = all.filter(c => c.b < 0).sort((a, b) => a.b - b.b);
const sum = list => list.reduce((s, c) => s + c.b, 0);

function renderTotal() {                       // the corner box: the total of the side being shown
  const list = state.filter === "surplus" ? surplus : deficit;
  document.getElementById("total").innerHTML =
    `<span>Total ${state.filter} · ${list.length} countries</span><span class="big">${money(sum(list), true)}</span>`;
}

function renderLegend() {                      // 5 red + 5 blue steps; the side not shown is faded
  const negOn = state.filter === "deficit", posOn = state.filter === "surplus";
  const sw = [4, 3, 2, 1, 0].map(i => `<span class="${negOn ? "" : "dim"}" style="background:var(--neg-${i})"></span>`).join("") +
             [0, 1, 2, 3, 4].map(i => `<span class="${posOn ? "" : "dim"}" style="background:var(--pos-${i})"></span>`).join("");
  const ticks = ["200", "50", "10", "1", "0", "1", "10", "50", "200"]
    .map((t, i) => `<span style="left:${(i + 1) * 10}%">${t}</span>`).join("");
  document.getElementById("legend").innerHTML =
    `<div class="ramp-box"><div class="ends"><span>&larr; Deficit</span><span>$ billions</span><span>Surplus &rarr;</span></div>` +
    `<div class="ramp">${sw}</div><div class="ticks">${ticks}</div></div>`;
}

function partnerRow(iso, v, i, total) {
  const c = C[iso];
  const share = total > 0 ? (100 * v / total).toFixed(0) + "% of total" : "";
  return `<li><button type="button" class="prow" data-iso="${iso}">` +
    `<span class="rk${i < ARROWS ? " on" : ""}">${i + 1}</span><span>${esc(c ? c.n : iso)}</span><span class="v">${money(v)} <small>${share}</small></span>` +
    `<span class="bar"><i style="width:${(100 * v / (total || v)).toFixed(1)}%"></i></span></button></li>`;
}

function renderPanel() {                       // below the map: left = the country, right = its top 10 partners
  const el = document.getElementById("panel");
  const sel = state.selected, c = sel && C[sel];
  if (!c) {                                     // nothing picked: the 10 largest of the side being shown
    const list = state.filter === "surplus" ? surplus : deficit;
    el.innerHTML = `<div><h2>Pick a country</h2><p>Tap it on the map or choose it in the list above: arrows show its top 3
      partners and its top 10 appear here.</p></div>` +
      `<div><h3>Largest ${state.filter === "surplus" ? "surpluses" : "deficits"}</h3><ol class="top">` +
      list.slice(0, 10).map((d, i) =>
        `<li><button type="button" class="prow" data-iso="${d.iso}"><span class="rk">${i + 1}</span><span>${esc(d.n)}</span>` +
        `<span class="v">${swatch(d.b)} ${money(d.b, true)}</span></button></li>`).join("") + `</ol></div>`;
  } else {
    const list = partnersOf(sel), total = state.flow === "x" ? c.x : c.m;
    el.innerHTML =
      `<div><div class="p-head"><h2>${esc(c.n)}</h2><button type="button" class="close" id="close" aria-label="Clear selection">&times;</button></div>` +
      (c.c ? `<p>Capital: ${esc(c.c)}</p>` : "") +
      `<div class="bal"><span class="big">${money(c.b, true)}</span><span class="tag">${swatch(c.b)}${c.b >= 0 ? "Surplus" : "Deficit"}</span></div>` +
      `<div class="xm"><div><span>Exports</span>${money(c.x)}</div><div><span>Imports</span>${money(c.m)}</div></div>` +
      (c.s === "m" ? `<p class="est">Estimated from partners' data: ${esc(c.n)} did not report its own __YEAR__ figures.</p>` : "") +
      `<div class="seg small" role="group" aria-label="Partners to show">` +
      `<button type="button" data-flow="x" aria-pressed="${state.flow === "x"}">Exports to</button>` +
      `<button type="button" data-flow="m" aria-pressed="${state.flow === "m"}">Imports from</button></div></div>` +
      `<div><h3>Top 10 ${state.flow === "x" ? "buyers of its goods" : "sellers to it"}</h3>` +
      `<ol class="top">${list.map(([iso, v], i) => partnerRow(iso, v, i, total)).join("")}</ol></div>`;
    document.getElementById("close").onclick = () => select(null);
    el.querySelectorAll("[data-flow]").forEach(b => b.onclick = () => {
      state.flow = b.dataset.flow; state.drawKey = sel + state.flow; paint();
    });
  }
  el.querySelectorAll(".prow").forEach(b => b.onclick = () => select(b.dataset.iso));
}

function renderTable() {                       // every country, biggest surplus first, biggest deficit last
  if (document.getElementById("view-notes").hidden) return;   // only build it when its tab is open
  const rows = all.slice().sort((a, b) => b.b - a.b);
  document.getElementById("table").innerHTML =
    `<thead><tr><th>Country</th><th>Balance</th><th>Exports</th><th>Imports</th><th class="col-src">Data</th></tr></thead><tbody>` +
    rows.map(c => `<tr><td>${esc(c.n)}</td><td>${money(c.b, true)}</td><td>${money(c.x)}</td><td>${money(c.m)}</td>` +
                  `<td class="col-src">${c.s === "m" ? "estimated" : "reported"}</td></tr>`).join("") + `</tbody>`;
}

// tabs: "Map" and "How to read it"
const tabs = [["tab-map", "view-map"], ["tab-notes", "view-notes"]];
tabs.forEach(([tabId]) => document.getElementById(tabId).onclick = () => {
  tabs.forEach(([t, v]) => {
    const on = t === tabId;
    document.getElementById(t).setAttribute("aria-selected", on);
    document.getElementById(v).hidden = !on;
  });
  renderTable();
});

// =====================================================================
// 10. Interaction: filter buttons, country picker, selection
// =====================================================================
document.querySelectorAll("[data-filter]").forEach(b => b.onclick = () => {
  state.filter = b.dataset.filter;
  document.querySelectorAll("[data-filter]").forEach(x => x.setAttribute("aria-pressed", x === b));
  paint();
});
const pick = document.getElementById("pick");
pick.innerHTML = `<option value="">Pick a country…</option>` +
  all.slice().sort((a, b) => a.n.localeCompare(b.n)).map(c => `<option value="${c.iso}">${esc(c.n)}</option>`).join("");
pick.onchange = () => select(pick.value || null);

function select(iso) {
  state.selected = iso && C[iso] ? iso : null;
  if (state.selected) {                          // colour the side the picked country is on (USA -> Deficits)
    state.filter = C[state.selected].b >= 0 ? "surplus" : "deficit";
    document.querySelectorAll("[data-filter]").forEach(x => x.setAttribute("aria-pressed", x.dataset.filter === state.filter));
  }
  state.drawKey = (state.selected || "") + state.flow;   // new key = arrows animate in again
  pick.value = state.selected || "";
  history.replaceState(null, "", state.selected ? "#" + state.selected : location.pathname + location.search);
  hideTip();
  paint();
  showSelection();
  if (state.selected && phoneQuery.matches && document.activeElement === pick) {   // phone: show the map after picking from the list
    document.getElementById("wrap").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
  }
}

function showSelection() {                       // if the picked country or its 3 arrows are off screen, move/zoom out until they fit
  if (!state.selected || !projection) return;
  const pts = [state.selected, ...arrowPartners(state.selected).map(p => p[0])]
    .map(geoPoint).filter(Boolean).map(ll => projection(ll));               // positions at zoom 1
  const inView = pts.every(p => { const q = state.t.apply(p); return q[0] > 10 && q[0] < W - 10 && q[1] > 10 && q[1] < H - 10; });
  if (inView) return;                                                       // everything visible: leave the view alone
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const dx = Math.max(...xs) - Math.min(...xs) || 1, dy = Math.max(...ys) - Math.min(...ys) || 1;
  const k = Math.max(1, Math.min(state.t.k, 0.85 * W / dx, 0.85 * H / dy)); // zoom out only as much as needed
  const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
  let t = d3.zoomIdentity.translate(W / 2 - cx * k, H / 2 - cy * k).scale(k);
  t = zoom.constrain()(t, [[0, 0], [W, H]], [[0, 0], [W, H]]);             // never past the edge of the world
  svg.transition().duration(dur).call(zoom.transform, t);
}

// =====================================================================
// 11. Start, and rebuild when the width changes (window resize, phone rotation)
// =====================================================================
let lastWidth = 0;
function rebuild() { lastWidth = wrap.clientWidth; build(); }
new ResizeObserver(() => requestAnimationFrame(() => { if (wrap.clientWidth && Math.abs(wrap.clientWidth - lastWidth) > 2) rebuild(); })).observe(wrap);
phoneQuery.addEventListener("change", rebuild);
rebuild();
const fromHash = location.hash.slice(1).toUpperCase();   // a link like trade_balance.html#DEU opens Germany
if (C[fromHash]) select(fromHash);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
