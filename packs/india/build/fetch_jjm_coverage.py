"""
Fetch Jal Jeevan Mission tap-water coverage from the public JJM dashboard API
and emit rows for admin_units.csv and indicators.csv.

Source:  https://ejalshakti.gov.in/jjmreport/   (Ministry of Jal Shakti, DDWS)

Two public JSON endpoints, no authentication:

    JJMDistrictView.aspx/BindDistrictMap   -> all 754 districts in India
    JJMBlockMapView.aspx/BindBlockMap      -> blocks within one district

The block endpoint keys off DtCode11, which is never returned by any endpoint.
It is derived:

    DtCode11 = KeyValue * 10 + 1111

where KeyValue is the district's code in the district list. Verified against
Ballari(565), Chitradurga(566), Davangere(567), Shivamogga(568),
Uttara Kannada(563) and Kolar(581).

Per block the API returns the three numbers Sangam needs:

    Total            total rural households
    HCPWS_01042019   households with a tap connection at mission launch
    Value            households with a tap connection today

Delivery rate is NOT stored -- it is derived at analysis time as
(now - 2019) / (total - 2019), so the stored data stays purely as published.

Usage:
    python fetch_jjm_coverage.py --kv-from 555 --kv-to 584
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://ejalshakti.gov.in/jjmreport"
DISTRICT_URL = BASE + "/JJMDistrictView.aspx/BindDistrictMap"
BLOCK_URL = BASE + "/JJMBlockMapView.aspx/BindBlockMap"

SOURCE_NAME = "Jal Jeevan Mission (DDWS, Ministry of Jal Shakti)"
SOURCE_URL = BASE + "/JJMBlockMapView.aspx"

HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE + "/JJMBlockMapView.aspx",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/151.0.0.0",
}

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
RAW = PACK / "raw"

UNIT_COLS = [
    "unit_id", "country_code", "level", "name", "name_variants",
    "parent_unit_id", "external_code", "population", "source_name", "source_url",
]
IND_COLS = [
    "unit_id", "indicator_key", "value", "unit", "period",
    "source_name", "source_url",
]


def post(url, payload, retries=3):
    """POST JSON and return the ASP.NET 'd' payload. None on failure."""
    body = json.dumps(payload).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, body, HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8")).get("d")
        except Exception as exc:
            if attempt == retries - 1:
                print("    ! " + str(exc), file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def slug(name):
    return re.sub(r"[^A-Z0-9]+", "-", name.strip().upper()).strip("-")


# A handful of districts sit in a second, older code space and do not follow
# the formula. Found by sweeping the "<n>%3A1" form and reading the district
# name back out of the response. Note Kalaburagi still reports as GULBARGA.
DTCODE11_OVERRIDES = {
    559: "66%3A1",   # Raichur
    569: "67%3A1",   # Udupi
    579: "68%3A1",   # Kalaburagi / Gulbarga
}


def dtcode11(key_value):
    """The block endpoint's district key. See module docstring."""
    if key_value in DTCODE11_OVERRIDES:
        return DTCODE11_OVERRIDES[key_value]
    return str(key_value * 10 + 1111)


def fetch_districts(cache):
    if cache.exists():
        print("districts: using cached " + cache.name)
        return json.loads(cache.read_text(encoding="utf-8"))
    print("districts: fetching all-India list ...")
    data = post(DISTRICT_URL, {
        "StCode11": "11", "Cat": "11", "SubCat": "11", "Param": "21",
    })
    if not data:
        sys.exit("could not fetch the district list")
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("districts: %d fetched, cached to %s" % (len(data), cache.name))
    return data


def fetch_blocks(key_value, delay):
    time.sleep(delay)
    return post(BLOCK_URL, {
        "Cat": "11", "SubCat": "11", "Param": "11",
        "StCode11": "3%3A1", "DtCode11": dtcode11(key_value),
    }) or []


def add_indicators(out, unit_id, total, conn_2019, conn_now, pct_now, pct_2019):
    def row(key, value, unit, period):
        if value in (None, ""):
            return
        out.append({
            "unit_id": unit_id, "indicator_key": key, "value": value,
            "unit": unit, "period": period,
            "source_name": SOURCE_NAME, "source_url": SOURCE_URL,
        })

    row("demography.rural_households", total, "households", "2026")
    row("water.households_connected", conn_now, "households", "2026")
    row("water.households_connected_2019", conn_2019, "households", "2019")
    row("water.piped_household_pct", pct_now, "percent", "2026")
    row("water.piped_household_pct_2019", pct_2019, "percent", "2019")


def write_csv(path, rows, cols):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-name", default="Karnataka")
    ap.add_argument("--state-slug", default="KA")
    ap.add_argument("--kv-from", type=int, required=True)
    ap.add_argument("--kv-to", type=int, required=True)
    ap.add_argument("--st-code", default="29",
                    help="expected StCode; districts reporting anything else are skipped")
    ap.add_argument("--delay", type=float, default=0.25)
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    districts = fetch_districts(RAW / "jjm_districts_india.json")
    by_kv = {int(d["KeyValue"]): d for d in districts}

    st = args.state_slug
    units = [{
        "unit_id": "IN-" + st, "country_code": "IN", "level": 1,
        "name": args.state_name, "name_variants": "", "parent_unit_id": "IN",
        "external_code": args.st_code, "population": "",
        "source_name": SOURCE_NAME, "source_url": SOURCE_URL,
    }]
    indicators = []
    raw_blocks = []
    skipped = []

    for kv in range(args.kv_from, args.kv_to + 1):
        meta = by_kv.get(kv)
        if not meta:
            continue
        dname = meta["Name"].strip()
        blocks = fetch_blocks(kv, args.delay)

        if not blocks:
            skipped.append("%s (kv=%d): no blocks returned" % (dname, kv))
            continue
        if blocks[0].get("StCode") != args.st_code:
            skipped.append("%s (kv=%d): StCode=%s, expected %s"
                           % (dname, kv, blocks[0].get("StCode"), args.st_code))
            continue

        district_id = "IN-%s-%s" % (st, slug(dname))
        units.append({
            "unit_id": district_id, "country_code": "IN", "level": 2,
            "name": dname, "name_variants": "", "parent_unit_id": "IN-" + st,
            "external_code": meta["KeyValue"], "population": "",
            "source_name": SOURCE_NAME, "source_url": SOURCE_URL,
        })
        add_indicators(indicators, district_id, meta.get("Total"), None,
                       meta.get("Value"), meta.get("Per"), None)

        for block in blocks:
            bname = block["Name"].strip().title()
            block_id = "%s-%s" % (district_id, slug(bname))
            units.append({
                "unit_id": block_id, "country_code": "IN", "level": 3,
                "name": bname, "name_variants": "", "parent_unit_id": district_id,
                "external_code": block.get("KeyValue", ""), "population": "",
                "source_name": SOURCE_NAME, "source_url": SOURCE_URL,
            })
            add_indicators(indicators, block_id, block["Total"],
                           block["HCPWS_01042019"], block["Value"],
                           block["Per"], block["Per_BeforeLaunchof_mission"])
            raw_blocks.append(block)

        print("  %-24s %2d blocks" % (dname, len(blocks)))

    (RAW / ("jjm_blocks_" + st.lower() + ".json")).write_text(
        json.dumps(raw_blocks, ensure_ascii=False, indent=1), encoding="utf-8")

    write_csv(PACK / "admin_units.csv", units, UNIT_COLS)
    write_csv(PACK / "indicators.csv", indicators, IND_COLS)

    n_dist = sum(1 for u in units if u["level"] == 2)
    n_block = sum(1 for u in units if u["level"] == 3)
    print("\nadmin_units.csv  %5d rows  (%d districts, %d blocks)"
          % (len(units), n_dist, n_block))
    print("indicators.csv   %5d rows" % len(indicators))
    if skipped:
        print("\nskipped:")
        for line in skipped:
            print("  - " + line)


if __name__ == "__main__":
    main()
