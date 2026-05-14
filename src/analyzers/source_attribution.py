"""Source Attribution Tracking analyzer.

Merges Peec /url-report data (url_type, domain_type, brand_mentioned,
retrieval metrics) with chat-derived platform_citations. Falls back to
chat-only data when url_records are not provided.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from src.matchers import LabeledChat

log = logging.getLogger(__name__)

# Domain type → section label + sort order
_SECTION_ORDER = {
    "Corporate": (0, "Client Sources"),
    "You": (0, "Client Sources"),
    "Related": (0, "Client Sources"),
    "Competitor": (1, "Competitor Sources"),
    "Editorial": (2, "Editorial & Reference Sources"),
    "Institutional": (2, "Editorial & Reference Sources"),
    "Reference": (2, "Editorial & Reference Sources"),
    "UGC": (3, "UGC & Other Sources"),
    "Other": (3, "UGC & Other Sources"),
}


@dataclass(frozen=True)
class SourceRow:
    domain: str
    source_url: str
    title: str              # from Peec URL report; "" in fallback mode
    url_type: str           # Profile, Article, Listicle, etc.; "" in fallback
    domain_type: str        # Corporate, Competitor, Editorial, etc.; "" in fallback
    brand_mentioned: bool   # from Peec URL report; False in fallback
    topic: str              # ALWAYS "" in v1 (judgment field)
    platform_citations: str # comma-separated unique sorted channels from chats
    citation_count: int
    retrieval_count: int    # from Peec URL report; 0 in fallback
    citation_rate: float    # from Peec URL report; 0.0 in fallback

    @property
    def section(self) -> str:
        return _SECTION_ORDER.get(self.domain_type, (3, "UGC & Other Sources"))[1]

    @property
    def section_order(self) -> int:
        return _SECTION_ORDER.get(self.domain_type, (3, "UGC & Other Sources"))[0]


def _extract_domain(url: str) -> str:
    netloc = urlparse(url).netloc
    if netloc:
        return netloc
    return url.split("/")[0] if "/" in url else url


def build_source_attribution(
    chats: list[LabeledChat],
    url_records=None,  # list[UrlRecord] | None
) -> list[SourceRow]:
    """Produce one SourceRow per unique URL.

    When url_records are provided (from fetch_url_report), they are the
    primary data source for URL metadata; chat data contributes platform_citations.
    When url_records is None/empty, falls back to chat-only URL extraction.

    Sort: section order → citation_count DESC → domain ASC → url ASC.
    """
    # Build platform_citations from chats regardless of mode
    url_platforms: dict[str, set[str]] = {}
    for labeled in chats:
        chat = labeled.chat
        seen: set[str] = set()
        for url in chat.sources:
            if not url or url in seen:
                continue
            seen.add(url)
            if url not in url_platforms:
                url_platforms[url] = set()
            url_platforms[url].add(chat.model_channel)

    if url_records:
        rows = [
            SourceRow(
                domain=ur.domain,
                source_url=ur.url,
                title=ur.title,
                url_type=ur.url_type,
                domain_type=ur.domain_type,
                brand_mentioned=ur.brand_mentioned,
                topic="",
                platform_citations=", ".join(sorted(url_platforms.get(ur.url, set()))),
                citation_count=ur.citation_count,
                retrieval_count=ur.retrieval_count,
                citation_rate=ur.citation_rate,
            )
            for ur in url_records
        ]
        rows.sort(key=lambda r: (r.section_order, -r.citation_count, r.domain, r.source_url))
        log.info("build_source_attribution: %d url_records → %d rows", len(url_records), len(rows))
        return rows

    # Fallback: chat-derived URLs only
    url_data: dict[str, dict] = {}
    for labeled in chats:
        chat = labeled.chat
        seen: set[str] = set()
        for url in chat.sources:
            if not url or url in seen:
                continue
            seen.add(url)
            if url not in url_data:
                url_data[url] = {"platforms": set(), "count": 0}
            url_data[url]["count"] += 1
            url_data[url]["platforms"].add(chat.model_channel)

    rows = [
        SourceRow(
            domain=_extract_domain(url),
            source_url=url,
            title="",
            url_type="",
            domain_type="",
            brand_mentioned=False,
            topic="",
            platform_citations=", ".join(sorted(data["platforms"])),
            citation_count=data["count"],
            retrieval_count=0,
            citation_rate=0.0,
        )
        for url, data in url_data.items()
    ]
    rows.sort(key=lambda r: (-r.citation_count, r.domain, r.source_url))
    log.info("build_source_attribution: %d input chats → %d rows (fallback)", len(chats), len(rows))
    return rows
