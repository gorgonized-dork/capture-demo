"""
Fitness functions for the evidence ledger.

The ledger is the checkpoint between proposed evidence and human review.
These tests hold that a proposal enters only as PROPOSED, that its excerpt
must appear word for word in a source that survived triage, that a proposer
can never set its own status, that only a matching review moves evidence
out of PROPOSED, and that contradicting evidence sits side by side with no
combined score.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from adapters.base import SourceItem
from core import ledger
from core.ledger import (ACCEPTED, BAD_DATE, DUPLICATE_PROPOSAL, DUPLICATE_REVIEW,
                         FINGERPRINT_MISMATCH, INVALID_DECISION, INVALID_STANCE,
                         MISSING_FIELD, PROPOSED, PROPOSER_SET_STATUS, QUOTE_NOT_IN_SOURCE,
                         REJECTED, SOURCE_EXCLUDED_AT_TRIAGE, UNKNOWN_EVIDENCE,
                         UNKNOWN_FIELD, UNKNOWN_SOURCE)
from core.triage import triage

BRIEF = {"title": "Test", "type": "topic", "statement": "Saturday visits.",
         "seed_terms": ["Saturday"], "exclude_terms": ["book sale"]}
A = SourceItem("test:a", "Saturday news", "2025-06-01", "Saturday visits rose to 1,200 from 900.")
B = SourceItem("test:b", "Saturday sale", "2025-06-02", "A book sale drew a crowd on Saturday.")
C = SourceItem("test:c", "Saturday repeat", "2025-06-03", "Saturday visits rose to 1,200 from 900, again.")
ITEMS = [A, B, C]            # B is excluded at triage; C repeats A's figures
TRIAGED = triage(ITEMS, BRIEF)
REMOVE = object()


def proposal(**changes):
    record = {"source_id": "test:a", "claim": "Saturday visits rose.",
              "verbatim_excerpt": "Saturday visits rose to 1,200 from 900.", "stance": "supports"}
    for name, value in changes.items():
        if value is REMOVE:
            record.pop(name, None)
        else:
            record[name] = value
    return record


def review_of(entry, **changes):
    record = {"evidence_id": entry["evidence_id"], "fingerprint": entry["fingerprint"],
              "decision": "accept", "reviewer_role": "analyst", "date": "2025-07-01"}
    record.update(changes)
    return record


def build(proposals, reviews=()):
    return ledger.build(list(proposals), list(reviews), ITEMS, TRIAGED)


def refusal_codes(refused):
    return [r["code"] for r in refused]


class Proposals(unittest.TestCase):

    def test_valid_proposal_enters_as_proposed_with_no_review(self):
        evidence, refused = build([proposal()])
        self.assertEqual(refused, [])
        [entry] = evidence
        self.assertEqual(entry["evidence_id"], "EV-001")
        self.assertEqual(entry["review_status"], PROPOSED)
        self.assertIsNone(entry["review"])
        self.assertEqual(entry["source_body_sha256"],
                         hashlib.sha256(A.body.encode("utf-8")).hexdigest())
        self.assertEqual(entry["source_triage_status"], "included")
        self.assertTrue(entry["independent"])

    def test_ids_follow_position_including_refused_proposals(self):
        evidence, refused = build([proposal(stance="maybe"), proposal()])
        self.assertEqual([r["id"] for r in refused], ["EV-001"])
        self.assertEqual([e["evidence_id"] for e in evidence], ["EV-002"])

    def test_a_proposer_can_never_set_its_own_status(self):
        for field in ("review_status", "status", "review"):
            with self.subTest(field=field):
                evidence, refused = build([proposal(**{field: ACCEPTED})])
                self.assertEqual(evidence, [])
                self.assertEqual(refusal_codes(refused), [PROPOSER_SET_STATUS])

    def test_excerpt_must_appear_word_for_word_in_the_body(self):
        for excerpt in ("Saturday visits rose to 1,300 from 900.",   # one digit changed
                        "saturday visits rose to 1,200 from 900.",   # case changed
                        "Saturday visits  rose to 1,200 from 900.",  # spacing changed
                        "Saturday news"):                            # title, not body
            with self.subTest(excerpt=excerpt):
                evidence, refused = build([proposal(verbatim_excerpt=excerpt)])
                self.assertEqual(evidence, [])
                self.assertEqual(refusal_codes(refused), [QUOTE_NOT_IN_SOURCE])

    def test_source_id_must_match_a_collected_source_exactly(self):
        for source_id in ("test:z", "test:aa", "test:", "a"):
            with self.subTest(source_id=source_id):
                _, refused = build([proposal(source_id=source_id)])
                self.assertEqual(refusal_codes(refused), [UNKNOWN_SOURCE])

    def test_source_excluded_at_triage_cannot_carry_evidence(self):
        _, refused = build([proposal(source_id="test:b",
                                     verbatim_excerpt="A book sale drew a crowd on Saturday.")])
        self.assertEqual(refusal_codes(refused), [SOURCE_EXCLUDED_AT_TRIAGE])

    def test_possible_duplicate_source_carries_evidence_marked_not_independent(self):
        evidence, _ = build([proposal(source_id="test:c",
                                      verbatim_excerpt="Saturday visits rose to 1,200 from 900, again.")])
        [entry] = evidence
        self.assertEqual(entry["source_triage_status"], "needs_review")
        self.assertFalse(entry["independent"])
        self.assertEqual(entry["source_possible_duplicate_of"], ["test:a"])

    def test_missing_unknown_and_invalid_fields_are_refused(self):
        cases = [(proposal(claim=REMOVE), MISSING_FIELD),
                 (proposal(claim="   "), MISSING_FIELD),
                 (proposal(confidence=0.9), UNKNOWN_FIELD),
                 (proposal(stance="strongly supports"), INVALID_STANCE)]
        for record, code in cases:
            with self.subTest(code=code, record=record):
                _, refused = build([record])
                self.assertEqual(refusal_codes(refused), [code])

    def test_repeated_proposal_is_refused(self):
        evidence, refused = build([proposal(), proposal()])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(refusal_codes(refused), [DUPLICATE_PROPOSAL])
        self.assertIn("EV-001", refused[0]["detail"])

    def test_contradicting_evidence_sits_side_by_side_without_a_score(self):
        evidence, _ = build([proposal(),
                             proposal(stance="challenges", claim="The rise may be noise.")])
        self.assertEqual([e["stance"] for e in evidence], ["supports", "challenges"])
        for entry in evidence:
            self.assertFalse([k for k in entry if "score" in k or "confidence" in k], entry)


class Reviews(unittest.TestCase):

    def setUp(self):
        self.evidence, _ = build([proposal()])
        self.entry = self.evidence[0]

    def test_without_reviews_everything_stays_proposed(self):
        evidence, _ = build([proposal(), proposal(stance="context")])
        self.assertEqual({e["review_status"] for e in evidence}, {PROPOSED})

    def test_accept_and_reject_set_status_and_keep_the_review(self):
        for decision, status in (("accept", ACCEPTED), ("reject", REJECTED)):
            with self.subTest(decision=decision):
                evidence, refused = build([proposal()],
                                          [review_of(self.entry, decision=decision, note="Checked.")])
                self.assertEqual(refused, [])
                self.assertEqual(evidence[0]["review_status"], status)
                self.assertEqual(evidence[0]["review"], {
                    "decision": decision, "reviewer_role": "analyst",
                    "date": "2025-07-01", "note": "Checked."})

    def test_review_counts_only_for_the_content_it_reviewed(self):
        stale = review_of(self.entry)
        edited, refused = build([proposal(claim="Saturday visits rose sharply.")], [stale])
        self.assertEqual(refusal_codes(refused), [FINGERPRINT_MISMATCH])
        self.assertEqual(edited[0]["review_status"], PROPOSED)

    def test_review_of_unknown_or_refused_evidence_is_refused(self):
        _, refused = build([proposal(stance="maybe")],
                           [review_of({"evidence_id": "EV-001", "fingerprint": "000000000000"})])
        self.assertEqual(refusal_codes(refused), [INVALID_STANCE, UNKNOWN_EVIDENCE])

    def test_second_review_is_refused_and_the_first_stands(self):
        evidence, refused = build([proposal()], [review_of(self.entry),
                                                 review_of(self.entry, decision="reject")])
        self.assertEqual(evidence[0]["review_status"], ACCEPTED)
        self.assertEqual(refusal_codes(refused), [DUPLICATE_REVIEW])

    def test_malformed_reviews_are_refused(self):
        cases = [(review_of(self.entry, decision="approve"), INVALID_DECISION),
                 (review_of(self.entry, date="1 Dec 2025"), BAD_DATE),
                 (review_of(self.entry, date="2025-02-30"), BAD_DATE),
                 (review_of(self.entry, reviewer="A. Person"), UNKNOWN_FIELD),
                 (review_of(self.entry, reviewer_role=""), MISSING_FIELD),
                 (review_of(self.entry, note=["not", "text"]), MISSING_FIELD)]
        for record, code in cases:
            with self.subTest(code=code, record=record):
                evidence, refused = build([proposal()], [record])
                self.assertEqual(refusal_codes(refused), [code])
                self.assertEqual(evidence[0]["review_status"], PROPOSED)


class Counting(unittest.TestCase):

    def test_counts_by_status_and_accepted_stance(self):
        first, _ = build([proposal()])
        evidence, refused = build([proposal(), proposal(stance="context"), proposal(stance="maybe")],
                                  [review_of(first[0])])
        counts = ledger.counts(evidence, refused)
        self.assertEqual(counts["in_ledger"], 2)
        self.assertEqual((counts["accepted"], counts["rejected"], counts["awaiting_review"]), (1, 0, 1))
        self.assertEqual(counts["refused"], 1)
        self.assertEqual(counts["accepted_by_stance"],
                         {"supports": 1, "challenges": 0, "context": 0, "unresolved": 0})


class InputFiles(unittest.TestCase):

    def test_file_that_is_not_a_list_of_objects_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            for text in ('{"source_id": "x"}', '["just text"]', "[not json"):
                with self.subTest(text=text):
                    path = Path(tmp) / "proposals.json"
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ledger.LedgerError):
                        ledger.load_records(path, "proposals")

    def test_list_of_objects_loads_as_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.json"
            path.write_text(json.dumps([proposal()]), encoding="utf-8")
            self.assertEqual(ledger.load_records(path, "proposals"), [proposal()])


if __name__ == "__main__":
    unittest.main()
