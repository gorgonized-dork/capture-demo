"""
Fitness functions for the evidence ledger inside a pipeline run.

A run writes the ledger and every refusal next to the snapshot and triage,
records the counts and the hashes of its inputs, and only ever reads the
proposals and the review log: a run never changes the human record.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import ledger, pipeline

REPO = Path(__file__).resolve().parent.parent
SAMPLE_BRIEF = REPO / "sample" / "brief.json"
PROPOSALS = REPO / "sample" / "proposed_evidence.json"
REVIEWS = REPO / "sample" / "review_log.json"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PipelineEvidence(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.runs_dir = self.tmp / "runs"

    def run_sample(self, **kwargs):
        return pipeline.run(SAMPLE_BRIEF, FixtureAdapter(), self.runs_dir,
                            proposals_path=PROPOSALS, reviews_path=REVIEWS, **kwargs)

    def test_run_writes_the_ledger_and_every_refusal(self):
        run_dir = self.run_sample()
        evidence = read_jsonl(run_dir / "evidence.jsonl")
        refused = read_jsonl(run_dir / "refused.jsonl")
        self.assertEqual([e["evidence_id"] for e in evidence],
                         [f"EV-{n:03d}" for n in range(1, 9)])
        self.assertEqual([(r["id"], r["code"]) for r in refused],
                         [("EV-009", ledger.QUOTE_NOT_IN_SOURCE),
                          ("EV-010", ledger.PROPOSER_SET_STATUS)])

    def test_run_record_counts_evidence_and_hashes_its_inputs(self):
        run_dir = self.run_sample()
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["evidence"]
        self.assertEqual((record["in_ledger"], record["accepted"], record["rejected"],
                          record["awaiting_review"], record["refused"]), (8, 4, 1, 3, 2))
        self.assertEqual(record["proposals_sha256"], sha256(PROPOSALS))
        self.assertEqual(record["reviews_sha256"], sha256(REVIEWS))
        self.assertEqual(record["evidence_sha256"], sha256(run_dir / "evidence.jsonl"))
        self.assertEqual(record["refused_sha256"], sha256(run_dir / "refused.jsonl"))

    def test_run_never_changes_the_proposals_or_the_review_log(self):
        before = (PROPOSALS.read_bytes(), REVIEWS.read_bytes())
        self.run_sample()
        self.assertEqual((PROPOSALS.read_bytes(), REVIEWS.read_bytes()), before)

    def test_without_proposals_the_ledger_files_are_written_empty(self):
        run_dir = pipeline.run(SAMPLE_BRIEF, FixtureAdapter(), self.runs_dir)
        self.assertEqual((run_dir / "evidence.jsonl").read_bytes(), b"")
        self.assertEqual((run_dir / "refused.jsonl").read_bytes(), b"")
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["evidence"]
        self.assertIsNone(record["proposals_sha256"])
        self.assertEqual(record["in_ledger"], 0)

    def test_unreadable_proposals_file_creates_no_folder(self):
        bad = self.tmp / "proposals.json"
        bad.write_text('{"not": "a list"}', encoding="utf-8")
        with self.assertRaises(ledger.LedgerError):
            pipeline.run(SAMPLE_BRIEF, FixtureAdapter(), self.runs_dir, proposals_path=bad)
        self.assertFalse(self.runs_dir.exists())

    def cli(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pipeline.main(["run", "--brief", str(SAMPLE_BRIEF), "--adapter", "fixture",
                                  "--runs-dir", str(self.runs_dir), *extra])
        return code, out.getvalue()

    def test_command_prints_evidence_counts(self):
        code, out = self.cli("--proposals", str(PROPOSALS), "--reviews", str(REVIEWS))
        self.assertEqual(code, 0, out)
        self.assertIn("evidence 8 in ledger: 4 accepted, 1 rejected, 3 awaiting review; 2 refused",
                      out)

    def test_command_says_when_no_proposals_were_given(self):
        code, out = self.cli()
        self.assertEqual(code, 0, out)
        self.assertIn("evidence no proposals given", out)

    def test_command_reports_an_unreadable_proposals_file(self):
        bad = self.tmp / "proposals.json"
        bad.write_text("[not json", encoding="utf-8")
        code, out = self.cli("--proposals", str(bad))
        self.assertEqual(code, 1)
        self.assertIn("ERROR", out)
        self.assertFalse(self.runs_dir.exists())


if __name__ == "__main__":
    unittest.main()
