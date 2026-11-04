"""
Fitness functions for the decision record.

A person owns the decision. These tests hold that the software records
undecided when no decision is entered, that a decision may rest only on
accepted evidence and list only open questions, that it can carry no score
or probability, and that anything wrong refuses the whole decision instead
of keeping part of it.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import decision, ledger, questions
from core.decision import (BAD_DATE, EVIDENCE_NOT_ACCEPTED, INVALID_DISPOSITION, MISSING_FIELD,
                           QUESTION_NOT_OPEN, UNKNOWN_EVIDENCE, UNKNOWN_FIELD, UNKNOWN_QUESTION)
from core.triage import triage

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
BRIEF = json.loads((SAMPLE / "brief.json").read_text(encoding="utf-8"))
ITEMS = FixtureAdapter().collect()
TRIAGED = triage(ITEMS, BRIEF)
EVIDENCE, _ = ledger.build(ledger.load_records(SAMPLE / "proposed_evidence.json", "proposals"),
                           ledger.load_records(SAMPLE / "review_log.json", "reviews"),
                           ITEMS, TRIAGED)
QUESTIONS = questions.ask(BRIEF, ITEMS, TRIAGED, EVIDENCE)

ENTERED = {
    "disposition": "defer",
    "owner_role": "capture lead",
    "date": "2025-12-05",
    "rationale": "Mixed evidence; more validation needed.",
    "supporting_evidence_ids": ["EV-002", "EV-005"],
    "open_questions": ["Q-DISPROOF"],
}


def entered(**changes):
    record = copy.deepcopy(ENTERED)
    record.update(changes)
    return record


def record(decision_input, asked=QUESTIONS):
    return decision.record(decision_input, EVIDENCE, asked)


class Decisions(unittest.TestCase):

    def test_with_no_decision_entered_the_run_is_undecided(self):
        recorded, refused = record(None)
        self.assertEqual(recorded, {"disposition": "undecided", "decision_entered": False,
                                    "reason": "no decision entered"})
        self.assertEqual(refused, [])

    def test_a_valid_decision_is_recorded_as_entered(self):
        recorded, refused = record(entered(note="Fictional."))
        self.assertEqual(refused, [])
        self.assertEqual(recorded, dict(ENTERED, note="Fictional.", decision_entered=True))

    def test_a_person_may_enter_undecided_explicitly(self):
        recorded, refused = record(entered(disposition="undecided",
                                           supporting_evidence_ids=[], open_questions=[]))
        self.assertEqual(refused, [])
        self.assertTrue(recorded["decision_entered"])

    def test_a_decision_carries_no_score_or_probability(self):
        for field, value in (("pwin", 0.4), ("probability", "60%"), ("score", 7)):
            with self.subTest(field=field):
                recorded, refused = record(entered(**{field: value}))
                self.assertEqual([r["code"] for r in refused], [UNKNOWN_FIELD])
                self.assertEqual(recorded["disposition"], "undecided")

    def test_a_decision_rests_only_on_accepted_evidence(self):
        cases = [("EV-099", UNKNOWN_EVIDENCE),        # not in the ledger
                 ("EV-001", EVIDENCE_NOT_ACCEPTED),   # still PROPOSED
                 ("EV-008", EVIDENCE_NOT_ACCEPTED),   # REJECTED by the reviewer
                 ("EV-009", UNKNOWN_EVIDENCE)]        # refused at the checkpoint
        for eid, code in cases:
            with self.subTest(evidence_id=eid):
                recorded, refused = record(entered(supporting_evidence_ids=["EV-002", eid]))
                self.assertEqual([r["code"] for r in refused], [code])
                self.assertEqual(recorded["disposition"], "undecided")

    def test_a_decision_lists_only_questions_still_open(self):
        asked = copy.deepcopy(QUESTIONS)
        questions.answer(asked, [{"question_id": "Q-DISPROOF", "answer": "Checked.",
                                  "respondent_role": "analyst", "date": "2025-12-04",
                                  "provenance": "meeting"}])
        for qid, code, run_questions in (("Q-NOPE", UNKNOWN_QUESTION, QUESTIONS),
                                         ("Q-DISPROOF", QUESTION_NOT_OPEN, asked)):
            with self.subTest(question_id=qid):
                recorded, refused = record(entered(open_questions=[qid]), run_questions)
                self.assertEqual([r["code"] for r in refused], [code])
                self.assertEqual(recorded["disposition"], "undecided")

    def test_malformed_decisions_are_refused_whole(self):
        cases = [(entered(disposition="bid"), INVALID_DISPOSITION),
                 (entered(date="5 Dec 2025"), BAD_DATE),
                 (entered(rationale=""), MISSING_FIELD),
                 (entered(owner_role=None), MISSING_FIELD),
                 (entered(open_questions="Q-DISPROOF"), MISSING_FIELD),
                 (entered(note=42), MISSING_FIELD)]
        for decision_input, code in cases:
            with self.subTest(code=code, decision=decision_input):
                recorded, refused = record(decision_input)
                self.assertEqual([r["code"] for r in refused], [code])
                self.assertEqual(recorded["disposition"], "undecided")
                self.assertFalse(recorded["decision_entered"])
                self.assertIn(code, recorded["reason"])


class DecisionFile(unittest.TestCase):

    def test_file_that_is_not_an_object_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            for text in ('["defer"]', '"defer"', "{not json"):
                with self.subTest(text=text):
                    path = Path(tmp) / "decision.json"
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(decision.DecisionError):
                        decision.load(path)


if __name__ == "__main__":
    unittest.main()
