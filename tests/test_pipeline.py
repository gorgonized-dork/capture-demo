"""
Fitness functions for the pipeline command.

One command takes a brief to a run folder. These tests hold that the run is
complete and reproducible, that every collected item is snapshotted exactly
as the adapter returned it, and that a failure before the folder exists
leaves nothing behind.
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
from core.pipeline import PipelineError
from core.runs import RunExistsError

REPO = Path(__file__).resolve().parent.parent
SAMPLE_BRIEF = REPO / "sample" / "brief.json"
SAMPLE_ITEMS = REPO / "sample" / "items.json"
SAMPLE = json.loads(SAMPLE_BRIEF.read_text(encoding="utf-8"))
SAMPLE_SLUG = "weekend-hours-and-branch-visits-in-harrowmere-valley"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def folder_bytes(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()}


class TempRuns(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.runs_dir = self.tmp / "runs"

    def run_sample(self, adapter=None, **kwargs):
        return pipeline.run(SAMPLE_BRIEF, adapter or FixtureAdapter(), self.runs_dir, **kwargs)


class SampleRun(TempRuns):

    def test_writes_brief_record_and_snapshot_into_one_folder(self):
        run_dir = self.run_sample()
        self.assertEqual([p.name for p in self.runs_dir.iterdir()], [SAMPLE_SLUG])
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()),
                         ["brief.json", "run.json", "sources.jsonl"])

    def test_snapshot_holds_every_item_in_order_with_exact_ids(self):
        run_dir = self.run_sample()
        on_disk = json.loads(SAMPLE_ITEMS.read_text(encoding="utf-8"))
        snapshot = read_jsonl(run_dir / "sources.jsonl")
        self.assertEqual([line["source_id"] for line in snapshot],
                         ["fixture:" + record["id"] for record in on_disk])

    def test_each_snapshot_body_matches_its_hash(self):
        for line in read_jsonl(self.run_sample() / "sources.jsonl"):
            with self.subTest(source_id=line["source_id"]):
                self.assertEqual(line["body_sha256"],
                                 hashlib.sha256(line["body"].encode("utf-8")).hexdigest())

    def test_missing_fields_stay_null_in_the_snapshot(self):
        snapshot = {line["source_id"]: line
                    for line in read_jsonl(self.run_sample() / "sources.jsonl")}
        district_wide = snapshot["fixture:fx-1008"]
        self.assertIsNone(district_wide["region"])
        self.assertIsNone(district_wide["unit"])

    def test_run_record_describes_the_collection(self):
        run_dir = self.run_sample()
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        snapshot_hash = hashlib.sha256((run_dir / "sources.jsonl").read_bytes()).hexdigest()
        self.assertEqual(record["collection"], {
            "adapter": "fixture",
            "mode": "fixture",
            "items": 10,
            "sources_file": "sources.jsonl",
            "sources_sha256": snapshot_hash,
        })

    def test_rerun_under_a_new_id_gives_an_identical_snapshot(self):
        first = self.run_sample()
        second = self.run_sample(run_id="second-look")
        self.assertEqual((first / "sources.jsonl").read_bytes(),
                         (second / "sources.jsonl").read_bytes())


class FailuresLeaveNothingBehind(TempRuns):

    def test_invalid_brief_creates_no_folder(self):
        path = self.tmp / "brief.json"
        path.write_text(json.dumps({k: v for k, v in SAMPLE.items() if k != "statement"}),
                        encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "'statement'"):
            pipeline.run(path, FixtureAdapter(), self.runs_dir)
        self.assertFalse(self.runs_dir.exists())

    def test_adapter_error_creates_no_folder(self):
        broken = self.tmp / "items.json"
        broken.write_text(json.dumps([{"id": "x-1", "title": "No body or date"}]),
                          encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "adapter 'fixture' failed"):
            self.run_sample(adapter=FixtureAdapter(broken))
        self.assertFalse(self.runs_dir.exists())

    def test_existing_run_is_not_overwritten(self):
        run_dir = self.run_sample()
        before = folder_bytes(run_dir)
        with self.assertRaises(RunExistsError):
            self.run_sample()
        self.assertEqual(folder_bytes(run_dir), before)


class CommandLine(TempRuns):

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = pipeline.main(["run", *args])
        return code, out.getvalue()

    def sample_args(self, *extra):
        return ("--brief", str(SAMPLE_BRIEF), "--adapter", "fixture",
                "--runs-dir", str(self.runs_dir), *extra)

    def test_runs_the_sample_end_to_end(self):
        code, out = self.cli(*self.sample_args())
        self.assertEqual(code, 0, out)
        self.assertIn("10 items", out)
        self.assertIn(f"{SAMPLE_SLUG}/", out)
        self.assertTrue((self.runs_dir / SAMPLE_SLUG / "sources.jsonl").exists())

    def test_adapter_must_be_chosen_explicitly(self):
        with self.assertRaises(SystemExit):
            self.cli("--brief", str(SAMPLE_BRIEF), "--runs-dir", str(self.runs_dir))
        self.assertFalse(self.runs_dir.exists())

    def test_unknown_adapter_is_refused(self):
        with self.assertRaises(SystemExit):
            self.cli("--brief", str(SAMPLE_BRIEF), "--adapter", "dvids",
                     "--runs-dir", str(self.runs_dir))
        self.assertFalse(self.runs_dir.exists())

    def test_repeat_run_explains_how_to_start_another(self):
        self.cli(*self.sample_args())
        code, out = self.cli(*self.sample_args())
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)
        self.assertIn("--run-id", out)

    def test_invalid_brief_is_reported_not_raised(self):
        path = self.tmp / "brief.json"
        path.write_text("{not json", encoding="utf-8")
        code, out = self.cli("--brief", str(path), "--adapter", "fixture",
                             "--runs-dir", str(self.runs_dir))
        self.assertEqual(code, 1)
        self.assertIn("ERROR", out)


if __name__ == "__main__":
    unittest.main()
