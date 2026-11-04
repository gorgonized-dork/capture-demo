"""
Pipeline: one command from a research brief to a run folder.

    python -m core.pipeline run --brief sample/brief.json --adapter fixture \\
        --proposals sample/proposed_evidence.json --reviews sample/review_log.json \\
        --field-notes sample/field_notes.json --decision sample/decision.json

Today the pipeline validates the brief, collects source items through the
chosen adapter, writes a snapshot of every item it collected, triages each
one against the brief, builds the evidence ledger from the proposals and the
review log, asks field questions and applies the field notes, records the
decision a person entered (or undecided), and last writes the report from
the files it just wrote, if the report's checks pass.

The adapter is always chosen explicitly. A failure before the run folder is
created (an invalid brief, an unreadable input file, an adapter error) leaves
nothing behind, and an existing run folder is never overwritten. The
proposals, review log, field notes, and decision are only read, never
written. If a report check fails, the run keeps its files, run.json records
the report as blocked with the failures, and no report is written.
"""
import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import brief as briefs
from core import decision, ledger, questions, report, triage
from core.runs import RUNS_DIR, RunError, RunExistsError, create_run

ADAPTERS = {"fixture": FixtureAdapter}
MODE_LABELS = {"fixture": "offline"}
SOURCES_FILE = "sources.jsonl"
TRIAGE_FILE = "triage.jsonl"
EVIDENCE_FILE = "evidence.jsonl"
REFUSED_FILE = "refused.jsonl"
QUESTIONS_FILE = "field_questions.json"
QUESTIONS_MD = "field_questions.md"
DECISION_FILE = "decision.json"
RUN_FILES = ("brief.json", "run.json", SOURCES_FILE, TRIAGE_FILE, EVIDENCE_FILE, REFUSED_FILE,
             QUESTIONS_FILE, QUESTIONS_MD, DECISION_FILE, report.REPORT_FILE)


class PipelineError(Exception):
    """The pipeline stopped before creating a run folder."""


def run(brief_path, adapter, runs_dir=RUNS_DIR, run_id=None, proposals_path=None,
        reviews_path=None, notes_path=None, decision_path=None):
    """Brief -> collect -> triage -> evidence -> questions -> decision, into a new run folder."""
    brief = briefs.load(brief_path)
    result = briefs.validate(brief)
    if not result.ok:
        raise PipelineError("brief is invalid: " + "; ".join(result.errors))
    proposals = ledger.load_records(proposals_path, "proposals") if proposals_path else []
    reviews = ledger.load_records(reviews_path, "reviews") if reviews_path else []
    notes = ledger.load_records(notes_path, "field notes") if notes_path else []
    entered = decision.load(decision_path) if decision_path else None

    # Collect before the folder exists, so a failing adapter leaves nothing behind.
    try:
        items = adapter.collect()
    except (OSError, ValueError) as e:
        raise PipelineError(f"adapter '{adapter.name}' failed: {e}") from None
    triaged = triage.triage(items, brief)
    evidence, ledger_refused = ledger.build(proposals, reviews, items, triaged)
    asked = questions.ask(brief, items, triaged, evidence)
    notes_refused = questions.answer(asked, notes)
    recorded, decision_refused = decision.record(entered, evidence, asked)
    refused = ledger_refused + notes_refused + decision_refused

    run_dir = create_run(brief_path, runs_dir, run_id)
    snapshot = [dict(dataclasses.asdict(item),
                     body_sha256=hashlib.sha256(item.body.encode("utf-8")).hexdigest())
                for item in items]
    snapshot_sha256 = write_jsonl(run_dir / SOURCES_FILE, snapshot)
    triage_sha256 = write_jsonl(run_dir / TRIAGE_FILE, triaged)
    evidence_sha256 = write_jsonl(run_dir / EVIDENCE_FILE, evidence)
    refused_sha256 = write_jsonl(run_dir / REFUSED_FILE, refused)
    questions_sha256 = write_json(run_dir / QUESTIONS_FILE, asked)
    questions_md_sha256 = write_text(run_dir / QUESTIONS_MD, questions.render_markdown(asked))
    decision_sha256 = write_json(run_dir / DECISION_FILE, recorded)

    record_path = run_dir / "run.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["collection"] = {
        "adapter": adapter.name,
        "mode": adapter.mode,
        "items": len(items),
        "sources_file": SOURCES_FILE,
        "sources_sha256": snapshot_sha256,
    }
    record["triage"] = dict(triage.counts(triaged),
                            triage_file=TRIAGE_FILE, triage_sha256=triage_sha256)
    record["evidence"] = dict(ledger.counts(evidence, ledger_refused),
                              proposals_sha256=file_sha256(proposals_path),
                              reviews_sha256=file_sha256(reviews_path),
                              evidence_file=EVIDENCE_FILE, evidence_sha256=evidence_sha256,
                              refused_file=REFUSED_FILE, refused_sha256=refused_sha256)
    record["questions"] = dict(questions.counts(asked), refused_notes=len(notes_refused),
                               field_notes_sha256=file_sha256(notes_path),
                               questions_file=QUESTIONS_FILE, questions_sha256=questions_sha256,
                               questions_md_file=QUESTIONS_MD, questions_md_sha256=questions_md_sha256)
    record["decision"] = {
        "disposition": recorded["disposition"],
        "decision_entered": recorded["decision_entered"],
        "refused": bool(decision_refused),
        "decision_input_sha256": file_sha256(decision_path),
        "decision_file": DECISION_FILE,
        "decision_sha256": decision_sha256,
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    # The report is rendered last, from the files just written, and only if its checks pass.
    try:
        report_sha256 = report.write(run_dir)
    except report.ReportBlocked as blocked:
        record["report"] = {"status": "blocked", "failures": blocked.failures}
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        raise
    record["report"] = {"status": "written", "checks": "passed",
                        "report_file": report.REPORT_FILE, "report_sha256": report_sha256}
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return run_dir


def write_jsonl(path, rows):
    """Write one JSON object per line. Returns the file's SHA-256."""
    return write_text(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def write_json(path, value):
    """Write one indented JSON document. Returns the file's SHA-256."""
    return write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def write_text(path, text):
    """Write UTF-8 text with LF line endings. Returns the file's SHA-256."""
    data = text.encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    """SHA-256 of an input file, or None when no file was given."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None


def display(path):
    """A path relative to the working directory when possible, with forward slashes."""
    path = Path(path).resolve()
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m core.pipeline",
                                 description="Run the pipeline on a research brief.")
    sub = ap.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("run", help="brief -> collect -> triage -> evidence -> questions -> decision -> report")
    cmd.add_argument("--brief", type=Path, required=True, help="research brief (JSON)")
    cmd.add_argument("--adapter", choices=sorted(ADAPTERS), required=True,
                     help="source adapter; 'fixture' reads sample/items.json offline")
    cmd.add_argument("--proposals", type=Path,
                     help="evidence proposals (JSON array); read only")
    cmd.add_argument("--reviews", type=Path,
                     help="review log of human decisions (JSON array); read only")
    cmd.add_argument("--field-notes", type=Path,
                     help="field notes answering field questions (JSON array); read only")
    cmd.add_argument("--decision", type=Path,
                     help="the decision a person entered (JSON object); read only")
    cmd.add_argument("--run-id", help="run folder name (default: slug of the brief title)")
    cmd.add_argument("--runs-dir", type=Path, default=RUNS_DIR,
                     help="where run folders are created (default: runs/)")
    args = ap.parse_args(argv)

    try:
        run_dir = run(args.brief, ADAPTERS[args.adapter](), args.runs_dir, args.run_id,
                      args.proposals, args.reviews, args.field_notes, args.decision)
    except RunExistsError as e:
        print(f"ERROR  {e}")
        print("       pass --run-id <new-id> to start a separate run")
        return 1
    except report.ReportBlocked as blocked:
        print("ERROR  report blocked; no report was written. Failed checks:")
        for failure in blocked.failures:
            print(f"       {failure['code']}: {failure['detail']}")
        return 1
    except (OSError, briefs.BriefError, ledger.LedgerError, decision.DecisionError,
            RunError, PipelineError) as e:
        print(f"ERROR  {e}")
        return 1

    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    collection = record["collection"]
    print(f"brief    {display(args.brief)}: valid")
    for flag in record["flags"]:
        print(f"FLAG     {flag}: {briefs.FLAG_MEANINGS[flag]}")
    mode = MODE_LABELS.get(collection["mode"], collection["mode"])
    print(f"adapter  {collection['adapter']} ({mode}): {collection['items']} items")
    screened = record["triage"]
    print(f"triage   {screened[triage.INCLUDED]} included, {screened[triage.NEEDS_REVIEW]} to review, "
          f"{screened[triage.EXCLUDED]} excluded")
    found = record["evidence"]
    if found["proposals_sha256"] is None:
        print("evidence no proposals given")
    else:
        print(f"evidence {found['in_ledger']} in ledger: {found['accepted']} accepted, "
              f"{found['rejected']} rejected, {found['awaiting_review']} awaiting review; "
              f"{found['refused']} refused")
    asked = record["questions"]
    print(f"questions {asked['asked']} asked: {asked['answered']} answered, {asked['open']} open")
    recorded = json.loads((run_dir / DECISION_FILE).read_text(encoding="utf-8"))
    if recorded["decision_entered"]:
        print(f"decision {recorded['disposition']} ({recorded['owner_role']}, {recorded['date']})")
    else:
        print(f"decision undecided: {recorded['reason']}")
    print(f"run      {display(run_dir)}/")
    print(f"report   {display(run_dir / report.REPORT_FILE)} (traceability and claim checks passed)")
    print(f"wrote    {', '.join(sorted(p.name for p in run_dir.iterdir()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
