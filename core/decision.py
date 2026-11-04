"""
Decision record: the pursue-or-pass call, entered by a person.

The software never writes a disposition. A person enters one (pursue,
defer, pass, or undecided) with their role, the date, a rationale, the
evidence it rests on, and the questions still open. The decision is checked
against the run: it may rest only on accepted evidence, and it may list
only questions that are still open. Anything wrong refuses the whole
decision, and the run records undecided rather than a partial or guessed
one. There is no win-probability field: any field not listed here is
refused.
"""
import json
from pathlib import Path

from core.ledger import ACCEPTED, is_date, is_text
from core.questions import OPEN

DISPOSITIONS = ("pursue", "defer", "pass", "undecided")
TEXT_FIELDS = ("disposition", "owner_role", "date", "rationale")
LIST_FIELDS = ("supporting_evidence_ids", "open_questions")
OPTIONAL = ("note",)

UNKNOWN_FIELD = "UNKNOWN_FIELD"
MISSING_FIELD = "MISSING_FIELD"
INVALID_DISPOSITION = "INVALID_DISPOSITION"
BAD_DATE = "BAD_DATE"
UNKNOWN_EVIDENCE = "UNKNOWN_EVIDENCE"
EVIDENCE_NOT_ACCEPTED = "EVIDENCE_NOT_ACCEPTED"
UNKNOWN_QUESTION = "UNKNOWN_QUESTION"
QUESTION_NOT_OPEN = "QUESTION_NOT_OPEN"


class DecisionError(ValueError):
    """The decision file is not a JSON object."""


def load(path):
    """Read a decision file. Anything but a JSON object raises DecisionError."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise DecisionError(f"{path}: not valid JSON ({e})") from None
    if not isinstance(data, dict):
        raise DecisionError(f"{path}: a decision must be a JSON object")
    return data


def record(entered, evidence, questions):
    """Check an entered decision against the run. Returns (decision, refused)."""
    if entered is None:
        return undecided("no decision entered"), []
    problem = _check(entered, evidence, questions)
    if problem:
        code, detail = problem
        refusal = {"kind": "decision", "position": 1, "id": "decision",
                   "code": code, "detail": detail, "record": entered}
        return undecided(f"the entered decision was refused ({code}); see refused.jsonl"), [refusal]
    decision = {name: entered[name] for name in TEXT_FIELDS + LIST_FIELDS}
    decision["note"] = entered.get("note")
    decision["decision_entered"] = True
    return decision, []


def undecided(reason):
    return {"disposition": "undecided", "decision_entered": False, "reason": reason}


def _check(entered, evidence, questions):
    unknown = sorted(set(entered) - set(TEXT_FIELDS) - set(LIST_FIELDS) - set(OPTIONAL))
    if unknown:
        return (UNKNOWN_FIELD, f"unknown field(s) {unknown}; a decision carries no score or probability")
    for name in TEXT_FIELDS:
        if not is_text(entered.get(name)):
            return (MISSING_FIELD, f"'{name}' is required and must be non-empty text")
    for name in LIST_FIELDS:
        value = entered.get(name)
        if not isinstance(value, list) or not all(is_text(v) for v in value):
            return (MISSING_FIELD, f"'{name}' is required and must be a list of ids (it may be empty)")
    if entered.get("note") is not None and not isinstance(entered["note"], str):
        return (MISSING_FIELD, "'note' must be text when given")
    if entered["disposition"] not in DISPOSITIONS:
        return (INVALID_DISPOSITION,
                f"disposition '{entered['disposition']}' is not one of: {', '.join(DISPOSITIONS)}")
    if not is_date(entered["date"]):
        return (BAD_DATE, f"date '{entered['date']}' must be a real date written YYYY-MM-DD")

    status = {e["evidence_id"]: e["review_status"] for e in evidence}
    for eid in entered["supporting_evidence_ids"]:
        if eid not in status:
            return (UNKNOWN_EVIDENCE, f"no evidence in the ledger has the id '{eid}'")
        if status[eid] != ACCEPTED:
            return (EVIDENCE_NOT_ACCEPTED, f"{eid} is {status[eid]}; a decision may rest only on accepted evidence")
    asked = {q["question_id"]: q["status"] for q in questions}
    for qid in entered["open_questions"]:
        if qid not in asked:
            return (UNKNOWN_QUESTION, f"no question in this run has the id '{qid}'")
        if asked[qid] != OPEN:
            return (QUESTION_NOT_OPEN, f"{qid} has already been answered")
    return None
