"""
Fitness functions for run folders.

A run folder records what the run was asked. These tests hold that: an
invalid brief creates nothing, the brief is copied byte for byte with its
hash, flags travel with the run, and an existing run is never overwritten.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.brief import UNTESTED_HYPOTHESIS
from core.runs import RunError, create_run

REPO = Path(__file__).resolve().parent.parent
SAMPLE_PATH = REPO / "sample" / "brief.json"
SAMPLE = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
SAMPLE_SLUG = "weekend-hours-and-branch-visits-in-harrowmere-valley"


class RunFolders(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.runs_dir = self.tmp / "runs"

    def write_brief(self, brief, name="brief.json"):
        path = self.tmp / name
        path.write_text(json.dumps(brief, indent=2), encoding="utf-8")
        return path

    def run_record(self, run_dir):
        return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    def test_folder_is_named_from_the_brief_title(self):
        run_dir = create_run(SAMPLE_PATH, self.runs_dir)
        self.assertEqual(run_dir, self.runs_dir / SAMPLE_SLUG)

    def test_brief_is_copied_byte_for_byte_with_its_hash(self):
        run_dir = create_run(SAMPLE_PATH, self.runs_dir)
        original = SAMPLE_PATH.read_bytes()
        self.assertEqual((run_dir / "brief.json").read_bytes(), original)
        self.assertEqual(self.run_record(run_dir)["brief_sha256"],
                         hashlib.sha256(original).hexdigest())

    def test_sample_run_carries_no_flags(self):
        run_dir = create_run(SAMPLE_PATH, self.runs_dir)
        self.assertEqual(self.run_record(run_dir)["flags"], [])

    def test_untested_hypothesis_flag_travels_with_the_run(self):
        brief = {k: v for k, v in SAMPLE.items() if k != "disproof"}
        run_dir = create_run(self.write_brief(brief), self.runs_dir)
        self.assertEqual(self.run_record(run_dir)["flags"], [UNTESTED_HYPOTHESIS])

    def test_invalid_brief_creates_nothing(self):
        brief = {k: v for k, v in SAMPLE.items() if k != "statement"}
        with self.assertRaisesRegex(RunError, "'statement'"):
            create_run(self.write_brief(brief), self.runs_dir)
        self.assertFalse(self.runs_dir.exists())

    def test_existing_run_is_never_overwritten(self):
        run_dir = create_run(SAMPLE_PATH, self.runs_dir)
        before = (run_dir / "brief.json").read_bytes()
        changed = dict(SAMPLE, statement="A different claim under the same title.")
        with self.assertRaisesRegex(RunError, "already exists"):
            create_run(self.write_brief(changed), self.runs_dir)
        self.assertEqual((run_dir / "brief.json").read_bytes(), before)

    def test_title_with_nothing_to_name_a_folder_is_rejected(self):
        with self.assertRaisesRegex(RunError, "title"):
            create_run(self.write_brief(dict(SAMPLE, title="???")), self.runs_dir)
        self.assertFalse(self.runs_dir.exists())


if __name__ == "__main__":
    unittest.main()
