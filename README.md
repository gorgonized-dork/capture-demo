# capture-primitives

A small, auditable research-to-capture pipeline. You give it a research brief
(for example, a capture hypothesis and what would disprove it) and a fixed set
of source items. Today it produces a traceable triage record and an evidence
ledger in which a person, not the software, accepts or rejects every claim.
It is being built to add questions to validate in the field, a decision
record that a person owns, and a one-page report.

**Status: early.** The first stages work today: a brief is validated, sources
are collected offline, every item is triaged with its reasons recorded,
proposed evidence is checked against its source and waits for a person's
review, and each run is saved as a frozen, traceable record. Field questions,
the decision record, and the report are next. See
[Implemented and next](#implemented-and-next).

Everything runs offline on fictional sample data. No credentials, no network,
nothing to install beyond Python.

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
another, and one claims a rise without any figures. The answer the sample is
built to reach is "not yet": mixed evidence, thin comparison data, and
specific questions to ask before deciding.

## The path

    Brief -> Collect -> Triage -> Review evidence -> Field questions -> Human decision -> Report

Brief, Collect, Triage, and Review evidence work today. The remaining stages
are being built in order.

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
python -m core.pipeline run --brief sample/brief.json --adapter fixture --proposals sample/proposed_evidence.json --reviews sample/review_log.json
```

Expected output:

```
brief    sample/brief.json: valid
adapter  fixture (offline): 10 items
triage   5 included, 2 to review, 3 excluded
evidence 8 in ledger: 4 accepted, 1 rejected, 3 awaiting review; 2 refused
run      runs/weekend-hours-and-branch-visits-in-harrowmere-valley/
wrote    brief.json, evidence.jsonl, refused.jsonl, run.json, sources.jsonl, triage.jsonl
```

`--proposals` and `--reviews` are optional; without them the run stops after
triage. Running the same command again is refused, so an earlier run is never
overwritten. To run the sample again, give the new run its own id:

```bash
python -m core.pipeline run --brief sample/brief.json --adapter fixture --proposals sample/proposed_evidence.json --reviews sample/review_log.json --run-id second-look
```

## What a run produces

```
runs/weekend-hours-and-branch-visits-in-harrowmere-valley/
├── brief.json      the brief, copied byte for byte and frozen for this run
├── run.json        run id, flags, counts, and the SHA-256 of every file read or written
├── sources.jsonl   every collected item exactly as returned, with a hash of its text
├── triage.jsonl    every item's triage status, each rule that fired, and why
├── evidence.jsonl  the evidence ledger: claim, verbatim excerpt, stance, review status
└── refused.jsonl   every proposal or review the ledger refused, and why
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

The brief behind the sample is [`sample/brief.json`](sample/brief.json). A
brief has a `title`, a `type` (`hypothesis` or `topic`), a `statement`,
`seed_terms`, and optionally a `disproof` condition, a `scope` (date range,
regions, units), `exclude_terms`, and `questions`.

## Guardrails

**In place today**

- **The software proposes; a person decides.** Evidence enters the ledger
  only as `PROPOSED`. A proposal that sets its own status is refused
  (EV-010). Only the review log, written by a person, accepts or rejects,
  and a review counts only for the exact content it reviewed.
- **Quotes must match.** Every claim carries an excerpt that must appear word
  for word in its source, or the proposal is refused. One changed digit is
  enough (EV-009).
- **Contradictions stay visible.** Supporting and challenging evidence sit
  side by side (EV-002 and EV-005). There is no combined score.
- **Missing stays missing.** A field a source leaves out is stored as empty,
  never guessed. `fx-1008` names no branch or region and keeps none; triage
  sends it to review instead of dropping it.
- **Every item gets a recorded reason.** Triage includes, excludes, or sends
  each item to review, and records every rule that fired. Excluded items keep
  their records, so nothing disappears silently.
- **Exact identities.** Source ids are compared whole, never by substring, so
  `fixture:fx-1001` and `fixture:fx-10010` stay two separate items.
- **Untestable hypotheses are flagged.** A hypothesis with no disproof
  condition is accepted but marked `UNTESTED_HYPOTHESIS` for the whole run.
- **Runs are records.** Each run keeps a byte-for-byte copy of its brief and
  the hash of every file it read or wrote. A run folder is never overwritten,
  and the proposals and review log are never written to.
- **Fail closed.** An invalid brief, an unreadable proposals or review file,
  or a broken source stops the run before anything is written. A malformed
  source record stops the read instead of being skipped.
- **The source is chosen explicitly.** The only source today is a local
  fixture file; nothing reaches the network.

**Being built**

- **Repeats are not confirmation.** Triage flags repeated figures, and the
  ledger marks evidence from a repeating source as not independent (EV-008).
  The report will count it once.
- **A person owns the decision.** Pursue, defer, pass, or undecided is
  entered by a person, with the evidence it rests on. There is no
  win-probability score and no automatic bid decision. If no decision has
  been entered, the report says "undecided".

## Implemented and next

| Stage | Status | Where |
|---|---|---|
| Research brief: format and validation | Implemented | `core/brief.py` |
| Collect: offline fixture source | Implemented | `adapters/` |
| One command: run folder and source snapshot | Implemented | `core/pipeline.py`, `core/runs.py` |
| Triage with a stated reason for every item | Implemented | `core/triage.py` |
| Evidence ledger with human review | Implemented | `core/ledger.py` |
| Field questions | Next | |
| Human decision record | Next | |
| Report | Next | |

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
- Duplicate detection compares figures. It misses a reworded repeat that
  gives no figures, and it flags two different reports that quote the same
  figures; either way, the cost is a review, never a silent drop.
- The pipeline does not write procurement requirements, find stakeholders,
  or make bid decisions.
- Today there is one offline source and no AI step of any kind. The sample's
  evidence proposals are written by hand; nothing extracts evidence
  automatically.
- Every person, organization, place, and figure in the sample is fictional.
  Nothing here describes a real customer, contract, or live government use.

## Repository layout

```
core/       brief validation, run folders, triage, the evidence ledger, the pipeline command
adapters/   source adapters (an offline fixture today)
sample/     the fictional brief, source items, evidence proposals, and review log
tests/      the guardrails in place today, written as tests
runs/       run output (gitignored)
config/     empty; reserved
state/      empty; reserved
```
