# capture-demo

A small, auditable research-to-capture pipeline. You give it a research brief
(for example, a capture hypothesis and what would disprove it) and a fixed set
of source items. It produces a traceable triage record, an evidence ledger in
which a person, not the software, accepts or rejects every claim, questions to
take to the field, a decision record that a person owns, and a one-page
report that is checked against the run's records before it is written.

**Status: MVP.** Every stage works on the offline, fictional sample. Live data
sources and AI-assisted extraction are not built. See
[Implemented and next](#implemented-and-next).

Everything runs offline on fictional sample data. No credentials, no network,
nothing to install beyond Python. To see the output without running anything,
read [the sample report](sample/expected/report.md).

## Why this matters for capture

Capture starts before an opportunity is real: a news item, a budget line, a
pilot that might grow. Teams decide early whether to spend effort pursuing it,
usually on a handful of public signals. The common failure is not too little
information. It is conclusions that outrun the evidence: the same report
counted twice as two confirmations, one good month read as a trend, a missing
number filled with a plausible one, a machine's summary taken as a finding.

This pipeline is built to keep those steps honest. A capture hypothesis is
written down with what would disprove it. Every claim stays tied to the exact
source it came from. Gaps become questions to take to the field, not guesses.
The pursue-or-pass call stays with a person, on the record.

The sample plays this out with invented data. A fictional vendor hears that
the fictional Harrowmere Valley Library District is trialling longer weekend
hours. If the trial is working, the district may extend it to more branches,
and that could become an opportunity worth pursuing. Before committing
capture effort, the vendor writes down the hypothesis (longer hours raised
weekend visits) and what would disprove it, then checks it against ten short,
invented news bulletins. Some support it, one contradicts it, one repeats
another, and one claims a rise without any figures. A field visit turns up
another possible cause for the one rise. The fictional capture lead decides
"defer": mixed evidence, thin comparison data, and specific questions still
to ask.

## The path

    Brief -> Collect -> Triage -> Review evidence -> Field questions -> Human decision -> Report

Every stage works today, on the offline sample.

## Read the sample report

[`sample/expected/report.md`](sample/expected/report.md) is the report the
sample produces; a test keeps it identical to what the code writes. In about
a minute:

1. **The bottom line comes first.** The status table shows **Defer**, entered
   by a capture lead, and says the brief's disproof test is not yet checked
   (Q-DISPROOF is open).
2. **One source supports the hypothesis, counted once.** EV-002 quotes
   `fixture:fx-1002`: 1,880 weekend visits against 1,410. Its republication,
   `fixture:fx-10010` (EV-008), was rejected by the reviewer and is listed
   under Not counted.
3. **A challenge sits beside it.** EV-005 (`fixture:fx-1004`): Millbrook also
   extended its hours and stayed nearly flat. No score combines the two.
4. **Gaps become questions, not guesses.** Q-SECOND-SOURCE, Q-DISPROOF, and
   Q-UNIT-STONECROSS-BRANCH are still open. A field note on
   Q-ALTERNATE-EV-002 reports a new housing estate near Northgate.
5. **What was refused stays on the record.** EV-009 misquoted 1,880 as 1,980
   and EV-010 tried to mark itself accepted; both appear under Not counted,
   with their reasons.

## Quick start

Python 3.10 or newer should work; developed and tested on Python 3.14. Only
the standard library is used. If your system names it `python3`, use that in
place of `python`.

Get the code:

```bash
git clone https://github.com/gorgonized-dork/capture-demo.git
```

```bash
cd capture-demo
```

Run the tests:

```bash
python -m unittest
```

Run the sample:

```bash
python -m core.pipeline run --brief sample/brief.json --adapter fixture --proposals sample/proposed_evidence.json --reviews sample/review_log.json --field-notes sample/field_notes.json --decision sample/decision.json
```

Expected output:

```
brief    sample/brief.json: valid
adapter  fixture (offline): 10 items
triage   5 included, 2 to review, 3 excluded
evidence 8 in ledger: 4 accepted, 1 rejected, 3 awaiting review; 2 refused
questions 9 asked: 3 answered, 6 open
decision defer (capture lead, 2025-12-05)
run      runs/weekend-hours-and-branch-visits-in-harrowmere-valley/
report   runs/weekend-hours-and-branch-visits-in-harrowmere-valley/report.md (traceability and claim checks passed)
wrote    brief.json, decision.json, evidence.jsonl, field_questions.json, field_questions.md, refused.jsonl, report.md, run.json, sources.jsonl, triage.jsonl
```

Check the finished run. This writes nothing; it confirms every file still
matches the hash recorded when the run was made and that the report is
unchanged:

```bash
python -m core.report check runs/weekend-hours-and-branch-visits-in-harrowmere-valley
```

Every flag after `--adapter` is optional, and every input file is only ever
read. Without `--decision`, the run records "undecided". Running the same
command again is refused, so an earlier run is never overwritten. To run the
sample again, give the new run its own id:

```bash
python -m core.pipeline run --brief sample/brief.json --adapter fixture --proposals sample/proposed_evidence.json --reviews sample/review_log.json --field-notes sample/field_notes.json --decision sample/decision.json --run-id second-look
```

## What a run produces

```
runs/weekend-hours-and-branch-visits-in-harrowmere-valley/
├── brief.json            the brief, copied byte for byte and frozen for this run
├── run.json              run id, flags, counts, and the SHA-256 of every file read or written
├── sources.jsonl         every collected item exactly as returned, with a hash of its text
├── triage.jsonl          every item's triage status, each rule that fired, and why
├── evidence.jsonl        the evidence ledger: claim, verbatim excerpt, stance, review status
├── refused.jsonl         every proposal, review, field note, or decision refused, and why
├── field_questions.json  questions still to ask, why each matters, and any field-note answer
├── field_questions.md    the same questions as a readable page, open ones first
├── decision.json         the decision a person entered, or "undecided" and why
└── report.md             one readable page, written last, after its checks pass
```

Run output stays on your machine: everything in `runs/` except its README is
gitignored, because a run holds full source text.

## The evidence ledger

Evidence comes from two inputs with two different roles:

- **Proposals** ([`sample/proposed_evidence.json`](sample/proposed_evidence.json)):
  claims, each with a verbatim excerpt and a stance (supports, challenges,
  context, or unresolved). In the sample they are written by hand, standing
  in for an extractor. A proposal can never set its own status.
- **The review log** ([`sample/review_log.json`](sample/review_log.json)):
  decisions by a person, named by role, to accept or reject one piece of
  evidence. It is the only way out of `PROPOSED`, and the pipeline only ever
  reads it.

Every proposal gets an id from its position (EV-001, EV-002, ...). The ledger
refuses any proposal whose excerpt does not appear word for word in its
source, whose source was excluded at triage, or that tries to set its own
status, and it records why. A review counts only if its fingerprint matches
the evidence's current content, so an edited claim never inherits an old
review.

`ACCEPTED` means a person checked that the excerpt says what the claim says
and that the stance fits. It does not make the claim true.

## Field questions and the decision

The pipeline asks; it never answers. Field questions come from the brief's
own questions and from fixed rules over accepted evidence: the brief's
disproof test, the baseline behind any comparison, other possible causes of
a supporting finding, the need for a second independent source, claims that
cannot be checked as stated, sources with no region or unit, and units in
scope that no evidence covers. Each question says why it matters and which
evidence it links to.

Only a field note ([`sample/field_notes.json`](sample/field_notes.json)) can
answer a question. A note names its respondent by role, never by name, and
says how the answer was obtained. Answers stay with their questions, labeled
as field notes; they never become sources or evidence.

The decision ([`sample/decision.json`](sample/decision.json)) is entered by a
person: pursue, defer, pass, or undecided, with their role, the date, a
rationale, the evidence it rests on, and the questions still open. It may
rest only on accepted evidence and list only open questions, and it carries
no score or probability. Anything wrong refuses the whole decision, and the
run records "undecided" instead.

## The report

The report is written last, from the run's files rather than from memory,
and only after two checks pass:

- **Traceability:** every file matches the SHA-256 recorded in `run.json`,
  every evidence, source, and question id in the report resolves to a record
  in the run, and every accepted excerpt appears word for word in its source.
- **Claim integrity:** the findings name only accepted evidence, and the
  decision shown is the one recorded.

A failed check is reported, not fixed: no report is written, and `run.json`
records the failures. Missing source fields print as "unverified", and each
source is counted once.

## The sample

All ten items are invented. The pipeline collects every one of them with its
exact id, triages it against the brief, and builds the evidence ledger from
ten hand-written proposals and five fictional review decisions. Two of the
proposals are wrong on purpose, to show the ledger refusing them.

| Source | What it says | Triage | Evidence |
|---|---|---|---|
| fx-1001, fx-1003 | Northgate and Millbrook branches announce longer weekend hours | Included | EV-001, EV-004: context, awaiting review |
| fx-1002 | Northgate: 1,880 weekend visits in June against 1,410 a year earlier | Included; its repeat is noted | EV-002: supports, accepted. EV-003: context (one month only), awaiting review. EV-009: refused, misquotes the figure as 1,980 |
| fx-10010 | The same Northgate figures, republished | To review: same figures as fx-1002 | EV-008: supports, rejected by the reviewer as not independent |
| fx-1004 | Millbrook: about 960 weekend visits a month against 940 | Included | EV-005: challenges, accepted. EV-010: refused, tried to mark itself accepted |
| fx-1007 | Linden Street, hours unchanged: 1,020 against 1,000 | Included | EV-006: context, accepted |
| fx-1008 | The district says visits rose, with no figures and no branch | To review: no branch or region given | EV-007: unresolved, accepted as a claim without figures |
| fx-1005, fx-1006, fx-1009 | A book sale; a 2024 board discussion; car park resurfacing | Excluded: exclude term; dated 2024; no seed term | None; set aside at triage |

From the accepted evidence the pipeline raises nine field questions,
including the baseline behind each comparison, whether the brief's disproof
condition holds, what else could explain Northgate's rise, and what
Stonecross Branch's records show. Three fictional field notes answer three of
them; one reports a new housing estate near Northgate, a possible other cause
of its rise. The fictional capture lead's decision is "defer", resting on
EV-002, EV-005, and EV-006, with three questions still open. It is there to
show the shape of the record and is not a procurement recommendation.

The brief behind the sample is [`sample/brief.json`](sample/brief.json). A
brief has a `title`, a `type` (`hypothesis` or `topic`), a `statement`,
`seed_terms`, and optionally a `disproof` condition, a `scope` (date range,
regions, units), `exclude_terms`, and `questions`.

## Guardrails

Each of these is enforced in code and covered by the tests.

- **The software proposes; a person decides.** Evidence enters the ledger
  only as `PROPOSED`. A proposal that sets its own status is refused
  (EV-010). Only the review log, written by a person, accepts or rejects,
  and a review counts only for the exact content it reviewed.
- **A person owns the decision.** Pursue, defer, pass, or undecided is
  entered by a person and may rest only on accepted evidence. With no
  decision, or a refused one, the run records "undecided". There is no
  win-probability score; a decision that carries one is refused.
- **The software asks; it never answers.** Field questions start open, and
  only a field note can answer one. Field notes name respondents by role and
  never become sources or evidence.
- **The report cannot say more than the record.** It is written from the
  run's files, only after its traceability and claim-integrity checks pass,
  and `python -m core.report check` re-verifies a finished run at any time.
- **Quotes must match.** Every claim carries an excerpt that must appear word
  for word in its source, or the proposal is refused. One changed digit is
  enough (EV-009).
- **Repeats are not confirmation.** Triage flags repeated figures, the ledger
  marks evidence from a repeating source as not independent (EV-008), and
  the report counts each source once.
- **Contradictions stay visible.** Supporting and challenging evidence sit
  side by side (EV-002 and EV-005). There is no combined score.
- **Missing stays missing.** A field a source leaves out is stored as empty,
  never guessed, and the report prints it as "unverified". `fx-1008` names no
  branch or region; triage sends it to review, and a field question asks
  which branches it covers.
- **Every item gets a recorded reason.** Triage includes, excludes, or sends
  each item to review, and records every rule that fired. Excluded items keep
  their records, so nothing disappears silently.
- **Exact identities.** Source ids are compared whole, never by substring, so
  `fixture:fx-1001` and `fixture:fx-10010` stay two separate items.
- **Untestable hypotheses are flagged.** A hypothesis with no disproof
  condition is accepted but marked `UNTESTED_HYPOTHESIS` for the whole run,
  a field question asks what would disprove it, and the report says it is
  untested.
- **Runs are records.** Each run keeps a byte-for-byte copy of its brief and
  the hash of every file it read or wrote. A run folder is never overwritten,
  and no input file is ever written to.
- **Fail closed.** An invalid brief, an unreadable input file, or a broken
  source stops the run before anything is written. A malformed source record
  stops the read instead of being skipped.
- **The source is chosen explicitly.** The only source today is a local
  fixture file; nothing reaches the network.

## Implemented and next

| Stage | Status | Where |
|---|---|---|
| Research brief: format and validation | Implemented | `core/brief.py` |
| Collect: offline fixture source | Implemented | `adapters/` |
| One command: run folder and source snapshot | Implemented | `core/pipeline.py`, `core/runs.py` |
| Triage with a stated reason for every item | Implemented | `core/triage.py` |
| Evidence ledger with human review | Implemented | `core/ledger.py` |
| Field questions | Implemented | `core/questions.py` |
| Human decision record | Implemented | `core/decision.py` |
| Report with traceability and claim-integrity checks | Implemented | `core/report.py` |

Not in this version: live data sources, AI-assisted extraction, dashboards,
databases, or multi-user review. A live public-source adapter (the DVIDS
public API is the first candidate) and an AI extraction step whose citations
are checked against the source are possible later additions. Neither is
needed for the pipeline to make its point.

## Limits

- Screening by keywords is a way to sort candidates, not proof of relevance.
  The evidence shows what sources say; it does not establish that one thing
  caused another.
- `ACCEPTED` means a person found that the excerpt supports the claim as
  worded. It is not a finding that the claim is true.
- The report's checks show that the report matches the run's records. They
  do not show that the records are true.
- Field questions come from fixed rules. They catch known kinds of gap, not
  every gap. A field-note answer records what a respondent said; it is not a
  verified fact.
- Duplicate detection compares figures. It misses a reworded repeat that
  gives no figures, and it flags two different reports that quote the same
  figures; either way, the cost is a review, never a silent drop.
- The pipeline does not write procurement requirements, find stakeholders,
  or make bid decisions.
- Today there is one offline source and no AI step of any kind. The sample's
  evidence proposals are written by hand; nothing extracts evidence
  automatically.
- Every person, organization, place, and figure in the sample is fictional,
  and the sample decision is not a procurement recommendation. Nothing here
  describes a real customer, contract, or live government use.

## Repository layout

```
core/       brief, run folders, triage, evidence ledger, field questions, decision, report, the pipeline command
adapters/   source adapters (an offline fixture today)
sample/     the fictional brief, source items, proposals, review log, field notes, and decision
sample/expected/  the report the sample produces, kept identical by a test
tests/      the guardrails above, written as tests
runs/       run output (gitignored)
config/     empty; reserved
state/      empty; reserved
```

Keep real field notes, reviews, and decisions under `private/`, which is
gitignored.

## License

MIT. See [`LICENSE`](LICENSE).
