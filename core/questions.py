"""
Field questions: what still has to be asked, and who answered.

The pipeline asks questions; it never writes answers. Questions come from
the brief's own questions and from fixed rules over the evidence a person
has accepted. Unreviewed evidence raises no questions.

    BRIEF             each question in the brief, word for word
    DISPROOF          the brief's disproof condition, still to be checked
    DISPROOF_MISSING  a hypothesis with no disproof condition
    BASELINE          accepted evidence that compares figures
    ALTERNATE         each accepted, independent piece of supporting evidence
    SECOND_SOURCE     only one independent source supports the hypothesis
    SETTLE            each accepted claim whose stance is unresolved
    SCOPE             accepted evidence from a source with no region or unit
    UNCOVERED_REGION, UNCOVERED_UNIT
                      a region or unit in scope with no accepted evidence

Question ids describe what they are about (Q-ALTERNATE-EV-002), so a field
note stays attached to the right question when the list changes.

A field note answers one question: the answer, the respondent's role (never
a name), the date, and how it was obtained. Answers stay with their
questions, labeled as field notes; they never become sources or evidence.
"""
import re

from core.ledger import ACCEPTED, is_date, is_text
from core.triage import FIGURE_RE, MISSING_SCOPE_METADATA

OPEN, ANSWERED = "open", "answered"
FIELD_NOTE = "field note, not a published source"

WHY = {
    "BRIEF": "Asked in the brief.",
    "DISPROOF": "This is the test the brief set. Until it is checked, the hypothesis is not tested.",
    "DISPROOF_MISSING": "Without a result that would count against it, the hypothesis cannot be tested.",
    "BASELINE": "A rise or fall means little unless the periods compared are alike.",
    "ALTERNATE": "Supporting evidence shows what happened, not why. Another cause would weaken the hypothesis.",
    "SECOND_SOURCE": "One source can be wrong, and a republished copy of it is not a second source.",
    "SETTLE": "The claim is on record but cannot be checked as stated.",
    "SCOPE": "Without a region or unit, the claim cannot be matched to the scope of the brief.",
    "UNCOVERED_REGION": "The brief covers this region, but the accepted evidence says nothing about it.",
    "UNCOVERED_UNIT": "The brief covers this unit, but the accepted evidence says nothing about it.",
}

NOTE_FIELDS = ("question_id", "answer", "respondent_role", "date", "provenance")

# Field-note refusals
UNKNOWN_FIELD = "UNKNOWN_FIELD"
MISSING_FIELD = "MISSING_FIELD"
BAD_DATE = "BAD_DATE"
UNKNOWN_QUESTION = "UNKNOWN_QUESTION"
DUPLICATE_ANSWER = "DUPLICATE_ANSWER"


def ask(brief, items, triage_records, evidence):
    """Return the run's field questions, all open, in a fixed order."""
    sources = {item.source_id: item for item in items}
    screened = {record["source_id"]: record for record in triage_records}
    accepted = [e for e in evidence if e["review_status"] == ACCEPTED]
    hypothesis = brief["type"] == "hypothesis"
    scope = brief.get("scope") or {}
    questions = []

    def add(question_id, origin, text, linked=()):
        if all(q["question_id"] != question_id for q in questions):
            questions.append({
                "question_id": question_id,
                "question": text,
                "why_it_matters": WHY[origin],
                "origin": origin,
                "linked_evidence_ids": list(linked),
                "status": OPEN,
                "answer": None,
            })

    for n, text in enumerate(brief.get("questions", []), 1):
        add(f"Q-BRIEF-{n}", "BRIEF", text)

    if hypothesis:
        disproof = (brief.get("disproof") or "").strip()
        if disproof:
            add("Q-DISPROOF", "DISPROOF",
                f'The brief says the hypothesis fails if: "{disproof}" What would show whether that holds?',
                [e["evidence_id"] for e in accepted if e["stance"] != "unresolved"])
        else:
            add("Q-DISPROOF-MISSING", "DISPROOF_MISSING",
                "The brief gives no disproof condition. What result would show the hypothesis is wrong?")

    comparisons = [e["evidence_id"] for e in accepted if len(_figures(e["verbatim_excerpt"])) >= 2]
    if comparisons:
        add("Q-BASELINE", "BASELINE",
            f"Accepted evidence compares figures ({', '.join(comparisons)}). What baseline period "
            f"does each comparison use, and are they comparable?", comparisons)

    if hypothesis:
        supporting = [e for e in accepted if e["stance"] == "supports" and e["independent"]]
        for e in supporting:
            add(f"Q-ALTERNATE-{e['evidence_id']}", "ALTERNATE",
                f'Apart from what the hypothesis says, what else could explain this: "{_quote(e["claim"])}"?',
                [e["evidence_id"]])
        supporting_sources = sorted({e["source_id"] for e in supporting})
        if len(supporting_sources) == 1:
            add("Q-SECOND-SOURCE", "SECOND_SOURCE",
                f"Only one independent source supports the hypothesis ({supporting_sources[0]}). "
                f"What would a second, independent source show?",
                [e["evidence_id"] for e in supporting])

    for e in accepted:
        if e["stance"] == "unresolved":
            add(f"Q-SETTLE-{e['evidence_id']}", "SETTLE",
                f'What records or figures would settle this claim: "{_quote(e["claim"])}"?',
                [e["evidence_id"]])

    for e in accepted:
        reasons = [r["code"] for r in screened[e["source_id"]]["reasons"]]
        if MISSING_SCOPE_METADATA in reasons:
            source = sources[e["source_id"]]
            missing = [f for f in ("region", "unit") if scope.get(f + "s") and not getattr(source, f)]
            if not missing:
                continue
            add(f"Q-SCOPE-{e['evidence_id']}", "SCOPE",
                f"The source behind {e['evidence_id']} ({e['source_id']}) gives no "
                f"{' or '.join(missing)}. Which {' and '.join(missing)} does its claim cover?",
                [e["evidence_id"]])

    period = ""
    if scope.get("date_from") or scope.get("date_to"):
        period = (f" for the brief's period, {scope.get('date_from') or 'any date'}"
                  f" to {scope.get('date_to') or 'any date'}")
    for field in ("region", "unit"):
        for value in scope.get(field + "s") or []:
            covered = any(_norm(getattr(sources[e["source_id"]], field) or "") == _norm(value)
                          for e in accepted)
            if not covered:
                add(f"Q-{field.upper()}-{_slug(value)}", f"UNCOVERED_{field.upper()}",
                    f"No accepted evidence covers {value}. What do its records show{period}?")
    return questions


def answer(questions, notes):
    """Apply field notes to their questions. Returns the refused notes."""
    by_id = {q["question_id"]: q for q in questions}
    refused = []
    for position, note in enumerate(notes, 1):
        problem = _check_note(note, by_id)
        if problem:
            code, detail = problem
            refused.append({"kind": "field_note", "position": position, "id": note.get("question_id"),
                            "code": code, "detail": detail, "record": note})
            continue
        question = by_id[note["question_id"]]
        question["status"] = ANSWERED
        question["answer"] = {
            "text": note["answer"],
            "respondent_role": note["respondent_role"],
            "date": note["date"],
            "provenance": note["provenance"],
            "kind": FIELD_NOTE,
        }
    return refused


def counts(questions):
    answered = sum(q["status"] == ANSWERED for q in questions)
    return {"asked": len(questions), "answered": answered, "open": len(questions) - answered}


def render_markdown(questions):
    """A readable list: open questions first, then answered ones with their answers."""
    c = counts(questions)
    lines = ["# Field questions", "",
             f"{c['asked']} asked: {c['answered']} answered, {c['open']} open. Questions come from "
             "the brief and from fixed rules over accepted evidence. Answers come only from field "
             "notes, which are not published sources.", ""]
    for heading, status in (("Open", OPEN), ("Answered", ANSWERED)):
        lines += [f"## {heading}", ""]
        group = [q for q in questions if q["status"] == status]
        if not group:
            lines += ["None.", ""]
        for q in group:
            lines += [f"### {q['question_id']}", "", q["question"], "",
                      f"- Why it matters: {q['why_it_matters']}",
                      f"- Raised by: {'the brief' if q['origin'] == 'BRIEF' else 'rule ' + q['origin']}",
                      f"- Evidence: {', '.join(q['linked_evidence_ids']) or 'none linked'}"]
            if q["answer"]:
                a = q["answer"]
                lines += [f"- Answer ({a['kind']}): {a['text']}",
                          f"  ({a['respondent_role']}, {a['provenance']}, {a['date']})"]
            lines.append("")
    return "\n".join(lines)


def _check_note(note, by_id):
    unknown = sorted(set(note) - set(NOTE_FIELDS))
    if unknown:
        return (UNKNOWN_FIELD, f"unknown field(s) {unknown}; a respondent is named by role only")
    for name in NOTE_FIELDS:
        if not is_text(note.get(name)):
            return (MISSING_FIELD, f"'{name}' is required and must be non-empty text")
    if not is_date(note["date"]):
        return (BAD_DATE, f"date '{note['date']}' must be a real date written YYYY-MM-DD")
    question = by_id.get(note["question_id"])
    if question is None:
        return (UNKNOWN_QUESTION, f"no question in this run has the id '{note['question_id']}'")
    if question["answer"] is not None:
        return (DUPLICATE_ANSWER, f"{note['question_id']} was already answered; the first answer stands")
    return None


def _figures(text):
    return {m.replace(",", "") for m in FIGURE_RE.findall(text)}


def _quote(claim):
    return claim.strip().rstrip(".")


def _norm(text):
    return " ".join(text.split()).casefold()


def _slug(value):
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")
