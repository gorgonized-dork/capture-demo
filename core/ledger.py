"""
Evidence ledger: the checkpoint between proposed evidence and human review.

Two inputs, two roles:

    proposals   claims, each with a verbatim excerpt and a stance, from a
                proposer (an extractor or an analyst; in the sample, written
                by hand). A proposal can never set its own status.
    review log  decisions by a person to accept or reject one piece of
                evidence. The only way out of PROPOSED.

Every proposal gets an id from its position (EV-001, EV-002, ...), refused
ones too. A valid proposal enters the ledger as PROPOSED; an invalid one is
refused with a reason code. A review counts only if its fingerprint matches
the evidence's current content, so an edited claim never inherits an old
review. This module reads the review log; nothing here writes it.

ACCEPTED means a person checked that the excerpt says what the claim says
and that the stance fits. It does not make the claim true. There is no
combined score: supporting and challenging evidence sit side by side.
"""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

PROPOSED, ACCEPTED, REJECTED = "PROPOSED", "ACCEPTED", "REJECTED"
STANCES = ("supports", "challenges", "context", "unresolved")
DECISIONS = {"accept": ACCEPTED, "reject": REJECTED}

PROPOSAL_FIELDS = ("source_id", "claim", "verbatim_excerpt", "stance")
STATUS_FIELDS = ("review_status", "status", "review")  # a proposer may never set these
REVIEW_REQUIRED = ("evidence_id", "fingerprint", "decision", "reviewer_role", "date")
REVIEW_OPTIONAL = ("note",)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Proposal refusals
PROPOSER_SET_STATUS = "PROPOSER_SET_STATUS"
UNKNOWN_FIELD = "UNKNOWN_FIELD"
MISSING_FIELD = "MISSING_FIELD"
INVALID_STANCE = "INVALID_STANCE"
UNKNOWN_SOURCE = "UNKNOWN_SOURCE"
SOURCE_EXCLUDED_AT_TRIAGE = "SOURCE_EXCLUDED_AT_TRIAGE"
QUOTE_NOT_IN_SOURCE = "QUOTE_NOT_IN_SOURCE"
DUPLICATE_PROPOSAL = "DUPLICATE_PROPOSAL"
# Review refusals (UNKNOWN_FIELD and MISSING_FIELD apply too)
INVALID_DECISION = "INVALID_DECISION"
BAD_DATE = "BAD_DATE"
UNKNOWN_EVIDENCE = "UNKNOWN_EVIDENCE"
FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
DUPLICATE_REVIEW = "DUPLICATE_REVIEW"


class LedgerError(ValueError):
    """An input file is not a JSON array of objects."""


def load_records(path, what):
    """Read a JSON array of objects from path. Anything else raises LedgerError."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise LedgerError(f"{path}: not valid JSON ({e})") from None
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise LedgerError(f"{path}: {what} must be a JSON array of objects")
    return data


def evidence_id(position):
    return f"EV-{position:03d}"


def fingerprint(source_id, claim, verbatim_excerpt, stance):
    """First 12 hex characters of a SHA-256 over the four content fields."""
    payload = json.dumps([source_id, claim, verbatim_excerpt, stance],
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def build(proposals, reviews, items, triage_records):
    """Check proposals, then apply reviews. Returns (evidence, refused), in input order."""
    sources = {item.source_id: item for item in items}
    screened = {record["source_id"]: record for record in triage_records}
    evidence, refused, seen = [], [], {}

    for position, proposal in enumerate(proposals, 1):
        eid = evidence_id(position)
        problem = _check_proposal(proposal, sources, screened, seen)
        if problem:
            refused.append(_refusal("proposal", position, eid, problem, proposal))
            continue
        entry = _entry(eid, proposal, sources, screened)
        seen[entry["fingerprint"]] = eid
        evidence.append(entry)

    by_id = {entry["evidence_id"]: entry for entry in evidence}
    for position, review in enumerate(reviews, 1):
        problem = _check_review(review, by_id)
        if problem:
            refused.append(_refusal("review", position, review.get("evidence_id"), problem, review))
            continue
        entry = by_id[review["evidence_id"]]
        entry["review_status"] = DECISIONS[review["decision"]]
        entry["review"] = {
            "decision": review["decision"],
            "reviewer_role": review["reviewer_role"],
            "date": review["date"],
            "note": review.get("note"),
        }
    return evidence, refused


def counts(evidence, refused):
    accepted = [e for e in evidence if e["review_status"] == ACCEPTED]
    return {
        "in_ledger": len(evidence),
        "accepted": len(accepted),
        "rejected": sum(e["review_status"] == REJECTED for e in evidence),
        "awaiting_review": sum(e["review_status"] == PROPOSED for e in evidence),
        "refused": len(refused),
        "accepted_by_stance": {s: sum(e["stance"] == s for e in accepted) for s in STANCES},
    }


def _check_proposal(proposal, sources, screened, seen):
    status_fields = [f for f in STATUS_FIELDS if f in proposal]
    if status_fields:
        return (PROPOSER_SET_STATUS, f"sets its own '{status_fields[0]}' "
                f"({proposal[status_fields[0]]!r}); only the review log can change status")
    unknown = sorted(set(proposal) - set(PROPOSAL_FIELDS))
    if unknown:
        return (UNKNOWN_FIELD, f"unknown field(s) {unknown}")
    for name in PROPOSAL_FIELDS:
        if not is_text(proposal.get(name)):
            return (MISSING_FIELD, f"'{name}' is required and must be non-empty text")
    if proposal["stance"] not in STANCES:
        return (INVALID_STANCE, f"stance '{proposal['stance']}' is not one of: {', '.join(STANCES)}")

    source_id = proposal["source_id"]
    if source_id not in sources:
        return (UNKNOWN_SOURCE, f"no collected source has the id '{source_id}'")
    if screened[source_id]["status"] == "excluded":
        return (SOURCE_EXCLUDED_AT_TRIAGE, f"{source_id} was excluded at triage")
    if proposal["verbatim_excerpt"] not in sources[source_id].body:
        return (QUOTE_NOT_IN_SOURCE, f"the excerpt does not appear word for word in {source_id}")
    fp = fingerprint(*(proposal[name] for name in PROPOSAL_FIELDS))
    if fp in seen:
        return (DUPLICATE_PROPOSAL, f"same content as {seen[fp]}")
    return None


def _check_review(review, by_id):
    unknown = sorted(set(review) - set(REVIEW_REQUIRED) - set(REVIEW_OPTIONAL))
    if unknown:
        return (UNKNOWN_FIELD, f"unknown field(s) {unknown}")
    for name in REVIEW_REQUIRED:
        if not is_text(review.get(name)):
            return (MISSING_FIELD, f"'{name}' is required and must be non-empty text")
    if review.get("note") is not None and not isinstance(review["note"], str):
        return (MISSING_FIELD, "'note' must be text when given")
    if review["decision"] not in DECISIONS:
        return (INVALID_DECISION, f"decision '{review['decision']}' is not one of: {', '.join(DECISIONS)}")
    if not is_date(review["date"]):
        return (BAD_DATE, f"date '{review['date']}' must be a real date written YYYY-MM-DD")

    entry = by_id.get(review["evidence_id"])
    if entry is None:
        return (UNKNOWN_EVIDENCE, f"no evidence in the ledger has the id '{review['evidence_id']}'")
    if review["fingerprint"] != entry["fingerprint"]:
        return (FINGERPRINT_MISMATCH, f"the review is for content with fingerprint {review['fingerprint']}; "
                f"{entry['evidence_id']} now has {entry['fingerprint']}")
    if entry["review"] is not None:
        return (DUPLICATE_REVIEW, f"{entry['evidence_id']} was already reviewed; the first review stands")
    return None


def _entry(eid, proposal, sources, screened):
    source = sources[proposal["source_id"]]
    screen = screened[source.source_id]
    return {
        "evidence_id": eid,
        "fingerprint": fingerprint(*(proposal[name] for name in PROPOSAL_FIELDS)),
        "source_id": source.source_id,
        "claim": proposal["claim"],
        "verbatim_excerpt": proposal["verbatim_excerpt"],
        "stance": proposal["stance"],
        "review_status": PROPOSED,
        "review": None,
        "source_body_sha256": hashlib.sha256(source.body.encode("utf-8")).hexdigest(),
        "source_triage_status": screen["status"],
        "independent": not screen["possible_duplicate_of"],
        "source_possible_duplicate_of": screen["possible_duplicate_of"],
    }


def _refusal(kind, position, ident, problem, record):
    code, detail = problem
    return {"kind": kind, "position": position, "id": ident,
            "code": code, "detail": detail, "record": record}


def is_text(value):
    return isinstance(value, str) and value.strip() != ""


def is_date(value):
    if not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
