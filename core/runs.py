"""
Run folders: one per research run, created from a valid brief.

    runs/<run-id>/brief.json   byte-for-byte copy of the brief, frozen for this run
    runs/<run-id>/run.json     run id, slug, creation time, brief SHA-256, flags

The run id defaults to a slug of the brief title. A caller may pass its own,
limited to lowercase letters, digits, and single hyphens, so it can only ever
name a folder directly inside the runs directory.

An invalid brief creates nothing. An existing run folder is never overwritten:
once a run exists, its record of what it was asked is fixed.

Usage:  python -m core.runs new <brief.json>
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from core import brief as briefs

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
SLUG_MAX = 60
RUN_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class RunError(Exception):
    """The run could not be created. Nothing was written."""


class RunExistsError(RunError):
    """A run folder with this id already exists. It was left untouched."""


def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:SLUG_MAX].rstrip("-")


def create_run(brief_path, runs_dir=RUNS_DIR, run_id=None):
    """Validate the brief, then create runs/<run-id>/ for it. Returns the folder."""
    brief_path = Path(brief_path)
    raw = brief_path.read_bytes()
    brief = briefs.parse(raw.decode("utf-8"), brief_path)

    result = briefs.validate(brief)
    if not result.ok:
        raise RunError("brief is invalid: " + "; ".join(result.errors))
    slug = slugify(brief["title"])
    if not slug:
        raise RunError("brief title has no letters or digits to name the run folder")
    if run_id is None:
        run_id = slug
    elif len(run_id) > SLUG_MAX or not RUN_ID_RE.match(run_id):
        raise RunError(f"run id '{run_id}' must be lowercase letters, digits, and single "
                       f"hyphens, at most {SLUG_MAX} characters (for example 'demo-2')")

    run_dir = Path(runs_dir) / run_id
    try:
        run_dir.mkdir(parents=True)
    except FileExistsError:
        raise RunExistsError(f"run folder already exists; not overwriting: {run_dir}") from None

    (run_dir / "brief.json").write_bytes(raw)
    record = {
        "run_id": run_id,
        "slug": slug,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief_sha256": hashlib.sha256(raw).hexdigest(),
        "brief_type": brief["type"],
        "flags": result.flags,
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return run_dir


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m core.runs",
                                 description="Create a run folder from a research brief.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("new", help="create runs/<slug>/ from a brief").add_argument("brief", type=Path)
    args = ap.parse_args(argv)

    try:
        run_dir = create_run(args.brief)
    except (OSError, briefs.BriefError, RunError) as e:
        print(f"ERROR  {e}")
        return 1
    print(f"created {run_dir}")
    for flag in json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["flags"]:
        print(f"FLAG   {flag}: {briefs.FLAG_MEANINGS[flag]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
