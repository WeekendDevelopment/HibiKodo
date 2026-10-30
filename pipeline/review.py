"""Step 4 of the pipeline: review queue (approve / reject / edit draft questions).

Usage: python pipeline/review.py <skill>
Approved questions are appended to content/<cert>/<skill>.yaml with status: approved and today's last_reviewed.
Keys: [a]pprove  [r]eject  [e]dit stem/options/answer/explanation in $EDITOR (default notepad)  [s]kip  [q]uit
Progress is saved after every decision, so a crash or Ctrl+C loses nothing.
"""
import os
import subprocess
import sys
import tempfile
from datetime import date

import yaml

from common import DRAFTS, ROOT, load_page, normalise
from validate import check_outline, check_question

CERT = "az-104"


def dump(data):
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def show(q):
    """Print everything the reviewer needs to judge a question in one screen."""
    print("\n" + "=" * 78)
    ver = q.get("verification")
    print(f"{q['id']}   difficulty {q['difficulty']}   {q['type']}   status {q['status']}")
    if ver:
        print(f"verifier: {'PASS' if ver['passed'] else 'FAIL'} - {ver['notes']}")
    print(f"\n{q['stem']}\n")
    for o in q["options"]:
        mark = "*" if o["id"] in q["answer"] else " "  # * marks the keyed answer
        print(f" {mark} {o['id']}) {o['text']}")
    print(f"\nExplanation: {q['explanation']}")
    print(f"Quote: \"{q['quote']}\"")
    print(f"Link:  {q['source_url']}")


def edit(q):
    """Open the editable fields in a text editor and merge the changes back. Bad YAML keeps the old values."""
    editor = os.environ.get("EDITOR", "notepad")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.safe_dump({k: q[k] for k in ("stem", "options", "answer", "explanation")}, f, allow_unicode=True, sort_keys=False)
        name = f.name
    subprocess.run([editor, name], check=False)
    try:
        with open(name, encoding="utf-8") as f:
            q.update(yaml.safe_load(f))
    except yaml.YAMLError as e:
        print(f"Edit not applied, invalid YAML: {e}")
    finally:
        os.unlink(name)


def try_approve(q, skills):
    """Return (approved_question, errors). Re-runs the schema and quote checks so edits can't sneak in bad data."""
    q = {x: y for x, y in q.items() if x != "verification"}  # verifier notes are pipeline-only
    q.update(status="approved", last_reviewed=date.today())
    errs = []
    check_question(q, "review", skills, CERT, errs)
    if normalise(q["quote"]) not in normalise(load_page(q["source_url"])["text"]):
        errs.append("quote not in page")
    return q, errs


def main(skill):
    draft_path = DRAFTS / f"{skill}.yaml"
    out_path = ROOT / "content" / CERT / f"{skill}.yaml"
    outline = yaml.safe_load((ROOT / "content" / CERT / "outline.yaml").read_text(encoding="utf-8"))
    skills = check_outline(outline, [])

    queue = yaml.safe_load(draft_path.read_text(encoding="utf-8")) or []
    approved = (yaml.safe_load(out_path.read_text(encoding="utf-8")) if out_path.exists() else None) or []
    kept = []  # skipped or failed questions stay in drafts for next time

    def save(pending):
        out_path.write_text(dump(approved), encoding="utf-8")
        draft_path.write_text(dump(kept + pending), encoding="utf-8")

    while queue:
        q = queue[0]
        while True:  # loop so [e]dit re-shows the question before you decide
            show(q)
            k = input("\n[a]pprove [r]eject [e]dit [s]kip [q]uit > ").strip().lower()
            if k != "e":
                break
            edit(q)
        queue.pop(0)
        if k == "a":
            q2, errs = try_approve(q, skills)
            if errs:
                print("Cannot approve:", *errs, sep="\n  ")
                kept.append(q)
            else:
                approved.append(q2)
        elif k == "q":
            queue.insert(0, q)  # put it back so it is saved and counted as still pending
            save(queue)
            break
        elif k != "r":  # reject simply drops it; anything else (incl. skip) keeps it
            kept.append(q)
        save(queue)
    print(f"\n{len(approved)} approved in content, {len(kept) + len(queue)} left in drafts")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
