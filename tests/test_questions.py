"""
Fitness functions for field questions.

The pipeline asks; it never answers. These tests pin the questions the
sample raises, and hold that only accepted evidence raises questions, that
every question starts open, that only a field note can answer one, and
that a respondent is named by role, never by name.
"""
import copy
import json
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import ledger, questions
from core.questions import (ANSWERED, BAD_DATE, DUPLICATE_ANSWER, FIELD_NOTE, MISSING_FIELD,
                            OPEN, UNKNOWN_FIELD, UNKNOWN_QUESTION)
from core.triage import triage

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
BRIEF = json.loads((SAMPLE / "brief.json").read_text(encoding="utf-8"))
ITEMS = FixtureAdapter().collect()
TRIAGED = triage(ITEMS, BRIEF)
PROPOSALS = ledger.load_records(SAMPLE / "proposed_evidence.json", "proposals")
REVIEWS = ledger.load_records(SAMPLE / "review_log.json", "reviews")
EVIDENCE, _ = ledger.build(PROPOSALS, REVIEWS, ITEMS, TRIAGED)

EXPECTED = [
    ("Q-BRIEF-1", "BRIEF"),
    ("Q-BRIEF-2", "BRIEF"),
    ("Q-DISPROOF", "DISPROOF"),
    ("Q-BASELINE", "BASELINE"),
    ("Q-ALTERNATE-EV-002", "ALTERNATE"),
    ("Q-SECOND-SOURCE", "SECOND_SOURCE"),
    ("Q-SETTLE-EV-007", "SETTLE"),
    ("Q-SCOPE-EV-007", "SCOPE"),
    ("Q-UNIT-STONECROSS-BRANCH", "UNCOVERED_UNIT"),
]


def ask(brief=BRIEF, evidence=EVIDENCE):
    triaged = TRIAGED if brief is BRIEF else triage(ITEMS, brief)
    return questions.ask(brief, ITEMS, triaged, copy.deepcopy(evidence))


def by_id(asked):
    return {q["question_id"]: q for q in asked}


def note(**changes):
    record = {"question_id": "Q-BRIEF-1", "answer": "Northgate and Millbrook.",
              "respondent_role": "branch staff", "date": "2025-12-03", "provenance": "phone call"}
    record.update(changes)
    return record


class SampleQuestions(unittest.TestCase):

    def setUp(self):
        self.asked = ask()
        self.by_id = by_id(self.asked)

    def test_the_sample_raises_these_questions_in_order(self):
        self.assertEqual([(q["question_id"], q["origin"]) for q in self.asked], EXPECTED)

    def test_brief_questions_are_asked_word_for_word(self):
        self.assertEqual([self.by_id["Q-BRIEF-1"]["question"], self.by_id["Q-BRIEF-2"]["question"]],
                         BRIEF["questions"])

    def test_asks_about_baselines_unchanged_branches_and_other_causes(self):
        self.assertIn("baseline period", self.by_id["Q-BASELINE"]["question"])
        self.assertIn("branches whose hours did not change", self.by_id["Q-DISPROOF"]["question"])
        self.assertIn("what else could explain", self.by_id["Q-ALTERNATE-EV-002"]["question"])

    def test_every_question_starts_open_with_no_answer(self):
        for q in self.asked:
            with self.subTest(question_id=q["question_id"]):
                self.assertEqual((q["status"], q["answer"]), (OPEN, None))
                self.assertTrue(q["why_it_matters"])

    def test_linked_evidence_is_always_accepted_evidence(self):
        accepted = {e["evidence_id"] for e in EVIDENCE if e["review_status"] == ledger.ACCEPTED}
        for q in self.asked:
            with self.subTest(question_id=q["question_id"]):
                self.assertLessEqual(set(q["linked_evidence_ids"]), accepted)

    def test_republished_evidence_raises_no_question_of_its_own(self):
        self.assertNotIn("Q-ALTERNATE-EV-008", self.by_id)
        self.assertEqual(self.by_id["Q-SECOND-SOURCE"]["linked_evidence_ids"], ["EV-002"])


class Rules(unittest.TestCase):

    def test_unreviewed_evidence_raises_no_questions(self):
        unreviewed, _ = ledger.build(PROPOSALS, [], ITEMS, TRIAGED)
        asked = ask(evidence=unreviewed)
        self.assertEqual([q for q in asked if q["linked_evidence_ids"]], [])
        self.assertEqual({q["origin"] for q in asked},
                         {"BRIEF", "DISPROOF", "UNCOVERED_REGION", "UNCOVERED_UNIT"})

    def test_hypothesis_without_disproof_asks_for_one(self):
        brief = {k: v for k, v in BRIEF.items() if k != "disproof"}
        ids = [q["question_id"] for q in ask(brief=brief)]
        self.assertIn("Q-DISPROOF-MISSING", ids)
        self.assertNotIn("Q-DISPROOF", ids)

    def test_topic_brief_asks_no_hypothesis_questions(self):
        brief = dict(BRIEF, type="topic")
        origins = {q["origin"] for q in ask(brief=brief)}
        self.assertFalse(origins & {"DISPROOF", "DISPROOF_MISSING", "ALTERNATE", "SECOND_SOURCE"})

    def test_brief_without_scope_lists_asks_nothing_about_coverage(self):
        brief = dict(BRIEF, scope={"date_from": "2025-01-01", "date_to": "2025-12-31"})
        origins = {q["origin"] for q in ask(brief=brief)}
        self.assertFalse(origins & {"SCOPE", "UNCOVERED_REGION", "UNCOVERED_UNIT"})


class FieldNotes(unittest.TestCase):

    def setUp(self):
        self.asked = ask()

    def test_a_field_note_closes_its_question_and_is_labeled(self):
        refused = questions.answer(self.asked, [note()])
        self.assertEqual(refused, [])
        q = by_id(self.asked)["Q-BRIEF-1"]
        self.assertEqual(q["status"], ANSWERED)
        self.assertEqual(q["answer"], {"text": "Northgate and Millbrook.", "respondent_role": "branch staff",
                                       "date": "2025-12-03", "provenance": "phone call",
                                       "kind": FIELD_NOTE})

    def test_unanswered_questions_stay_open(self):
        questions.answer(self.asked, [note()])
        self.assertEqual(questions.counts(self.asked), {"asked": 9, "answered": 1, "open": 8})

    def test_a_respondent_is_named_by_role_only(self):
        for field in ("respondent", "name", "email"):
            with self.subTest(field=field):
                refused = questions.answer(ask(), [note(**{field: "A. Person"})])
                self.assertEqual([r["code"] for r in refused], [UNKNOWN_FIELD])

    def test_malformed_notes_are_refused_and_leave_the_question_open(self):
        cases = [(note(question_id="Q-NOPE"), UNKNOWN_QUESTION),
                 (note(date="3 Dec 2025"), BAD_DATE),
                 (note(answer=""), MISSING_FIELD),
                 (note(provenance=None), MISSING_FIELD)]
        for record, code in cases:
            with self.subTest(code=code, record=record):
                asked = ask()
                refused = questions.answer(asked, [record])
                self.assertEqual([r["code"] for r in refused], [code])
                self.assertEqual(questions.counts(asked)["answered"], 0)

    def test_second_answer_is_refused_and_the_first_stands(self):
        refused = questions.answer(self.asked, [note(), note(answer="Every branch.")])
        self.assertEqual([r["code"] for r in refused], [DUPLICATE_ANSWER])
        self.assertEqual(by_id(self.asked)["Q-BRIEF-1"]["answer"]["text"], "Northgate and Millbrook.")


class Markdown(unittest.TestCase):

    def test_open_questions_come_first_and_answers_are_labeled(self):
        asked = ask()
        questions.answer(asked, [note()])
        text = questions.render_markdown(asked)
        self.assertLess(text.index("## Open"), text.index("## Answered"))
        for q in asked:
            self.assertIn(f"### {q['question_id']}", text)
        self.assertIn(f"Answer ({FIELD_NOTE})", text)


if __name__ == "__main__":
    unittest.main()
