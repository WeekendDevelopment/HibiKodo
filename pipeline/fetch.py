"""Fetch a Microsoft Learn page and store its text with URL and retrieval date.

Usage: python pipeline/fetch.py <url> [--refresh]
"""
import io
import json
import sys
from datetime import date
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from common import PAGES, slug

ALLOWED_HOSTS = {"learn.microsoft.com"}


def extract_text(html: str) -> tuple[str, str]:
    """Reduce a Learn page to (title, plain text), one block element per line, ignoring nav/ads/scripts."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.body
    if main is None:
        raise SystemExit("The page has no <main> or <body>; it may not be a normal docs page.")
    for tag in main.find_all(["script", "style", "nav", "footer", "aside", "button"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    lines = [el.get_text(" ", strip=True) for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "pre"])]
    # Nested elements (li > p) repeat text; drop exact consecutive duplicates.
    out: list[str] = []
    for line in lines:
        if line and not line.startswith("Access to this page requires authorization") and (not out or out[-1] != line):
            out.append(line)
    return title, "\n".join(out)


def fetch(url: str, refresh: bool = False) -> dict[str, str]:
    """Return the stored page for `url`, downloading it first if it isn't cached (or refresh is set)."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise SystemExit(f"Refusing {url}: only https URLs on {sorted(ALLOWED_HOSTS)} are allowed sources")
    path = PAGES / f"{slug(url)}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "HibiKodo-pipeline/0.1 (study project)"})
        resp.raise_for_status()
    except requests.RequestException as e:
        # A readable one-liner instead of a long traceback (offline, 404, timeout...).
        raise SystemExit(f"Could not fetch {url}: {e}") from None
    title, text = extract_text(resp.text)
    page = {"url": url, "title": title, "retrieved_at": date.today().isoformat(), "text": text}
    PAGES.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
    return page


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if isinstance(sys.stdout, io.TextIOWrapper):  # Windows consoles default to cp1252, which can't print some page text
        sys.stdout.reconfigure(encoding="utf-8")
    page = fetch(sys.argv[1], refresh="--refresh" in sys.argv)
    print(f"{page['title']}\nretrieved {page['retrieved_at']}, {len(page['text'])} chars, {page['text'].count(chr(10)) + 1} lines")
    print("---")
    print(page["text"][:1200])
