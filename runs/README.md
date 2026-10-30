# runs/

One folder per research run, created from a research brief:

    python -m core.runs new sample/brief.json

Each `runs/<slug>/` holds, today:

- `brief.json`: a byte-for-byte copy of the brief, frozen for this run
- `run.json`: the slug, creation time, the brief's SHA-256, and any
  validation flags (for example `UNTESTED_HYPOTHESIS`)

Planned in later build steps: approved queries, raw pulls, triage scores,
extractions, the ledger, and rendered findings.

Raw pulls (`runs/<slug>/raw/`) are gitignored and never committed.
An existing run folder is never overwritten.
