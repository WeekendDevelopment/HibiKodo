"""Shared helpers: paths, page cache, text normalisation."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "pipeline" / "cache"
PAGES = CACHE / "pages"
DRAFTS = ROOT / "pipeline" / "drafts"


def slug(url: str) -> str:
    """Short stable filename for a URL's cache entry."""
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def normalise(text: str) -> str:
    """Collapse whitespace and unify quotes/dashes so quote matching survives HTML quirks."""
    text = (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "-").replace(" ", " "))
    return re.sub(r"\s+", " ", text).strip()


def load_page(url: str) -> dict[str, str]:
    """Load a page saved by fetch.py ({url, title, retrieved_at, text}); stops with a hint if it isn't fetched."""
    path = PAGES / f"{slug(url)}.json"
    if not path.exists():
        raise SystemExit(f"Page not fetched yet: run fetch.py {url}")
    return json.loads(path.read_text(encoding="utf-8"))
