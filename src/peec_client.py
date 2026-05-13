"""Peec REST API client. Returns typed Chat objects."""

import time
from dataclasses import dataclass
from datetime import date
from typing import Optional

import requests

from src.config import (
    INCLUDED_PLATFORMS,
    PEEC_BASE_URL,
    PEEC_MAX_RETRIES,
    PEEC_PAGE_SIZE,
)

# Maps Peec model_channel.id → human-readable platform name used in INCLUDED_PLATFORMS
_CHANNEL_TO_PLATFORM: dict[str, str] = {
    "openai-0": "ChatGPT",
    "openai-1": "ChatGPT",
    "openai-2": "ChatGPT",
    "perplexity-0": "Perplexity",
    "perplexity-1": "Perplexity",
    "google-0": "Google AI Overview",
    "google-1": "Google AI Mode",
    "google-2": "Google",
    "google-3": "Google",
    "anthropic-0": "Claude",
    "anthropic-1": "Claude",
    "deepseek-0": "DeepSeek",
    "meta-0": "Meta AI",
    "xai-0": "Grok",
    "xai-1": "Grok",
    "microsoft-0": "Copilot",
    "amazon-0": "Rufus",
    "qwen-0": "Qwen",
}


@dataclass(frozen=True)
class Chat:
    """A single AI chat record from Peec. Field names are normalized
    regardless of what Peec calls them in the raw response."""
    id: str
    model: str           # e.g. "chatgpt-scraper"
    model_channel: str   # e.g. "ChatGPT"
    prompt: str          # the user message text
    response: str        # the AI assistant message text
    country: str
    position: Optional[int]    # None if no brand found
    mentions: list[str]        # list of brand names mentioned in response
    sources: list[str]         # list of cited URLs
    sentiment: Optional[float] # 0.0–100.0; None if unscored
    created: str               # YYYY-MM-DD date string


class PeecError(Exception):
    """Base class for Peec API errors."""


class PeecAuthError(PeecError):
    """401 or 403 from Peec API."""


class PeecRateLimitError(PeecError):
    """429 from Peec after retries exhausted."""


class PeecAPIError(PeecError):
    """Other 4xx/5xx from Peec."""


def _request(url: str, params: dict, api_key: str) -> dict:
    headers = {"x-api-key": api_key}
    for attempt in range(PEEC_MAX_RETRIES + 1):
        resp = requests.get(url, params=params, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (401, 403):
            raise PeecAuthError(resp.text)
        if resp.status_code == 429:
            if attempt == PEEC_MAX_RETRIES:
                raise PeecRateLimitError(resp.text)
            wait = int(resp.headers.get("Retry-After", 2 ** attempt))
            time.sleep(wait)
            continue
        raise PeecAPIError(f"{resp.status_code}: {resp.text}")


def _str(v) -> str:
    return "" if v is None else str(v).strip()


def _int_or_none(v) -> Optional[int]:
    if v is None or v == "" or v == "-":
        return None
    return int(v)


def _float_or_none(v) -> Optional[float]:
    if v is None or v == "" or v == "-":
        return None
    return float(v)


def _str_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [s.strip() for s in (str(x) for x in v) if s.strip()]
    if isinstance(v, str):
        return [s.strip() for s in v.splitlines() if s.strip()]
    return []


def fetch_chats(
    project_id: str,
    start_date: date,
    end_date: date,
    api_key: str,
) -> list[Chat]:
    """Fetch all chats for a project in a date range.

    Handles pagination automatically. Retries 429 with exponential backoff
    (1s, 2s, 4s — max 3 attempts). Raises typed exceptions on auth failures.
    Filters out chats whose model_channel is not in INCLUDED_PLATFORMS
    (from src/config.py) BEFORE returning — keeps the Step 3 footprint small.

    Returns Chat objects in the order returned by the API.
    """
    # 1. Paginated list of chat stubs from /chats
    stubs: list[dict] = []
    offset = 0
    while True:
        page_data = _request(
            f"{PEEC_BASE_URL}/chats",
            {
                "project_id": project_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "limit": PEEC_PAGE_SIZE,
                "offset": offset,
            },
            api_key,
        )
        page = page_data.get("data", [])
        stubs.extend(page)
        total = page_data.get("totalCount", 0)
        if not page or len(stubs) >= total:
            break
        offset += len(page)

    # 2. Filter to included platforms before fetching content (avoids N extra calls)
    stubs = [
        s for s in stubs
        if _CHANNEL_TO_PLATFORM.get(s["model_channel"]["id"], s["model_channel"]["id"])
        in INCLUDED_PLATFORMS
    ]

    # 3. Cache prompt text and country from /prompts (one call covers all prompts)
    prompts_resp = _request(
        f"{PEEC_BASE_URL}/prompts",
        {"project_id": project_id},
        api_key,
    )
    prompt_cache: dict[str, dict] = {}
    for p in prompts_resp.get("data", []):
        msgs = p.get("messages", [])
        text = msgs[0].get("content", "") if msgs else ""
        country = (p.get("user_location") or {}).get("country", "")
        prompt_cache[p["id"]] = {"text": text, "country": country}

    # 4. Fetch full content per chat and assemble Chat objects
    result: list[Chat] = []
    for stub in stubs:
        chat_id = stub["id"]
        content = _request(
            f"{PEEC_BASE_URL}/chats/{chat_id}/content",
            {"project_id": project_id},
            api_key,
        )

        messages = content.get("messages", []) or []
        prompt_text = next(
            (m.get("content", "") for m in messages if m.get("role") == "user"), ""
        )
        response_text = next(
            (m.get("content", "") for m in messages if m.get("role") == "assistant"), ""
        )

        brands = content.get("brands_mentioned", []) or []
        raw_sources = content.get("sources", []) or []

        p_info = prompt_cache.get(stub["prompt"]["id"], {})
        raw_channel = stub["model_channel"]["id"]

        result.append(Chat(
            id=chat_id,
            model=_str(stub["model"]["id"]),
            model_channel=_CHANNEL_TO_PLATFORM.get(raw_channel, _str(raw_channel)),
            prompt=_str(prompt_text) or _str(p_info.get("text", "")),
            response=_str(response_text),
            country=_str(p_info.get("country", "")),
            position=_int_or_none(brands[0].get("position") if brands else None),
            mentions=_str_list([b.get("name", "") for b in brands]),
            sources=_str_list([s.get("url", "") for s in raw_sources]),
            sentiment=None,  # requires separate brand_report call; not fetched here
            created=_str(stub.get("date", "")),
        ))

    return result
