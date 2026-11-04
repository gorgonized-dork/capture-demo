"""
Report: one readable page, written from the run folder's files.

The report is rendered from what the run recorded on disk, never from
memory, and is written only after two checks pass:

    traceability     every file matches the SHA-256 recorded in run.json,
                     every evidence, source, and question id in the report
                     resolves to a record in the run, and every accepted
                     excerpt appears word for word in its source
    claim integrity  the findings name only accepted evidence, and the
                     decision shown is the one recorded

A failed check is reported, not fixed: no report is written. Missing source
fields print as "unverified", and each source is counted once.

Usage:  python -m core.report check <run-dir>
        Re-checks a finished run and its report without writing anything.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPORT_FILE = "report.md"

HASH_MISMATCH = "HASH_MISMATCH"
UNRESOLVED_ID = "UNRESOLVED_ID"
QUOTE_NOT_IN_SOURCE = "QUOTE_NOT_IN_SOURCE"
FINDING_NOT_ACCEPTED = "FINDING_NOT_ACCEPTED"
DECISION_MISMATCH = "DECISION_MISMATCH"
REPORT_CHANGED = "REPORT_CHANGED"

EVIDENCE_ID_RE = re.compile(r"\bEV-\d{3,}\b")
QUESTION_ID_RE = re.compile(r"\bQ-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
STANCES = (("supports", "Supports"), ("challenges", "Challenges"),
           ("context", "Context"), ("unresolved", "Unresolved"))


class ReportBlocked(Exception):
    """A check failed, so no report was written."""

    def __init__(self, failures):
        self.failures = failures
        super().__init__("report blocked: " + "; ".join(f"{f['code']} {f['detail']}" for f in failures))


def load_run(run_dir):
    """Read everything the report is built from, from the run folder's files."""
    d = Path(run_dir)
    return {
        "run": _json(d / "run.json"),
        "brief": _json(d / "brief.json"),
        "sources": _jsonl(d / "sources.jsonl"),
        "triage": _jsonl(d / "triage.jsonl"),
        "evidence": _jsonl(d / "evidence.jsonl"),
        "refused": _jsonl(d / "refused.jsonl"),
        "questions": _json(d / "field_questions.json"),
        "decision": _json(d / "decision.json"),
    }


def write(run_dir):
    """Render, check, and write report.md. Returns its SHA-256, or raises ReportBlocked."""
    run = load_run(run_dir)
    text = render(run)
    failures = check(run_dir, run, text)
    if failures:
        raise ReportBlocked(failures)
    data = text.encode("utf-8")
    (Path(run_dir) / REPORT_FILE).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def verify(run_dir):
    """Re-check a finished run: hashes, ids, quotes, and an unchanged report. Writes nothing."""
    run = load_run(run_dir)
    text = render(run)
    failures = check(run_dir, run, text)
    path = Path(run_dir) / REPORT_FILE
    if not path.exists():
        failures.append(_failure(REPORT_CHANGED, f"{REPORT_FILE} is missing"))
    elif path.read_bytes() != text.encode("utf-8"):
        failures.append(_failure(REPORT_CHANGED, f"{REPORT_FILE} differs from a fresh render of the run"))
    return failures


def render(run):
    r, brief, decision = run["run"], run["brief"], run["decision"]
    sources = {s["source_id"]: s for s in run["sources"]}
    screened = {t["source_id"]: t for t in run["triage"]}
    evidence = {e["evidence_id"]: e for e in run["evidence"]}
    accepted = [e for e in run["evidence"] if e["review_status"] == "ACCEPTED"]
    asked = run["questions"]
    still_open = [q for q in asked if q["status"] == "open"]
    answered = [q for q in asked if q["status"] == "answered"]
    counted, screen = r["evidence"], r["triage"]
    disposition = decision["disposition"].capitalize()

    if decision["decision_entered"]:
        decided = f"**{disposition}**, entered by {decision['owner_role']} on {decision['date']}"
    else:
        decided = f"**Undecided**: {decision['reason']}"

    lines = [f"# {brief['title']}", "",
             f"Run `{r['run_id']}`, generated from the run's files. Every finding cites the evidence (EV-...) "
             "and the source it rests on, and every id in this report resolves to a record in the run folder. "
             "The report shows what sources say and what a person decided; it does not establish what caused what.",
             "", "| | |", "|---|---|",
             f"| Decision | {decided} |",
             f"| Hypothesis test | {_test_status(brief, r, asked)} |",
             f"| Evidence | {counted['accepted']} accepted, {counted['rejected']} rejected, "
             f"{counted['awaiting_review']} awaiting review, {counted['refused']} refused |",
             f"| Sources | {r['collection']['items']} collected: {screen['included']} included, "
             f"{screen['needs_review']} to review, {screen['excluded']} excluded |",
             f"| Field questions | {len(asked)} asked: {len(answered)} answered, {len(still_open)} open |", ""]

    hypothesis = brief["type"] == "hypothesis"
    lines += ["## Hypothesis" if hypothesis else "## Topic", "", f"> {brief['statement']}", ""]
    if hypothesis:
        disproof = (brief.get("disproof") or "").strip()
        lines += [f'Disproof condition: "{disproof}"' if disproof
                  else "Disproof condition: none given. This hypothesis is untested.", ""]
    lines += [f"Scope: {_scope(brief.get('scope') or {})}.", ""]

    lines += ["## Decision", ""]
    if decision["decision_entered"]:
        rests = ", ".join(f"{i} ({evidence.get(i, {}).get('source_id', 'unknown source')})"
                          for i in decision["supporting_evidence_ids"])
        lines += [f"**{disposition}**, entered by {decision['owner_role']} on {decision['date']}.", "",
                  f"Rationale, as entered: {decision['rationale']}", "",
                  f"- Rests on: {rests or 'no evidence cited'}",
                  f"- Left open: {', '.join(decision['open_questions']) or 'none'}"]
        if decision.get("note"):
            lines.append(f"- Note: {decision['note']}")
    else:
        lines.append(f"**Undecided.** Reason: {decision['reason']}. The software never enters a decision.")

    lines += ["", "## Findings", "",
              "Accepted evidence only. Each source is counted once; a source that repeats another's "
              "figures is not counted again.", ""]
    for stance, heading in STANCES:
        group = [e for e in accepted if e["stance"] == stance]
        n = len({e["source_id"] for e in group if e["independent"]})
        lines += [f"### {heading}: {n} independent source{'' if n == 1 else 's'}", ""]
        if not group:
            lines += ["None.", ""]
        for e in group:
            # A source missing from the snapshot renders as unverified; the checks then block the report.
            source, review = sources.get(e["source_id"], {}), e["review"]
            where = (f"{source.get('unit') or 'unit unverified'}, "
                     f"{source.get('region') or 'region unverified'}, {source.get('date') or 'date unverified'}")
            lines += [f"- **{e['evidence_id']}** from {e['source_id']} ({where})",
                      f"  - Claim: {e['claim']}",
                      f'  - Excerpt: "{e["verbatim_excerpt"]}"',
                      f"  - Accepted by {review['reviewer_role']} on {review['date']}"
                      + (f": {review['note']}" if review.get("note") else "")]
            if not e["independent"]:
                lines.append(f"  - Repeats {', '.join(e['source_possible_duplicate_of'])}; "
                             "not counted as a separate source")
        if group:
            lines.append("")

    lines += [f"## Field questions: {len(still_open)} open, {len(answered)} answered", "", "### Open", ""]
    for q in still_open:
        linked = f" ({', '.join(q['linked_evidence_ids'])})" if q["linked_evidence_ids"] else ""
        lines.append(f"- **{q['question_id']}**: {q['question']}{linked}")
    if not still_open:
        lines.append("None.")
    lines += ["", "### Answered by field notes (not published sources)", ""]
    for q in answered:
        a = q["answer"]
        lines += [f"- **{q['question_id']}**: {q['question']}",
                  f"  - Answer: {a['text']} ({a['respondent_role']}, {a['provenance']}, {a['date']})"]
    if not answered:
        lines.append("None.")

    lines += ["", f"## Sources: {r['collection']['items']} collected", "",
              "| Source | Date | Region | Unit | Triage | Reason |", "|---|---|---|---|---|---|"]
    for s in run["sources"]:
        t = screened.get(s["source_id"], {"status": "unverified", "rationale": "no triage record"})
        lines.append(f"| {s['source_id']} | {s['date']} | {s['region'] or 'unverified'} | "
                     f"{s['unit'] or 'unverified'} | {t['status']} | {t['rationale']} |")

    lines += ["", "## Not counted", ""]
    waiting = [e for e in run["evidence"] if e["review_status"] == "PROPOSED"]
    lines.append("- Awaiting review, so not used: "
                 + (", ".join(f"{e['evidence_id']} ({e['source_id']})" for e in waiting) or "none"))
    for e in run["evidence"]:
        if e["review_status"] == "REJECTED":
            rv = e["review"]
            lines.append(f"- Rejected: {e['evidence_id']} ({e['source_id']}) by {rv['reviewer_role']} "
                         f"on {rv['date']}" + (f": {rv['note']}" if rv.get("note") else ""))
    for f in run["refused"]:
        lines.append(_refusal_line(f))

    lines += ["", "## Checks", "", "This report was written only after passing two checks:", "",
              "- Traceability: every evidence, source, and question id in it resolves to the run's files, "
              "every quoted excerpt appears word for word in its source, and every file matches the "
              "SHA-256 recorded in `run.json`.",
              "- Claim integrity: findings list only accepted evidence, each source is counted once, and "
              "the decision shown is the one recorded."]
    return "\n".join(lines) + "\n"


def check(run_dir, run, text):
    """Run the traceability and claim-integrity checks. Returns a list of failures."""
    d = Path(run_dir)
    r = run["run"]
    failures = []

    recorded = [("brief.json", r["brief_sha256"])]
    for block in r.values():
        if isinstance(block, dict):
            recorded += [(block[k], block.get(k[:-5] + "_sha256")) for k in block if k.endswith("_file")]
    for name, expected in recorded:
        path = d / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(_failure(HASH_MISMATCH, f"{name} does not match the SHA-256 recorded in run.json"))

    evidence = {e["evidence_id"]: e for e in run["evidence"]}
    known_evidence = set(evidence) | {f["id"] for f in run["refused"] if f["kind"] == "proposal"}
    sources = {s["source_id"]: s for s in run["sources"]}
    questions = {q["question_id"] for q in run["questions"]}
    for eid in sorted(set(EVIDENCE_ID_RE.findall(text)) - known_evidence):
        failures.append(_failure(UNRESOLVED_ID, f"{eid} is not in the run's evidence"))
    for qid in sorted(set(QUESTION_ID_RE.findall(text)) - questions):
        failures.append(_failure(UNRESOLVED_ID, f"{qid} is not in the run's field questions"))
    namespaces = sorted({sid.split(":", 1)[0] for sid in sources})
    if namespaces:
        source_re = re.compile(r"\b(?:" + "|".join(map(re.escape, namespaces)) + r"):[A-Za-z0-9_-]+")
        for sid in sorted(set(source_re.findall(text)) - set(sources)):
            failures.append(_failure(UNRESOLVED_ID, f"{sid} is not in the run's sources"))

    for e in run["evidence"]:
        if e["review_status"] != "ACCEPTED":
            continue
        source = sources.get(e["source_id"])
        if (source is None or e["verbatim_excerpt"] not in source["body"]
                or source["body_sha256"] != e["source_body_sha256"]):
            failures.append(_failure(QUOTE_NOT_IN_SOURCE,
                                     f"{e['evidence_id']}'s excerpt is not word for word in {e['source_id']}"))

    findings = _section(text, "## Findings")
    for eid in sorted(set(EVIDENCE_ID_RE.findall(findings))):
        status = evidence[eid]["review_status"] if eid in evidence else "not in the ledger"
        if status != "ACCEPTED":
            failures.append(_failure(FINDING_NOT_ACCEPTED, f"{eid} is listed under Findings but is {status}"))

    shown = re.search(r"^\| Decision \| \*\*(\w+)\*\*", text, re.MULTILINE)
    recorded_disposition = run["decision"]["disposition"]
    if not shown or shown.group(1).lower() != recorded_disposition:
        failures.append(_failure(DECISION_MISMATCH,
                                 f"the report does not show the recorded decision '{recorded_disposition}'"))
    return failures


def _test_status(brief, r, asked):
    if brief["type"] != "hypothesis":
        return "Topic brief: no hypothesis to test"
    if "UNTESTED_HYPOTHESIS" in r["flags"]:
        return "No disproof condition given: this hypothesis is untested"
    disproof = next((q for q in asked if q["question_id"] == "Q-DISPROOF"), None)
    if disproof and disproof["status"] == "answered":
        return "Disproof condition given; a field note addresses it (Q-DISPROOF)"
    return "Disproof condition given; not yet checked (Q-DISPROOF is open)"


def _scope(scope):
    parts = []
    if scope.get("date_from") or scope.get("date_to"):
        parts.append(f"{scope.get('date_from') or 'any date'} to {scope.get('date_to') or 'any date'}")
    if scope.get("regions"):
        parts.append("regions " + ", ".join(scope["regions"]))
    if scope.get("units"):
        parts.append("units " + ", ".join(scope["units"]))
    return "; ".join(parts) or "none given"


def _refusal_line(f):
    if f["kind"] == "decision":
        return f"- Refused decision, {f['code']}: {f['detail']}"
    if f["kind"] == "field_note":
        return f"- Refused field note for {f['id']}, {f['code']}: {f['detail']}"
    source = f["record"].get("source_id")
    return (f"- Refused {f['kind']}: {f['id']}" + (f" ({source})" if source else "")
            + f", {f['code']}: {f['detail']}")


def _section(text, heading):
    after = text.split(f"\n{heading}\n", 1)
    return after[1].split("\n## ", 1)[0] if len(after) == 2 else ""


def _failure(code, detail):
    return {"code": code, "detail": detail}


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m core.report",
                                 description="Check a finished run and its report.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="re-check a run folder; writes nothing").add_argument("run_dir", type=Path)
    args = ap.parse_args(argv)

    try:
        failures = verify(args.run_dir)
    except (OSError, ValueError, KeyError) as e:
        print(f"ERROR  cannot read run folder {args.run_dir}: {e}")
        return 1
    for f in failures:
        print(f"FAIL   {f['code']}: {f['detail']}")
    if failures:
        return 1
    print(f"verified {args.run_dir.as_posix()}: files match run.json, every id resolves, "
          "every accepted excerpt is in its source, and the report is unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
