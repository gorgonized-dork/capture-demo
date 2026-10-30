"""
Fitness functions for the fixture adapter.

The fixture adapter is the offline source. It must return every sample item
in the shared SourceItem shape, keep ids exact, leave missing fields empty
rather than fill them, and fail loudly on a malformed record instead of
skipping it.
"""
import json
import tempfile
import unittest
from pathlib import Path

from adapters.base import SourceAdapter, SourceItem
from adapters.fixture import DEFAULT_PATH, FixtureAdapter, FixtureError

GOOD = {"id": "x-1", "title": "A title", "date": "2025-01-01", "body": "Some text."}


def collect_from(records):
    """Write records to a temporary fixture file and collect from it."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "items.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        return FixtureAdapter(path).collect()


class SampleItems(unittest.TestCase):

    def setUp(self):
        self.items = FixtureAdapter().collect()
        self.by_id = {item.source_id: item for item in self.items}

    def test_returns_every_item_in_the_file(self):
        on_disk = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(self.items), len(on_disk))

    def test_is_an_offline_source_adapter(self):
        adapter = FixtureAdapter()
        self.assertIsInstance(adapter, SourceAdapter)
        self.assertEqual(adapter.mode, "fixture")

    def test_items_use_the_shared_record_shape(self):
        for item in self.items:
            self.assertIsInstance(item, SourceItem)

    def test_source_ids_are_namespaced_and_unique(self):
        ids = [item.source_id for item in self.items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(i.startswith("fixture:") for i in ids), ids)

    def test_ids_sharing_a_prefix_stay_distinct(self):
        # fx-10010 contains fx-1001; exact ids keep them two separate items.
        short, long = self.by_id["fixture:fx-1001"], self.by_id["fixture:fx-10010"]
        self.assertNotEqual(short.title, long.title)

    def test_missing_fields_stay_empty(self):
        district_wide = self.by_id["fixture:fx-1008"]
        self.assertIsNone(district_wide.region)
        self.assertIsNone(district_wide.unit)

    def test_queries_do_not_filter_the_fixture(self):
        filtered = FixtureAdapter().collect(queries=["nothing matches this"])
        self.assertEqual(filtered, self.items)


class MalformedFixtures(unittest.TestCase):
    """Bad records stop the read; none are dropped quietly."""

    def test_good_record_is_read(self):
        [item] = collect_from([GOOD])
        self.assertEqual(item.source_id, "fixture:x-1")
        self.assertIsNone(item.url)

    def test_missing_required_field_fails(self):
        for name in ("id", "title", "date", "body"):
            with self.subTest(missing=name):
                record = {k: v for k, v in GOOD.items() if k != name}
                with self.assertRaisesRegex(FixtureError, f"'{name}'"):
                    collect_from([record])

    def test_blank_body_fails(self):
        with self.assertRaisesRegex(FixtureError, "'body'"):
            collect_from([dict(GOOD, body="   ")])

    def test_badly_written_date_fails(self):
        with self.assertRaisesRegex(FixtureError, "'date'"):
            collect_from([dict(GOOD, date="1 Jan 2025")])

    def test_duplicate_id_fails(self):
        with self.assertRaisesRegex(FixtureError, "duplicate id 'x-1'"):
            collect_from([GOOD, dict(GOOD, title="Another")])

    def test_unknown_field_fails(self):
        with self.assertRaisesRegex(FixtureError, "unknown field"):
            collect_from([dict(GOOD, author="someone")])

    def test_blank_optional_field_stays_empty(self):
        [item] = collect_from([dict(GOOD, region="  ")])
        self.assertIsNone(item.region)


if __name__ == "__main__":
    unittest.main()
