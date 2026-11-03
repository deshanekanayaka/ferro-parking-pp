"""Ferro PP: rule R10's policy-fill. A dry run only command: cautious
chain-policy rows for large and convenience chain branches, and cautious
presumed-no-parking rows for small venues with no OSM car park nearby.

python -m ferro_parking policy-fill --borough NAME

Eligible: Verification Result blank. For each eligible row:
  a) a known chain (rules.toml) in a large format, or a convenience format
     with an OSM car park within rules.r10_nearby_car_park_radius_m: a
     cautious chain-policy row (Evidence Level "Chain policy").
  b) a small venue (R10's categories) with no OSM car park within that
     radius: Can Park? No, Evidence Level "Presumed".
  c) everything else: skipped, logged as "needs research".

This command never sets Free, Anyone, Anyone (paid), or a max stay (rule
R7): only cautious values. See docs/PP_rules_and_pilot.md (R10) and
page_fill.py's consistency_checks, which this module's output must also
satisfy.
"""
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

from . import fill, page_fill, rules as rules_mod, sheets

PLACE_ID = fill.PLACE_ID
LOCATION_NAME = fill.LOCATION_NAME
CAN_PARK = fill.CAN_PARK
WHO_CAN_PARK = fill.WHO_CAN_PARK
NOTES = fill.NOTES
REVIEW_FLAG = fill.REVIEW_FLAG
FLAG_STATUS = fill.FLAG_STATUS
VERIFIED_BY = "Policy script"

GOOGLE_THIRD_PARTY_SOURCE_TIER = "Google search / third-party"
OPERATOR_SOURCE_TIER = "Operator / council site"

FAST_FOOD_DRIVE_THRU_HINTS = ("drive-thru", "drive thru", "drivethru")


# ---------------------------------------------------------------- eligibility

def candidate_rows(sheet_rows, osm_rows, borough):
    """Every row for one borough with Verification Result blank, paired
    with its osm_results.csv row (for Car Park Distance (m)). A row with
    no matching OSM row still counts eligible; has_nearby_car_park then
    reads as no car park found."""
    by_place_id = {r.get(PLACE_ID, ""): r for r in osm_rows if r.get("Place ID")}
    out = []
    for sheet_row in sheet_rows:
        if sheet_row.get("Borough", "") != borough:
            continue
        if sheet_row.get("Verification Result", "") != "":
            continue
        place_id = sheet_row.get(PLACE_ID, "")
        out.append((sheet_row, by_place_id.get(place_id, {})))
    return out


def has_nearby_car_park(osm_row, rules):
    try:
        distance = float(osm_row.get("Car Park Distance (m)", ""))
    except (TypeError, ValueError):
        return False
    return distance <= rules.r10_nearby_car_park_radius_m


# ---------------------------------------------------------------- categories

def is_fast_food_without_drive_thru(category_text):
    low = category_text.lower()
    return not any(h in low for h in FAST_FOOD_DRIVE_THRU_HINTS)


def _contains_word(text, phrase):
    """Whole-word match: plain substring would read "Public Car Park" as
    containing "pub"."""
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


def small_venue_category(sheet_row, rules):
    """R10's small venue categories, matched against Place Category and
    Type (as captured) together; "fast food" only counts without a
    drive-thru, which has its own parking."""
    category_text = f"{sheet_row.get('Place Category', '')} {sheet_row.get('Type (as captured)', '')}"
    low = category_text.lower()
    if _contains_word(low, "fast food"):
        return is_fast_food_without_drive_thru(low)
    return any(_contains_word(low, c) for c in rules.r10_small_venue_categories if c != "fast food")


# ---------------------------------------------------------------- branch a: chain policy

def chain_source_tier(chain_key, sheet_row):
    urls = (sheet_row.get("Source URLs (primary first)", "") or "").lower()
    if chain_key and chain_key.replace(" ", "") in urls.replace(" ", ""):
        return OPERATOR_SOURCE_TIER
    return GOOGLE_THIRD_PARTY_SOURCE_TIER


def chain_who_can_park(chain, sheet_row, rules):
    who = (chain or {}).get("who_can_park")
    if who and who not in rules.r7_risky_who_can_park:
        return who
    return fill.category_default(sheet_row, rules)


def chain_cost_type(chain):
    cost_type = (chain or {}).get("cost_type")
    return "Paid" if cost_type == "Paid" else "Unknown"


def chain_hours_basis(sheet_row):
    captured = (sheet_row.get("Hours (as captured)", "") or "").lower()
    return "Store hours" if "store hours" in captured else "Not published"


def chain_policy_fields(sheet_row, chain_key, chain, rules):
    who_can_park = chain_who_can_park(chain, sheet_row, rules)
    cost_type = chain_cost_type(chain)
    new = {
        CAN_PARK: "Conditional",
        WHO_CAN_PARK: who_can_park,
        "Cost Type": cost_type,
        "Price Status": "Chain policy (not store-specific)",
        "Tariff Type": "Not published",
        "Tariff Detail": "Not published",
        "Max Stay (mins)": "Not published",
        "Hours (OpenStreetMap opening_hours format)": "Not published",
        "Hours Basis": chain_hours_basis(sheet_row),
        "Operator": (chain or {}).get("operator", "Not published"),
        "Specificity": "Chain-wide",
        "Source Tier": chain_source_tier(chain_key, sheet_row),
        "Evidence Type": "Official site: partial info",
        "Evidence Level": "Chain policy",
        "Verification Result": "Confirmed, details not published",
        VERIFIED_BY: VERIFIED_BY,
        "Verified Date": None,  # filled in by caller with today's date
        "Decision Reason": f"Route-independent policy fill (rule R10): large or convenience "
                            f"chain format ({chain_key or 'unrecognised chain'}), no "
                            "site-specific evidence read.",
    }
    hint = (chain or {}).get("hint")
    extra_notes = [f"Chain rule ({chain_key}): {hint}"] if hint else []
    extra_flags = ["Chain policy presumed: confirm store-specific details on arrival"]
    return new, extra_notes, extra_flags


# ---------------------------------------------------------------- branch b: presumed no parking

def presumed_no_parking_fields():
    new = {CAN_PARK: "No", "Evidence Level": "Presumed", "Source Tier": "OpenStreetMap",
           "Evidence Detail (what the source shows)":
               "No car park mapped in OpenStreetMap within 40 m of the venue",
           "Rules Summary": "No parking listed (none mapped nearby). Check on arrival.",
           "Verification Result": "Confirmed, details not published", VERIFIED_BY: VERIFIED_BY,
           "Verified Date": None,
           "Decision Reason": "Route-independent policy fill (rule R10): small venue "
                               "category, no OpenStreetMap car park within 40 m."}
    for col in page_fill.NOT_APPLICABLE_IF_NO_PARKING:
        new[col] = "Not applicable"
    extra_flags = ["Presumed no parking: confirm on arrival"]
    return new, [], extra_flags


# ---------------------------------------------------------------- classify

def classify(sheet_row, osm_row, rules):
    """Returns ("a" | "b" | "c", fields_dict | None, reason | None).
    fields_dict is None for "c" (needs research)."""
    location_name = sheet_row.get(LOCATION_NAME, "")
    fmt = rules.format_for(location_name)
    chain_key_words = rules_mod.norm_chain_key(location_name).split()
    chain = None
    chain_key = None
    for n in (2, 1):
        key = " ".join(chain_key_words[:n])
        if key in rules.r6_chains:
            chain, chain_key = rules.r6_chains[key], key
            break

    if fmt == "large" or (fmt == "convenience" and has_nearby_car_park(osm_row, rules)):
        fields, extra_notes, extra_flags = chain_policy_fields(sheet_row, chain_key, chain, rules)
        return "a", (fields, extra_notes, extra_flags), None

    if small_venue_category(sheet_row, rules) and not has_nearby_car_park(osm_row, rules):
        fields, extra_notes, extra_flags = presumed_no_parking_fields()
        return "b", (fields, extra_notes, extra_flags), None

    if fmt == "convenience":
        return "c", None, "convenience format, no OSM car park within 40 m"
    return "c", None, "not a recognised chain format or small venue pattern"


# ---------------------------------------------------------------- assembling a row

def finish_record(sheet_row, fields, extra_notes, extra_flags, today):
    new, notes_list, flags_list = dict(fields), list(extra_notes), list(extra_flags)
    new["Verified Date"] = today.isoformat()

    if notes_list:
        existing = sheet_row.get(NOTES, "") or ""
        new[NOTES] = f"{existing}{' | ' if existing else ''}{'; '.join(notes_list)}"
    if flags_list:
        existing = sheet_row.get(REVIEW_FLAG, "") or ""
        new[REVIEW_FLAG] = f"{existing}{'; ' if existing else ''}{'; '.join(flags_list)}"
        new[FLAG_STATUS] = "Open"

    fill.assert_not_protected(new)
    violations = page_fill.consistency_checks(new)
    return (new, None) if not violations else (None, violations)


# ---------------------------------------------------------------- plan building

def build_plan(eligible, rules, today):
    plan, undo, dry_run_rows = [], [], []
    counts = {"a": 0, "b": 0, "c": 0}
    needs_research = []
    for sheet_row, osm_row in eligible:
        branch, result, reason = classify(sheet_row, osm_row, rules)
        counts[branch] += 1
        if branch == "c":
            needs_research.append((sheet_row.get(PLACE_ID, ""), sheet_row.get(LOCATION_NAME, ""), reason))
            continue
        fields, extra_notes, extra_flags = result
        new, violations = finish_record(sheet_row, fields, extra_notes, extra_flags, today)
        if new is None:
            counts[branch] -= 1
            counts["c"] += 1
            needs_research.append((sheet_row.get(PLACE_ID, ""), sheet_row.get(LOCATION_NAME, ""),
                                    "failed consistency check: " + "; ".join(violations)))
            continue
        sheet_row_num = sheet_row["_sheet_row"]
        place_id = sheet_row.get(PLACE_ID, "")
        name = sheet_row.get(LOCATION_NAME, "")
        old = {col: sheet_row.get(col, "") for col in new}
        plan.append({"sheet_row": sheet_row_num, "place_id": place_id, "name": name, "new": new})
        undo.append({"sheet_row": sheet_row_num, "place_id": place_id, "old": old})
        for col, value in new.items():
            dry_run_rows.append({"Sheet Row": sheet_row_num, "Place ID": place_id,
                                 "Location Name": name, "Column": col,
                                 "Current value": old[col], "New value": value})
    return plan, undo, dry_run_rows, counts, needs_research


# ---------------------------------------------------------------- command

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--borough", required=True)
    ap.add_argument("--osm-results", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    today = date.today()
    rules = rules_mod.load_rules()
    osm_path = args.osm_results or fill.latest_osm_results()
    with open(osm_path, newline="", encoding="utf-8") as f:
        osm_rows = list(csv.DictReader(f))

    service = sheets.get_service()
    headers, sheet_rows = sheets.read_tab(service)
    eligible = candidate_rows(sheet_rows, osm_rows, args.borough)

    plan, undo, dry_run_rows, counts, needs_research = build_plan(eligible, rules, today)

    out_dir = Path(args.out) if args.out else Path("data/runs") / today.isoformat() / "policy_fill" / args.borough
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=1))
    (out_dir / "undo.json").write_text(json.dumps(undo, indent=1))
    fill.write_csv(out_dir / "dry_run.csv",
                    ["Sheet Row", "Place ID", "Location Name", "Column", "Current value", "New value"],
                    dry_run_rows)
    with open(out_dir / "needs_research.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Place ID", "Location Name", "Reason"])
        w.writerows(needs_research)

    print(f"Borough: {args.borough}")
    print(f"Eligible rows: {len(eligible)}")
    print(f"a) chain policy: {counts['a']}")
    print(f"b) presumed no parking: {counts['b']}")
    print(f"c) needs research (skipped): {counts['c']}")
    print(f"\nOutputs in {out_dir}/. Dry run only, nothing written to the sheet.")
    return 0


if __name__ == "__main__":
    main()
