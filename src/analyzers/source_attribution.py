"""Source Attribution Tracking analyzer.

Deduplicates URLs cited across all chats and counts citations per URL.
"""

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from src.matchers import LabeledChat

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceRow:
    domain: str
    source_url: str
    content_type: str        # ALWAYS "" in v1 (judgment field)
    topic: str               # ALWAYS "" in v1 (judgment field)
    platform_citations: str  # comma-separated unique sorted channels
    citation_count: int


def _extract_domain(url: str) -> str:
    netloc = urlparse(url).netloc
    if netloc:
        return netloc
    # URL has no scheme — take the part before the first "/"
    return url.split("/")[0] if "/" in url else url


def build_source_attribution(chats: list[LabeledChat]) -> list[SourceRow]:
    """Produce one SourceRow per unique URL across all chats.

    For each unique URL across chats[*].chat.sources:
    - domain: extracted via urlparse; falls back to pre-slash segment for scheme-less URLs.
    - source_url: the URL as-is.
    - content_type: "" (v1 leaves blank).
    - topic: "" (v1 leaves blank).
    - platform_citations: alphabetically sorted, comma-joined unique model_channel values.
    - citation_count: number of chats containing this URL.

    Sort: citation_count DESC, then domain ASC, then source_url ASC.
    Returns [] if no chats or no sources.
    """
    url_data: dict[str, dict] = {}

    for labeled in chats:
        chat = labeled.chat
        seen_in_this_chat: set[str] = set()
        for url in chat.sources:
            if not url or url in seen_in_this_chat:
                continue
            seen_in_this_chat.add(url)
            if url not in url_data:
                url_data[url] = {"platforms": set(), "count": 0}
            url_data[url]["count"] += 1
            url_data[url]["platforms"].add(chat.model_channel)

    rows = [
        SourceRow(
            domain=_extract_domain(url),
            source_url=url,
            content_type="",
            topic="",
            platform_citations=", ".join(sorted(data["platforms"])),
            citation_count=data["count"],
        )
        for url, data in url_data.items()
    ]

    rows.sort(key=lambda r: (-r.citation_count, r.domain, r.source_url))
    log.info("build_source_attribution: %d input chats → %d rows", len(chats), len(rows))
    return rows
