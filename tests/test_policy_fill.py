"""Tests for policy_fill.py (rule R10): branches a (chain policy), b
(presumed no parking), c (needs research), and that rule R7 is never
broken by this command (no Free, no Anyone, no max stay)."""
from datetime import date

from ferro_parking import policy_fill as pf
from ferro_parking import rules as rules_mod

TODAY = date(2026, 11, 4)
RULES = rules_mod.load_rules()


def sheet_row(**kw):
    base = {
        "Location Name": "Tesco Acton Superstore", "Borough": "Ealing",
        "Place Category": "Supermarket", "Type (as captured)": "Retail - Supermarket",
        "Verification Result": "", "Notes": "", "Review Flag": "", "Flag Status": "",
        "Source URLs (primary first)": "", "Hours (as captured)": "", "Place ID": "PP-1",
    }
    base.update(kw)
    return base


def osm_row(distance=""):
    return {"Place ID": "PP-1", "Car Park Distance (m)": distance}


# ---- branch a: chain policy, large format --------------------------------
def test_large_format_tesco_gets_chain_policy():
    branch, result, reason = pf.classify(sheet_row(), osm_row(), RULES)
    assert branch == "a"
    fields, notes, flags = result
    assert fields[pf.CAN_PARK] == "Conditional"
    assert fields[pf.WHO_CAN_PARK] == "Customers only"
    assert fields["Cost Type"] == "Unknown"
    assert fields["Price Status"] == "Chain policy (not store-specific)"
    assert fields["Tariff Type"] == "Not published"
    assert fields["Max Stay (mins)"] == "Not published"
    assert fields["Specificity"] == "Chain-wide"
    assert fields["Evidence Level"] == "Chain policy"
    assert any("Max stay set per store" in n for n in notes)


def test_large_format_lidl_has_no_who_can_park_override_falls_back_to_category_default():
    row = sheet_row(**{"Location Name": "Lidl East Acton"})
    branch, result, reason = pf.classify(row, osm_row(), RULES)
    assert branch == "a"
    fields, notes, flags = result
    assert fields[pf.WHO_CAN_PARK] == "Customers only"
    assert any("90 minutes" in n for n in notes)


def test_morrisons_gets_operator_from_chain_rule():
    row = sheet_row(**{"Location Name": "Morrisons Southwark"})
    branch, result, reason = pf.classify(row, osm_row(), RULES)
    assert branch == "a"
    fields, notes, flags = result
    assert fields["Operator"] == "Euro Car Parks"


def test_chain_source_tier_is_official_when_chain_name_in_source_url():
    row = sheet_row(**{"Source URLs (primary first)": "https://www.tesco.com/store-locator/x"})
    branch, result, reason = pf.classify(row, osm_row(), RULES)
    fields, notes, flags = result
    assert fields["Source Tier"] == pf.OPERATOR_SOURCE_TIER


def test_chain_source_tier_is_third_party_with_no_chain_url():
    branch, result, reason = pf.classify(sheet_row(), osm_row(), RULES)
    fields, notes, flags = result
    assert fields["Source Tier"] == pf.GOOGLE_THIRD_PARTY_SOURCE_TIER


def test_hours_basis_store_hours_when_captured_text_says_so():
    row = sheet_row(**{"Hours (as captured)": "Store hours Mon-Sat 07:00-22:00"})
    branch, result, reason = pf.classify(row, osm_row(), RULES)
    fields, notes, flags = result
    assert fields["Hours Basis"] == "Store hours"


# ---- branch a: convenience format needs a nearby OSM car park ------------
def test_convenience_format_with_nearby_car_park_gets_chain_policy():
    row = sheet_row(**{"Location Name": "Tesco Express Baker Street"})
    branch, result, reason = pf.classify(row, osm_row(distance="25"), RULES)
    assert branch == "a"


def test_convenience_format_without_nearby_car_park_is_needs_research():
    row = sheet_row(**{"Location Name": "Tesco Express Baker Street"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    assert branch == "c"
    assert "convenience format" in reason


def test_convenience_format_car_park_too_far_is_still_needs_research():
    row = sheet_row(**{"Location Name": "Co-op Food Camden"})
    branch, result, reason = pf.classify(row, osm_row(distance="80"), RULES)
    assert branch == "c"


# ---- branch b: small venue, no nearby OSM car park ------------------------
def test_small_venue_with_no_nearby_car_park_is_presumed_no_parking():
    row = sheet_row(**{"Location Name": "The Red Lion", "Place Category": "Pub",
                        "Type (as captured)": "Pub"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    assert branch == "b"
    fields, notes, flags = result
    assert fields[pf.CAN_PARK] == "No"
    assert fields["Evidence Level"] == "Presumed"
    assert fields["Source Tier"] == "OpenStreetMap"
    assert fields["Rules Summary"] == "No parking listed (none mapped nearby). Check on arrival."
    for col in ("Who Can Park", "Cost Type", "Tariff Type", "Tariff Detail", "Max Stay (mins)",
                "Operator"):
        assert fields[col] == "Not applicable"


def test_small_venue_with_a_nearby_car_park_is_needs_research():
    row = sheet_row(**{"Location Name": "The Red Lion", "Place Category": "Pub",
                        "Type (as captured)": "Pub"})
    branch, result, reason = pf.classify(row, osm_row(distance="10"), RULES)
    assert branch == "c"


def test_fast_food_with_drive_thru_is_not_a_small_venue():
    row = sheet_row(**{"Location Name": "McDonald's North Acton",
                        "Place Category": "Fast food (drive-thru)",
                        "Type (as captured)": "Fast food restaurant"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    assert branch == "c"


def test_fast_food_without_drive_thru_is_a_small_venue():
    row = sheet_row(**{"Location Name": "McDonald's Baker Street",
                        "Place Category": "Fast food", "Type (as captured)": "Fast food restaurant"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    assert branch == "b"


def test_public_car_park_is_not_misread_as_a_pub():
    # "Public Car Park" contains the substring "pub"; a plain substring
    # check would wrongly call this a small venue and mark it No parking.
    row = sheet_row(**{"Location Name": "Oaklands Gate Car Park (Hillingdon Council)",
                        "Place Category": "", "Type (as captured)": "Public Car Park (Council)"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    assert branch == "c"


# ---- branch c: everything else --------------------------------------------
def test_unrecognised_store_is_needs_research():
    row = sheet_row(**{"Location Name": "Generic Hardware Store",
                        "Place Category": "DIY store", "Type (as captured)": "Retail"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    assert branch == "c"
    assert "not a recognised chain format" in reason


# ---- finish_record passes the shared validator ----------------------------
def test_finish_record_chain_policy_passes_consistency_checks():
    branch, result, reason = pf.classify(sheet_row(), osm_row(), RULES)
    fields, notes, flags = result
    new, violations = pf.finish_record(sheet_row(), fields, notes, flags, TODAY)
    assert violations is None
    assert "Route" in new["Decision Reason"]
    assert new["Review Flag"]
    assert new["Flag Status"] == "Open"


def test_finish_record_presumed_no_parking_passes_consistency_checks():
    row = sheet_row(**{"Location Name": "The Red Lion", "Place Category": "Pub",
                        "Type (as captured)": "Pub"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    fields, notes, flags = result
    new, violations = pf.finish_record(row, fields, notes, flags, TODAY)
    assert violations is None


# ---- rule R7: never Free, Anyone, or a max stay ----------------------------
def test_r7_never_violated_across_every_known_chain():
    chains_to_try = ["Tesco Acton Superstore", "Sainsbury's Superstore Example",
                      "Lidl East Acton", "Aldi Example Store", "Asda Example Superstore",
                      "Morrisons Southwark"]
    for name in chains_to_try:
        row = sheet_row(**{"Location Name": name})
        branch, result, reason = pf.classify(row, osm_row(), RULES)
        if branch != "a":
            continue
        fields, _, _ = result
        assert fields["Cost Type"] != "Free", name
        assert fields[pf.WHO_CAN_PARK] not in ("Anyone", "Anyone (paid)"), name
        assert fields["Max Stay (mins)"] == "Not published", name


def test_r7_small_venue_never_sets_a_risky_value():
    row = sheet_row(**{"Location Name": "Corner Cafe", "Place Category": "Cafe",
                        "Type (as captured)": "Cafe"})
    branch, result, reason = pf.classify(row, osm_row(distance=""), RULES)
    assert branch == "b"
    fields, _, _ = result
    assert fields[pf.CAN_PARK] == "No"
    assert fields["Cost Type"] == "Not applicable"
