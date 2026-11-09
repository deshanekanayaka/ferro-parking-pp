# PP matching and readiness follow-up

- `README.md`: Document matching priorities, field flags, validator warnings, triage, readiness and replay usage.
- `docs/PP_DISCOVERY_FOLLOWUP.md`: Record the file-by-file changes, measured fixture evidence and pending live-batch acceptance.
- `scripts/replay_discovery_batches.py`: Reconstruct sources from the four original exceptions files, replay the existing pipeline and verify listing counts plus a majority matched.
- `src/ferro_parking/__main__.py`: Register and describe the two new read-only commands.
- `src/ferro_parking/discover.py`: Match Place ID and source URLs first; resolve shared postcode/pin hits by a clear name winner; retain identities and withhold only unparsed/unverified fields with structured flags.
- `src/ferro_parking/policy_fill.py`: Make the obsolete map-absence no-parking builder raise instead of constructing a writeable record.
- `src/ferro_parking/readiness.py`: Count showable and complete rows overall, by borough and by postcode district.
- `src/ferro_parking/sources/__init__.py`: Preserve either Place ID spelling in generic sources and repair only City tariff question marks before digits.
- `src/ferro_parking/triage_blanks.py`: Bucket every blank parking answer using local metadata, optionally attaching raw nearby OSM evidence.
- `src/ferro_parking/validation.py`: Gate optional identity checks; add price-status, charging-hours, cost-type and required identity fields; distinguish warnings from errors.
- `tests/fixtures/discovery_match_cases.json`: Add small explicitly synthetic Place ID, URL and name-disambiguation cases; no full sheet export.
- `tests/test_discovery_followup.py`: Regress matching, parser fallbacks, currency repair, disabled presumed builder and validator rules, including warning-only exit status.
- `tests/test_pp_workflow.py`: Update prior behavior assertions for field-level fallback and an optional identity column.
- `tests/test_readiness_triage.py`: Test both readiness bars, source exceptions, districts, triage buckets, optional local OSM evidence and CSV-only command routing.

## Validation evidence

- Initial regression command `PYTHONPATH=src python -m pytest tests/test_discovery_followup.py -q`: 7 failed, 1 passed against the reported failure paths.
- Final suite: 427 passed with socket connections blocked by tests/conftest.py.
- Four synthetic matching cases replayed through both original and current discover.run: before listed=4, matched=0, exceptions=4; after listed=4, matched=4, exceptions=0. These are not the four live batches.
- Both command smoke tests ran against the available local export: 6,924 rows; 2,451 blank rows triaged; showable=1,060 and complete=782. The original CSV remains an input only.
- No apply, sync-apply, clear-unverified or live-sheet commands were run. No auth was added. The writer, protected-column policy, sync.py, sheets.py and clear_unverified.py are unchanged.

## Original batch acceptance

The following before counts are quoted from the owner's 9 Nov 2026 task. The
corresponding run folders do not exist in this environment; `/home/box/ferro-parking`
is also absent. A local CSV export exists, but has 6,924 rows rather than the
7,607-row reference mentioned in the task. Actual batch results are not inferred
from synthetic fixtures or from sheet rows.

| Batch | Before listed | Before matched | Before exceptions | After listed / matched / exceptions |
|---|---:|---:|---:|---|
| Heathrow | 20 | 0 | 20 | Not measured: source input unavailable |
| LCY | 4 | 0 | 4 | Not measured: source input unavailable |
| NR3 | 125 | 0 | 125 | Not measured: source input unavailable |
| Havering | 27 | 0 | 27 | Not measured: source input unavailable |

The majority-of-each-batch acceptance requirement remains unverified. Keep this PR
in draft until the original inputs are available and the replay passes. Run:

```bash
PYTHONPATH=src python scripts/replay_discovery_batches.py --runs-dir PATH_TO_RUNS --sheet-csv PATH_TO_REFERENCE_EXPORT
```

The replay writes fresh sources.json, normal discover outputs and comparison.json.
It returns success only when each batch has its expected listing count and a
strict majority in matches.csv. It uses the existing postcodes.io client/cache.
No sheet data is read through Google APIs or written.
