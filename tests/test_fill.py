"""Tests for fill.py: R7, the eligibility filter, protected columns, Notes
appending, and the write/undo abort-on-change check (Sheets API mocked)."""
from datetime import date

import pytest

from ferro_parking import fill, rules as rules_mod

RULES = rules_mod.load_rules()
TODAY = date(2026, 11, 2)


def sheet_row(**kw):
    base = {
        "Location Name": "Test Place", "Place Category": "", "Type (as captured)": "",
        "Can Park? (Yes/No/Conditional)": "Conditional",
        "Source URLs (primary first)": "", "Notes": "", "Review Flag": "",
        "Flag Status": "", "Geo Precision": "Building", "Postcode": "",
        "Borough": "Haringey", "Verification Result": "", "Verified By": "",
        "Ferro Autopay": "", "Place ID": "PP-1",
    }
    base.update(kw)
    return base


def osm_row(tags, **kw):
    base = {
        "OSM Raw Tags": tags, "OSM Car Park": "https://www.openstreetmap.org/way/1",
        "Car Park Last Edited": "2026-01-01", "Car Park Distance (m)": "0",
        "Route": "C. OSM car park + official page check",
        "Car Park Link": "Adjacent to place", "Place ID": "PP-1",
    }
    base.update(kw)
    return base


# ---- rule R7: Free and Anyone need site-specific evidence -----------------
def test_fee_no_on_customers_only_gives_free():
    new = fill.derive_values(sheet_row(), osm_row("access=customers; fee=no"), RULES, TODAY)
    assert new["Cost Type"] == "Free"


def test_fee_no_on_untagged_car_park_gives_unknown_not_free():
    new = fill.derive_values(sheet_row(), osm_row("fee=no"), RULES, TODAY)
    assert new["Cost Type"] == "Unknown"
    assert "R7" in new["Notes"]


def test_chain_paid_vs_osm_free_gives_unknown_and_flag():
    new = fill.derive_values(sheet_row(**{"Location Name": "NCP Somewhere"}),
                              osm_row("access=customers; fee=no"), RULES, TODAY)
    assert new["Cost Type"] == "Unknown"
    assert "Review Flag" in new
    assert "rule R7" in new["Review Flag"]


def test_chain_free_hint_never_sets_cost_type_free():
    # Asda's chain rule says Free, but with no fee tag at all OSM gives nothing:
    # the chain hint must never set Cost Type on its own.
    new = fill.derive_values(sheet_row(**{"Location Name": "Asda Example"}),
                              osm_row("access=customers"), RULES, TODAY)
    assert new["Cost Type"] != "Free"
    assert "hint only" in new["Notes"]


# ---- eligibility filter ------------------------------------------------------
def test_eligible_row_passes_all_conditions():
    checks = fill.check_eligibility(sheet_row(), osm_row("access=customers; fee=no"), "Haringey", TODAY)
    assert fill.is_eligible(checks)


@pytest.mark.parametrize("field,value,failed", [
    ("Borough", "Camden", "Borough matches"),
    ("Verification Result", "Confirmed", "Verification Result blank"),
    ("Verified By", "Someone else", "Verified By blank or PP (validation)"),
    ("Ferro Autopay", "✅", "Ferro Autopay not checked"),
    ("Can Park? (Yes/No/Conditional)", "No", "captured Can Park is not No"),
])
def test_eligibility_fails_on_each_condition(field, value, failed):
    checks = fill.check_eligibility(sheet_row(**{field: value}), osm_row("access=customers; fee=no"),
                                     "Haringey", TODAY)
    assert checks[failed] is False
    assert not fill.is_eligible(checks)


def test_route_must_start_with_c():
    checks = fill.check_eligibility(sheet_row(), osm_row("access=customers", Route="D. Full research"),
                                     "Haringey", TODAY)
    assert checks["Route starts with C"] is False


def test_car_park_link_must_be_adjacent_or_brand():
    checks = fill.check_eligibility(sheet_row(), osm_row("access=customers", **{
        "Car Park Link": "Near precise pin (place not matched)"}), "Haringey", TODAY)
    assert checks["Car Park Link is adjacent or brand match"] is False


def test_car_park_edited_over_2_years_ago_fails():
    checks = fill.check_eligibility(sheet_row(), osm_row("access=customers", **{
        "Car Park Last Edited": "2020-01-01"}), "Haringey", TODAY)
    assert checks["Car Park Last Edited within 2 years"] is False


# ---- protected columns -------------------------------------------------------
def test_derive_values_never_touches_a_protected_column():
    new = fill.derive_values(sheet_row(), osm_row("access=customers; fee=no"), RULES, TODAY)
    for col in new:
        assert col not in fill.PROTECTED_COLUMNS
        assert not col.endswith(fill.PROTECTED_SUFFIXES)


def test_assert_not_protected_raises_on_protected_column():
    with pytest.raises(AssertionError):
        fill.assert_not_protected({"Latitude": "1"})
    with pytest.raises(AssertionError):
        fill.assert_not_protected({"Max Stay (as captured)": "1"})


# ---- Notes appending ----------------------------------------------------------
def test_notes_keeps_existing_text_and_appends_osm():
    new = fill.derive_values(sheet_row(Notes="Store 2332 (main)."),
                              osm_row("access=customers; fee=no; capacity=30"), RULES, TODAY)
    assert new["Notes"].startswith("Store 2332 (main).")
    assert " | OSM: " in new["Notes"]
    assert "capacity=30" in new["Notes"]


def test_notes_omitted_when_nothing_to_add():
    new = fill.derive_values(sheet_row(Notes="Existing note."),
                              osm_row("access=customers; fee=no"), RULES, TODAY)
    assert "Notes" not in new


def test_review_flag_appends_without_losing_existing_text():
    new = fill.derive_values(sheet_row(**{"Can Park? (Yes/No/Conditional)": "Yes",
                                           "Review Flag": "Possible duplicate of row 5"}),
                              osm_row("access=customers; fee=no"), RULES, TODAY)
    assert new["Review Flag"].startswith("Possible duplicate of row 5")
    assert "Can Park changed from Yes to Conditional" in new["Review Flag"]
    assert new["Flag Status"] == "Open"


# ---- write/undo abort-on-change (Sheets API mocked) --------------------------
class FakeValues:
    def __init__(self, store):
        self.store = store
        self.batch_update_calls = []

    def batchGet(self, spreadsheetId, ranges):
        return FakeExec({"valueRanges": [{"values": [[self.store.get(r, "")]]} for r in ranges]})

    def batchUpdate(self, spreadsheetId, body):
        self.batch_update_calls.append(body)
        for entry in body["data"]:
            self.store[entry["range"]] = entry["values"][0][0]
        return FakeExec({})

    def get(self, spreadsheetId, range):
        return FakeExec({"values": [["Place ID", "Verification Result"]]})


class FakeExec:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeSpreadsheets:
    def __init__(self, store):
        self._values = FakeValues(store)

    def values(self):
        return self._values


class FakeService:
    def __init__(self, store):
        self._spreadsheets = FakeSpreadsheets(store)

    def spreadsheets(self):
        return self._spreadsheets


HEADERS = ["Place ID", "Verification Result", "Who Can Park"]


def test_write_aborts_row_when_live_cell_differs_from_undo():
    plan = [{"sheet_row": 5, "place_id": "PP-5", "name": "X",
              "new": {"Who Can Park": "Customers only"}}]
    undo_by_row = {5: {"sheet_row": 5, "place_id": "PP-5", "old": {"Who Can Park": "Unknown"}}}
    # Live sheet now has a different value than the undo snapshot recorded.
    store = {"ALL LONDON (clean)!C5": "Guests only"}
    service = FakeService(store)
    result = fill._apply_write(service, HEADERS, plan, undo_by_row, apply=True)
    assert result == 0
    assert service._spreadsheets._values.batch_update_calls == []


def test_write_proceeds_when_live_cell_matches_undo():
    plan = [{"sheet_row": 5, "place_id": "PP-5", "name": "X",
              "new": {"Who Can Park": "Customers only"}}]
    undo_by_row = {5: {"sheet_row": 5, "place_id": "PP-5", "old": {"Who Can Park": "Unknown"}}}
    store = {"ALL LONDON (clean)!C5": "Unknown"}
    service = FakeService(store)
    result = fill._apply_write(service, HEADERS, plan, undo_by_row, apply=True)
    assert result == 0
    assert len(service._spreadsheets._values.batch_update_calls) == 1
    assert store["ALL LONDON (clean)!C5"] == "Customers only"


def test_undo_aborts_when_place_id_no_longer_matches():
    undo_entries = [{"sheet_row": 5, "place_id": "PP-5", "old": {"Who Can Park": "Unknown"}}]
    store = {"ALL LONDON (clean)!A5": "PP-999"}
    service = FakeService(store)
    result = fill._apply_undo(service, HEADERS, undo_entries, apply=True)
    assert result == 0
    assert service._spreadsheets._values.batch_update_calls == []
