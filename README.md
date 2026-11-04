# capture-primitives

A small, auditable research-to-capture pipeline. You give it a research brief
(for example, a capture hypothesis and what would disprove it) and a fixed set
of source items. It is being built to produce a traceable triage record, an evidence
ledger tied to exact sources, questions to validate in the field, and a
decision record that a person owns, not the software.

**Status: early.** The first stages work today: a brief is validated, sources
are collected offline, and each run is saved as a frozen, traceable record.
Triage, evidence review, field questions, the decision record, and the report
are next. See [Implemented and next](#implemented-and-next).

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

Brief and Collect work today. The remaining stages are being built in order.

## Quick start

Python 3.10 or newer should work; developed and tested on Python 3.14. Only
the standard library is used. If your system names it `python3`, use that in
place of `python`.

From the repository root, run the tests:

```bash
python -m unittest
```

Run the sample:

```bash
python -m core.pipeline run --brief sample/brief.json --adapter fixture
```

Expected output:

```
brief    sample/brief.json: valid
adapter  fixture (offline): 10 items
run      runs/weekend-hours-and-branch-visits-in-harrowmere-valley/
wrote    brief.json, run.json, sources.jsonl
```

Running the same command again is refused, so an earlier run is never
overwritten. To run the sample again, give the new run its own id:

```bash
python -m core.pipeline run --brief sample/brief.json --adapter fixture --run-id second-look
```

## What a run produces

```
runs/weekend-hours-and-branch-visits-in-harrowmere-valley/
├── brief.json      the brief, copied byte for byte and frozen for this run
├── run.json        run id, the brief's SHA-256, any flags, what was collected
└── sources.jsonl   every collected item exactly as returned, with a hash of its text
```

Run output stays on your machine: everything in `runs/` except its README is
gitignored, because a run holds full source text.

## The sample

All ten items are invented. Today the pipeline collects and snapshots every
one of them with its exact id. The handling in the right-hand column arrives
with triage and the evidence ledger.

| Source | What it says | Intended handling |
|---|---|---|
| fx-1001, fx-1003 | Northgate and Millbrook branches announce longer weekend hours | Context: a policy change, not proof of impact |
| fx-1002 | Northgate: 1,880 weekend visits in June against 1,410 a year earlier | Supports the hypothesis, for one month at one branch |
| fx-10010 | The same Northgate figures, republished | Possible duplicate; not a second confirmation |
| fx-1004 | Millbrook: about 960 weekend visits a month against 940 | Challenges a district-wide effect |
| fx-1007 | Linden Street, hours unchanged: 1,020 against 1,000 | Comparison point for the branches that changed |
| fx-1008 | The district says visits rose, with no figures and no branch | Kept, but flagged as a claim without figures |
| fx-1005, fx-1006, fx-1009 | A book sale; a 2024 board discussion; car park resurfacing | Set aside, with the reason recorded |

The brief behind the sample is [`sample/brief.json`](sample/brief.json). A
brief has a `title`, a `type` (`hypothesis` or `topic`), a `statement`,
`seed_terms`, and optionally a `disproof` condition, a `scope` (date range,
regions, units), `exclude_terms`, and `questions`.

## Guardrails

**In place today**

- **Missing stays missing.** A field a source leaves out is stored as empty,
  never guessed. `fx-1008` names no branch or region and keeps none.
- **Exact identities.** Source ids are compared whole, never by substring, so
  `fixture:fx-1001` and `fixture:fx-10010` stay two separate items.
- **Untestable hypotheses are flagged.** A hypothesis with no disproof
  condition is accepted but marked `UNTESTED_HYPOTHESIS` for the whole run.
- **Runs are records.** Each run keeps a byte-for-byte copy of its brief with
  a hash, and a run folder is never overwritten.
- **Fail closed.** An invalid brief or a broken source stops the run before
  anything is written. A malformed source record stops the read instead of
  being skipped.
- **The source is chosen explicitly.** The only source today is a local
  fixture file; nothing reaches the network.

**Being built**

- **The software proposes; a person decides.** Evidence enters the ledger as
  `PROPOSED`, and only a person's review promotes it.
- **Quotes must match.** Every accepted claim carries an excerpt that must
  match its source text exactly, or it is rejected.
- **Contradictions stay visible.** Supporting and challenging evidence sit
  side by side. There is no single confidence score.
- **Repeats are not confirmation.** A republished report is marked as a
  possible duplicate, not counted as independent evidence.
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
| Triage with a stated reason for every item | Next | |
| Evidence ledger with human review | Next | |
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
- The pipeline does not write procurement requirements, find stakeholders,
  or make bid decisions.
- Today there is one offline source and no AI step of any kind.
- Every person, organization, place, and figure in the sample is fictional.
  Nothing here describes a real customer, contract, or live government use.

## Repository layout

```
core/       brief validation, run folders, the pipeline command
adapters/   source adapters (an offline fixture today)
sample/     the fictional brief and source items
tests/      the guardrails in place today, written as tests
runs/       run output (gitignored)
config/     empty; reserved
state/      empty; reserved
```
