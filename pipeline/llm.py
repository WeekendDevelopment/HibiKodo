"""Thin LLM client. Groq by default (OpenAI-compatible); override with env vars.

GROQ_API_KEY   required for generate/verify (put it in .env at the repo root)
LLM_BASE_URL   default https://api.groq.com/openai/v1
GEN_MODEL      default openai/gpt-oss-20b
VERIFY_MODEL   default openai/gpt-oss-120b   (a different model from GEN_MODEL on purpose)
Model ids change over time; check your provider's model list if a call 404s.
"""
import json
import os
import time

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI, RateLimitError

from common import ROOT

# Reads GROQ_API_KEY etc. from .env (git-ignored) without overriding real environment variables.
load_dotenv(ROOT / ".env")

GEN_MODEL = os.environ.get("GEN_MODEL", "openai/gpt-oss-20b")
VERIFY_MODEL = os.environ.get("VERIFY_MODEL", "openai/gpt-oss-120b")


def _client() -> OpenAI:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise SystemExit("GROQ_API_KEY is not set. Get a free key at console.groq.com and put it in .env.")
    return OpenAI(api_key=key, base_url=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"))


def chat_json(model: str, system: str, user: str, retries: int = 5) -> dict:
    """Call the model in JSON mode and return the parsed object, retrying transient failures."""
    client = _client()
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.3,
                # Groq counts this toward the free tier's 8000 tokens-per-minute cap on the request itself,
                # so keep it small (page + prompt is ~3K tokens).
                max_completion_tokens=3500,
            )
            # content is None if the model returned nothing; "" then fails to parse and takes the retry path below.
            return json.loads(resp.choices[0].message.content or "")
        except json.JSONDecodeError:
            # Output was cut off at the token limit or otherwise not JSON; the model is non-deterministic, so retry.
            print(f"  model returned unparseable JSON (attempt {attempt + 1}/{retries})")
        except BadRequestError as e:
            # Groq itself rejects output that fails its JSON check and includes the text as 'failed_generation'.
            body = getattr(e, "body", None)
            detail = body.get("error", {}).get("failed_generation", "") if isinstance(body, dict) else ""
            print(f"  invalid JSON from model (attempt {attempt + 1}/{retries}): {str(detail)[:200]!r}")
            if "failed_generation" not in str(e) and "JSON" not in str(e):
                raise  # a different 400 (bad model id, bad params) will not fix itself on retry
        except RateLimitError:
            # Free-tier per-minute limit hit: back off 5s, 10s, 20s, 40s, 80s.
            wait = 2 ** attempt * 5
            print(f"  rate limited, waiting {wait}s")
            time.sleep(wait)
    raise SystemExit("Gave up after retries (rate limit or invalid model output); try again.")
