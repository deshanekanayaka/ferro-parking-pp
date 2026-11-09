# Pipeline handover

Repository: https://github.com/tharidu-e/ferro-parking

See [README.md](../README.md#pp-workflow) for the PP workflow and command examples.
Read [PP_rules_and_pilot.md](PP_rules_and_pilot.md) and
[PP_Validator_prompt_v2_OSM.md](PP_Validator_prompt_v2_OSM.md) for evidence rules.
The owner instructions in the active session take precedence over older policy.

Discovery, validation and OSM gap reports never write to Google Sheets. OSM-only
fills do not mark a row finished. Map absence is not evidence of no parking.
Every sheet change needs a fresh plan, dry run, undo file, six checks and independent
second reading. Show counts, samples and rejects and wait for an explicit go.
After applying, independently re-export and require 0 mismatches.

Sheet configuration is in config/sheets.toml. Never print or commit credentials.
Run directories are append-only; completed and personally verified rows are protected.
