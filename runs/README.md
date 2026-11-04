# runs/

One folder per pipeline run, created from a research brief:

    python -m core.pipeline run --brief sample/brief.json --adapter fixture \
        --proposals sample/proposed_evidence.json --reviews sample/review_log.json \
        --field-notes sample/field_notes.json --decision sample/decision.json

Every flag after `--adapter` is optional, and every input file is only ever
read.

Each `runs/<run-id>/` holds, today:

- `brief.json`: a byte-for-byte copy of the brief, frozen for this run
- `run.json`: the run id, slug, creation time, the brief's SHA-256, any
  validation flags (for example `UNTESTED_HYPOTHESIS`), what was collected,
  the triage, evidence, and question counts, the decision, and the SHA-256
  of every file the run read or wrote
- `sources.jsonl`: one line per collected source item, exactly as the
  adapter returned it, with a SHA-256 of its body
- `triage.jsonl`: one line per item, in the same order: included,
  needs_review, or excluded, with every rule that fired and a one-line
  rationale
- `evidence.jsonl`: the evidence ledger, one line per proposal that passed
  the checks: claim, verbatim excerpt, stance, review status (`PROPOSED`,
  `ACCEPTED`, or `REJECTED`), the review if there is one, and the source's
  hash and triage status
- `refused.jsonl`: every proposal, review, field note, or decision that was
  refused, with a reason code and the original record
- `field_questions.json`: the questions still to ask, why each matters, the
  evidence it links to, and the field-note answer if there is one
- `field_questions.md`: the same questions as a readable page, open ones first
- `decision.json`: the decision a person entered, or `undecided` with the
  reason
- `report.md`: one readable page, written last from the files above, and
  only after its traceability and claim-integrity checks pass. If a check
  fails, no report is written and `run.json` records the failures.

Check a finished run at any time; this writes nothing:

    python -m core.report check runs/<run-id>

`evidence.jsonl` and `refused.jsonl` are written empty when nothing was
proposed or refused.

The run id defaults to a slug of the brief title. An existing run folder is
never overwritten; pass `--run-id <new-id>` to start a separate run.

Everything in `runs/` except this README is gitignored, because a run holds
full source text. Deliberate synthetic examples belong under `sample/expected/`.
