# runs/

One folder per pipeline run, created from a research brief:

    python -m core.pipeline run --brief sample/brief.json --adapter fixture

Each `runs/<run-id>/` holds, today:

- `brief.json`: a byte-for-byte copy of the brief, frozen for this run
- `run.json`: the run id, slug, creation time, the brief's SHA-256, any
  validation flags (for example `UNTESTED_HYPOTHESIS`), and what was
  collected: adapter, mode, item count, and the snapshot's SHA-256
- `sources.jsonl`: one line per collected source item, exactly as the
  adapter returned it, with a SHA-256 of its body
- `triage.jsonl`: one line per item, in the same order: included,
  needs_review, or excluded, with every rule that fired and a one-line
  rationale

`run.json` also counts the triage outcomes and records the SHA-256 of
`triage.jsonl`.

The run id defaults to a slug of the brief title. An existing run folder is
never overwritten; pass `--run-id <new-id>` to start a separate run.

Everything in `runs/` except this README is gitignored, because a run holds
full source text. Deliberate synthetic examples belong under `sample/expected/`.

Planned: the evidence ledger, field questions, the decision record, and the
report.
