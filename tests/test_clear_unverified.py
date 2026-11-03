"""Tests for clear_unverified.py: scope (Verification Result blank),
which columns get cleared, and that a finished row or an already-blank
row is left alone."""
from ferro_parking import clear_unverified as cu


def sheet_row(**kw):
    base = {
        "_sheet_row": 2, "Place ID": "PP-1", "Location Name": "Test Place",
        "Verification Result": "",
        "Can Park? (Yes/No/Conditional)": "Conditional", "Who Can Park": "Customers only",
        "Rules Summary": "Customer car park, cost unknown.", "Cost Type": "Unknown",
        "Price Status": "Not published", "Tariff Type": "Not published",
        "Tariff Detail": "Not published", "Max Stay (mins)": "Not published",
        "Hours (OpenStreetMap opening_hours format)": "Not published",
        "Hours Basis": "Not published",
        "Parking Control Type (Cameras / Barrier / Patrol)": "Not published",
        "Operator": "Not published", "PCN (Penalty Charge Notice) amount (£)": "Not published",
        "Street Address": "1 Test Road", "Postcode": "W1 1AA", "Borough": "Westminster",
    }
    base.update(kw)
    return base


def test_eligible_rows_only_blank_verification_result():
    rows = [sheet_row(**{"Place ID": "PP-1", "Verification Result": ""}),
            sheet_row(**{"Place ID": "PP-2", "Verification Result": "Confirmed"})]
    assert [r["Place ID"] for r in cu.eligible_rows(rows)] == ["PP-1"]


def test_build_plan_clears_exactly_the_named_columns():
    plan, undo, dry_run_rows = cu.build_plan([sheet_row()])
    assert len(plan) == 1
    new = plan[0]["new"]
    assert set(new) == set(cu.CLEARED_COLUMNS)
    assert all(v == "" for v in new.values())


def test_build_plan_never_touches_an_unlisted_column():
    plan, undo, dry_run_rows = cu.build_plan([sheet_row()])
    for col in ("Street Address", "Postcode", "Borough", "Location Name", "Place ID"):
        assert col not in plan[0]["new"]


def test_build_plan_skips_a_finished_row():
    rows = [sheet_row(**{"Verification Result": "Confirmed"})]
    plan, undo, dry_run_rows = cu.build_plan(rows)
    assert plan == []
    assert undo == []


def test_build_plan_skips_a_row_with_nothing_to_clear():
    row = sheet_row(**{col: "" for col in cu.CLEARED_COLUMNS})
    plan, undo, dry_run_rows = cu.build_plan([row])
    assert plan == []
    assert undo == []


def test_undo_records_every_current_value():
    plan, undo, dry_run_rows = cu.build_plan([sheet_row()])
    old = undo[0]["old"]
    assert old["Can Park? (Yes/No/Conditional)"] == "Conditional"
    assert old["Operator"] == "Not published"
    assert set(old) == set(cu.CLEARED_COLUMNS)


def test_dry_run_rows_one_per_cleared_column():
    plan, undo, dry_run_rows = cu.build_plan([sheet_row()])
    assert len(dry_run_rows) == len(cu.CLEARED_COLUMNS)
    assert all(r["New value"] == "" for r in dry_run_rows)


def test_build_plan_matches_place_id_and_sheet_row():
    row = sheet_row(**{"_sheet_row": 42, "Place ID": "PP-42"})
    plan, undo, dry_run_rows = cu.build_plan([row])
    assert plan[0]["sheet_row"] == 42
    assert plan[0]["place_id"] == "PP-42"
    assert undo[0]["sheet_row"] == 42
    assert undo[0]["place_id"] == "PP-42"
