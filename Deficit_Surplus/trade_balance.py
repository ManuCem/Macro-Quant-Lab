"""
Who sells more to the world than it buys? A world map of trade surpluses and deficits.

For every country we take its trade in GOODS for one year from UN Comtrade (free,
no API key) and compute:

    trade balance = exports - imports
        > 0  -> SURPLUS  (the country sells more than it buys, e.g. China, Germany)
        < 0  -> DEFICIT  (the country buys more than it sells, e.g. the US, the UK)

Comtrade also splits each country's trade by partner, so for every country we
keep its top 10 export destinations and its top 10 import sources. On the map,
tapping a country draws arrows to its top 3 partners (the top 10 are in a table);
tapping it again switches to the other side, a third tap returns to the world map. While a country is
picked the red/blue surplus colours switch off: only its top 3 partners are
coloured (green = buy its exports, purple = sell it its imports, darker = bigger)
and each gets a numbered badge 1-2-3 where its arrow ends.

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
            "tx": [[p, round(v, 3)] for p, v in row["top_exports"]],  # top 10 export destinations
            "tm": [[p, round(v, 3)] for p, v in row["top_imports"]],  # top 10 import sources
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
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Trade Surplus Map</title>
<meta name="description" content="World map of trade surpluses and deficits in goods, __YEAR__, with each country's top trading partners.">
<style>
  /* ---------- colour tokens: light by default, dark when the viewer's system is dark ---------- */
  :root {
    color-scheme: light dark;
    --page: #f9f9f7;  --surface: #fcfcfb;  --ink: #0b0b0b;  --ink-2: #52514e;  --ink-3: #898781;
    --border: #e1e0d9;  --hover: #c3c2b7;
    --land-off: #e6e5e0;                       /* countries of the other side (not highlighted) or without data */
    /* deficit arm (red) and surplus arm (blue): step 0 = smallest amount, step 4 = largest */
    --neg-0: #fbd0cc; --neg-1: #f4a19b; --neg-2: #e5605c; --neg-3: #bf3534; --neg-4: #87201f;
    --pos-0: #cde2fb; --pos-1: #9ec5f4; --pos-2: #5598e7; --pos-3: #256abf; --pos-4: #104281;
    --arrow: #0b0b0b;
    /* a country is picked: red/blue switch off and only its top 3 partners are coloured (step 2 = #1, 1 = #2, 0 = #3) */
    --sel-fill: #52514e;                       /* the picked country itself */
    --exp-0: #9ad8b6; --exp-1: #4cb584; --exp-2: #1f7f55;   /* green: countries that BUY its goods (its exports) */
    --imp-0: #c9b3f0; --imp-1: #9a74de; --imp-2: #6236bd;   /* purple: countries that SELL to it (its imports) */
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --page: #0d0d0d;  --surface: #1a1a19;  --ink: #f0efec;  --ink-2: #c3c2b7;  --ink-3: #898781;
      --border: #2c2c2a;  --hover: #4a4a46;  --land-off: #2f2f2c;
      /* in dark mode small amounts sit close to the dark surface and big ones glow */
      --neg-0: #4a1f1e; --neg-1: #7d2b2a; --neg-2: #c63b3a; --neg-3: #e5605c; --neg-4: #f4a19b;
      --pos-0: #173459; --pos-1: #1c4f8f; --pos-2: #2a78d6; --pos-3: #5598e7; --pos-4: #9ec5f4;
      --arrow: #f0efec;
      --sel-fill: #c3c2b7;
      --exp-0: #2a6b4d; --exp-1: #3fa874; --exp-2: #7fe0ae;
      --imp-0: #4d3880; --imp-1: #7d5ad0; --imp-2: #b79bf0;
    }
  }
  :root[data-theme="dark"] {
    --page: #0d0d0d;  --surface: #1a1a19;  --ink: #f0efec;  --ink-2: #c3c2b7;  --ink-3: #898781;
    --border: #2c2c2a;  --hover: #4a4a46;  --land-off: #2f2f2c;
    --neg-0: #4a1f1e; --neg-1: #7d2b2a; --neg-2: #c63b3a; --neg-3: #e5605c; --neg-4: #f4a19b;
    --pos-0: #173459; --pos-1: #1c4f8f; --pos-2: #2a78d6; --pos-3: #5598e7; --pos-4: #9ec5f4;
    --arrow: #f0efec;
    --sel-fill: #c3c2b7;
    --exp-0: #2a6b4d; --exp-1: #3fa874; --exp-2: #7fe0ae;
    --imp-0: #4d3880; --imp-1: #7d5ad0; --imp-2: #b79bf0;
  }

  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--page); color: var(--ink);
               font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  [hidden] { display: none !important; }
  button { font: inherit; color: inherit; }
  :focus-visible { outline: 2px solid var(--pos-2); outline-offset: 2px; }

  /* ================= MAP VIEW: the map fills the whole screen, the controls float on top ================= */
  #view-map { position: fixed; inset: 0; overflow: hidden; background: var(--page); }
  #map { position: absolute; inset: 0; width: 100%; height: 100%; display: block;
         touch-action: none; user-select: none; -webkit-user-select: none; }   /* the map is the whole screen: fingers move it */
  .float { position: absolute; z-index: 2; background: var(--surface);
           background: color-mix(in srgb, var(--surface) 92%, transparent); backdrop-filter: blur(6px);
           border: 1px solid var(--border); border-radius: 12px; }

  /* top-left: title, side buttons, country picker, total */
  .top-left { top: max(12px, env(safe-area-inset-top)); left: max(12px, env(safe-area-inset-left)); padding: 8px 12px 10px;
              width: min(520px, calc(100% - 140px)); }
  .title-row { display: flex; align-items: center; gap: 4px; }
  .back { display: grid; place-items: center; width: 40px; height: 40px; margin-left: -10px; flex: none; border-radius: 8px;
          color: var(--ink-2); text-decoration: none; font-size: 18px; }
  .back:hover { background: var(--page); color: var(--ink); }
  h1 { font-size: 18px; line-height: 1.25; margin: 0; letter-spacing: -0.01em; }
  h1 span { color: var(--ink-3); font-weight: 500; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
  .seg { display: inline-flex; flex: 1 1 200px; background: var(--page); border: 1px solid var(--border); border-radius: 10px; padding: 3px; }
  .seg button { flex: 1; min-height: 40px; padding: 0 12px; border: 0; border-radius: 7px; background: transparent;
                color: var(--ink-2); font-size: 15px; cursor: pointer; }
  .seg button:hover { color: var(--ink); }
  .seg button[aria-pressed="true"] { background: var(--ink); color: var(--surface); font-weight: 600; }
  .pick { flex: 1 1 180px; display: flex; }
  .pick select { width: 100%; min-height: 46px; padding: 0 10px; border: 1px solid var(--border); border-radius: 10px;
                 background: var(--page); color: var(--ink); font: inherit; font-size: 15px; }
  .total { margin-top: 8px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; font-size: 13px; color: var(--ink-2); }
  .total b { font-size: 24px; color: var(--ink); line-height: 1.1; }

  /* top-right: the two icons, and the panel with the top 10 under them */
  .icons { position: absolute; z-index: 3; top: max(12px, env(safe-area-inset-top)); right: max(12px, env(safe-area-inset-right));
           display: flex; gap: 8px; }
  .icon { width: 44px; height: 44px; display: grid; place-items: center; border: 1px solid var(--border); border-radius: 10px;
          background: var(--surface); color: var(--ink); cursor: pointer; }
  .icon:hover { border-color: var(--hover); }
  .icon[aria-expanded="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
  .icon svg { width: 20px; height: 20px; }
  .panel { top: calc(max(12px, env(safe-area-inset-top)) + 54px); right: max(12px, env(safe-area-inset-right)); width: 360px;
           max-height: calc(100% - 140px); overflow: auto; padding: 14px 16px 16px; }
  .panel h2 { margin: 0; font-size: 20px; line-height: 1.2; }
  .panel h3 { margin: 14px 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--ink-3); }
  .panel p { margin: 4px 0; color: var(--ink-2); font-size: 14px; }
  .p-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
  .close { width: 40px; height: 40px; flex: none; margin: -8px -8px 0 0; border: 0; border-radius: 8px; background: transparent;
           color: var(--ink-2); font-size: 22px; cursor: pointer; }
  .close:hover { background: var(--page); color: var(--ink); }
  .bal { display: flex; align-items: center; gap: 10px; margin: 6px 0 2px; }
  .bal .big { font-size: 28px; font-weight: 700; line-height: 1.1; }
  .tag { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); }
  .xm { display: flex; gap: 24px; font-size: 14px; }
  .xm div span { display: block; color: var(--ink-3); font-size: 12px; }
  .est { font-size: 13px !important; padding: 6px 10px; border-radius: 8px; background: var(--page); }
  .seg.small { margin-top: 12px; width: 100%; }
  .again { font-size: 13px !important; color: var(--ink-3) !important; }
  .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; flex: none; }

  /* the scrollable top-10 table */
  .tbl { max-height: min(420px, 48vh); overflow: auto; border: 1px solid var(--border); border-radius: 10px; margin-top: 6px; }
  .tbl table { border-collapse: collapse; width: 100%; font-size: 14px; }
  .tbl th, .tbl td { padding: 0 8px; height: 40px; text-align: right; border-bottom: 1px solid var(--border);
                     font-variant-numeric: tabular-nums; white-space: nowrap; }
  .tbl tr:last-child td { border-bottom: 0; }
  .tbl th { position: sticky; top: 0; z-index: 1; height: 32px; background: var(--surface); color: var(--ink-3); font-size: 12px; font-weight: 600; }
  .tbl td.name, .tbl th.name { text-align: left; white-space: normal; width: 100%; }
  .tbl td.rk { color: var(--ink-3); text-align: center; width: 28px; padding: 0 0 0 8px; }
  .tbl tr.on td.rk { color: var(--ink); font-weight: 700; }
  .tbl td.rk .num { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;   /* the same 1-2-3 */
                    border: 2px solid var(--arrow); background: var(--surface); font-size: 12px; }                  /* badge as on the map */
  .tbl small { color: var(--ink-3); }
  .rowbtn { all: unset; cursor: pointer; display: block; padding: 10px 0; }
  .rowbtn:hover { text-decoration: underline; }
  .rowbtn:focus-visible { outline: 2px solid var(--pos-2); }

  /* bottom-left legend, bottom-right zoom */
  .legend { left: max(12px, env(safe-area-inset-left)); bottom: max(12px, env(safe-area-inset-bottom)); width: 300px;
            padding: 6px 10px 2px; font-size: 12px; color: var(--ink-2); }
  .ramp { display: grid; grid-template-columns: repeat(10, 1fr); gap: 2px; }
  .ramp span { height: 10px; transition: opacity .25s; }
  .ramp span:first-child { border-radius: 3px 0 0 3px; }
  .ramp span:last-child { border-radius: 0 3px 3px 0; }
  .ramp span.dim { opacity: .18; }
  .ticks { position: relative; height: 16px; font-size: 11px; color: var(--ink-3); }
  .ticks span { position: absolute; top: 1px; transform: translateX(-50%); font-variant-numeric: tabular-nums; }
  .ends { display: flex; justify-content: space-between; font-weight: 600; }
  /* the legend while a country is picked: the picked country + 3 partner steps */
  .lkey { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; padding: 4px 0 6px; }
  .lkey .item { display: inline-flex; align-items: center; gap: 6px; }
  .lkey .steps { display: inline-flex; gap: 2px; }
  .lkey .steps span { width: 20px; height: 10px; }
  .lkey .steps span:first-child { border-radius: 3px 0 0 3px; }
  .lkey .steps span:last-child { border-radius: 0 3px 3px 0; }
  .zoom { position: absolute; z-index: 2; right: max(12px, env(safe-area-inset-right)); bottom: max(12px, env(safe-area-inset-bottom));
          display: flex; gap: 6px; }
  .zoom button { width: 44px; height: 44px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface);
                 font: 600 18px/1 system-ui, sans-serif; cursor: pointer; }
  .zoom button:hover { border-color: var(--hover); }

  /* map drawing */
  .country { stroke: var(--surface); stroke-width: 0.6px; vector-effect: non-scaling-stroke; cursor: pointer; transition: fill .25s, opacity .25s; }
  .country.partner { stroke: var(--ink); stroke-width: 1.2px; opacity: 1; }
  .country.sel { stroke: var(--ink); stroke-width: 2px; opacity: 1; }
  .dot { fill: var(--ink-3); opacity: .75; pointer-events: none; }
  .dot.on { fill: var(--ink); opacity: 1; }
  .hit { fill: transparent; cursor: pointer; }
  .lbl { font-size: 10.5px; fill: var(--ink); paint-order: stroke; stroke: var(--surface); stroke-width: 2.5px; stroke-opacity: .8;
         stroke-linejoin: round; pointer-events: none; transition: opacity .25s; }
  .lbl.faint { opacity: .35; }
  .lbl.cap { font-size: 9px; fill: var(--ink-3); }
  .lbl.key { font-size: 12.5px; font-weight: 700; stroke-width: 3.5px; stroke-opacity: 1; }
  /* arrows: drawn ABOVE every border and name: halo + thick line + head in the MIDDLE (shows the direction without
     piling up on one country) + moving dashes; a ring on the picked country and a numbered badge 1-2-3 on each partner */
  .arrows { pointer-events: none; }
  .arc-halo { fill: none; stroke: var(--surface); stroke-linecap: round; }
  .arc { fill: none; stroke: var(--arrow); stroke-linecap: round; }
  .flowdash { fill: none; stroke: var(--surface); stroke-linecap: round; stroke-dasharray: 1 11; animation: flow 1s linear infinite; }
  .head { fill: var(--arrow); stroke: var(--surface); stroke-width: 1.5px; stroke-linejoin: round; }
  .home { fill: var(--surface); stroke: var(--arrow); stroke-width: 2.5px; }      /* where every line starts: the picked country */
  .badge circle { fill: var(--arrow); stroke: var(--surface); stroke-width: 2px; }  /* where a line ends: the partner, with its rank */
  .badge text { fill: var(--surface); font: 700 12px/1 system-ui, sans-serif; }
  .leader { stroke: var(--arrow); stroke-width: 1.5px; stroke-dasharray: 2 3; }      /* a badge pushed off a crowded spot -> its capital */
  @keyframes flow { from { stroke-dashoffset: 12; } to { stroke-dashoffset: 0; } }   /* dashes travel from seller to buyer */
  .arc.grow, .arc-halo.grow { stroke-dasharray: 1; animation: grow .6s ease-out both; }
  .head.grow, .badge.grow, .flowdash.grow { animation: fadein .25s ease-out .5s both; }
  .flowdash.grow { animation: fadein .25s ease-out .5s both, flow 1s linear .5s infinite; }
  @keyframes grow { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
  @keyframes fadein { from { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .arc.grow, .arc-halo.grow, .head.grow, .badge.grow, .flowdash, .flowdash.grow { animation: none; } }

  .tip { position: absolute; z-index: 4; pointer-events: none; background: var(--surface); border: 1px solid var(--border);
         border-radius: 8px; padding: 8px 10px; font-size: 13px; line-height: 1.4; box-shadow: 0 4px 14px rgba(0,0,0,.12);
         max-width: 240px; opacity: 0; transition: opacity .1s; }
  .tip b { font-size: 14px; }
  .tip .muted { color: var(--ink-3); }

  /* ================= HOW TO READ IT: a normal scrolling page, full width ================= */
  #view-notes { padding: 20px 32px 40px; }
  .notes-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .notes-head h1 { font-size: 24px; }
  .btn { min-height: 44px; padding: 0 16px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface);
         cursor: pointer; font-size: 15px; }
  .btn:hover { border-color: var(--hover); }
  .facts { list-style: none; margin: 0 0 28px; padding: 0; display: grid; gap: 10px;
           grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
  .facts li { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px;
              font-size: 14px; color: var(--ink-2); }
  .facts b { display: block; color: var(--ink); font-size: 15px; }
  #view-notes h2 { font-size: 18px; margin: 0 0 8px; }
  .table-box { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
  .table-box table { border-collapse: collapse; width: 100%; font-size: 14px; }
  .table-box th, .table-box td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap;
                                 font-variant-numeric: tabular-nums; }
  .table-box th:first-child, .table-box td:first-child { text-align: left; position: sticky; left: 0; background: var(--surface); white-space: normal; }
  .table-box thead th { position: sticky; top: 0; background: var(--surface); color: var(--ink-3); font-weight: 600; font-size: 12px; z-index: 1; }
  .table-box thead th:first-child { z-index: 2; }
  footer { margin-top: 24px; color: var(--ink-3); font-size: 13px; }
  footer a { color: inherit; display: inline-block; padding: 12px 4px; margin: -12px -4px; }

  /* ================= PHONE ================= */
  @media (max-width: 640px) {
    .top-left { left: 8px; right: 8px; top: max(8px, env(safe-area-inset-top)); width: auto; padding: 6px 10px 8px; }
    .title-row { padding-right: 96px; min-height: 44px; }              /* room for the two icons that sit in this bar's corner */
    h1 { font-size: 15px; }
    .icons { top: calc(max(8px, env(safe-area-inset-top)) + 6px); right: 14px; }
    .seg { flex-basis: 160px; }
    .pick { flex-basis: 130px; }
    .total { margin-top: 6px; }
    .total b { font-size: 20px; }
    .legend { left: 8px; bottom: max(8px, env(safe-area-inset-bottom)); width: calc(100% - 76px); }
    .zoom { right: 8px; bottom: max(8px, env(safe-area-inset-bottom)); flex-direction: column; }
    /* the panel becomes a sheet at the bottom of the screen */
    .panel { top: auto; left: 0; right: 0; bottom: 0; width: auto; height: 46%; max-height: none; border-radius: 14px 14px 0 0;
             padding: 12px 14px calc(16px + env(safe-area-inset-bottom)); border-bottom: 0; }
    .tbl { max-height: none; }
    #view-map.sheet-open .legend, #view-map.sheet-open .zoom { bottom: calc(46% + 8px); }
    #view-map.sheet-open .legend, #view-map.sheet-open .zoom { display: none; }   /* the sheet needs the room; pinch still zooms */
    #view-notes { padding: 14px 16px 32px; }
    .col-src { display: none; }                                         /* the least useful table column goes on a phone */
  }
</style>
</head>
<body>

<!-- ======================= MAP VIEW ======================= -->
<div id="view-map">
  <svg id="map" role="img" aria-label="World map coloured by trade balance"></svg>

  <div class="float top-left">
    <div class="title-row">
      <a class="back" href="../index.html" aria-label="Back to Macro Quant Lab">&larr;</a>
      <h1>Who sells more than it buys? <span>__YEAR__</span></h1>
    </div>
    <div class="controls">
      <div class="seg" role="group" aria-label="Show countries">
        <button type="button" data-side="surplus" aria-pressed="true">Surpluses</button>
        <button type="button" data-side="deficit" aria-pressed="false">Deficits</button>
      </div>
      <label class="pick"><select id="pick" aria-label="Pick a country"></select></label>
    </div>
    <div class="total" id="total" aria-live="polite"></div>
  </div>

  <div class="icons">
    <button type="button" class="icon" id="open-notes" aria-label="How to read it" title="How to read it">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v6"/><circle cx="12" cy="7.5" r=".6" fill="currentColor"/></svg>
    </button>
    <button type="button" class="icon" id="toggle-panel" aria-label="Top 10 table" title="Top 10 table" aria-expanded="false" aria-controls="panel">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3.5" y="4" width="17" height="16" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M9 4v16"/></svg>
    </button>
  </div>

  <section class="float panel" id="panel" aria-live="polite" hidden></section>

  <div class="float legend" id="legend"></div>
  <div class="zoom">
    <button type="button" id="zin" aria-label="Zoom in">+</button>
    <button type="button" id="zout" aria-label="Zoom out">&minus;</button>
    <button type="button" id="zreset" aria-label="Reset the view">&#8634;</button>
  </div>
  <div class="tip" id="tip" role="tooltip"></div>
</div>

<!-- ======================= HOW TO READ IT ======================= -->
<div id="view-notes" hidden>
  <div class="notes-head">
    <button type="button" class="btn" id="back-map">&larr; Map</button>
    <h1>How to read it</h1>
  </div>
  <ul class="facts">
    <li><b>Balance = exports &minus; imports</b>Goods only, __YEAR__, in US dollars.</li>
    <li><b>Blue = surplus, red = deficit</b>Sells more than it buys, or the opposite. Darker = bigger.</li>
    <li><b>Click a country three times</b>1st: its bigger side. 2nd: the other side. 3rd: back to the world map.</li>
    <li><b>Pick a country: red and blue switch off</b>Green = its top 3 buyers, purple = its top 3 sellers. Darker = bigger.</li>
    <li><b>Arrows: seller &rarr; buyer</b>Numbered 1-2-3 where they end; the arrowhead in the middle shows the direction. Top 10 in the table.</li>
    <li><b>Services not counted</b>Tourism, finance and software are not in these numbers.</li>
    <li><b>__MIRROR_COUNT__ countries are estimated</b>They did not report; their partners' numbers are used instead.</li>
    <li><b>The world does not add to zero</b>Freight costs, timing and re-exports through hubs.</li>
    <li><b>Source</b>UN Comtrade; capitals: World Bank; borders: Natural Earth.</li>
  </ul>
  <h2>All countries</h2>
  <div class="table-box"><table id="table"></table></div>
  <footer>Made in the <a href="../index.html">Macro Quant Lab</a>. Data: UN Comtrade, __YEAR__.</footer>
</div>

<script src="lib/d3.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i"></script>
<script src="lib/topojson-client.min.js" integrity="sha384-Ukv1p/xTma6P4/2bY5KzWBw+ydSpXmhCMtyciIQVDJ1RmOxtCYNMF1uXT9T63H67"></script>
<script>
// =====================================================================
// 1. Data (written into the page by trade_balance.py)
// =====================================================================
const DATA = __DATA__;                    // {summary, countries: {ISO3: {...}}, byMapId: {"840": "USA", ...}, aliasIds}
const WORLD = __WORLD__;                  // country borders (TopoJSON)
const C = DATA.countries;                 // shortcut: C.ESP = {n: "Spain", b: -57.8, ...}
const BINS = [1, 10, 50, 200];            // $ bn boundaries of the 5 colour steps: <1, 1-10, 10-50, 50-200, 200+
const ARROWS = 3;                         // arrows drawn on the map (the table shows the top 10)
const phoneQuery = matchMedia("(max-width: 640px)");   // the phone layout switch
const touchQuery = matchMedia("(pointer: coarse)");    // a finger, not a mouse
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {
  side: "surplus",                        // "surplus" | "deficit": which side is coloured
  selected: null,                         // ISO3 of the picked country, or null
  flow: "x",                              // "x" = its exports (who buys from it), "m" = its imports (who sells to it)
  panelOpen: false,                       // the top-10 panel in the corner
  t: d3.zoomIdentity,                     // current zoom (scale k, shift x/y)
  drawKey: "",                            // changes when arrows must animate again
};
// the side and the flow go together: Surpluses = what it SELLS (exports), Deficits = what it BUYS (imports)
const FLOW_OF = { surplus: "x", deficit: "m" };

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
function shown(c) { return !!c && (state.side === "surplus" ? c.b > 0 : c.b < 0); }   // highlighted by the current side?
function esc(s) { return String(s).replace(/[&<>"]/g, ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[ch])); }
function partnersOf(iso) { const c = C[iso]; return c ? (state.flow === "x" ? c.tx : c.tm) : []; }   // the top 10
function arrowPartners(iso) { return partnersOf(iso).slice(0, ARROWS); }                             // the top 3, drawn as arrows

// A country is picked -> only its top 3 partners (the ones with arrows) get a colour, by rank:
// #1 = step 2 (darkest), #2 = step 1, #3 = step 0. Recomputed in paint(); empty when nothing is picked.
let partnerStep = {};                     // e.g. {FRA: 2, DEU: 1, PRT: 0}
function partnerSteps(iso) {
  const out = {};
  arrowPartners(iso).forEach(([p], i) => { out[p] = 2 - i; });   // the list is sorted biggest first
  return out;
}
function flowHue() { return state.flow === "x" ? "exp" : "imp"; }   // green for buyers, purple for sellers
function fillFor(iso) {                   // the colour of a country on the map
  if (state.selected) {                   // a country is picked: no red/blue, only the picked country and its partners
    if (iso === state.selected) return "var(--sel-fill)";
    if (iso in partnerStep) return `var(--${flowHue()}-${partnerStep[iso]})`;
    return "var(--land-off)";
  }
  const c = C[iso];                       // nothing picked: red/blue by surplus or deficit
  if (!shown(c)) return "var(--land-off)";
  return `var(--${c.b >= 0 ? "pos" : "neg"}-${step(c.b)})`;
}
function swatch(bn) { return `<span class="sw" style="background:var(--${bn >= 0 ? "pos" : "neg"}-${step(bn)})"></span>`; }
function partnerSwatch(iso) { return iso in partnerStep ? `<span class="sw" style="background:var(--${flowHue()}-${partnerStep[iso]})"></span>` : ""; }

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
const WORLD_FC = { type: "FeatureCollection", features };
function geoPoint(iso) {                        // where arrows start/end: the capital, or the shape's centre
  const c = C[iso];
  if (c && c.ll) return c.ll;
  return featureByIso[iso] ? featureByIso[iso].anchor : null;
}

// =====================================================================
// 4. The SVG layers (order = drawing order: arrows come after the names, so they sit on top)
// =====================================================================
const viewMap = document.getElementById("view-map");
const svg = d3.select("#map");
const gWorld = svg.append("g");                 // shapes: moved/zoomed as one group
const gBack = gWorld.append("rect").attr("fill", "transparent");  // click on the sea = clear the selection
const gCountries = gWorld.append("g");
const gOverlay = svg.append("g");               // dots, names, arrows: redrawn in screen pixels so they stay crisp
const gDots = gOverlay.append("g");
const gLabels = gOverlay.append("g");
const gArrows = gOverlay.append("g").attr("class", "arrows");
const gBadges = gOverlay.append("g").attr("class", "arrows");   // the 1-2-3 badges sit above every line, so no line hides a number
const gHits = gOverlay.append("g");             // invisible bigger tap targets for tiny countries
let W = 0, H = 0, projection, path, box, home = d3.zoomIdentity, lastInsets = "", started = false;

// mouse: wheel + drag; finger: one finger moves, two fingers zoom (the map is the whole screen, so nothing else needs the finger)
const zoom = d3.zoom()
  .scaleExtent([1, 14])
  .on("zoom", e => { state.t = e.transform; gWorld.attr("transform", e.transform); scheduleOverlay(); });
svg.call(zoom).on("dblclick.zoom", null);
const dur = reduceMotion ? 0 : 400;
function zoomCentre() {                         // zoom buttons zoom around the picked country, or the middle of the free area
  const ll = state.selected && geoPoint(state.selected);
  if (ll) { const p = state.t.apply(projection(ll)); if (p[0] > box.x0 && p[0] < box.x1 && p[1] > box.y0 && p[1] < box.y1) return p; }
  return [(box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2];
}
document.getElementById("zin").onclick = () => svg.transition().duration(dur).call(zoom.scaleBy, 1.8, zoomCentre());
document.getElementById("zout").onclick = () => svg.transition().duration(dur).call(zoom.scaleBy, 1 / 1.8, zoomCentre());
document.getElementById("zreset").onclick = () => svg.transition().duration(dur).call(zoom.transform, home);
function fit(t) { return zoom.constrain()(t, [[0, 0], [W, H]], [[0, 0], [W, H]]); }   // never past the edge of the world

// =====================================================================
// 5. Build: fit the world into the screen area NOT covered by the floating boxes (rebuilt on resize / rotation / panel)
// =====================================================================
function insets() {                             // how much of each screen edge the floating boxes cover
  const phone = phoneQuery.matches;
  const v = viewMap.getBoundingClientRect();
  const top = document.querySelector(".top-left").getBoundingClientRect().bottom - v.top + 6;
  const panel = document.getElementById("panel");
  let bottom = phone ? document.getElementById("legend").offsetHeight + 16 : 12, right = 0;
  if (state.panelOpen && phone) bottom = panel.offsetHeight + 6;          // the bottom sheet
  if (state.panelOpen && !phone) right = panel.offsetWidth + 24;          // the corner panel
  return { top, bottom, right };
}
function build() {
  if (viewMap.hidden) return;                   // the "How to read it" page is showing: nothing to draw
  const phone = phoneQuery.matches;
  W = viewMap.clientWidth; H = viewMap.clientHeight;
  const ins = insets();
  lastInsets = JSON.stringify(ins) + W + "x" + H;
  box = { x0: 8, y0: ins.top, x1: W - 8 - ins.right, y1: H - ins.bottom };   // the free area where the world goes
  projection = d3.geoNaturalEarth1().fitExtent([[box.x0, box.y0], [box.x1, box.y1]], WORLD_FC);
  path = d3.geoPath(projection);
  features.forEach(f => { f.baseArea = path.area(f.main); });   // size on screen at zoom 1, decides which names fit
  byArea.sort((a, b) => b.baseArea - a.baseArea);               // biggest countries get their names first
  gBack.attr("width", W).attr("height", H);
  gCountries.selectAll("path").data(features, f => f.id + f.properties.name).join("path")
    .attr("class", "country").attr("d", path)
    .on("click", (e, f) => { if (f.iso) select(f.iso); })
    .on("mousemove", (e, f) => showTip(e, f.iso, f.properties.name))
    .on("mouseleave", hideTip);
  zoom.extent([[0, 0], [W, H]]).translateExtent([[0, 0], [W, H]]);
  // on a phone the world is much wider than tall: start zoomed in so it fills the free area (Europe/Africa in the middle)
  const [[, by0], [, by1]] = path.bounds(WORLD_FC);
  const k0 = phone ? Math.max(1, Math.min(1.6, (box.y1 - box.y0) / (by1 - by0))) : 1;
  const centre = projection([12, 20]);
  home = k0 > 1 ? fit(d3.zoomIdentity.translate((box.x0 + box.x1) / 2 - centre[0] * k0, (box.y0 + box.y1) / 2 - (by0 + by1) / 2 * k0).scale(k0))
                : d3.zoomIdentity;
  // first draw: start at home. Later rebuilds (panel opens/closes, rotation): keep the zoom the user already has
  svg.interrupt().call(zoom.transform, started ? fit(state.t) : home);
  started = true;
  paint();
}
gBack.on("click", () => select(null));

// =====================================================================
// 6. Paint: country colours, outlines and fading (side + selection)
// =====================================================================
function paint() {
  const sel = state.selected;
  partnerStep = sel ? partnerSteps(sel) : {};   // the colour step of each of the top 10 partners (fillFor reads it)
  const partners = new Set(arrowPartners(sel).map(p => p[0]));   // the top 3 (with arrows) also get a dark outline
  gCountries.selectAll("path")
    .style("fill", f => f.iso ? fillFor(f.iso) : "var(--land-off)")
    .classed("partner", f => partners.has(f.iso))
    .classed("sel", f => !!f.iso && f.iso === sel);
  gCountries.selectAll(".partner").raise();     // outlines on top of neighbours
  gCountries.selectAll(".sel").raise();
  document.querySelectorAll("[data-side]").forEach(b => b.setAttribute("aria-pressed", b.dataset.side === state.side));
  renderTotal(); renderLegend(); renderPanel();
  overlay();
}

// =====================================================================
// 7. Overlay: capital dots, names that never overlap, and the arrows on top of everything
// =====================================================================
let overlayQueued = false;
function scheduleOverlay() {                    // redraw at most once per animation frame while zooming
  if (overlayQueued) return;
  overlayQueued = true;
  requestAnimationFrame(() => { overlayQueued = false; overlay(); });
}
function toScreen(ll) { const p = projection(ll); return p ? state.t.apply(p) : null; }

function arrowGeometry(a, b, width, rank) {   // a curved line from seller a to buyer b (screen points), bending "north",
                                               // with the arrow head in the MIDDLE of the curve
  const dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy);
  const ux = dx / d, uy = dy / d;                        // unit vector seller -> buyer
  const [px, py] = ux >= 0 ? [uy, -ux] : [-uy, ux];      // the perpendicular that points up the screen
  const bend = Math.min(d * (0.12 + 0.08 * rank), 70 + 40 * rank);  // each rank its own curve, so lines to one region do not overlap
  const c = [(a[0] + b[0]) / 2 + px * bend, (a[1] + b[1]) / 2 + py * bend];   // control point of the curve
  // middle of a quadratic curve: 0.25*a + 0.5*c + 0.25*b; there the curve runs exactly parallel to a -> b
  const m = [0.25 * a[0] + 0.5 * c[0] + 0.25 * b[0], 0.25 * a[1] + 0.5 * c[1] + 0.25 * b[1]];
  const hl = Math.min(11 + width * 1.8, d * 0.35);       // head length (never longer than a third of a short line)
  const hw = hl * 0.62;                                  // half of the head's width
  const tip = [m[0] + ux * hl / 2, m[1] + uy * hl / 2];  // the head is centred on the middle point, pointing at the buyer
  const base = [m[0] - ux * hl / 2, m[1] - uy * hl / 2];
  const head = [tip, [base[0] - uy * hw, base[1] + ux * hw], [base[0] + uy * hw, base[1] - ux * hw]];
  return { d: `M${a[0]},${a[1]}Q${c[0]},${c[1]} ${b[0]},${b[1]}`, head: "M" + head.join("L") + "Z" };
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
    .style("opacity", d => key.has(d.iso) ? null : (sel ? 0.2 : shown(C[d.iso]) ? null : 0.3));

  // bigger invisible tap targets for countries too small to hit (or missing from the map)
  const hits = Object.keys(C).filter(iso => {
    const f = featureByIso[iso];
    return geoPoint(iso) && (!f || f.baseArea * k * k < 160);
  }).map(iso => ({ iso, p: toScreen(geoPoint(iso)) }));
  gHits.selectAll("circle").data(hits, d => d.iso).join("circle")
    .attr("class", "hit").attr("r", 11).attr("cx", d => d.p[0]).attr("cy", d => d.p[1])
    .on("click", (e, d) => select(d.iso))
    .on("mousemove", (e, d) => showTip(e, d.iso))
    .on("mouseleave", hideTip);

  // badges and lines first (the names below must avoid them).
  // Exports: goods go from the picked country to the buyer; imports: from the seller to the picked country.
  // The line always joins the picked country (a ring) to the partner (a numbered badge 1-2-3); the head in the
  // middle of the line says which way the goods travel.
  let arrows = [], badges = [], homes = [], leaders = [];
  const from = sel && geoPoint(sel);
  const badgeR = phone ? 10 : 11;                  // badge radius in pixels (big enough to read the number)
  const s = from ? toScreen(from) : null;          // the picked country's capital on screen
  if (from) {
    const maxV = list.length ? list[0][1] : 1;     // the #1 partner's value, for the line widths
    homes = [{ iso: sel, p: s }];                  // the ring on the picked country
    list.forEach(([iso, v], i) => {
      const ll = geoPoint(iso); if (!ll) return;
      const cap = toScreen(ll);                    // the partner's capital on screen
      badges.push({ iso, rank: i + 1, v, cap, p: cap.slice() });   // p = where the badge goes (starts on the capital)
    });
    // Neighbours (Spain -> France, Germany -> Netherlands) sit too close for a readable line, and their badges
    // pile up. Push each badge out to at least minSep from the picked country, then push badges off each other.
    const minSep = 2 * badgeR + 18;                // room for a short line with its head between ring and badge
    const gap = 2 * badgeR + 6;                    // two badges never closer than this (centre to centre)
    for (let round = 0; round < 12; round++) {     // a few rounds settle 3 badges
      badges.forEach(b => {
        let dx = b.p[0] - s[0], dy = b.p[1] - s[1], d = Math.hypot(dx, dy);
        if (d >= minSep) return;
        if (d < 0.5) { dx = 0; dy = -1; d = 1; }  // exactly on top of it: go straight up
        b.p = [s[0] + dx / d * minSep, s[1] + dy / d * minSep];
      });
      for (let i = 0; i < badges.length; i++) for (let j = i + 1; j < badges.length; j++) {
        const a = badges[i], b = badges[j];
        let dx = b.p[0] - a.p[0], dy = b.p[1] - a.p[1], d = Math.hypot(dx, dy);
        if (d >= gap) continue;
        if (d < 0.5) { dx = 1; dy = 0; d = 1; }
        const push = (gap - d) / 2;                // each badge moves half of the overlap, in opposite directions
        a.p = [a.p[0] - dx / d * push, a.p[1] - dy / d * push];
        b.p = [b.p[0] + dx / d * push, b.p[1] + dy / d * push];
      }
    }
    badges.forEach((b, i) => {
      const width = (phone ? 2.2 : 2.6) + (phone ? 3.4 : 4.6) * b.v / maxV;   // thicker = bigger flow
      const g = state.flow === "x" ? arrowGeometry(s, b.p, width, i) : arrowGeometry(b.p, s, width, i);
      arrows.push({ iso: b.iso, width, ...g });
      if (Math.hypot(b.p[0] - b.cap[0], b.p[1] - b.cap[1]) > badgeR) leaders.push(b);   // badge was moved: dotted line back to the capital
    });
    arrows.reverse(); badges.reverse();            // draw #1 last so it sits on top
  }

  // names: most important first; a name is skipped if it would overlap one already placed (or a badge)
  const fs = phone ? 10 : 10.5;
  const cands = [];
  key.forEach(iso => {                             // bold names of the picked country and its partners: tried above,
    const b = badges.find(d => d.iso === iso);     // below, right, then left of their ring/badge
    const ll = geoPoint(iso); if (!ll) return;
    const p = b ? b.p : toScreen(ll), r = b ? badgeR + 9 : 14;
    cands.push({ id: "k" + iso, text: C[iso].n, size: 12.5, cls: "key",
                 alts: [{ x: p[0], y: p[1] - r, anchor: "middle" }, { x: p[0], y: p[1] + r, anchor: "middle" },
                        { x: p[0] + r - 4, y: p[1], anchor: "start" }, { x: p[0] - r + 4, y: p[1], anchor: "end" }] });
  });
  const showCapitals = k >= (phone ? 2.5 : 2.2);  // capital names only once zoomed in
  byArea.forEach(f => {
    if (key.has(f.iso) || f.baseArea * k * k < 1000) return;   // a country name needs ~1000 square pixels of land
    const p = toScreen(f.anchor);
    const id = "n" + f.id + f.properties.name;
    cands.push({ id, text: f.label, x: p[0], y: p[1], size: fs, cls: sel ? "faint" : "", anchor: "middle" });
    const c = showCapitals && !f.alias && f.iso && C[f.iso];   // its capital comes right after it: never a capital without its country
    if (c && c.ll && c.c) {
      const q = toScreen(c.ll);
      cands.push({ id: "c" + f.iso, text: c.c, x: q[0] + 4, y: q[1], size: 9, cls: "cap" + (sel ? " faint" : ""), anchor: "start", needs: id });
    }
  });
  const boxes = badges.map(b => [b.p[0] - badgeR, b.p[1] - badgeR, b.p[0] + badgeR, b.p[1] + badgeR]);   // badges are taken
  if (s) boxes.push([s[0] - 7, s[1] - 7, s[0] + 7, s[1] + 7]);                                           // and the ring
  const placed = [], placedIds = new Set();
  cands.forEach(l => {
    if (l.needs && !placedIds.has(l.needs)) return;                     // its country name did not fit: skip the capital too
    const w = l.text.length * l.size * 0.56 + 4, h = l.size + 3;
    const spots = l.alts || [{ x: l.x, y: l.y, anchor: l.anchor }];      // where this name may go, best first
    for (const o of spots) {
      const x0 = o.anchor === "middle" ? o.x - w / 2 : o.anchor === "end" ? o.x - w : o.x, y0 = o.y - h / 2;
      const b = [x0, y0, x0 + w, y0 + h];
      if (b[0] < 0 || b[2] > W || b[1] < 0 || b[3] > H) continue;            // off screen
      if (boxes.some(q => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])) continue;  // overlaps
      boxes.push(b); placed.push({ ...l, ...o }); placedIds.add(l.id);
      break;
    }
  });
  gLabels.selectAll("text").data(placed, d => d.id).join("text")
    .attr("class", d => "lbl " + d.cls).attr("x", d => d.x).attr("y", d => d.y)
    .attr("text-anchor", d => d.anchor).attr("dominant-baseline", "central").text(d => d.text);

  const ak = state.drawKey;
  gArrows.selectAll("g.arrow").data(arrows, d => ak + d.iso).join(
      enter => { const g = enter.append("g").attr("class", "arrow");
                 g.append("path").attr("class", "arc-halo grow").attr("pathLength", 1);
                 g.append("path").attr("class", "arc grow").attr("pathLength", 1);
                 g.append("path").attr("class", "flowdash grow");
                 g.append("path").attr("class", "head grow");
                 return g; })
    .each(function (d) {
      const g = d3.select(this);
      g.select(".arc-halo").attr("d", d.d).attr("stroke-width", d.width + 5);
      g.select(".arc").attr("d", d.d).attr("stroke-width", d.width);
      g.select(".flowdash").attr("d", d.d).attr("stroke-width", Math.max(1.4, d.width * 0.4));
      g.select(".head").attr("d", d.head);
    });
  gBadges.selectAll("line.leader").data(leaders, d => d.iso).join("line")
    .attr("class", "leader")
    .attr("x1", d => d.cap[0]).attr("y1", d => d.cap[1]).attr("x2", d => d.p[0]).attr("y2", d => d.p[1]);
  gBadges.selectAll("circle.home").data(homes, d => d.iso).join("circle")
    .attr("class", "home").attr("r", phone ? 5 : 6).attr("cx", d => d.p[0]).attr("cy", d => d.p[1]);
  gBadges.selectAll("g.badge").data(badges, d => ak + d.iso).join(
      enter => { const g = enter.append("g").attr("class", "badge grow");
                 g.append("circle");
                 g.append("text").attr("text-anchor", "middle").attr("dominant-baseline", "central");
                 return g; })
    .raise()                                       // keep the draw order: #3, #2, then #1 on top of everything
    .attr("transform", d => `translate(${d.p[0]},${d.p[1]})`)
    .each(function (d) {
      const g = d3.select(this);
      g.select("circle").attr("r", badgeR);
      g.select("text").attr("y", 0.5).text(d.rank);
    });
}
const byArea = features.filter(f => f.label).slice();   // sorted biggest first in build()

// =====================================================================
// 8. Tooltip (mouse only; with a finger the panel shows the same and more)
// =====================================================================
const tip = document.getElementById("tip");
function showTip(e, iso, fallbackName) {
  if (touchQuery.matches) return;
  const c = C[iso], sel = state.selected;
  const deal = sel && iso !== sel && partnersOf(sel).find(p => p[0] === iso);   // [iso, $bn] if it is a top-10 partner of the picked country
  tip.innerHTML = c
    ? `<b>${esc(c.n)}</b><br>` +
      (deal ? `${partnerSwatch(iso)} ${state.flow === "x" ? "Buys" : "Sells"} ${money(deal[1])} ${state.flow === "x" ? "from" : "to"} ${esc(C[sel].n)}<br>`
            : `${sel ? "" : swatch(c.b) + " "}${money(c.b, true)} ${c.b >= 0 ? "surplus" : "deficit"}<br>`) +
      `<span class="muted">Exports ${money(c.x)} · Imports ${money(c.m)}${c.s === "m" ? "<br>Estimated from partners' data" : ""}</span>`
    : `<b>${esc(fallbackName || "")}</b><br><span class="muted">No data</span>`;
  const [x, y] = d3.pointer(e, viewMap);
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  tip.style.left = Math.min(x + 14, W - tw - 4) + "px";
  tip.style.top = (y + 14 + th > H ? y - th - 10 : y + 14) + "px";
  tip.style.opacity = 1;
}
function hideTip() { tip.style.opacity = 0; }

// =====================================================================
// 9. Total, legend, the top-10 panel, the all-countries table
// =====================================================================
const all = Object.entries(C).map(([iso, c]) => ({ iso, ...c }));
const surplus = all.filter(c => c.b > 0).sort((a, b) => b.b - a.b);
const deficit = all.filter(c => c.b < 0).sort((a, b) => a.b - b.b);
const sum = list => list.reduce((s, c) => s + c.b, 0);

function renderTotal() {                       // the total of the side being shown
  const list = state.side === "surplus" ? surplus : deficit;
  document.getElementById("total").innerHTML =
    `<span>Total ${state.side} · ${list.length} countries</span><b>${money(sum(list), true)}</b>`;
}

function renderLegend() {                      // 5 red + 5 blue steps; the side not shown is faded
  const sel = state.selected;
  if (sel) {                                    // a country is picked: explain the partner colours instead
    const hue = flowHue(), name = esc(C[sel].n);
    document.getElementById("legend").innerHTML =
      `<div class="ends"><span>${state.flow === "x" ? `Top 3 buyers of ${name}'s goods` : `Top 3 sellers to ${name}`}</span></div>` +
      `<div class="lkey"><span class="item"><span class="sw" style="background:var(--sel-fill)"></span>${name}</span>` +
      [2, 1, 0].map((s, i) => `<span class="item"><span class="sw" style="background:var(--${hue}-${s})"></span>#${i + 1}</span>`).join("") +
      `</div>`;
    return;
  }
  const negOn = state.side === "deficit", posOn = state.side === "surplus";
  const sw = [4, 3, 2, 1, 0].map(i => `<span class="${negOn ? "" : "dim"}" style="background:var(--neg-${i})"></span>`).join("") +
             [0, 1, 2, 3, 4].map(i => `<span class="${posOn ? "" : "dim"}" style="background:var(--pos-${i})"></span>`).join("");
  const ticks = ["200", "50", "10", "1", "0", "1", "10", "50", "200"]
    .map((t, i) => `<span style="left:${(i + 1) * 10}%">${t}</span>`).join("");
  document.getElementById("legend").innerHTML =
    `<div class="ends"><span>&larr; Deficit</span><span>$ billions</span><span>Surplus &rarr;</span></div>` +
    `<div class="ramp">${sw}</div><div class="ticks">${ticks}</div>`;
}

function renderPanel() {                       // the corner panel (a bottom sheet on a phone)
  const el = document.getElementById("panel");
  if (!state.panelOpen) return;
  const sel = state.selected, c = sel && C[sel];
  const closeBtn = `<button type="button" class="close" id="close" aria-label="Close">&times;</button>`;
  if (!c) {                                     // nothing picked: the 10 largest of the side being shown
    const list = (state.side === "surplus" ? surplus : deficit).slice(0, 10);
    el.innerHTML = `<div class="p-head"><h2>Largest ${state.side === "surplus" ? "surpluses" : "deficits"}</h2>${closeBtn}</div>` +
      `<p>Pick a country on the map to see its top partners.</p>` +
      `<div class="tbl"><table><thead><tr><th class="rk">#</th><th class="name">Country</th><th>Balance</th></tr></thead><tbody>` +
      list.map((d, i) => `<tr><td class="rk">${i + 1}</td><td class="name"><button type="button" class="rowbtn" data-iso="${d.iso}">${esc(d.n)}</button></td>` +
                         `<td>${swatch(d.b)} ${money(d.b, true)}</td></tr>`).join("") + `</tbody></table></div>`;
  } else {
    const list = partnersOf(sel), total = state.flow === "x" ? c.x : c.m;
    const other = state.flow === "x" ? "imports" : "exports";
    el.innerHTML =
      `<div class="p-head"><h2>${esc(c.n)}</h2>${closeBtn}</div>` +
      (c.c ? `<p>Capital: ${esc(c.c)}</p>` : "") +
      `<div class="bal"><span class="big">${money(c.b, true)}</span><span class="tag">${swatch(c.b)}${c.b >= 0 ? "Surplus" : "Deficit"}</span></div>` +
      `<div class="xm"><div><span>Exports</span>${money(c.x)}</div><div><span>Imports</span>${money(c.m)}</div></div>` +
      (c.s === "m" ? `<p class="est">Estimated from partners' data: it did not report its own __YEAR__ figures.</p>` : "") +
      `<div class="seg small" role="group" aria-label="Partners to show">` +
      `<button type="button" data-side="surplus" aria-pressed="${state.flow === "x"}">Exports to</button>` +
      `<button type="button" data-side="deficit" aria-pressed="${state.flow === "m"}">Imports from</button></div>` +
      `<p class="again">${state.flow === state.firstFlow ? `Click ${esc(c.n)} again to see its ${other}.` : `Click ${esc(c.n)} again to go back to the world map.`}</p>` +
      `<h3>Top 10 ${state.flow === "x" ? "buyers of its goods" : "sellers to it"}</h3>` +
      `<div class="tbl"><table><thead><tr><th class="rk">#</th><th class="name">${state.flow === "x" ? "Buyer" : "Seller"}</th><th>US$</th><th>Share</th></tr></thead><tbody>` +
      list.map(([iso, v], i) => `<tr class="${i < ARROWS ? "on" : ""}"><td class="rk">${i < ARROWS ? `<span class="num">${i + 1}</span>` : i + 1}</td>` +
        `<td class="name"><button type="button" class="rowbtn" data-iso="${iso}">${esc(C[iso] ? C[iso].n : iso)}</button></td>` +
        `<td>${partnerSwatch(iso)} ${money(v)}</td><td><small>${total > 0 ? (100 * v / total).toFixed(0) + "%" : ""}</small></td></tr>`).join("") +
      `</tbody></table></div>`;
  }
  document.getElementById("close").onclick = () => { select(null); setPanel(false); };   // close = clear the pick too
  el.querySelectorAll("[data-side]").forEach(b => b.onclick = () => setSide(b.dataset.side));
  el.querySelectorAll(".rowbtn").forEach(b => b.onclick = () => select(b.dataset.iso));
}

function renderTable() {                       // "How to read it": every country, biggest surplus first, biggest deficit last
  const rows = all.slice().sort((a, b) => b.b - a.b);
  document.getElementById("table").innerHTML =
    `<thead><tr><th>Country</th><th>Balance</th><th>Exports</th><th>Imports</th><th class="col-src">Data</th></tr></thead><tbody>` +
    rows.map(c => `<tr><td>${esc(c.n)}</td><td>${swatch(c.b)} ${money(c.b, true)}</td><td>${money(c.x)}</td><td>${money(c.m)}</td>` +
                  `<td class="col-src">${c.s === "m" ? "estimated" : "reported"}</td></tr>`).join("") + `</tbody>`;
}

// =====================================================================
// 10. Interaction: side buttons, country picker, selection, panel, "How to read it"
// =====================================================================
function setSide(side) {                        // Surpluses <-> Deficits (with a country picked: its exports <-> imports)
  state.side = side;
  if (state.selected) { state.flow = FLOW_OF[side]; state.drawKey = state.selected + state.flow; }
  paint();                                      // redraw only; the view stays where the user left it
}
document.querySelectorAll(".controls [data-side]").forEach(b => b.onclick = () => setSide(b.dataset.side));

const pick = document.getElementById("pick");
pick.innerHTML = `<option value="">Pick a country…</option>` +
  all.slice().sort((a, b) => a.n.localeCompare(b.n)).map(c => `<option value="${c.iso}">${esc(c.n)}</option>`).join("");
pick.onchange = () => select(pick.value || null);

function select(iso) {
  if (iso && iso === state.selected) {          // the same country again:
    if (state.flow === state.firstFlow) {       //   2nd click: switch to its other side
      setSide(state.side === "surplus" ? "deficit" : "surplus");
      return;
    }
    iso = null;                                 //   3rd click: back to the world map in red/blue
  }
  state.selected = iso && C[iso] ? iso : null;
  if (state.selected) {                         // first click: its BIGGER side (surplus -> exports, deficit -> imports)
    state.side = C[state.selected].b >= 0 ? "surplus" : "deficit";
    state.flow = FLOW_OF[state.side];
    state.firstFlow = state.flow;               // remember the 1st click's side, to know when the 3rd click comes
  }
  state.drawKey = (state.selected || "") + state.flow;   // new key = arrows animate in again
  pick.value = state.selected || "";
  history.replaceState(null, "", state.selected ? "#" + state.selected : location.pathname + location.search);
  hideTip();
  if (state.selected && !state.panelOpen) { setPanel(true); return; }   // opening the panel rebuilds the map (and shows the arrows)
  paint();                                      // arrows redraw; the zoom and position are left exactly as they are
}

function setPanel(open) {                       // open/close the top-10 panel; the map makes room for it
  state.panelOpen = open;
  document.getElementById("panel").hidden = !open;
  document.getElementById("toggle-panel").setAttribute("aria-expanded", open);
  viewMap.classList.toggle("sheet-open", open);
  renderPanel();
  build();
}
document.getElementById("toggle-panel").onclick = () => setPanel(!state.panelOpen);

// "How to read it": a separate view on the same page
function showNotes(open) {
  viewMap.hidden = open;
  document.getElementById("view-notes").hidden = !open;
  if (open) { renderTable(); window.scrollTo(0, 0); document.getElementById("back-map").focus(); }
  else build();
}
document.getElementById("open-notes").onclick = () => showNotes(true);
document.getElementById("back-map").onclick = () => showNotes(false);
document.addEventListener("keydown", e => {     // Esc: back to the map, or clear the picked country
  if (e.key !== "Escape") return;
  if (viewMap.hidden) showNotes(false); else if (state.selected) select(null);
});

// =====================================================================
// 11. Start, and rebuild when the screen size changes (window resize, phone rotation)
// =====================================================================
new ResizeObserver(() => requestAnimationFrame(() => {
  if (viewMap.hidden) return;
  const now = JSON.stringify(insets()) + viewMap.clientWidth + "x" + viewMap.clientHeight;
  if (now !== lastInsets) build();
})).observe(viewMap);
phoneQuery.addEventListener("change", build);
build();
const fromHash = location.hash.slice(1).toUpperCase();   // a link like trade_balance.html#DEU opens Germany
if (C[fromHash]) select(fromHash);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
