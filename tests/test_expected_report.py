"""
Fitness function for the committed example report.

sample/expected/report.md is what a reader sees without running anything.
This test regenerates it from the sample and requires an exact match, so the
committed example is always what the code actually produces.
"""
import tempfile
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import pipeline

SAMPLE = Path(__file__).resolve().parent.parent / "sample"


def normalized(text):
    return text.replace("\r\n", "\n")


class ExpectedReport(unittest.TestCase):

    def test_the_committed_report_is_exactly_what_the_sample_produces(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pipeline.run(SAMPLE / "brief.json", FixtureAdapter(), Path(tmp),
                                   proposals_path=SAMPLE / "proposed_evidence.json",
                                   reviews_path=SAMPLE / "review_log.json",
                                   notes_path=SAMPLE / "field_notes.json",
                                   decision_path=SAMPLE / "decision.json")
            produced = (run_dir / "report.md").read_text(encoding="utf-8")
        committed = (SAMPLE / "expected" / "report.md").read_text(encoding="utf-8")
        self.assertEqual(normalized(produced), normalized(committed))


if __name__ == "__main__":
    unittest.main()
