"""AI Platform Response Tracking analyzer.

Groups labeled chats by (platform, category, prompt_id) and produces one row
per group with brand mention rate, average position, average sentiment, top
co-mentions, citations, and a chat snapshot.

v1: ChatGPT only.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from src.config import (
    CHAT_SNAPSHOT_CHARS,
    INCLUDED_PLATFORMS,
    MAX_SOURCES_PER_GROUP,
    SENTIMENT_NEGATIVE_THRESHOLD,
    SENTIMENT_POSITIVE_THRESHOLD,
)
from src.matchers import LabeledChat
from src.prompt_library import Category, PromptEntry


@dataclass(frozen=True)
class PlatformResponseRow:
    prompt_id: str
    prompt: str
    brand_mentioned: str       # "Y", "N", "Y (4/7)", "N (0/7)"
    position: str              # avg as formatted string, or "-"
    context_analysis: str      # ALWAYS "" in v1
    sentiment_score: str       # avg as formatted string (1 decimal), or "-"
    sentiment_label: str       # "Positive" | "Neutral" | "Negative" | "No Sentiment"
    co_mentions: str           # "Brand A (3/7), Brand B (2/7)" or "None"
    sources_citations: str     # newline-joined unique URLs, max MAX_SOURCES_PER_GROUP, or "-"
    chat_snapshot: str         # first CHAT_SNAPSHOT_CHARS of one representative response
    notes: str                 # ALWAYS "" in v1


CATEGORIES_ORDERED: list[Category] = [
    "Direct Brand Queries",
    "Category-Based Queries",
    "Comparison Queries",
]


def _brand_mentioned(chat, brand_name: str) -> bool:
    bn_lower = brand_name.lower()
    if any(bn_lower in m.lower() for m in chat.mentions):
        return True
    return bn_lower in chat.response.lower()


def _prompt_sort_key(prompt_id: str) -> int:
    parts = prompt_id.rsplit("-", 1)
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def build_ai_platform_response(
    chats: list[LabeledChat],
    prompt_library: dict[str, PromptEntry],
    brand_name: str,
) -> dict[str, dict[Category, list[PlatformResponseRow]]]:
    """Group chats by (model_channel, category, prompt_id).

    Returns: { platform_name: { category: [PlatformResponseRow, ...] } }

    For v1, only platforms in INCLUDED_PLATFORMS appear. Categories are always
    present (DB, CB, CO) even if empty for a platform — the caller decides
    whether to emit an "empty section" placeholder.

    Rows within a category are sorted by prompt_id numerically (not lexicographically).
    """
    # Filter to included platforms only
    filtered = [c for c in chats if c.chat.model_channel in INCLUDED_PLATFORMS]

    # Group by (platform, category, prompt_id)
    groups: dict[str, dict[str, dict[str, list[LabeledChat]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for lc in filtered:
        groups[lc.chat.model_channel][lc.category][lc.prompt_id].append(lc)

    result: dict[str, dict[Category, list[PlatformResponseRow]]] = {}

    for platform in sorted(groups.keys()):
        result[platform] = {}
        for category in CATEGORIES_ORDERED:
            rows: list[PlatformResponseRow] = []
            prompt_groups = groups[platform].get(category, {})

            for prompt_id in sorted(prompt_groups.keys(), key=_prompt_sort_key):
                g = prompt_groups[prompt_id]
                n = len(g)

                # Brand mention flags per chat
                mentioned_flags = [_brand_mentioned(lc.chat, brand_name) for lc in g]
                n_mentioned = sum(mentioned_flags)

                # brand_mentioned string
                if n == 1:
                    brand_mentioned_str = "Y" if n_mentioned >= 1 else "N"
                else:
                    brand_mentioned_str = (
                        f"Y ({n_mentioned}/{n})" if n_mentioned >= 1 else f"N (0/{n})"
                    )

                # Position average (only chats where brand mentioned + position not None)
                positions = [
                    lc.chat.position
                    for lc, mentioned in zip(g, mentioned_flags)
                    if mentioned and lc.chat.position is not None
                ]
                if positions:
                    avg_pos = sum(positions) / len(positions)
                    position_str = f"{avg_pos:.1f}"
                else:
                    position_str = "-"

                # Sentiment average (only chats where brand mentioned + sentiment not None)
                sentiments = [
                    lc.chat.sentiment
                    for lc, mentioned in zip(g, mentioned_flags)
                    if mentioned and lc.chat.sentiment is not None
                ]
                if sentiments:
                    avg_sent = sum(sentiments) / len(sentiments)
                    sentiment_score_str = f"{avg_sent:.1f}"
                    if avg_sent >= SENTIMENT_POSITIVE_THRESHOLD:
                        sentiment_label = "Positive"
                    elif avg_sent <= SENTIMENT_NEGATIVE_THRESHOLD:
                        sentiment_label = "Negative"
                    else:
                        sentiment_label = "Neutral"
                else:
                    sentiment_score_str = "-"
                    sentiment_label = "No Sentiment"

                # Co-mentions: count non-brand mentions across group
                bn_lower = brand_name.lower()
                mention_counts: dict[str, int] = {}
                mention_first_case: dict[str, str] = {}
                for lc in g:
                    for m in lc.chat.mentions:
                        m_lower_check = m.lower()
                        if bn_lower in m_lower_check or m_lower_check in bn_lower:
                            continue
                        m_lower = m.lower()
                        if m_lower not in mention_counts:
                            mention_counts[m_lower] = 0
                            mention_first_case[m_lower] = m
                        mention_counts[m_lower] += 1

                co_list = sorted(mention_counts.items(), key=lambda x: (-x[1], x[0]))[:5]
                co_mentions_str = (
                    ", ".join(
                        f"{mention_first_case[m_lower]} ({cnt}/{n})"
                        for m_lower, cnt in co_list
                    )
                    if co_list
                    else "None"
                )

                # Sources: union, deduped, capped
                seen_urls: set[str] = set()
                urls: list[str] = []
                for lc in g:
                    for url in lc.chat.sources:
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            urls.append(url)
                        if len(urls) >= MAX_SOURCES_PER_GROUP:
                            break
                    if len(urls) >= MAX_SOURCES_PER_GROUP:
                        break
                sources_str = "\n".join(urls) if urls else "-"

                # Chat snapshot: prefer a chat where brand was mentioned
                snapshot_lc = next(
                    (lc for lc, mentioned in zip(g, mentioned_flags) if mentioned),
                    g[0] if g else None,
                )
                if snapshot_lc:
                    resp = snapshot_lc.chat.response.strip()
                    chat_snapshot = (
                        resp[:CHAT_SNAPSHOT_CHARS] + "..."
                        if len(resp) > CHAT_SNAPSHOT_CHARS
                        else resp
                    )
                else:
                    chat_snapshot = ""

                entry = prompt_library.get(prompt_id)
                prompt_text = entry.text if entry else prompt_id

                rows.append(PlatformResponseRow(
                    prompt_id=prompt_id,
                    prompt=prompt_text,
                    brand_mentioned=brand_mentioned_str,
                    position=position_str,
                    context_analysis="",
                    sentiment_score=sentiment_score_str,
                    sentiment_label=sentiment_label,
                    co_mentions=co_mentions_str,
                    sources_citations=sources_str,
                    chat_snapshot=chat_snapshot,
                    notes="",
                ))

            result[platform][category] = rows

    return result
