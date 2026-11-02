"""Command line entry point: python -m ferro_parking <command> [options]

Commands:
  match   Stage 1: match sheet rows to OpenStreetMap and pick a research route
  export  Save the live sheet tab to data/raw/all_london_clean.csv
  fill    Stage 2-3: dry run fill for one borough (never writes to the sheet)
  write   Write a plan.json to the sheet (--apply to actually write)
  undo    Restore an undo.json to the sheet (--apply to actually write)
"""
import csv
import sys
from pathlib import Path


def cmd_export(argv):
    from . import sheets
    service = sheets.get_service()
    headers, rows = sheets.read_tab(service)
    out = Path("data/raw/all_london_clean.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in rows:
            w.writerow({h: row.get(h, "") for h in headers})
    print(f"Wrote {len(rows)} rows to {out}")
    row698 = next((r for r in rows if r["_sheet_row"] == 698), None)
    print(f"Row 698 Verified By: {row698.get('Verified By', '') if row698 else '(not found)'}")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, argv = sys.argv[1], sys.argv[2:]
    if cmd == "match":
        from .osm_match import main as match_main
        return match_main(argv)
    if cmd == "export":
        return cmd_export(argv)
    if cmd == "fill":
        from .fill import main as fill_main
        return fill_main(argv)
    if cmd == "write":
        from .fill import write_main
        return write_main(argv)
    if cmd == "undo":
        from .fill import undo_main
        return undo_main(argv)
    print(f"Unknown command: {cmd}\n\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
