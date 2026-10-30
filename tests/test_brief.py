"""
Fitness functions for the research brief.

A brief drives every run, so these tests pin down what makes one usable:
required fields are enforced, unknown fields are rejected, and a hypothesis
with no disproof condition is accepted but flagged as untested.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from core import brief as briefs
from core.brief import UNTESTED_HYPOTHESIS

REPO = Path(__file__).resolve().parent.parent
SAMPLE = briefs.load(REPO / "sample" / "brief.json")
REMOVE = object()


def sample_with(**changes):
    """The sample brief with fields replaced, or dropped when set to REMOVE."""
    brief = copy.deepcopy(SAMPLE)
    for name, value in changes.items():
        if value is REMOVE:
            brief.pop(name, None)
        else:
            brief[name] = value
    return brief


def mentions(errors, text):
    return any(text in error for error in errors)


class SampleBrief(unittest.TestCase):

    def test_sample_brief_is_valid_with_no_flags(self):
        result = briefs.validate(SAMPLE)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.flags, [])


class RequiredFields(unittest.TestCase):

    def test_each_required_field_is_enforced(self):
        for name in briefs.REQUIRED:
            with self.subTest(missing=name):
                result = briefs.validate(sample_with(**{name: REMOVE}))
                self.assertFalse(result.ok)
                self.assertTrue(mentions(result.errors, f"'{name}'"), result.errors)

    def test_blank_title_or_statement_is_rejected(self):
        for name in ("title", "statement"):
            with self.subTest(blank=name):
                result = briefs.validate(sample_with(**{name: "   "}))
                self.assertTrue(mentions(result.errors, f"'{name}'"), result.errors)

    def test_type_must_be_hypothesis_or_topic(self):
        result = briefs.validate(sample_with(type="hunch"))
        self.assertTrue(mentions(result.errors, "'type'"), result.errors)

    def test_seed_terms_must_be_a_nonempty_list_of_text(self):
        for bad in ([], [""], "weekend hours", None):
            with self.subTest(seed_terms=bad):
                result = briefs.validate(sample_with(seed_terms=bad))
                self.assertTrue(mentions(result.errors, "'seed_terms'"), result.errors)

    def test_optional_fields_may_be_left_out(self):
        result = briefs.validate(sample_with(
            type="topic", disproof=REMOVE, scope=REMOVE,
            exclude_terms=REMOVE, questions=REMOVE))
        self.assertEqual(result.errors, [])


class BlankDisproof(unittest.TestCase):
    """A hypothesis nobody could disprove is allowed, but never silently."""

    def test_missing_disproof_is_valid_but_flagged_untested(self):
        result = briefs.validate(sample_with(disproof=REMOVE))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.flags, [UNTESTED_HYPOTHESIS])

    def test_empty_or_whitespace_or_null_disproof_is_flagged_untested(self):
        for blank in ("", "   ", None):
            with self.subTest(disproof=blank):
                result = briefs.validate(sample_with(disproof=blank))
                self.assertTrue(result.ok, result.errors)
                self.assertEqual(result.flags, [UNTESTED_HYPOTHESIS])

    def test_topic_brief_without_disproof_is_not_flagged(self):
        result = briefs.validate(sample_with(type="topic", disproof=REMOVE))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.flags, [])

    def test_disproof_that_is_not_text_is_rejected(self):
        result = briefs.validate(sample_with(disproof=["visits fell"]))
        self.assertTrue(mentions(result.errors, "'disproof'"), result.errors)


class Shape(unittest.TestCase):

    def test_unknown_field_is_rejected(self):
        # A misspelled field must not pass quietly as a brief with no disproof.
        result = briefs.validate(sample_with(disproof=REMOVE, disprove="visits fell"))
        self.assertTrue(mentions(result.errors, "unknown field 'disprove'"), result.errors)

    def test_brief_must_be_an_object(self):
        result = briefs.validate(["not", "a", "brief"])
        self.assertFalse(result.ok)

    def test_scope_dates_must_be_written_yyyy_mm_dd(self):
        for bad in ("03/01/2025", "2025-02-30", "20250101", 2025):
            with self.subTest(date_from=bad):
                scope = dict(SAMPLE["scope"], date_from=bad)
                result = briefs.validate(sample_with(scope=scope))
                self.assertTrue(mentions(result.errors, "'date_from'"), result.errors)

    def test_scope_date_range_must_not_run_backwards(self):
        scope = dict(SAMPLE["scope"], date_from="2025-12-31", date_to="2025-01-01")
        result = briefs.validate(sample_with(scope=scope))
        self.assertTrue(mentions(result.errors, "after 'date_to'"), result.errors)

    def test_unknown_scope_field_is_rejected(self):
        scope = dict(SAMPLE["scope"], countries=["Nowhere"])
        result = briefs.validate(sample_with(scope=scope))
        self.assertTrue(mentions(result.errors, "unknown scope field 'countries'"), result.errors)


class Loading(unittest.TestCase):

    def test_malformed_json_raises_brief_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text('{"title": "unclosed"', encoding="utf-8")
            with self.assertRaises(briefs.BriefError):
                briefs.load(path)


if __name__ == "__main__":
    unittest.main()
