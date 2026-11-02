# Ferro parking pipeline

Fills and checks the Ferro Maps parking sheet ("PP Parking places", tab **ALL LONDON (clean)**)
using free data first (OpenStreetMap + rules) and the Grok PP bot only for the rows code cannot settle.

Design: `docs/PP_architecture_OSM_first.md`. Rules R1-R6 and the pilot: `docs/PP_rules_and_pilot.md`.
Bot prompt for the residue rows: `docs/PP_Validator_prompt_v2_OSM.md`.

## Setup (once)

```bash
cd ~/Documents/ferro-parking
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest            # all tests should pass
```

Put the input data in `data/raw/` (never committed):
- `greater-london-latest.osm.pbf` from https://download.geofabrik.de/europe/united-kingdom/england/greater-london-latest.osm.pbf
- `all_london_clean.csv`: export of the ALL LONDON (clean) tab
  (https://docs.google.com/spreadsheets/d/1VHtzY1001e0aRSXE6s_-IJU9YioJtjSNZ5WCOt1IO-o/export?format=csv&gid=1850000003)

## Commands

| Step | Command | Status |
|---|---|---|
| 1. Match + route | `python -m ferro_parking match data/raw/greater-london-latest.osm.pbf data/raw/all_london_clean.csv` | built, tested |
| 2-3. Fill (rules R1-R6, dry run, undo, write batch) | `python -m ferro_parking fill --borough Haringey` | next to build |
| Review file for spot checks | `python -m ferro_parking review` | next to build |
| Write + read back | Sheets API writer | to decide |

Outputs go to `data/runs/<date>/`, so nothing is ever overwritten and no `_v2` files are needed.

## Rules

Rules live in `config/rules.toml`, not in code. Change a rule there, add a test in `tests/`, run `python -m pytest`.

## Safety

- The pipeline never edits these columns: Brandon's four (Free Stay Countdown, Ferro Autopay, Parking Charge, Total incl. Ferro Fee), Latitude, Longitude, Place ID, formulas, and the "(as captured)" columns.
- Every write has a dry run and an undo file first, writes Verification Result last, and is read back.
- OSM data (c) OpenStreetMap contributors, ODbL.
