"""
Fitness functions for triage.

Triage screens collected items against the brief. These tests pin the
sample's outcome item by item, and hold that every item keeps exactly one
record (excluded ones too), that every rule that fires is recorded, and that
a repeated report is flagged for review without either copy disappearing.
"""
import copy
import json
import unittest
from pathlib import Path

from adapters.base import SourceItem
from adapters.fixture import FixtureAdapter
from core.triage import (EXCLUDE_TERM, EXCLUDED, INCLUDED, MISSING_SCOPE_METADATA,
                         NEEDS_REVIEW, NO_SEED_MATCH, OUT_OF_DATE_RANGE, OUT_OF_SCOPE_UNIT,
                         POSSIBLE_DUPLICATE, counts, triage)

REPO = Path(__file__).resolve().parent.parent
BRIEF = json.loads((REPO / "sample" / "brief.json").read_text(encoding="utf-8"))
ITEMS = FixtureAdapter().collect()

EXPECTED = {
    "fixture:fx-1001": INCLUDED,
    "fixture:fx-1002": INCLUDED,
    "fixture:fx-1003": INCLUDED,
    "fixture:fx-1004": INCLUDED,
    "fixture:fx-1005": EXCLUDED,       # exclude term "book sale"
    "fixture:fx-1006": EXCLUDED,       # dated 2024, before the brief's scope
    "fixture:fx-1007": INCLUDED,
    "fixture:fx-1008": NEEDS_REVIEW,   # no region or unit given
    "fixture:fx-1009": EXCLUDED,       # no seed term: car park resurfacing
    "fixture:fx-10010": NEEDS_REVIEW,  # repeats fx-1002's figures
}


def by_id(records):
    return {record["source_id"]: record for record in records}


def codes(record):
    return [reason["code"] for reason in record["reasons"]]


def item(n, title="Weekend hours update", body="Saturday opening continues.",
         date="2025-06-01", region="North Valley", unit="Northgate Branch"):
    return SourceItem(source_id=f"test:{n}", title=title, date=date, body=body,
                      region=region, unit=unit)


def brief_with(**changes):
    brief = copy.deepcopy(BRIEF)
    brief.update(changes)
    return brief


class SampleOutcome(unittest.TestCase):

    def setUp(self):
        self.records = triage(ITEMS, BRIEF)
        self.by_id = by_id(self.records)

    def test_each_sample_item_gets_the_expected_status(self):
        self.assertEqual({r["source_id"]: r["status"] for r in self.records}, EXPECTED)

    def test_every_item_keeps_exactly_one_record_in_order(self):
        self.assertEqual([r["source_id"] for r in self.records],
                         [i.source_id for i in ITEMS])

    def test_counts_by_status(self):
        self.assertEqual(counts(self.records),
                         {INCLUDED: 5, NEEDS_REVIEW: 2, EXCLUDED: 3})

    def test_old_item_is_excluded_on_date_with_every_reason_recorded(self):
        record = self.by_id["fixture:fx-1006"]
        self.assertEqual(codes(record), [OUT_OF_DATE_RANGE, MISSING_SCOPE_METADATA])

    def test_book_sale_is_excluded_on_its_exclude_term(self):
        record = self.by_id["fixture:fx-1005"]
        self.assertEqual(codes(record), [EXCLUDE_TERM])
        self.assertEqual(record["matched_exclude_terms"], ["book sale"])

    def test_car_park_item_has_no_topic_signal(self):
        record = self.by_id["fixture:fx-1009"]
        self.assertEqual(codes(record), [NO_SEED_MATCH])
        self.assertEqual(record["matched_seed_terms"], [])

    def test_district_wide_claim_goes_to_review_not_away(self):
        record = self.by_id["fixture:fx-1008"]
        self.assertEqual(record["status"], NEEDS_REVIEW)
        self.assertEqual(codes(record), [MISSING_SCOPE_METADATA])

    def test_republished_figures_are_flagged_and_both_copies_kept(self):
        original, repeat = self.by_id["fixture:fx-1002"], self.by_id["fixture:fx-10010"]
        self.assertEqual(original["status"], INCLUDED)
        self.assertEqual(original["possible_duplicates"], ["fixture:fx-10010"])
        self.assertEqual(repeat["status"], NEEDS_REVIEW)
        self.assertEqual(codes(repeat), [POSSIBLE_DUPLICATE])
        self.assertEqual(repeat["possible_duplicate_of"], ["fixture:fx-1002"])

    def test_every_record_explains_itself(self):
        for record in self.records:
            with self.subTest(source_id=record["source_id"]):
                self.assertTrue(record["rationale"].strip())
                self.assertEqual(bool(record["reasons"]), record["status"] != INCLUDED)

    def test_triage_is_deterministic(self):
        self.assertEqual(triage(ITEMS, BRIEF), self.records)


class TermMatching(unittest.TestCase):

    def status(self, *items, brief=BRIEF):
        return [r["status"] for r in triage(list(items), brief)]

    def test_terms_ignore_case_and_allow_word_endings(self):
        self.assertEqual(self.status(item(1, title="News", body="Open on SATURDAYS now.")),
                         [INCLUDED])

    def test_terms_must_start_a_word(self):
        brief = brief_with(seed_terms=["day"])
        self.assertEqual(self.status(item(1, title="News", body="Open on Saturdays."),
                                     brief=brief), [EXCLUDED])

    def test_phrases_match_across_line_breaks_and_spacing(self):
        self.assertEqual(self.status(item(1, title="News", body="New weekend\n  hours.")),
                         [INCLUDED])


class ScopeRules(unittest.TestCase):

    def first(self, one_item, brief=BRIEF):
        return triage([one_item], brief)[0]

    def test_without_scope_dates_any_date_passes(self):
        brief = brief_with(scope={"regions": BRIEF["scope"]["regions"],
                                  "units": BRIEF["scope"]["units"]})
        self.assertEqual(self.first(item(1, date="1999-01-01"), brief)["status"], INCLUDED)

    def test_open_ended_date_range(self):
        brief = brief_with(scope=dict(BRIEF["scope"], date_from=None))
        self.assertEqual(self.first(item(1, date="2001-01-01"), brief)["status"], INCLUDED)
        self.assertEqual(codes(self.first(item(2, date="2026-01-01"), brief)), [OUT_OF_DATE_RANGE])

    def test_unit_outside_scope_is_excluded(self):
        record = self.first(item(1, unit="Elsewhere Branch"))
        self.assertEqual(record["status"], EXCLUDED)
        self.assertEqual(codes(record), [OUT_OF_SCOPE_UNIT])

    def test_scope_names_compare_without_case_or_extra_spaces(self):
        self.assertEqual(self.first(item(1, unit="northgate   BRANCH"))["status"], INCLUDED)

    def test_missing_metadata_only_matters_when_the_brief_scopes_by_it(self):
        brief = brief_with(scope={"date_from": "2025-01-01", "date_to": "2025-12-31"})
        self.assertEqual(self.first(item(1, region=None, unit=None), brief)["status"], INCLUDED)


class Duplicates(unittest.TestCase):

    def test_one_shared_figure_is_not_a_duplicate(self):
        records = triage([item(1, body="Saturday visits: 1,200 and 300."),
                          item(2, body="Saturday visits: 1,200 and 450.")], BRIEF)
        self.assertEqual([r["status"] for r in records], [INCLUDED, INCLUDED])

    def test_the_later_report_is_the_one_flagged(self):
        records = triage([item(1, date="2025-06-05", body="Saturday: 1,200 and 300."),
                          item(2, date="2025-06-01", body="Saturday: 1,200 and 300.")], BRIEF)
        self.assertEqual([r["status"] for r in records], [NEEDS_REVIEW, INCLUDED])
        self.assertEqual(records[0]["possible_duplicate_of"], ["test:2"])

    def test_excluded_items_do_not_flag_duplicates(self):
        records = triage([item(1, date="2024-06-01", body="Saturday: 1,200 and 300."),
                          item(2, body="Saturday: 1,200 and 300.")], BRIEF)
        self.assertEqual([r["status"] for r in records], [EXCLUDED, INCLUDED])
        self.assertEqual(records[1]["possible_duplicate_of"], [])


if __name__ == "__main__":
    unittest.main()
