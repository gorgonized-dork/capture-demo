"""
Fitness functions for field questions and the decision inside a pipeline run.

A run writes its field questions (as data and as a readable page) and the
decision record next to everything else. With no decision entered, or with
one that is refused, the run records undecided. The field notes and the
decision file are only ever read.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import decision, pipeline

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "sample"
INPUTS = {
    "proposals_path": SAMPLE / "proposed_evidence.json",
    "reviews_path": SAMPLE / "review_log.json",
    "notes_path": SAMPLE / "field_notes.json",
    "decision_path": SAMPLE / "decision.json",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PipelineFieldWork(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.runs_dir = self.tmp / "runs"

    def run_sample(self, **overrides):
        inputs = dict(INPUTS, **overrides)
        return pipeline.run(SAMPLE / "brief.json", FixtureAdapter(), self.runs_dir, **inputs)

    def test_run_writes_questions_and_the_decision(self):
        run_dir = self.run_sample()
        asked = load(run_dir / "field_questions.json")
        self.assertEqual(len(asked), 9)
        self.assertEqual(sum(q["status"] == "answered" for q in asked), 3)
        page = (run_dir / "field_questions.md").read_text(encoding="utf-8")
        self.assertIn("## Open", page)
        self.assertIn("### Q-DISPROOF", page)
        recorded = load(run_dir / "decision.json")
        self.assertEqual((recorded["disposition"], recorded["decision_entered"]), ("defer", True))

    def test_run_record_counts_questions_and_hashes_inputs_and_outputs(self):
        run_dir = self.run_sample()
        record = load(run_dir / "run.json")
        q = record["questions"]
        self.assertEqual((q["asked"], q["answered"], q["open"], q["refused_notes"]), (9, 3, 6, 0))
        self.assertEqual(q["field_notes_sha256"], sha256(INPUTS["notes_path"]))
        self.assertEqual(q["questions_sha256"], sha256(run_dir / "field_questions.json"))
        self.assertEqual(q["questions_md_sha256"], sha256(run_dir / "field_questions.md"))
        d = record["decision"]
        self.assertEqual((d["disposition"], d["decision_entered"], d["refused"]), ("defer", True, False))
        self.assertEqual(d["decision_input_sha256"], sha256(INPUTS["decision_path"]))
        self.assertEqual(d["decision_sha256"], sha256(run_dir / "decision.json"))

    def test_without_a_decision_the_run_is_undecided(self):
        run_dir = self.run_sample(decision_path=None)
        self.assertEqual(load(run_dir / "decision.json"),
                         {"disposition": "undecided", "decision_entered": False,
                          "reason": "no decision entered"})

    def test_a_refused_decision_leaves_the_run_undecided_and_is_recorded(self):
        bad = self.tmp / "decision.json"
        bad.write_text(json.dumps(dict(load(INPUTS["decision_path"]), pwin=0.6)), encoding="utf-8")
        run_dir = self.run_sample(decision_path=bad)
        self.assertEqual(load(run_dir / "decision.json")["disposition"], "undecided")
        refused = [json.loads(line) for line in
                   (run_dir / "refused.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(r["kind"], r["code"]) for r in refused if r["kind"] == "decision"],
                         [("decision", decision.UNKNOWN_FIELD)])

    def test_run_never_changes_the_field_notes_or_the_decision(self):
        before = {k: Path(v).read_bytes() for k, v in INPUTS.items()}
        self.run_sample()
        self.assertEqual({k: Path(v).read_bytes() for k, v in INPUTS.items()}, before)

    def test_decision_file_that_is_not_an_object_creates_no_folder(self):
        bad = self.tmp / "decision.json"
        bad.write_text('["defer"]', encoding="utf-8")
        with self.assertRaises(decision.DecisionError):
            self.run_sample(decision_path=bad)
        self.assertFalse(self.runs_dir.exists())

    def cli(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pipeline.main(["run", "--brief", str(SAMPLE / "brief.json"), "--adapter", "fixture",
                                  "--runs-dir", str(self.runs_dir), *extra])
        return code, out.getvalue()

    def test_command_prints_questions_and_decision(self):
        code, out = self.cli("--proposals", str(INPUTS["proposals_path"]),
                             "--reviews", str(INPUTS["reviews_path"]),
                             "--field-notes", str(INPUTS["notes_path"]),
                             "--decision", str(INPUTS["decision_path"]))
        self.assertEqual(code, 0, out)
        self.assertIn("questions 9 asked: 3 answered, 6 open", out)
        self.assertIn("decision defer (capture lead, 2025-12-05)", out)

    def test_command_says_undecided_when_no_decision_is_entered(self):
        code, out = self.cli()
        self.assertEqual(code, 0, out)
        self.assertIn("decision undecided: no decision entered", out)


if __name__ == "__main__":
    unittest.main()
