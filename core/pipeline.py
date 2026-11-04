"""
Pipeline: one command from a research brief to a run folder.

    python -m core.pipeline run --brief sample/brief.json --adapter fixture

Today the pipeline validates the brief, collects source items through the
chosen adapter, creates the run folder, writes a snapshot of every item it
collected, and triages each one against the brief. Evidence review, field
questions, the decision record, and the report are not built yet.

The adapter is always chosen explicitly. A failure before the run folder is
created (an invalid brief, an adapter error) leaves nothing behind, and an
existing run folder is never overwritten.
"""
import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

from adapters.fixture import FixtureAdapter
from core import brief as briefs
from core import triage
from core.runs import RUNS_DIR, RunError, RunExistsError, create_run

ADAPTERS = {"fixture": FixtureAdapter}
MODE_LABELS = {"fixture": "offline"}
SOURCES_FILE = "sources.jsonl"
TRIAGE_FILE = "triage.jsonl"
RUN_FILES = ("brief.json", "run.json", SOURCES_FILE, TRIAGE_FILE)


class PipelineError(Exception):
    """The pipeline stopped before creating a run folder."""


def run(brief_path, adapter, runs_dir=RUNS_DIR, run_id=None):
    """Brief -> collect -> run folder with a source snapshot and triage. Returns the folder."""
    brief = briefs.load(brief_path)
    result = briefs.validate(brief)
    if not result.ok:
        raise PipelineError("brief is invalid: " + "; ".join(result.errors))

    # Collect before the folder exists, so a failing adapter leaves nothing behind.
    try:
        items = adapter.collect()
    except (OSError, ValueError) as e:
        raise PipelineError(f"adapter '{adapter.name}' failed: {e}") from None

    run_dir = create_run(brief_path, runs_dir, run_id)
    snapshot = [dict(dataclasses.asdict(item),
                     body_sha256=hashlib.sha256(item.body.encode("utf-8")).hexdigest())
                for item in items]
    snapshot_sha256 = write_jsonl(run_dir / SOURCES_FILE, snapshot)
    triaged = triage.triage(items, brief)
    triage_sha256 = write_jsonl(run_dir / TRIAGE_FILE, triaged)

    record_path = run_dir / "run.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["collection"] = {
        "adapter": adapter.name,
        "mode": adapter.mode,
        "items": len(items),
        "sources_file": SOURCES_FILE,
        "sources_sha256": snapshot_sha256,
    }
    record["triage"] = dict(triage.counts(triaged),
                            triage_file=TRIAGE_FILE, triage_sha256=triage_sha256)
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return run_dir


def write_jsonl(path, rows):
    """Write one JSON object per line. Returns the file's SHA-256."""
    data = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def display(path):
    """A path relative to the working directory when possible, with forward slashes."""
    path = Path(path).resolve()
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m core.pipeline",
                                 description="Run the pipeline on a research brief.")
    sub = ap.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("run", help="brief -> collect -> triage, into a run folder")
    cmd.add_argument("--brief", type=Path, required=True, help="research brief (JSON)")
    cmd.add_argument("--adapter", choices=sorted(ADAPTERS), required=True,
                     help="source adapter; 'fixture' reads sample/items.json offline")
    cmd.add_argument("--run-id", help="run folder name (default: slug of the brief title)")
    cmd.add_argument("--runs-dir", type=Path, default=RUNS_DIR,
                     help="where run folders are created (default: runs/)")
    args = ap.parse_args(argv)

    try:
        run_dir = run(args.brief, ADAPTERS[args.adapter](), args.runs_dir, args.run_id)
    except RunExistsError as e:
        print(f"ERROR  {e}")
        print("       pass --run-id <new-id> to start a separate run")
        return 1
    except (OSError, briefs.BriefError, RunError, PipelineError) as e:
        print(f"ERROR  {e}")
        return 1

    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    collection = record["collection"]
    print(f"brief    {display(args.brief)}: valid")
    for flag in record["flags"]:
        print(f"FLAG     {flag}: {briefs.FLAG_MEANINGS[flag]}")
    mode = MODE_LABELS.get(collection["mode"], collection["mode"])
    print(f"adapter  {collection['adapter']} ({mode}): {collection['items']} items")
    screened = record["triage"]
    print(f"triage   {screened[triage.INCLUDED]} included, {screened[triage.NEEDS_REVIEW]} to review, "
          f"{screened[triage.EXCLUDED]} excluded")
    print(f"run      {display(run_dir)}/")
    print(f"wrote    {', '.join(sorted(p.name for p in run_dir.iterdir()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
