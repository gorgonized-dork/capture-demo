"""
Fitness functions for triage inside a pipeline run.

Each run writes a triage record for every item it snapshotted, in the same
order, and records the outcome counts so a reader can check them against the
file without rerunning anything.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import pipeline

REPO = Path(__file__).resolve().parent.parent
SAMPLE_BRIEF = REPO / "sample" / "brief.json"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class PipelineTriage(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.runs_dir = Path(tmp.name) / "runs"

    def test_run_writes_triage_next_to_the_snapshot(self):
        run_dir = pipeline.run(SAMPLE_BRIEF, FixtureAdapter(), self.runs_dir)
        self.assertIn("triage.jsonl", pipeline.RUN_FILES)
        sources = [line["source_id"] for line in read_jsonl(run_dir / "sources.jsonl")]
        triaged = [line["source_id"] for line in read_jsonl(run_dir / "triage.jsonl")]
        self.assertEqual(triaged, sources)

    def test_run_record_counts_triage_outcomes(self):
        run_dir = pipeline.run(SAMPLE_BRIEF, FixtureAdapter(), self.runs_dir)
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        file_hash = hashlib.sha256((run_dir / "triage.jsonl").read_bytes()).hexdigest()
        self.assertEqual(record["triage"], {
            "included": 5,
            "needs_review": 2,
            "excluded": 3,
            "triage_file": "triage.jsonl",
            "triage_sha256": file_hash,
        })

    def test_command_prints_triage_counts(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pipeline.main(["run", "--brief", str(SAMPLE_BRIEF), "--adapter", "fixture",
                                  "--runs-dir", str(self.runs_dir)])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("triage   5 included, 2 to review, 3 excluded", out.getvalue())


if __name__ == "__main__":
    unittest.main()
