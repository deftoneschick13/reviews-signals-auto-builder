"""Peec REST API client. Returns typed Chat and UrlRecord objects."""

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Optional
from urllib.parse import urlparse

import requests

from src.config import (
    INCLUDED_PLATFORMS,
    PEEC_BASE_URL,
    PEEC_MAX_RETRIES,
    PEEC_PAGE_SIZE,
)

log = logging.getLogger(__name__)

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
class UrlRecord:
    """A single URL citation record from the Peec /url-report endpoint."""
    url: str
    domain: str
    title: str
    url_type: str           # Homepage, Profile, Article, Listicle, etc.
    domain_type: str        # Corporate, Competitor, Editorial, UGC, etc.
    brand_mentioned: bool   # True if focal brand appears in mentioned_brand_ids
    citation_count: int
    retrieval_count: int
    citation_rate: float


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


def _request(url: str, params, api_key: str) -> dict:
    headers = {"x-api-key": api_key}
    for attempt in range(PEEC_MAX_RETRIES + 1):
        resp = requests.get(url, params=params, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (401, 403):
            log.error("Peec auth failure: %s", resp.status_code)
            raise PeecAuthError(resp.text)
        if resp.status_code == 429:
            if attempt == PEEC_MAX_RETRIES:
                raise PeecRateLimitError(resp.text)
            wait = int(resp.headers.get("Retry-After", 2 ** attempt))
            log.warning("Rate limited by Peec (attempt %d/%d), retrying in %ds", attempt + 1, PEEC_MAX_RETRIES, wait)
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


def _extract_domain(url: str) -> str:
    netloc = urlparse(url).netloc
    if netloc:
        return netloc
    return url.split("/")[0] if "/" in url else url


def _lookup_brand_id(project_id: str, brand_name: str, api_key: str) -> str | None:
    """Resolve a brand name to its Peec brand_id. Returns None if not found."""
    try:
        resp = _request(f"{PEEC_BASE_URL}/brands", {"project_id": project_id}, api_key)
    except PeecError as e:
        log.warning("_lookup_brand_id: /brands call failed: %s", e)
        return None

    bn_lower = brand_name.lower()

    # Columnar format: {columns: [...], rows: [[...], ...]}
    columns = resp.get("columns")
    rows = resp.get("rows") or []
    if columns and rows:
        try:
            id_idx = columns.index("id")
            name_idx = columns.index("name")
        except ValueError:
            return None
        for row in rows:
            name_val = str(row[name_idx] or "").lower()
            if bn_lower in name_val or name_val in bn_lower:
                return row[id_idx]

    # Object format fallback: {data: [{id, name, ...}]}
    for item in resp.get("data", []):
        name_val = str(item.get("name") or "").lower()
        if bn_lower in name_val or name_val in bn_lower:
            return item.get("id")

    return None


def _fetch_brand_sentiments(
    project_id: str,
    start_date: date,
    end_date: date,
    brand_name: str,
    api_key: str,
) -> dict[str, tuple[Optional[float], Optional[int]]]:
    """Return {chat_id: (sentiment, position)} for the focal brand.

    Makes one /brand-report call dimensioned by chat_id. Returns empty dict
    on any failure so the rest of the pipeline continues with sentiment=None.
    """
    brand_id = _lookup_brand_id(project_id, brand_name, api_key)
    if not brand_id:
        log.warning("_fetch_brand_sentiments: brand '%s' not found — sentiment will be None", brand_name)
        return {}

    try:
        resp = _request(
            f"{PEEC_BASE_URL}/brand-report",
            [
                ("project_id", project_id),
                ("start_date", start_date.isoformat()),
                ("end_date", end_date.isoformat()),
                ("dimensions[]", "chat_id"),
                ("brand_id", brand_id),
                ("limit", "10000"),
            ],
            api_key,
        )
    except PeecError as e:
        log.warning("_fetch_brand_sentiments: /brand-report call failed: %s", e)
        return {}

    result: dict[str, tuple[Optional[float], Optional[int]]] = {}

    # Columnar format (matches MCP response shape)
    columns = resp.get("columns")
    rows = resp.get("rows") or []
    if columns and rows:
        try:
            chat_id_idx = columns.index("chat_id")
            sentiment_idx = columns.index("sentiment")
            position_idx = columns.index("position")
        except ValueError:
            log.warning("_fetch_brand_sentiments: unexpected columns: %s", columns)
            return {}
        for row in rows:
            cid = row[chat_id_idx]
            if cid:
                s = row[sentiment_idx]
                p = row[position_idx]
                result[cid] = (
                    float(s) if s is not None else None,
                    int(p) if p is not None else None,
                )
    else:
        # Object format fallback
        for item in resp.get("data", []):
            cid = item.get("chat_id")
            if cid:
                result[cid] = (
                    _float_or_none(item.get("sentiment")),
                    _int_or_none(item.get("position")),
                )

    log.info("_fetch_brand_sentiments: %d records fetched for brand '%s'", len(result), brand_name)
    return result


def fetch_chats(
    project_id: str,
    start_date: date,
    end_date: date,
    api_key: str,
    brand_name: str = "",
) -> list[Chat]:
    """Fetch all chats for a project in a date range.

    Handles pagination automatically. Retries 429 with exponential backoff
    (1s, 2s, 4s — max 3 attempts). Raises typed exceptions on auth failures.
    Filters out chats whose model_channel is not in INCLUDED_PLATFORMS
    (from src/config.py) BEFORE returning — keeps the Step 3 footprint small.

    If brand_name is provided, fetches per-chat sentiment and position from
    /brand-report and populates Chat.sentiment and Chat.position accordingly.

    Returns Chat objects in the order returned by the API.
    """
    log.info("fetch_chats: project=%s  %s → %s  brand=%r", project_id, start_date, end_date, brand_name)

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
        log.debug("fetch_chats: fetched page offset=%d, got %d stubs (total=%d)", offset, len(page), total)
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

    # 4. Fetch per-chat sentiment from /brand-report (one call for all chats)
    sentiments: dict[str, tuple[Optional[float], Optional[int]]] = {}
    if brand_name and stubs:
        sentiments = _fetch_brand_sentiments(project_id, start_date, end_date, brand_name, api_key)

    # 5. Fetch full content per chat and assemble Chat objects
    bn_lower = brand_name.lower() if brand_name else ""
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

        # Use brand_report sentiment/position when available; fall back to brands_mentioned
        brand_report_sentiment, brand_report_position = sentiments.get(chat_id, (None, None))

        if brand_name and brands:
            focal = next(
                (b for b in brands if bn_lower in b.get("name", "").lower()
                 or b.get("name", "").lower() in bn_lower),
                None,
            )
            content_position = _int_or_none(focal.get("position") if focal else None)
        else:
            content_position = _int_or_none(brands[0].get("position") if brands else None)

        result.append(Chat(
            id=chat_id,
            model=_str(stub["model"]["id"]),
            model_channel=_CHANNEL_TO_PLATFORM.get(raw_channel, _str(raw_channel)),
            prompt=_str(prompt_text) or _str(p_info.get("text", "")),
            response=_str(response_text),
            country=_str(p_info.get("country", "")),
            position=brand_report_position if brand_report_position is not None else content_position,
            mentions=_str_list([b.get("name", "") for b in brands]),
            sources=_str_list([s.get("url", "") for s in raw_sources]),
            sentiment=brand_report_sentiment,
            created=_str(stub.get("date", "")),
        ))

    log.info("fetch_chats: returning %d chats for %d included-platform stubs", len(result), len(stubs))
    return result


def fetch_url_report(
    project_id: str,
    start_date: date,
    end_date: date,
    api_key: str,
    brand_name: str = "",
) -> list[UrlRecord]:
    """Fetch URL-level citation data from Peec /url-report endpoint.

    Also calls /domain-report to get domain classifications (Corporate,
    Competitor, Editorial, etc.) which drive Source Attribution sectioning.
    Gracefully returns [] on any API failure so the build continues.
    """
    log.info("fetch_url_report: project=%s  %s → %s  brand=%r", project_id, start_date, end_date, brand_name)

    # 1. Domain classifications from /domain-report
    domain_types: dict[str, str] = {}
    try:
        dom_resp = _request(
            f"{PEEC_BASE_URL}/domain-report",
            [
                ("project_id", project_id),
                ("start_date", start_date.isoformat()),
                ("end_date", end_date.isoformat()),
                ("limit", "5000"),
            ],
            api_key,
        )
        columns = dom_resp.get("columns")
        rows = dom_resp.get("rows") or []
        if columns and rows:
            try:
                d_idx = columns.index("domain")
                c_idx = columns.index("classification")
            except ValueError:
                pass
            else:
                for row in rows:
                    d = row[d_idx]
                    if d:
                        domain_types[str(d)] = _str(row[c_idx]) or "Other"
        else:
            for item in dom_resp.get("data", []):
                d = item.get("domain")
                if d:
                    domain_types[str(d)] = _str(item.get("classification")) or "Other"
    except PeecError as e:
        log.warning("fetch_url_report: /domain-report failed: %s", e)

    # 2. Brand ID for brand_mentioned flag
    brand_id: str | None = None
    if brand_name:
        brand_id = _lookup_brand_id(project_id, brand_name, api_key)

    # 3. URL report from /url-report
    try:
        url_resp = _request(
            f"{PEEC_BASE_URL}/url-report",
            [
                ("project_id", project_id),
                ("start_date", start_date.isoformat()),
                ("end_date", end_date.isoformat()),
                ("limit", "5000"),
            ],
            api_key,
        )
    except PeecError as e:
        log.warning("fetch_url_report: /url-report failed: %s", e)
        return []

    result: list[UrlRecord] = []
    columns = url_resp.get("columns")
    rows = url_resp.get("rows") or []

    if columns and rows:
        try:
            url_idx = columns.index("url")
            cls_idx = columns.index("classification")
            title_idx = columns.index("title")
            cite_idx = columns.index("citation_count")
            ret_idx = columns.index("retrieval_count")
            rate_idx = columns.index("citation_rate")
            bid_idx = columns.index("mentioned_brand_ids")
        except ValueError as exc:
            log.warning("fetch_url_report: unexpected columns %s: %s", columns, exc)
            return []
        for row in rows:
            url = _str(row[url_idx])
            if not url:
                continue
            domain = _extract_domain(url)
            bids = row[bid_idx] or []
            result.append(UrlRecord(
                url=url,
                domain=domain,
                title=_str(row[title_idx]),
                url_type=_str(row[cls_idx]) or "Other",
                domain_type=domain_types.get(domain, "Other"),
                brand_mentioned=bool(brand_id and brand_id in bids),
                citation_count=int(row[cite_idx]) if row[cite_idx] is not None else 0,
                retrieval_count=int(row[ret_idx]) if row[ret_idx] is not None else 0,
                citation_rate=float(row[rate_idx]) if row[rate_idx] is not None else 0.0,
            ))
    else:
        for item in url_resp.get("data", []):
            url = _str(item.get("url", ""))
            if not url:
                continue
            domain = _extract_domain(url)
            bids = item.get("mentioned_brand_ids") or []
            result.append(UrlRecord(
                url=url,
                domain=domain,
                title=_str(item.get("title", "")),
                url_type=_str(item.get("classification")) or "Other",
                domain_type=domain_types.get(domain, "Other"),
                brand_mentioned=bool(brand_id and brand_id in bids),
                citation_count=_int_or_none(item.get("citation_count")) or 0,
                retrieval_count=_int_or_none(item.get("retrieval_count")) or 0,
                citation_rate=_float_or_none(item.get("citation_rate")) or 0.0,
            ))

    log.info("fetch_url_report: %d URL records fetched", len(result))
    result.sort(key=lambda r: -r.citation_count)
    return result
