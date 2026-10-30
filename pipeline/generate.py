"""Step 2 of the pipeline: generate draft questions from one cached page, then apply rule filters.

Usage: python pipeline/generate.py <url> <domain> <skill> [count]
Writes accepted drafts to pipeline/drafts/<skill>.yaml (status: draft); run verify.py next.
"""
import sys
import time
from datetime import date
from difflib import SequenceMatcher

import yaml

import llm
from common import DRAFTS, ROOT, load_page, normalise
from validate import check_outline, check_question

# The prompt is where question quality is won or lost: it forces scenarios over recall,
# plausible distractors, and a verbatim supporting quote that the filters can check.
SYSTEM = """You write exam-style practice questions for the Azure Administrator certification.
Use ONLY the page text provided. Do not use outside knowledge. Write original wording.

Quality bar (this matters more than anything else):
- Test APPLICATION, not recall. Every stem is a 2-4 sentence situation with a concrete requirement or constraint
  (who needs what access, at what scope, with what limitation, what must NOT happen), ending in "What should you do?"
  or similar. Never ask for a definition, a count of things, or "which of these is NOT ...".
- Each question must need a reasoning step: combining two facts from the page, applying a rule to a specific case,
  or choosing between options that are all real Azure features.
- Distractors are real concepts from the page that would be correct in a DIFFERENT situation, so each fails
  on one specific constraint in the stem. No joke options, no "all of the above".
- All options are similar in length and style; the correct one is not the longest.
- Difficulty 2 = one reasoning step, 3 = two or more. Do not write difficulty 1.
- The explanation says why the key is right AND, in one clause each, why every other option fails.
- Each question tests a different fact; do not write variations of the same case.
- Each question has one supporting quote copied VERBATIM, character for character, from the page.
Return JSON: {"questions": [{"type": "multiple_choice|multi_select|scenario", "stem": str,
"options": [{"id": "a", "text": str}, ...4 options], "answer": ["a"], "explanation": str,
"quote": str, "difficulty": 2-3, "tags": [str]}]}"""

BATCH_SIZE = 4      # small batches keep the JSON short, so malformed output is much less likely
BATCH_PAUSE_S = 30  # lets the free tier's per-minute token budget refill between calls
SIMILARITY_LIMIT = 0.7  # stems more alike than this are treated as the same question


def question_files(cert):
    """Approved question files plus drafts: everything a new question must not collide with."""
    return list((ROOT / "content" / cert).glob("*.yaml")) + list(DRAFTS.glob("*.yaml"))


def load_questions(path):
    return [q for q in (yaml.safe_load(path.read_text(encoding="utf-8")) or []) if isinstance(q, dict)]


def next_number(cert, domain, skill):
    """Next free 4-digit suffix for ids of the form <cert>.<domain>.<skill>.NNNN."""
    prefix = f"{cert}.{domain}.{skill}."
    used = [int(q["id"].rsplit(".", 1)[1]) for f in question_files(cert) for q in load_questions(f)
            if str(q.get("id", "")).startswith(prefix)]
    return max(used, default=0) + 1


def existing_stems(cert):
    return {normalise(q["stem"]).lower() for f in question_files(cert) for q in load_questions(f) if q.get("stem")}


def apply_filters(drafts, page, skills, cert, seen_stems):
    """Rule filters: schema valid, quote verbatim in page, no near-duplicate of any earlier stem."""
    page_text = normalise(page["text"])
    accepted = []
    for q in drafts:
        errors = []
        check_question(q, "draft", skills, cert, errors)
        # The key defence against invented facts: the supporting quote must really be on the page.
        if normalise(q["quote"]) not in page_text:
            errors.append("quote not found verbatim in page")
        stem = normalise(q["stem"]).lower()
        if any(SequenceMatcher(None, stem, other).ratio() > SIMILARITY_LIMIT for other in seen_stems):
            errors.append("near-duplicate of an existing stem")
        if errors:
            print(f"  rejected {q['id']}: {'; '.join(errors)}")
            continue
        seen_stems.add(stem)  # so later drafts in this same batch are also compared against this one
        accepted.append(q)
    return accepted


def is_well_formed(q):
    """Model output is untrusted: drop anything whose shape would crash the filters."""
    return (isinstance(q["options"], list) and all(isinstance(o, dict) for o in q["options"])
            and isinstance(q["answer"], list) and isinstance(q["quote"], str) and isinstance(q["stem"], str))


def main(url, domain, skill, count=8):
    page = load_page(url)
    cert = "az-104"
    outline = yaml.safe_load((ROOT / "content" / cert / "outline.yaml").read_text(encoding="utf-8"))
    skills = check_outline(outline, [])
    if skills.get(skill) != domain:
        raise SystemExit(f"{skill} is not a skill under {domain} in the outline")

    # Ask the model in small batches, telling it what it already wrote so batches don't repeat each other.
    generated = []
    for start in range(0, count, BATCH_SIZE):
        want = min(BATCH_SIZE, count - start)
        covered = f" Do not repeat these stems: {[g.get('stem') for g in generated]}." if generated else ""
        raw = llm.chat_json(llm.GEN_MODEL, SYSTEM, f"Write {want} questions from this page.{covered}\n\nPAGE ({url}):\n{page['text']}")
        generated += [g for g in raw.get("questions", []) if isinstance(g, dict)]
        if start + BATCH_SIZE < count:
            print(f"  {len(generated)} generated so far, pausing {BATCH_PAUSE_S}s for the free tier's per-minute token cap")
            time.sleep(BATCH_PAUSE_S)

    # Wrap each raw model question in our full schema (id, source, dates, status) so it can be validated.
    n = next_number(cert, domain, skill)
    drafts = []
    for i, q in enumerate(generated):
        drafts.append({
            "id": f"{cert}.{domain}.{skill}.{n + i:04d}", "cert": cert, "domain": domain, "skill": skill,
            "type": q.get("type"), "stem": q.get("stem") or "", "options": q.get("options"), "answer": q.get("answer"),
            "explanation": q.get("explanation"), "source_url": url, "quote": q.get("quote") or "",
            "retrieved_at": date.fromisoformat(page["retrieved_at"]), "difficulty": q.get("difficulty"),
            "tags": q.get("tags", []), "status": "draft", "last_reviewed": None,
        })
    drafts = [d for d in drafts if is_well_formed(d)]
    accepted = apply_filters(drafts, page, skills, cert, existing_stems(cert))

    # Append to any drafts already waiting for review rather than overwriting them.
    DRAFTS.mkdir(parents=True, exist_ok=True)
    out = DRAFTS / f"{skill}.yaml"
    prior = load_questions(out) if out.exists() else []
    out.write_text(yaml.safe_dump(prior + accepted, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    print(f"{len(accepted)}/{len(drafts)} drafts passed rule filters -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 8)
