"""
Research brief: the input that drives each run.

A brief is a small JSON file naming what a run is looking for: a hypothesis to
test or an open topic to survey. Nothing about the subject is built into the
pipeline; it all comes from the brief.

The validator reports two kinds of finding:

    errors  the brief cannot drive a run (a field is missing or malformed)
    flags   the brief is usable, but every output must carry a warning

A hypothesis with no disproof condition is valid but cannot be tested as
written, so it is flagged UNTESTED_HYPOTHESIS rather than rejected.

Usage:  python -m core.brief validate <brief.json>
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

BRIEF_TYPES = ("hypothesis", "topic")
REQUIRED = ("title", "type", "statement", "seed_terms")
OPTIONAL = ("disproof", "scope", "exclude_terms", "questions")
SCOPE_FIELDS = ("date_from", "date_to", "regions", "units")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

UNTESTED_HYPOTHESIS = "UNTESTED_HYPOTHESIS"
FLAG_MEANINGS = {
    UNTESTED_HYPOTHESIS: "no disproof condition; findings must mark this hypothesis untested",
}


class BriefError(ValueError):
    """The brief file could not be read as JSON."""


@dataclass
class Validation:
    errors: list = field(default_factory=list)
    flags: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


def parse(text, source="brief"):
    """Parse brief text. Bad JSON raises BriefError naming the source."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise BriefError(f"{source}: not valid JSON ({e})") from None


def load(path):
    """Read and parse a brief file (not yet validated)."""
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), path)


def validate(brief):
    """Check a parsed brief. Returns a Validation; never raises on bad content."""
    v = Validation()
    if not isinstance(brief, dict):
        v.errors.append("brief must be a JSON object")
        return v

    for name in sorted(set(brief) - set(REQUIRED) - set(OPTIONAL)):
        v.errors.append(f"unknown field '{name}'")

    for name in ("title", "statement"):
        if not _is_text(brief.get(name)):
            v.errors.append(f"'{name}' is required and must be non-empty text")

    if brief.get("type") not in BRIEF_TYPES:
        v.errors.append(f"'type' is required and must be one of: {', '.join(BRIEF_TYPES)}")

    if not brief.get("seed_terms") or not _is_text_list(brief.get("seed_terms")):
        v.errors.append("'seed_terms' is required and must be a non-empty list of text terms")

    for name in ("exclude_terms", "questions"):
        if name in brief and not _is_text_list(brief[name]):
            v.errors.append(f"'{name}' must be a list of non-empty text items")

    disproof = brief.get("disproof")
    if disproof is not None and not isinstance(disproof, str):
        v.errors.append("'disproof' must be text")

    if "scope" in brief:
        _check_scope(brief["scope"], v.errors)

    if brief.get("type") == "hypothesis" and not _is_text(disproof):
        v.flags.append(UNTESTED_HYPOTHESIS)
    return v


def _check_scope(scope, errors):
    if not isinstance(scope, dict):
        errors.append("'scope' must be an object")
        return
    for name in sorted(set(scope) - set(SCOPE_FIELDS)):
        errors.append(f"unknown scope field '{name}'")

    dates = {}
    for name in ("date_from", "date_to"):
        value = scope.get(name)
        if value in (None, ""):
            continue
        try:
            if not isinstance(value, str) or not DATE_RE.match(value):
                raise ValueError
            dates[name] = date.fromisoformat(value)
        except ValueError:
            errors.append(f"scope '{name}' must be a real date written YYYY-MM-DD")
    if len(dates) == 2 and dates["date_from"] > dates["date_to"]:
        errors.append("scope 'date_from' is after 'date_to'")

    for name in ("regions", "units"):
        if name in scope and not _is_text_list(scope[name]):
            errors.append(f"scope '{name}' must be a list of non-empty text items")


def _is_text(value):
    return isinstance(value, str) and value.strip() != ""


def _is_text_list(value):
    return isinstance(value, list) and all(_is_text(item) for item in value)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m core.brief",
                                 description="Validate a research brief.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="check a brief file").add_argument("brief", type=Path)
    args = ap.parse_args(argv)

    try:
        result = validate(load(args.brief))
    except (OSError, BriefError) as e:
        print(f"ERROR  {e}")
        return 1
    for error in result.errors:
        print(f"ERROR  {error}")
    for flag in result.flags:
        print(f"FLAG   {flag}: {FLAG_MEANINGS[flag]}")
    print("valid" if result.ok else "invalid")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
