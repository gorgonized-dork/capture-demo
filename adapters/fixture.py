"""
Fixture adapter: reads hand-written sample items from a JSON file.

Offline and deterministic, with no keys. Used by the tests and for running
the pipeline without network access. The default file, sample/items.json,
is entirely fictional.

A malformed record stops the read with FixtureError. Bad records are never
skipped quietly.
"""
import json
import re
from pathlib import Path

from adapters.base import SourceAdapter, SourceItem, source_id

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "sample" / "items.json"
REQUIRED = ("id", "title", "date", "body")
OPTIONAL = ("region", "unit", "url")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FixtureError(ValueError):
    """The fixture file is malformed."""


class FixtureAdapter(SourceAdapter):
    name = "fixture"
    mode = "fixture"

    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)

    def collect(self, queries=()):
        """Return every item in the fixture file, in file order.

        The fixture is the whole corpus, so queries are not applied here.
        A live adapter uses them to search.
        """
        records = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise FixtureError(f"{self.path}: expected a JSON array of items")

        items, seen = [], set()
        for number, record in enumerate(records, 1):
            item = self._to_item(record, number)
            if item.source_id in seen:
                raise FixtureError(f"{self.path}: item {number}: duplicate id '{record['id']}'")
            seen.add(item.source_id)
            items.append(item)
        return items

    def _to_item(self, record, number):
        where = f"{self.path}: item {number}"
        if not isinstance(record, dict):
            raise FixtureError(f"{where}: expected an object")
        unknown = sorted(set(record) - set(REQUIRED) - set(OPTIONAL))
        if unknown:
            raise FixtureError(f"{where}: unknown field(s) {unknown}")
        for name in REQUIRED:
            if not isinstance(record.get(name), str) or not record[name].strip():
                raise FixtureError(f"{where}: '{name}' is required and must be non-empty text")
        if not DATE_RE.match(record["date"]):
            raise FixtureError(f"{where}: 'date' must be YYYY-MM-DD")
        optional = {}
        for name in OPTIONAL:
            value = record.get(name)
            if value is not None and not isinstance(value, str):
                raise FixtureError(f"{where}: '{name}' must be text or null")
            optional[name] = value if value and value.strip() else None  # blank stays empty

        return SourceItem(
            source_id=source_id(self.name, record["id"]),
            title=record["title"],
            date=record["date"],
            body=record["body"],
            **optional,
        )
