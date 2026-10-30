"""Second-model verification of draft questions.

Usage: python pipeline/verify.py <skill>
Reads pipeline/drafts/<skill>.yaml. Each draft gets `verification: {passed, notes}`;
failed drafts get status: flagged so the review tool shows them with the reason.
"""
import sys

import yaml

import llm
from common import DRAFTS, load_page

SYSTEM = """You are a strict fact-checker for exam questions. You get a documentation page and one question.
Check, using ONLY the page text:
(a) supported: the keyed answer(s) are supported by the quote and the page.
(b) single_best: no distractor is also correct according to the page; the question has an unambiguous key.
(c) not_outdated: nothing in the stem or options contradicts the page.
Return JSON: {"supported": bool, "single_best": bool, "not_outdated": bool, "notes": str}"""


def main(skill):
    path = DRAFTS / f"{skill}.yaml"
    questions = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    for q in questions:
        if q.get("verification"):
            continue  # already checked on an earlier run
        page = load_page(q["source_url"])
        # Send only what the checker needs to judge: the question itself, not ids or metadata.
        payload = yaml.safe_dump({k: q[k] for k in ("type", "stem", "options", "answer", "explanation", "quote")}, allow_unicode=True)
        r = llm.chat_json(llm.VERIFY_MODEL, SYSTEM, f"PAGE:\n{page['text']}\n\nQUESTION:\n{payload}")
        # All three checks must hold; a failure only flags the question, the human still decides in review.py.
        passed = bool(r.get("supported")) and bool(r.get("single_best")) and bool(r.get("not_outdated"))
        q["verification"] = {"passed": passed, "notes": str(r.get("notes", "")), "model": llm.VERIFY_MODEL}
        if not passed:
            q["status"] = "flagged"
        print(f"{q['id']}: {'pass' if passed else 'FAIL'} {r.get('notes', '')[:100]}")
    path.write_text(yaml.safe_dump(questions, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
