"""Export questions for the web app to app/questions.js.

Usage: python pipeline/build_app_data.py [--include-drafts]
By default only status: approved questions are exported. --include-drafts also adds
unreviewed drafts from pipeline/drafts/ so you can preview them as a learner would.
"""
import json
import sys

import yaml

from common import DRAFTS, ROOT

FIELDS = ("id", "domain", "skill", "type", "stem", "options", "answer", "explanation", "source_url", "difficulty", "status")


def main(include_drafts):
    files = sorted((ROOT / "content").glob("*/*.yaml"))
    files = [f for f in files if f.name != "outline.yaml"]
    if include_drafts:
        files += sorted(DRAFTS.glob("*.yaml"))
    out = []
    for f in files:
        for q in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            if include_drafts or q.get("status") == "approved":
                out.append({k: q[k] for k in FIELDS})
    path = ROOT / "app" / "questions.js"
    path.write_text("window.QUESTIONS = " + json.dumps(out, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"{len(out)} questions -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main("--include-drafts" in sys.argv)
