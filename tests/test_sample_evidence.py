"""
Fitness functions for the sample evidence.

Runs the sample proposals and review log through the ledger. These tests pin
the outcome for each proposal, and hold that every accepted claim traces to
an unchanged source item and that Northgate's rise and Millbrook's flat
visits are both on the record.
"""
import hashlib
import json
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import ledger
from core.ledger import ACCEPTED, PROPOSED, PROPOSER_SET_STATUS, QUOTE_NOT_IN_SOURCE, REJECTED
from core.triage import triage

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "sample"
BRIEF = json.loads((SAMPLE / "brief.json").read_text(encoding="utf-8"))
ITEMS = FixtureAdapter().collect()
PROPOSALS = ledger.load_records(SAMPLE / "proposed_evidence.json", "proposals")
REVIEWS = ledger.load_records(SAMPLE / "review_log.json", "reviews")

EXPECTED_STATUS = {
    "EV-001": PROPOSED,   # not reviewed
    "EV-002": ACCEPTED,   # Northgate: 1,880 against 1,410
    "EV-003": PROPOSED,
    "EV-004": PROPOSED,
    "EV-005": ACCEPTED,   # Millbrook: about 960 against 940
    "EV-006": ACCEPTED,   # Linden Street, hours unchanged
    "EV-007": ACCEPTED,   # district claim with no figures
    "EV-008": REJECTED,   # republishes fx-1002's figures
}
EXPECTED_REFUSALS = {
    "EV-009": QUOTE_NOT_IN_SOURCE,   # 1,980 instead of 1,880
    "EV-010": PROPOSER_SET_STATUS,   # tries to mark itself ACCEPTED
}


class SampleEvidence(unittest.TestCase):

    def setUp(self):
        self.evidence, self.refused = ledger.build(PROPOSALS, REVIEWS, ITEMS, triage(ITEMS, BRIEF))
        self.by_id = {entry["evidence_id"]: entry for entry in self.evidence}

    def test_each_proposal_has_the_expected_outcome(self):
        self.assertEqual({e["evidence_id"]: e["review_status"] for e in self.evidence},
                         EXPECTED_STATUS)
        self.assertEqual({r["id"]: r["code"] for r in self.refused}, EXPECTED_REFUSALS)

    def test_every_review_in_the_log_applies(self):
        self.assertEqual([r for r in self.refused if r["kind"] == "review"], [])
        reviewed = [e["evidence_id"] for e in self.evidence if e["review"] is not None]
        self.assertEqual(reviewed, [r["evidence_id"] for r in REVIEWS])

    def test_every_accepted_claim_traces_to_an_unchanged_source(self):
        bodies = {item.source_id: item.body for item in ITEMS}
        for entry in self.evidence:
            if entry["review_status"] != ACCEPTED:
                continue
            with self.subTest(evidence_id=entry["evidence_id"]):
                body = bodies[entry["source_id"]]
                self.assertIn(entry["verbatim_excerpt"], body)
                self.assertEqual(entry["source_body_sha256"],
                                 hashlib.sha256(body.encode("utf-8")).hexdigest())

    def test_rise_and_flat_visits_are_both_on_the_record(self):
        rise, flat = self.by_id["EV-002"], self.by_id["EV-005"]
        self.assertEqual((rise["source_id"], rise["stance"]), ("fixture:fx-1002", "supports"))
        self.assertEqual((flat["source_id"], flat["stance"]), ("fixture:fx-1004", "challenges"))
        self.assertEqual({rise["review_status"], flat["review_status"]}, {ACCEPTED})

    def test_republished_report_is_rejected_and_not_independent(self):
        repeat = self.by_id["EV-008"]
        self.assertEqual(repeat["review_status"], REJECTED)
        self.assertFalse(repeat["independent"])
        self.assertEqual(repeat["source_possible_duplicate_of"], ["fixture:fx-1002"])


if __name__ == "__main__":
    unittest.main()
