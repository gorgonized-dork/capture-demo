# sample/expected/

`report.md` is the report the pipeline writes for the fictional sample, so
you can read the output without running anything. It is generated, not
written by hand: it comes from this command, run from the repository root,

    python -m core.pipeline run --brief sample/brief.json --adapter fixture --proposals sample/proposed_evidence.json --reviews sample/review_log.json --field-notes sample/field_notes.json --decision sample/decision.json

and a test regenerates it and requires the result to match this file
exactly. Everything in it is fictional, like the rest of `sample/`.
