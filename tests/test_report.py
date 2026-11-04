"""
Fitness functions for the report and its checks.

The report is written from the run folder's files and only after two checks
pass. These tests hold that it shows the recorded decision first, lists
only accepted evidence as findings, counts each source once, prints missing
fields as "unverified", and that every check catches the failure it exists
for: an edited file, an id that resolves to nothing, a quote not in its
source, unaccepted evidence under Findings, or a decision that was not the
one recorded.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import pipeline, report
from core.report import (DECISION_MISMATCH, FINDING_NOT_ACCEPTED, HASH_MISMATCH,
                         QUOTE_NOT_IN_SOURCE, REPORT_CHANGED, UNRESOLVED_ID)

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
INPUTS = {
    "proposals_path": SAMPLE / "proposed_evidence.json",
    "reviews_path": SAMPLE / "review_log.json",
    "notes_path": SAMPLE / "field_notes.json",
    "decision_path": SAMPLE / "decision.json",
}


def codes(failures):
    return sorted(f["code"] for f in failures)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl(path, rows):
    path.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))


class TempRun(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def make_run(self, brief=SAMPLE / "brief.json", run_id=None, **overrides):
        inputs = dict(INPUTS, **overrides)
        return pipeline.run(brief, FixtureAdapter(), self.tmp / "runs", run_id=run_id, **inputs)

    def rendered(self, run_dir):
        run = report.load_run(run_dir)
        return run, report.render(run)


class Rendering(TempRun):

    def setUp(self):
        super().setUp()
        self.run_dir = self.make_run()
        self.run, self.text = self.rendered(self.run_dir)

    def test_the_sample_report_passes_both_checks(self):
        self.assertEqual(report.check(self.run_dir, self.run, self.text), [])

    def test_the_recorded_decision_comes_before_the_findings(self):
        self.assertIn("| Decision | **Defer**, entered by capture lead on 2025-12-05 |", self.text)
        self.assertLess(self.text.index("## Decision"), self.text.index("## Findings"))

    def test_findings_list_only_accepted_evidence(self):
        findings = report._section(self.text, "## Findings")
        self.assertEqual(set(report.EVIDENCE_ID_RE.findall(findings)),
                         {"EV-002", "EV-005", "EV-006", "EV-007"})

    def test_missing_fields_print_as_unverified(self):
        self.assertIn("| fixture:fx-1008 | 2025-11-20 | unverified | unverified |", self.text)
        self.assertIn("**EV-007** from fixture:fx-1008 (unit unverified, region unverified,", self.text)

    def test_answers_are_labeled_as_field_notes(self):
        self.assertIn("### Answered by field notes (not published sources)", self.text)

    def test_unreviewed_rejected_and_refused_evidence_is_listed_as_not_counted(self):
        not_counted = report._section(self.text, "## Not counted")
        for eid in ("EV-001", "EV-003", "EV-004", "EV-008", "EV-009", "EV-010"):
            self.assertIn(eid, not_counted)


class Cases(TempRun):

    def test_a_repeated_source_is_counted_once(self):
        reviews = json.loads(INPUTS["reviews_path"].read_text(encoding="utf-8"))
        for review in reviews:
            if review["evidence_id"] == "EV-008":
                review["decision"] = "accept"
        path = self.tmp / "reviews.json"
        path.write_text(json.dumps(reviews), encoding="utf-8")
        _, text = self.rendered(self.make_run(reviews_path=path, decision_path=None))
        self.assertIn("### Supports: 1 independent source", text)
        self.assertIn("Repeats fixture:fx-1002; not counted as a separate source", text)

    def test_with_no_decision_the_report_says_undecided(self):
        _, text = self.rendered(self.make_run(decision_path=None))
        self.assertIn("| Decision | **Undecided**: no decision entered |", text)
        self.assertIn("The software never enters a decision.", text)

    def test_an_untested_hypothesis_is_said_plainly(self):
        brief = json.loads((SAMPLE / "brief.json").read_text(encoding="utf-8"))
        del brief["disproof"]
        path = self.tmp / "brief.json"
        path.write_text(json.dumps(brief), encoding="utf-8")
        _, text = self.rendered(self.make_run(brief=path, decision_path=None))
        self.assertIn("| Hypothesis test | No disproof condition given: this hypothesis is untested |", text)


class Checks(TempRun):

    def setUp(self):
        super().setUp()
        self.run_dir = self.make_run()
        self.run, self.text = self.rendered(self.run_dir)

    def check(self, text=None):
        run = report.load_run(self.run_dir)
        return report.check(self.run_dir, run, report.render(run) if text is None else text)

    def test_an_edited_file_fails_the_hash_check(self):
        path = self.run_dir / "evidence.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        self.assertEqual(codes(self.check()), [HASH_MISMATCH])

    def test_ids_that_resolve_to_nothing_fail(self):
        text = self.text + "See EV-099, Q-NOPE, and fixture:fx-9999.\n"
        self.assertEqual(codes(self.check(text)), [UNRESOLVED_ID] * 3)

    def test_unaccepted_evidence_under_findings_fails(self):
        text = self.text.replace("## Findings\n", "## Findings\n\n- EV-001 slipped in\n", 1)
        self.assertEqual(codes(self.check(text)), [FINDING_NOT_ACCEPTED])

    def test_a_decision_other_than_the_recorded_one_fails(self):
        text = self.text.replace("| Decision | **Defer**", "| Decision | **Pursue**", 1)
        self.assertEqual(codes(self.check(text)), [DECISION_MISMATCH])

    def test_an_accepted_excerpt_not_in_its_source_fails_even_with_hashes_updated(self):
        path = self.run_dir / "evidence.jsonl"
        rows = read_jsonl(path)
        rows[1]["verbatim_excerpt"] = "Northgate Branch counted 1,980 weekend visits in June"
        write_jsonl(path, rows)
        record_path = self.run_dir / "run.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["evidence"]["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.assertEqual(codes(self.check()), [QUOTE_NOT_IN_SOURCE])

    def test_a_failed_check_writes_no_report(self):
        (self.run_dir / "sources.jsonl").write_bytes(b"")
        (self.run_dir / "report.md").unlink(missing_ok=True)
        with self.assertRaises(report.ReportBlocked) as caught:
            report.write(self.run_dir)
        self.assertIn(HASH_MISMATCH, codes(caught.exception.failures))
        self.assertFalse((self.run_dir / "report.md").exists())


class Verify(TempRun):

    def setUp(self):
        super().setUp()
        self.run_dir = self.make_run()
        report.write(self.run_dir)

    def cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = report.main(["check", str(self.run_dir)])
        return code, out.getvalue()

    def test_an_untouched_run_verifies(self):
        self.assertEqual(report.verify(self.run_dir), [])
        code, out = self.cli()
        self.assertEqual(code, 0, out)
        self.assertIn("verified", out)

    def test_an_edited_report_fails_verification(self):
        path = self.run_dir / "report.md"
        path.write_text(path.read_text(encoding="utf-8").replace("**Defer**", "**Pursue**"),
                        encoding="utf-8")
        self.assertIn(REPORT_CHANGED, codes(report.verify(self.run_dir)))
        code, out = self.cli()
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)


if __name__ == "__main__":
    unittest.main()
