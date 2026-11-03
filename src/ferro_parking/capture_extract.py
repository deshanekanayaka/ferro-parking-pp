"""Ferro PP: capture extract. Turns a row's captured text into a structured
record of the same shape capture_fill.py expects in extracted.jsonl, by
pattern matching rather than a model read of each row.

This covers the patterns found by reading Westminster's captured text:
operator car parks with real banded tariffs, operator car parks with an
unclear tariff but real hours, explicit "no parking" denials under rule R9,
customer car parks that may be chain-wide policy, and the large remainder
left for Grok. A record this module cannot support with real site text is
always left_for_grok, never guessed.
"""
import json
import re
from pathlib import Path

from . import capture_fill

NOT_APPLICABLE = {
    "who_can_park": "Not applicable", "cost_type": "Not applicable",
    "tariff_type": "Not applicable", "tariff_detail": "Not applicable",
    "max_stay_mins": "Not applicable", "hours_osm_format": "Not applicable",
    "hours_basis": "Not applicable", "control_type": "Not applicable",
    "operator": "Not applicable", "pcn_gbp": "Not applicable",
}

WEEKEND_MARKERS = ("weekend", "saturday", "sat ", "evening", "night", "bank holiday", "motorcycle")

CUSTOMER_CAR_PARK_RE = re.compile(r"customer car park", re.I)
MAYBE_GENERIC_RE = re.compile(r"may be generic|VERIFY.{0,40}generic", re.I)


def record(place_id, fields=None, leave_for_grok=False, reason=""):
    return {"place_id": place_id, "leave_for_grok": leave_for_grok, "reason": reason,
            "fields": fields or {}}


def field(value, scope, quote):
    return {"value": value, "scope": scope, "quote": quote}


def no_parking_record(place_id, quote):
    fields = {"can_park": field("No", "site", quote)}
    for name, value in NOT_APPLICABLE.items():
        fields[name] = field(value, "site", quote)
    return record(place_id, fields)


def matches_r9(text):
    low = (text or "").lower()
    return any(re.search(r"\b" + re.escape(p) + r"\b", low) for p in capture_fill.NO_PARKING_PHRASES)


def find_r9_quote(captured):
    for col in capture_fill.CAPTURE_COLS:
        text = captured.get(col, "")
        if matches_r9(text):
            return text
    return None


def parse_bands(charges_text):
    """"1 hour £10.00", "Up to 1 hour £4.50", or the abbreviated "1h £5.15"
    all count, each giving one (hours, price) band. Only the weekday rate:
    cut the string at the first weekend/night/motorcycle marker, wherever
    it falls, since a semicolon does not always separate the two (some
    charges strings run weekday and weekend rates together in one sentence).

    A per-minute tariff ("£0.10 per 15 minutes", the Royal Parks pattern)
    has no "<N>h ... £<price>" shape, so it returns no bands here and stays
    left for Grok rather than being misread as hourly."""
    cutoff = len(charges_text)
    low = charges_text.lower()
    for marker in WEEKEND_MARKERS:
        idx = low.find(marker)
        if idx != -1:
            cutoff = min(cutoff, idx)
    weekday_text = charges_text[:cutoff]
    return [(int(h), float(p)) for h, p in
            re.findall(r"(\d+)\s*h(?:ours?)?\b.{0,3}£\s?(\d+(?:\.\d{2})?)", weekday_text, re.I)]


def tariff_detail_from_bands(bands):
    parts = []
    prev = 0
    for hours, price in bands:
        parts.append(f"{prev}-{hours} hrs £{price:.2f}")
        prev = hours
    return "; ".join(parts)


def is_real_tariff(charges_text):
    low = charges_text.lower()
    if any(w in low for w in ("unclear", "not shown", "not stated", "no official info")):
        return False
    return len(parse_bands(charges_text)) >= 2


def who_can_park_for_commercial(captured_text):
    return "Anyone (paid)"  # a named commercial car park operator: open to any paying driver


def extract_hours_osm(hours_text):
    low = hours_text.lower()
    if "24 hour" in low or "24/7" in low or "00:00" in low:
        return "24/7"
    return None


def customer_car_park_record(place_id, notes):
    scope = "chain" if MAYBE_GENERIC_RE.search(notes) else "site"
    fields = {
        "can_park": field("Conditional", scope, notes[:200]),
        "who_can_park": field("Customers only", scope, notes[:200]),
        "cost_type": field("Unknown", scope, notes[:200]),
        "tariff_type": field("Not published", scope, notes[:200]),
        "tariff_detail": field("Not published", scope, notes[:200]),
        "max_stay_mins": field("Not published", scope, notes[:200]),
        "hours_osm_format": field("Not published", scope, notes[:200]),
        "hours_basis": field("Not published", scope, notes[:200]),
        "control_type": field("Not published", scope, notes[:200]),
        "operator": field("Not published", scope, notes[:200]),
        "pcn_gbp": field("Not published", scope, notes[:200]),
    }
    return record(place_id, fields)


def classify(sr, osm_row):
    place_id = sr["Place ID"]
    captured = {c: sr.get(c, "") for c in capture_fill.CAPTURE_COLS}
    type_text = captured.get("Type (as captured)", "")
    notes = captured.get("Notes", "")

    r9_quote = find_r9_quote(captured)
    if r9_quote:
        return no_parking_record(place_id, r9_quote.strip())

    if CUSTOMER_CAR_PARK_RE.search(notes):
        return customer_car_park_record(place_id, notes)

    is_operator_car_park = any(k in type_text for k in
                                ("NCP", "Q-Park", "Euro Car Parks", "CitiPark", "Station Car Park"))
    charges = captured.get("Charges (as published)", "")
    hours_raw = captured.get("Hours (as captured)", "")
    enforcement = captured.get("Enforcement Details", "")

    if is_operator_car_park and is_real_tariff(charges):
        bands = parse_bands(charges)
        operator_match = re.search(r"(NCP|Q-Park|Euro Car Parks|CitiPark|APCOA[\w .()]*)", notes)
        operator = operator_match.group(1).strip() if operator_match else "Not published"
        control = "ANPR (Automatic Number Plate Recognition) camera" if "anpr" in enforcement.lower() else "Not published"
        hours_osm = extract_hours_osm(hours_raw) or "Not published"
        fields = {
            "can_park": field("Yes", "site", charges[:200]),
            "who_can_park": field(who_can_park_for_commercial(charges + " " + notes), "site", charges[:200]),
            "cost_type": field("Paid", "site", charges[:200]),
            "tariff_type": field("Banded by stay length", "site", charges[:200]),
            "tariff_detail": field(tariff_detail_from_bands(bands), "site", charges[:200]),
            "max_stay_mins": field("No limit", "site", charges[:200]),
            "hours_osm_format": field(hours_osm, "site", hours_raw[:120]),
            "hours_basis": field("Car park hours" if hours_osm != "Not published" else "Not published",
                                  "site", hours_raw[:120]),
            "control_type": field(control, "site", enforcement[:150]),
            "operator": field(operator, "site", notes[:150]),
            "pcn_gbp": field("Not published", "site", enforcement[:150]),
        }
        return record(place_id, fields)

    tariff_unclear = any(p in charges.lower() for p in
                          ("unclear", "prebook", "tariff not shown", "not stated", "not shown"))
    confirmed_paid = "public pay car park" in notes.lower() or "pay on the day" in charges.lower()
    hours_known = hours_raw and "no official info" not in hours_raw.lower()
    if is_operator_car_park and tariff_unclear and (hours_known or confirmed_paid):
        operator_match = re.search(r"(NCP|Q-Park|Euro Car Parks|CitiPark)", notes)
        operator = operator_match.group(1) if operator_match else "Not published"
        hours_osm = (extract_hours_osm(hours_raw) or "Not published") if hours_known else "Not published"
        can_park = "Yes" if confirmed_paid else "Conditional"
        who_can_park = "Anyone (paid)" if confirmed_paid else "Unknown"
        quote = notes[:200] if confirmed_paid else charges[:200]
        fields = {
            "can_park": field(can_park, "site", quote),
            "who_can_park": field(who_can_park, "site", quote),
            "cost_type": field("Paid" if confirmed_paid else "Unknown", "site", charges[:200]),
            "tariff_type": field("Not published", "site", charges[:200]),
            "tariff_detail": field("Not published", "site", charges[:200]),
            "max_stay_mins": field("Not published", "site", charges[:200]),
            "hours_osm_format": field(hours_osm, "site", hours_raw[:120]),
            "hours_basis": field("Car park hours" if hours_osm != "Not published" else "Not published",
                                  "site", hours_raw[:120]),
            "control_type": field("Not published", "site", enforcement[:150]),
            "operator": field(operator, "site", notes[:150]),
            "pcn_gbp": field("Not published", "site", enforcement[:150]),
        }
        return record(place_id, fields)

    return record(place_id, leave_for_grok=True,
                   reason="Captured text has no site-specific parking fact beyond NO OFFICIAL INFO / N/A")


def build_records(candidates):
    """`candidates` is a list of (sheet_row, osm_row) pairs, as returned by
    capture_fill.candidate_rows. Returns one classify() record per pair."""
    return [classify(sr, osm_row) for sr, osm_row in candidates]


def write_extracted(candidates, out_path):
    records = build_records(candidates)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return records


def main(argv=None):
    import argparse
    import csv

    from . import fill, sheets

    ap = argparse.ArgumentParser()
    ap.add_argument("--borough", required=True)
    ap.add_argument("--osm-results", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    service = sheets.get_service()
    headers, sheet_rows = sheets.read_tab(service)
    osm_path = args.osm_results or fill.latest_osm_results()
    with open(osm_path, newline="", encoding="utf-8") as f:
        osm_rows = list(csv.DictReader(f))

    candidates = capture_fill.candidate_rows(sheet_rows, osm_rows, args.borough)
    print(f"{len(candidates)} candidates")

    from datetime import date
    out = Path(args.out) if args.out else \
        Path("data/runs") / date.today().isoformat() / "capture" / args.borough / "extracted.jsonl"
    records = write_extracted(candidates, out)
    print(f"Wrote {len(records)} records to {out}")

    n_grok = sum(1 for r in records if r["leave_for_grok"])
    print(f"Classified as leave_for_grok: {n_grok}")
    print(f"Classified as fillable: {len(records) - n_grok}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
