"""Validate content/<cert>/outline.yaml and question files against content/schema.md.

Usage: python pipeline/validate.py [content_dir]
Exits 1 if anything is wrong, so it can gate commits or CI.
"""
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml

# Only these hosts are allowed as question sources (see content policy in the README).
ALLOWED_HOSTS = {"learn.microsoft.com"}
TYPES = {"multiple_choice", "multi_select", "scenario"}
STATUSES = {"draft", "approved", "flagged"}
REQUIRED = [
    "id", "cert", "domain", "skill", "type", "stem", "options", "answer",
    "explanation", "source_url", "quote", "retrieved_at", "difficulty",
    "tags", "status", "last_reviewed",
]


def check_outline(outline, errors):
    """Check ids are unique and weights can sum to 100. Returns {skill_id: domain_id} for question checks."""
    seen = set()
    skills = {}
    for d in outline.get("domains", []):
        if d["id"] in seen:
            errors.append(f"outline: duplicate id {d['id']}")
        seen.add(d["id"])
        for s in d.get("skills", []):
            if s["id"] in seen:
                errors.append(f"outline: duplicate id {s['id']}")
            seen.add(s["id"])
            if not s.get("objectives"):
                errors.append(f"outline: skill {s['id']} has no objectives")
            skills[s["id"]] = d["id"]
    # Exam weights are ranges (e.g. 20-25%), so 100 just has to be reachable.
    lo = sum(d["weight"]["min"] for d in outline["domains"])
    hi = sum(d["weight"]["max"] for d in outline["domains"])
    if not (lo <= 100 <= hi):
        errors.append(f"outline: weights cannot sum to 100 (min {lo}, max {hi})")
    return skills


def check_question(q, where, skills, cert, errors):
    """Append a message to `errors` for every schema rule this question breaks."""
    def err(msg):
        errors.append(f"{where}: {q.get('id', '?')}: {msg}")

    missing = [k for k in REQUIRED if k not in q]
    if missing:
        err(f"missing fields {missing}")
        return  # the checks below assume every field exists

    if q["cert"] != cert:
        err(f"cert {q['cert']} != {cert}")
    if skills.get(q["skill"]) != q["domain"]:
        err(f"skill {q['skill']} not under domain {q['domain']} in outline")
    if not str(q["id"]).startswith(f"{cert}.{q['domain']}.{q['skill']}."):
        err("id must start with <cert>.<domain>.<skill>.")
    if q["type"] not in TYPES:
        err(f"bad type {q['type']}")
    if q["status"] not in STATUSES:
        err(f"bad status {q['status']}")

    # Options and answer: 3-6 unique options; the key must point at real options.
    ids = [o.get("id") for o in q["options"]]
    if not 3 <= len(ids) <= 6 or len(set(ids)) != len(ids):
        err("options need 3-6 entries with unique ids")
    if not q["answer"] or not set(q["answer"]) <= set(ids):
        err("answer must be a non-empty list of option ids")
    elif q["type"] == "multi_select" and len(q["answer"]) < 2:
        err("multi_select needs 2+ answers")
    elif q["type"] != "multi_select" and len(q["answer"]) != 1:
        err(f"{q['type']} needs exactly 1 answer")

    # Provenance: every question must trace back to an allowed page and a quote from it.
    url = urlparse(str(q["source_url"]))
    if url.scheme != "https" or url.hostname not in ALLOWED_HOSTS:
        err(f"source_url not an https URL on {sorted(ALLOWED_HOSTS)}")
    if not str(q["quote"]).strip():
        err("quote is empty")

    if not isinstance(q["difficulty"], int) or not 1 <= q["difficulty"] <= 3:
        err("difficulty must be 1-3")
    if not isinstance(q["retrieved_at"], date):
        err("retrieved_at must be a date")
    if q["status"] == "approved" and not isinstance(q["last_reviewed"], date):
        err("approved questions need last_reviewed")


def main(content_dir):
    errors = []
    count = 0
    stems = {}  # (cert, normalised stem) -> id, to catch exact duplicates across files
    for outline_path in sorted(content_dir.glob("*/outline.yaml")):
        cert_dir = outline_path.parent
        outline = yaml.safe_load(outline_path.read_text(encoding="utf-8"))
        skills = check_outline(outline, errors)
        for f in sorted(cert_dir.glob("*.yaml")):
            if f.name == "outline.yaml":
                continue
            for q in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
                count += 1
                check_question(q, f.relative_to(content_dir).as_posix(), skills, outline["cert"], errors)
                key = (outline["cert"], " ".join(str(q.get("stem", "")).lower().split()))
                if key in stems:
                    errors.append(f"{q.get('id')}: duplicate stem of {stems[key]}")
                stems[key] = q.get("id")
        print(f"{outline['cert']}: {len(outline['domains'])} domains, {len(skills)} skills")
    print(f"{count} questions checked")
    for e in errors:
        print("ERROR", e)
    return 1 if errors else 0


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "content"
    sys.exit(main(root))
