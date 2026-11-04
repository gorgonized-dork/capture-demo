"""
Fitness functions for the report inside a pipeline run.

The report is written last, from the files the run just wrote, and run.json
records its hash, so the finished run verifies end to end. If a report check
fails, the run says so, keeps its files for inspection, and writes no report.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.fixture import FixtureAdapter
from core import pipeline, report

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
INPUTS = {
    "proposals_path": SAMPLE / "proposed_evidence.json",
    "reviews_path": SAMPLE / "review_log.json",
    "notes_path": SAMPLE / "field_notes.json",
    "decision_path": SAMPLE / "decision.json",
}
BLOCKED = report.ReportBlocked([{"code": report.UNRESOLVED_ID, "detail": "EV-099 is not in the run's evidence"}])


class PipelineReport(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.runs_dir = Path(tmp.name) / "runs"

    def run_sample(self):
        return pipeline.run(SAMPLE / "brief.json", FixtureAdapter(), self.runs_dir, **INPUTS)

    def test_run_writes_a_report_that_verifies_end_to_end(self):
        run_dir = self.run_sample()
        self.assertIn("report.md", pipeline.RUN_FILES)
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["report"]
        self.assertEqual((record["status"], record["checks"], record["report_file"]),
                         ("written", "passed", "report.md"))
        self.assertEqual(report.verify(run_dir), [])

    def test_a_blocked_report_is_recorded_and_nothing_is_written(self):
        with mock.patch.object(report, "check", return_value=BLOCKED.failures):
            with self.assertRaises(report.ReportBlocked):
                self.run_sample()
        [run_dir] = self.runs_dir.iterdir()
        self.assertFalse((run_dir / "report.md").exists())
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["report"]
        self.assertEqual(record, {"status": "blocked", "failures": BLOCKED.failures})

    def cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pipeline.main(["run", "--brief", str(SAMPLE / "brief.json"), "--adapter", "fixture",
                                  "--runs-dir", str(self.runs_dir),
                                  "--proposals", str(INPUTS["proposals_path"]),
                                  "--reviews", str(INPUTS["reviews_path"]),
                                  "--field-notes", str(INPUTS["notes_path"]),
                                  "--decision", str(INPUTS["decision_path"])])
        return code, out.getvalue()

    def test_command_prints_where_the_checked_report_is(self):
        code, out = self.cli()
        self.assertEqual(code, 0, out)
        self.assertIn("report.md (traceability and claim checks passed)", out)

    def test_command_reports_a_blocked_report_and_fails(self):
        with mock.patch.object(report, "check", return_value=BLOCKED.failures):
            code, out = self.cli()
        self.assertEqual(code, 1)
        self.assertIn("report blocked; no report was written", out)
        self.assertIn("UNRESOLVED_ID: EV-099", out)


if __name__ == "__main__":
    unittest.main()
