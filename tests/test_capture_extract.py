"""Tests for capture_extract.py: the pattern-match classifier capture_fill
uses to build extracted.jsonl automatically. Each test uses captured text
taken from the real Westminster rows (quoted in the comments), not made-up
text, so a change to the classifier that breaks a known real case fails here
first.
"""
from ferro_parking import capture_extract as ce


def sheet_row(place_id, type_captured="", charges="", hours="", enforcement="", notes=""):
    return {
        "Place ID": place_id,
        "Type (as captured)": type_captured,
        "Max Stay (as captured)": "",
        "Hours (as captured)": hours,
        "Geo (as captured)": "",
        "Charges (as published)": charges,
        "Enforcement Details": enforcement,
        "Notes": notes,
    }


OSM_ROW = {}


# ---- PP-000798: APCOA "1h £5.15" style, from Network Rail's Paddington page --
def test_apcoa_1h_style_bands():
    row = sheet_row(
        "PP-000798", type_captured="Station Car Park",
        charges=("APCOA Paddington Station car park (code 2085, Bishops Bridge Road W2 6AA). "
                 "Mon–Fri: up to 1h £5.15, 3h £11.50, 6h £22.00, 12h £29.80, "
                 "24h £35.20; night (6pm–6am) £11.50. Weekends/BH: full day £16.90; "),
        hours="Not stated on NRE",
        enforcement="APCOA Parking (UK) Ltd (per Network Rail)",
        notes=("Station operator: Network Rail. Network Rail lists 'Paddington Station Car Park "
               "off of Platform 1', APCOA, 152 spaces, 24h, chargeable for all vehicle"),
    )
    rec = ce.classify(row, OSM_ROW)
    assert rec["leave_for_grok"] is False
    assert rec["fields"]["can_park"]["value"] == "Yes"
    assert rec["fields"]["operator"]["value"] == "APCOA"
    assert rec["fields"]["tariff_detail"]["value"] == (
        "0-1 hrs £5.15; 1-3 hrs £11.50; 3-6 hrs £22.00; 6-12 hrs £29.80; 12-24 hrs £35.20")
    assert rec["fields"]["max_stay_mins"]["value"] == "No limit"


# ---- PP-000799: one sentence runs the weekday and weekend rate together ----
def test_weekday_weekend_split_in_one_sentence_keeps_only_weekday_bands():
    row = sheet_row(
        "PP-000799", type_captured="Station Car Park",
        charges=("APCOA tariff: Monday - Friday | Up to 1 hour: £5.15 | Up to 3 hours: "
                 "£11.50 | Up to 6 hours: £22.00 | Up to 12 hours: £29.80 | "
                 "Up to 24 hours: £35.20 | Night rate (6pm-6am): £11.50 | Weekends and Bank"),
        hours="Mon–Fri: 24 hours; Sat: 24 hours; Sun: 24 hours",
        enforcement="APCOA Parking (UK) Limited (car park operator); PCN amount not stated on NRE",
        notes=("Car park operator: APCOA Parking (UK) Limited. Station operator: Network Rail. "
               "CCTV: yes. Accessible parking: Parking is chargeable for all vehicles H"),
    )
    rec = ce.classify(row, OSM_ROW)
    assert rec["leave_for_grok"] is False
    # Five weekday bands only: the weekend rate after "Weekends and Bank" is cut off,
    # not folded in as a sixth band or used to overwrite a weekday price.
    assert rec["fields"]["tariff_detail"]["value"] == (
        "0-1 hrs £5.15; 1-3 hrs £11.50; 3-6 hrs £22.00; 6-12 hrs £29.80; 12-24 hrs £35.20")
    assert rec["fields"]["hours_osm_format"]["value"] == "24/7"


# ---- PP-000124: Q-Park "prebook only", no published tariff ----------------
def test_q_park_prebook_only_leaves_tariff_not_published():
    row = sheet_row(
        "PP-000124", type_captured="Q-Park",
        charges=("UNCLEAR – no tariff published online; prebook price quoted on booking; "
                 "card payment (Maestro/Mastercard/Visa)"),
        hours="24/7 (Mon–Sun)",
        enforcement="Q-Park (operator); penalty/PCN not stated on page",
        notes=("Operator: Q-Park. 311 spaces; height limit 2.03 m; services listed: AED, CCTV "
               "in operation, Lift, Help point, Information, Shoe polisher; UNCLEAR: no "),
    )
    rec = ce.classify(row, OSM_ROW)
    assert rec["leave_for_grok"] is False
    assert rec["fields"]["can_park"]["value"] == "Conditional"
    assert rec["fields"]["cost_type"]["value"] == "Unknown"
    assert rec["fields"]["tariff_type"]["value"] == "Not published"
    assert rec["fields"]["tariff_detail"]["value"] == "Not published"
    assert rec["fields"]["operator"]["value"] == "Q-Park"
    assert rec["fields"]["hours_osm_format"]["value"] == "24/7"


# ---- PP-001363: Waitrose, "may be generic" so the record is chain scope ---
def test_waitrose_may_be_generic_is_chain_scope():
    row = sheet_row(
        "PP-001363", type_captured="Supermarket",
        notes=("Facilities: Disabled car parking, Customer car park. VERIFY: Waitrose lists car "
               "park at ~75% of stores incl. central sites – may be generic."),
    )
    rec = ce.classify(row, OSM_ROW)
    assert rec["leave_for_grok"] is False
    assert rec["fields"]["can_park"]["scope"] == "chain"
    assert rec["fields"]["can_park"]["value"] == "Conditional"
    assert rec["fields"]["who_can_park"]["value"] == "Customers only"


# ---- Royal Parks per-15-minute tariff: must stay left for Grok ------------
def test_royal_parks_per_15_minute_tariff_stays_left_for_grok():
    # "70p/15min" and "£2.80/h" never produce the "<N>h ... £<price>" shape
    # parse_bands looks for, so this can never be misread as an hourly band
    # even if a future change widened the operator-car-park keyword list.
    charges = ("Mon–Sat: 70p/15min, £2.80/h, £11.20 for 4h. "
               "Sun & BH: 50p/15min, £2/h, £20 for 10h.")
    assert len(ce.parse_bands(charges)) < 2

    row = sheet_row(
        "PP-002141", type_captured="Park / Attraction",
        charges=charges,
        hours="Charges 8:30am–6:30pm daily; vehicle gates open 5am",
        enforcement=("Excess Charge Notice issued by NSL on behalf of The Royal Parks; amount "
                      "not published (UNCLEAR); appeals via royalparks.org.uk/parking-fines-appeals"),
        notes="Blue Badge free (4h limit); motorcycles free (4h).",
    )
    rec = ce.classify(row, OSM_ROW)
    assert rec["leave_for_grok"] is True
