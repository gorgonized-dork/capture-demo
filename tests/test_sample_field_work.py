"""
Fitness functions for the sample field notes and decision.

Runs the sample through questions and the decision record. These tests pin
which questions the field notes answer, and hold that the sample decision
is recorded as entered, rests only on accepted evidence, and names only
questions that are still open.
"""
import json
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import decision, ledger, questions
from core.triage import triage

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
BRIEF = json.loads((SAMPLE / "brief.json").read_text(encoding="utf-8"))
ITEMS = FixtureAdapter().collect()
TRIAGED = triage(ITEMS, BRIEF)
EVIDENCE, _ = ledger.build(ledger.load_records(SAMPLE / "proposed_evidence.json", "proposals"),
                           ledger.load_records(SAMPLE / "review_log.json", "reviews"),
                           ITEMS, TRIAGED)
NOTES = ledger.load_records(SAMPLE / "field_notes.json", "field notes")
DECISION = decision.load(SAMPLE / "decision.json")


class SampleFieldWork(unittest.TestCase):

    def setUp(self):
        self.asked = questions.ask(BRIEF, ITEMS, TRIAGED, EVIDENCE)
        self.refused_notes = questions.answer(self.asked, NOTES)
        self.by_id = {q["question_id"]: q for q in self.asked}

    def test_field_notes_answer_three_questions_and_six_stay_open(self):
        self.assertEqual(self.refused_notes, [])
        answered = [q["question_id"] for q in self.asked if q["status"] == questions.ANSWERED]
        self.assertEqual(answered, ["Q-BRIEF-1", "Q-BASELINE", "Q-ALTERNATE-EV-002"])
        self.assertEqual(questions.counts(self.asked), {"asked": 9, "answered": 3, "open": 6})

    def test_a_field_note_surfaces_another_possible_cause(self):
        answer = self.by_id["Q-ALTERNATE-EV-002"]["answer"]
        self.assertIn("housing estate", answer["text"])
        self.assertEqual(answer["kind"], questions.FIELD_NOTE)

    def test_the_sample_decision_is_recorded_as_entered(self):
        recorded, refused = decision.record(DECISION, EVIDENCE, self.asked)
        self.assertEqual(refused, [])
        self.assertEqual((recorded["disposition"], recorded["owner_role"], recorded["date"]),
                         ("defer", "capture lead", "2025-12-05"))
        self.assertTrue(recorded["decision_entered"])
        self.assertIn("Fictional", recorded["note"])

    def test_the_decision_rests_on_accepted_evidence_and_open_questions(self):
        status = {e["evidence_id"]: e["review_status"] for e in EVIDENCE}
        for eid in DECISION["supporting_evidence_ids"]:
            self.assertEqual(status[eid], ledger.ACCEPTED, eid)
        for qid in DECISION["open_questions"]:
            self.assertEqual(self.by_id[qid]["status"], questions.OPEN, qid)


if __name__ == "__main__":
    unittest.main()
