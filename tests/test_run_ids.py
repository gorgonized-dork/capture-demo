"""
Fitness functions for run ids.

A run id names the run's folder. It defaults to the brief title's slug; a
caller may choose another so the same brief can run again without touching
the first run. A chosen id can only name a folder inside the runs directory.
"""
import json
import tempfile
import unittest
from pathlib import Path

from core.runs import RunError, RunExistsError, create_run

REPO = Path(__file__).resolve().parent.parent
SAMPLE_PATH = REPO / "sample" / "brief.json"
SAMPLE_SLUG = "weekend-hours-and-branch-visits-in-harrowmere-valley"


class RunIds(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.runs_dir = Path(tmp.name) / "runs"

    def run_record(self, run_dir):
        return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    def test_default_run_id_is_the_title_slug(self):
        run_dir = create_run(SAMPLE_PATH, self.runs_dir)
        record = self.run_record(run_dir)
        self.assertEqual(record["run_id"], SAMPLE_SLUG)
        self.assertEqual(record["slug"], SAMPLE_SLUG)

    def test_chosen_run_id_names_the_folder(self):
        run_dir = create_run(SAMPLE_PATH, self.runs_dir, run_id="demo-2")
        self.assertEqual(run_dir, self.runs_dir / "demo-2")
        record = self.run_record(run_dir)
        self.assertEqual(record["run_id"], "demo-2")
        self.assertEqual(record["slug"], SAMPLE_SLUG)

    def test_same_brief_runs_again_under_a_new_id(self):
        first = create_run(SAMPLE_PATH, self.runs_dir)
        second = create_run(SAMPLE_PATH, self.runs_dir, run_id="second-look")
        self.assertNotEqual(first, second)
        self.assertEqual((first / "brief.json").read_bytes(),
                         (second / "brief.json").read_bytes())

    def test_reused_run_id_is_refused(self):
        create_run(SAMPLE_PATH, self.runs_dir, run_id="demo-2")
        with self.assertRaises(RunExistsError):
            create_run(SAMPLE_PATH, self.runs_dir, run_id="demo-2")

    def test_unsafe_run_ids_are_refused(self):
        for bad in ("../elsewhere", "demo/2", "C:\\demo", "Demo", "demo_2",
                    "-demo", "demo--2", "", "x" * 61):
            with self.subTest(run_id=bad):
                with self.assertRaisesRegex(RunError, "run id"):
                    create_run(SAMPLE_PATH, self.runs_dir, run_id=bad)
        self.assertFalse(self.runs_dir.exists())


if __name__ == "__main__":
    unittest.main()
