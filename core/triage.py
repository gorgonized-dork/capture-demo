"""
Triage: a transparent screen over collected items, driven by the brief.

Every collected item gets exactly one triage record: a status, every rule
that fired with a short explanation, and its exact source_id. Excluded items
keep their records, so nothing silently disappears.

    included      no rule fired
    needs_review  a person should look: scope metadata is missing, or the
                  item reports the same figures as an earlier one
    excluded      the brief rules it out (date, exclude term, region, unit)
                  or none of its seed terms appear

Triage is a keyword and scope screen. It does not rank relevance or judge
truth, and a triage record claims nothing about the world: it says only
which rules fired. All terms and scope come from the brief; nothing about
the subject is built in.
"""
import re
from itertools import combinations

INCLUDED, NEEDS_REVIEW, EXCLUDED = "included", "needs_review", "excluded"
STATUSES = (INCLUDED, NEEDS_REVIEW, EXCLUDED)

OUT_OF_DATE_RANGE = "OUT_OF_DATE_RANGE"
EXCLUDE_TERM = "EXCLUDE_TERM"
NO_SEED_MATCH = "NO_SEED_MATCH"
OUT_OF_SCOPE_REGION = "OUT_OF_SCOPE_REGION"
OUT_OF_SCOPE_UNIT = "OUT_OF_SCOPE_UNIT"
MISSING_SCOPE_METADATA = "MISSING_SCOPE_METADATA"
POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
EXCLUDING = {OUT_OF_DATE_RANGE, EXCLUDE_TERM, NO_SEED_MATCH,
             OUT_OF_SCOPE_REGION, OUT_OF_SCOPE_UNIT}

# Items sharing this many identical figures are possible duplicates. A figure
# is a number of three or more digits, commas ignored ("1,880" == "1880").
# Years count as figures; a false match costs a review, never an exclusion.
DUPLICATE_MIN_SHARED_FIGURES = 2
FIGURE_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{3,}\b")


def triage(items, brief):
    """Return one triage record per item, in item order."""
    scope = brief.get("scope") or {}
    screens = [_screen(item, brief, scope) for item in items]
    _mark_duplicates(items, screens)
    return [_record(item, screen) for item, screen in zip(items, screens)]


def counts(records):
    return {status: sum(r["status"] == status for r in records) for status in STATUSES}


def term_pattern(term):
    """Ignores case; must start a word; any ending, so 'Saturday' matches 'Saturdays'."""
    return re.compile(r"\b" + r"\s+".join(re.escape(w) for w in term.split()), re.IGNORECASE)


def matched_terms(terms, text):
    return [term for term in terms if term_pattern(term).search(text)]


def _screen(item, brief, scope):
    text = f"{item.title}\n{item.body}"
    screen = {
        "reasons": [],
        "seeds": matched_terms(brief["seed_terms"], text),
        "excludes": matched_terms(brief.get("exclude_terms", []), text),
        "duplicate_of": [],
        "duplicates": [],
    }
    reasons = screen["reasons"]

    date_from, date_to = scope.get("date_from"), scope.get("date_to")
    if (date_from and item.date < date_from) or (date_to and item.date > date_to):
        reasons.append(_reason(OUT_OF_DATE_RANGE, f"dated {item.date}, outside the brief's "
                               f"scope of {date_from or 'any date'} to {date_to or 'any date'}"))
    if screen["excludes"]:
        reasons.append(_reason(EXCLUDE_TERM, "matches exclude term "
                               + ", ".join(f"'{t}'" for t in screen["excludes"])))
    if not screen["seeds"]:
        reasons.append(_reason(NO_SEED_MATCH, "none of the brief's seed terms appear"))

    for field, code in (("region", OUT_OF_SCOPE_REGION), ("unit", OUT_OF_SCOPE_UNIT)):
        allowed = scope.get(field + "s")
        value = getattr(item, field)
        if allowed and value and _norm(value) not in {_norm(a) for a in allowed}:
            reasons.append(_reason(code, f"{field} '{value}' is not in the brief's scope"))

    missing = [field for field in ("region", "unit") if scope.get(field + "s") and not getattr(item, field)]
    if missing:
        reasons.append(_reason(MISSING_SCOPE_METADATA,
                               f"gives no {' or '.join(missing)} (left empty, not guessed), "
                               f"and the brief's scope lists {' and '.join(f + 's' for f in missing)}"))
    return screen


def _mark_duplicates(items, screens):
    """Flag later items that report the same figures as earlier, non-excluded ones."""
    candidates = [i for i, screen in enumerate(screens) if not _excluded(screen["reasons"])]
    figures = {i: _figures(items[i]) for i in candidates}
    for a, b in combinations(candidates, 2):
        shared = figures[a] & figures[b]
        if len(shared) < DUPLICATE_MIN_SHARED_FIGURES:
            continue
        earlier, later = sorted((a, b), key=lambda i: (items[i].date, i))
        shown = " and ".join(f"{int(f):,}" for f in sorted(shared, key=int))
        screens[later]["reasons"].append(_reason(
            POSSIBLE_DUPLICATE, f"reports the same figures ({shown}) as "
            f"{items[earlier].source_id}, dated {items[earlier].date}"))
        screens[later]["duplicate_of"].append(items[earlier].source_id)
        screens[earlier]["duplicates"].append(items[later].source_id)


def _record(item, screen):
    reasons = screen["reasons"]
    if _excluded(reasons):
        status = EXCLUDED
    elif reasons:
        status = NEEDS_REVIEW
    else:
        status = INCLUDED

    if reasons:
        rationale = "; ".join(r["detail"] for r in reasons)
        rationale = rationale[0].upper() + rationale[1:] + "."
    else:
        rationale = "No rule fired; matches seed terms " + ", ".join(f"'{t}'" for t in screen["seeds"]) + "."
    if screen["duplicates"]:
        rationale += " Later items repeat its figures: " + ", ".join(screen["duplicates"]) + "."

    return {
        "source_id": item.source_id,
        "status": status,
        "rationale": rationale,
        "reasons": reasons,
        "matched_seed_terms": screen["seeds"],
        "matched_exclude_terms": screen["excludes"],
        "possible_duplicate_of": screen["duplicate_of"],
        "possible_duplicates": screen["duplicates"],
    }


def _reason(code, detail):
    return {"code": code, "detail": detail}


def _excluded(reasons):
    return any(r["code"] in EXCLUDING for r in reasons)


def _figures(item):
    return {m.replace(",", "") for m in FIGURE_RE.findall(f"{item.title}\n{item.body}")}


def _norm(text):
    return " ".join(text.split()).casefold()
