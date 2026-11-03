"""Ferro PP: sync "ALL LONDON" (the original capture tab, read only, never
written) into "ALL LONDON (clean)" (the working tab).

ALL LONDON grows as new places are captured there; this module finds the
rows "ALL LONDON (clean)" does not have yet, maps each one onto the clean
layout, and flags likely duplicates. It never writes to the sheet; the
caller decides what to do with the mapped rows.

The column mapping below is read, not designed: it comes from comparing
real aligned row pairs between the two tabs (see map_row's docstring for
which fields are a direct, reliable copy and which are not).
"""
import csv
import re
from datetime import date
from pathlib import Path

ORIG_TAB = "ALL LONDON"
CLEAN_TAB = "ALL LONDON (clean)"

# The clean tab's row 1, cell A1, holds a stray note instead of its real
# header "Location Name" (someone typed a comment directly into the
# header cell). The data beneath is untouched; this module corrects the
# key when reading so every lookup by "Location Name" still works. Fix
# the cell itself by hand before any future write to this tab.
CORRUPTED_LOCATION_NAME_HEADER = (
    "4774 rows, and it says that all boroughs have been written to the sheet, but if you "
    "look at the all London original sheet which Brandon completed using Grogbot, there are "
    "nearly 5000. "
)

# "ALL LONDON"'s own column headers, by clean-tab field name, for every
# field a direct copy reproduces reliably (checked against all 4773
# aligned row pairs; see sync_mapping_notes below for the fidelity of
# each one). Google Sheets' header for the name column is, confusingly,
# just "sheet".
DIRECT_FIELD_MAP = {
    "Location Name": "sheet",
    "Type (as captured)": "Type (Public/Private/Retail/Hotel/etc.)",
    "Borough": "Borough",
    "Charges (as published)": "Charges / Fees",
    "Max Stay (as captured)": "Max Stay",
    "Hours (as captured)": "Hours / Days Allowed",
    "Enforcement Details": "Enforcement / Penalties",
    "Source URLs (primary first)": "Source URL",
    "Notes": "Notes / Special Conditions",
    "Date Captured": "Date Captured",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
    "Geo (as captured)": "Geo Source / Precision",
    # ALL LONDON's "Verified By" is who captured the row, not a second
    # reviewer; it becomes "Captured By" in the clean tab, which has its
    # own separate "Verified By" for the second-pass reviewer.
    "Captured By": "Verified By",
}

# Fields that LOOK like a direct copy (the two tabs happen to share
# similar column names, e.g. ALL LONDON has its own "Can Park?" and
# "Location Status") but were edited by hand often enough in the aligned
# rows (Rules Summary 58%, Notes 59% before trimming, Location Status's
# free text in particular) that copying them mechanically would carry
# that judgment call's shape without the judgment itself. These stay
# blank for a new row, same as every other research column (Cost Type,
# Tariff Type, Operator, Evidence Type, Brand, Place Category, Area Type,
# Geo Source, Geo Precision, and so on): a new row gets them from running
# the research pipeline on it, not from ALL LONDON's own rough pass.
RESEARCH_ONLY_FIELDS = (
    "Brand", "Place Category", "Area Type", "Can Park? (Yes/No/Conditional)",
    "Who Can Park", "Rules Summary", "Cost Type", "Price Status", "Tariff Type",
    "Tariff Detail", "Max Stay (mins)", "Hours (OpenStreetMap opening_hours format)",
    "Hours Basis", "Parking Control Type (Cameras / Barrier / Patrol)", "Operator",
    "PCN (Penalty Charge Notice) amount (£)", "Evidence Type",
    "Evidence Detail (what the source shows)", "Source Tier", "Specificity",
    "Rules Stated", "Prices Stated", "Evidence Age", "Agreeing Sources", "Conflict",
    "Verified By", "Verified Date", "Verification Result", "Change Made (Yes/No)",
    "Geo Source", "Geo Precision", "Review Flag", "Flag Status", "Decision Reason",
)

# Columns that hold a Sheets formula in the existing rows, so a new row
# needs the formula filled down, not a value written: Postcode Area reads
# the Postcode column, Confidence (1-5) reads several Evidence/Rules
# columns, and Total incl. Ferro Fee (£) reads Parking Charge (£).
FORMULA_COLUMNS = ("Postcode Area", "Confidence (1-5)", "Total incl. Ferro Fee (£)")

# Brandon's own four columns. Three (Free Stay Countdown, Ferro Autopay,
# Parking Charge) are plain hand-entered values in the existing rows, not
# formulas; Total incl. Ferro Fee (£) is the one formula among them (see
# FORMULA_COLUMNS). All four stay empty for a new row either way.
BRANDON_COLUMNS = ("Free Stay Countdown (mins)", "Ferro Autopay",
                    "Parking Charge (£)", "Total incl. Ferro Fee (£)")

FULL_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b", re.I)
OUTWARD_ONLY_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z]?)\s*$", re.I)


def split_address(address):
    """Split ALL LONDON's combined "Address / Postcode" into (street,
    postcode), the way the clean tab's Street Address and Postcode were
    built. Checked against all 4773 aligned rows: exact on postcode 99.4%
    of the time, on street address 95.2%; the rest are source rows with
    an ambiguous or annotated postcode (two postcode districts, a
    parenthetical note) that a person already had to read individually."""
    address = (address or "").strip()
    match = FULL_POSTCODE_RE.search(address)
    if match:
        postcode = re.sub(r"\s+", " ", match.group(1).upper())
        street = address[:match.start()] + " " + address[match.end():]
        street = re.sub(r"\s*\([^)]*\)\s*", " ", street)
        street = re.sub(r"\s+", " ", street).strip().rstrip(", ").strip()
        return street, postcode
    match = OUTWARD_ONLY_RE.search(address)
    if match:
        return address[:match.start()].rstrip(", ").strip(), match.group(1).upper()
    return address, ""


# ALL LONDON's free-text Location Status does not reduce to a pure
# function of the text: the aligned rows show the same kind of phrase
# ("UNCLEAR ...", "Open (...)") landing on different clean values
# depending on what a reviewer actually knew. This covers only the
# handful of values every row in the "new" range for this sync actually
# has (all 667 are plain "Open"); anything else is a judgment call this
# function declines to make and reports as "Unknown" instead of guessing.
LOCATION_STATUS_MAP = {
    "open": "Open",
    "closed": "Closed",
    "temporarily closed": "Temporarily closed",
    "active": "Open",
}


def map_location_status(value):
    return LOCATION_STATUS_MAP.get((value or "").strip().lower(), "Unknown")


def map_row(orig_row):
    """Map one ALL LONDON row onto the clean tab's field names. Returns a
    dict of only the fields this module can fill reliably; every other
    clean column (RESEARCH_ONLY_FIELDS, the formula and Brandon columns)
    is left out, for the caller to leave blank or fill down as a formula."""
    mapped = {clean_field: orig_row.get(orig_field, "")
              for clean_field, orig_field in DIRECT_FIELD_MAP.items()}
    street, postcode = split_address(orig_row.get("Address / Postcode", ""))
    mapped["Street Address"] = street
    mapped["Postcode"] = postcode
    mapped["Location Status"] = map_location_status(
        orig_row.get("Location Status (Open / Closed)", ""))
    return mapped


def normalize_name(name):
    """Lowercase, trailing-parenthetical-stripped form of a location name,
    for duplicate matching. The trailing parenthetical is often a
    disambiguating note ("(Ealing Council, ref A02)") that does not
    appear on both sides of a true duplicate pair."""
    name = (name or "").strip().lower()
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def normalize_postcode(postcode):
    return re.sub(r"\s+", "", (postcode or "").strip().upper())


EARTH_RADIUS_M = 6371000


def haversine_m(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * atan2(sqrt(a), sqrt(1 - a))


def find_duplicates(new_rows, clean_rows, radius_m=100):
    """For each new ALL LONDON row, look for a likely duplicate already
    in the clean tab: the same normalized name and postcode, or the same
    Brand within radius_m metres. Returns a list of
    (new_row, clean_row, reason) triples; callers flag these, they never
    get appended automatically."""
    by_name_postcode = {}
    by_brand = {}
    for row in clean_rows:
        key = (normalize_name(row.get("Location Name", "")),
               normalize_postcode(row.get("Postcode", "")))
        if key[1]:
            by_name_postcode.setdefault(key, []).append(row)
        brand = (row.get("Brand", "") or "").strip().lower()
        if brand:
            by_brand.setdefault(brand, []).append(row)

    duplicates = []
    for new_row in new_rows:
        name = normalize_name(new_row.get("sheet", ""))
        _, postcode = split_address(new_row.get("Address / Postcode", ""))
        key = (name, normalize_postcode(postcode))
        matched_ids = set()
        if key[1]:
            for clean_row in by_name_postcode.get(key, []):
                duplicates.append((new_row, clean_row, "same name and postcode"))
                matched_ids.add(id(clean_row))

        type_text = (new_row.get("Type (Public/Private/Retail/Hotel/etc.)", "") or "")
        brand_match = re.search(r"\(([^()]+)\)\s*$", type_text)
        brand = (brand_match.group(1) if brand_match else type_text).strip().lower()
        try:
            new_lat = float(new_row.get("Latitude", ""))
            new_lon = float(new_row.get("Longitude", ""))
        except (TypeError, ValueError):
            continue
        for clean_row in by_brand.get(brand, []):
            if id(clean_row) in matched_ids:
                continue
            try:
                lat = float(clean_row.get("Latitude", ""))
                lon = float(clean_row.get("Longitude", ""))
            except (TypeError, ValueError):
                continue
            distance = haversine_m(new_lat, new_lon, lat, lon)
            if distance <= radius_m:
                duplicates.append((new_row, clean_row,
                                    f"same brand within {distance:.0f} m"))
    return duplicates


def _load_tabs(service):
    from . import sheets
    clean_headers, clean_rows = sheets.read_tab(service, tab=CLEAN_TAB)
    orig_headers, orig_rows = sheets.read_tab(service, tab=ORIG_TAB)
    if clean_headers and clean_headers[0] == CORRUPTED_LOCATION_NAME_HEADER:
        for row in clean_rows:
            row["Location Name"] = row.pop(clean_headers[0])
        clean_headers[0] = "Location Name"
    return clean_headers, clean_rows, orig_headers, orig_rows


def check_alignment(clean_rows, orig_rows):
    """Compare Location Name (clean) against "sheet" (original) for every
    row the two tabs should share. Returns (aligned_count, mismatches),
    where a mismatch is (clean_row, orig_row) whose names differ even
    after dropping a trailing parenthetical."""
    n = min(len(clean_rows), len(orig_rows))
    mismatches = []
    for i in range(n):
        c, o = clean_rows[i], orig_rows[i]
        if normalize_name(c.get("Location Name", "")) != normalize_name(o.get("sheet", "")):
            mismatches.append((c, o))
    return n - len(mismatches), mismatches


def main(argv=None):
    import argparse
    from . import sheets

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    service = sheets.get_service()
    clean_headers, clean_rows, orig_headers, orig_rows = _load_tabs(service)

    print(f"{CLEAN_TAB}: {len(clean_rows)} rows, {len(clean_headers)} columns")
    print(f"{ORIG_TAB}: {len(orig_rows)} rows, {len(orig_headers)} columns")

    aligned_count, mismatches = check_alignment(clean_rows, orig_rows)
    print(f"aligned rows checked: {aligned_count + len(mismatches)}, "
          f"name mismatches: {len(mismatches)}")
    for c, o in mismatches:
        print(f"  mismatch: clean row {c['_sheet_row']} {c.get('Location Name','')!r} "
              f"vs {ORIG_TAB} row {o['_sheet_row']} {o.get('sheet','')!r}")
    if len(mismatches) > 5:
        print("More than a handful of mismatches. Stopping before the append plan.")
        return 1

    new_rows = orig_rows[len(clean_rows):]
    print(f"new rows in {ORIG_TAB}: {len(new_rows)}")

    duplicates = find_duplicates(new_rows, clean_rows)
    dup_ids = {id(nr) for nr, _, _ in duplicates}
    print(f"likely duplicates flagged: {len(duplicates)}")

    max_num = 0
    for row in clean_rows:
        m = re.match(r"PP-(\d+)$", row.get("Place ID", "").strip())
        if m:
            max_num = max(max_num, int(m.group(1)))

    clean_columns = ["Location Name" if i == 0 else h for i, h in enumerate(clean_headers)]
    clean_columns.remove("Place ID")
    fieldnames = ["Place ID"] + clean_columns

    append_rows, duplicate_rows = [], []
    next_num = max_num + 1
    for nr in new_rows:
        if id(nr) in dup_ids:
            continue
        mapped = map_row(nr)
        mapped["Place ID"] = f"PP-{next_num:06d}"
        next_num += 1
        append_rows.append(mapped)
    for nr, cr, reason in duplicates:
        duplicate_rows.append({
            "ALL LONDON row": nr["_sheet_row"], "ALL LONDON name": nr.get("sheet", ""),
            "Clean row": cr.get("_sheet_row", ""), "Clean Place ID": cr.get("Place ID", ""),
            "Clean name": cr.get("Location Name", ""), "Reason": reason,
        })

    out_dir = Path(args.out) if args.out else Path("data/runs") / date.today().isoformat() / "sync"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "append_plan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in append_rows:
            w.writerow({c: row.get(c, "") for c in fieldnames})
    with open(out_dir / "duplicates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ALL LONDON row", "ALL LONDON name", "Clean row",
                                           "Clean Place ID", "Clean name", "Reason"])
        w.writeheader()
        w.writerows(duplicate_rows)

    print(f"append plan: {len(append_rows)} rows, Place ID {append_rows[0]['Place ID']} to "
          f"{append_rows[-1]['Place ID']}" if append_rows else "append plan: 0 rows")
    print(f"wrote {out_dir}/append_plan.csv and {out_dir}/duplicates.csv")
    print("No writes were made to the sheet.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
