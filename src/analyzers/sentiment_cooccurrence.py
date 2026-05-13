"""Sentiment & Co-Occurrence analyzer."""

from collections import defaultdict
from dataclasses import dataclass

from src.analyzers.ai_platform_response import CATEGORIES_ORDERED, _brand_mentioned, _prompt_sort_key
from src.config import (
    MAX_COOCCURRENCE_ROWS,
    SENTIMENT_NEGATIVE_THRESHOLD,
    SENTIMENT_POSITIVE_THRESHOLD,
)
from src.matchers import LabeledChat
from src.prompt_library import PromptEntry


@dataclass(frozen=True)
class SummaryRow:
    category: str
    total_prompts: int
    brand_mentioned_count: int
    mention_rate: str
    avg_sentiment_score: str
    positive_count: int
    neutral_count: int
    negative_count: int


@dataclass(frozen=True)
class CoOccurrenceRow:
    brand_or_entity: str
    cooccurrence_count: int
    relationship_type: str
    typical_position: str
    key_associations: str
    opportunity_threat: str


@dataclass(frozen=True)
class DetailedSentimentRow:
    prompt_id: str
    prompt: str
    category: str
    brand_mentioned: str
    sentiment_score: str
    sentiment_label: str
    key_observations: str


def _sentiment_label(avg: float) -> str:
    if avg >= SENTIMENT_POSITIVE_THRESHOLD:
        return "Positive"
    if avg <= SENTIMENT_NEGATIVE_THRESHOLD:
        return "Negative"
    return "Neutral"


def _mention_rate(mentioned: int, total: int) -> str:
    if total == 0:
        return "0/0 (—)"
    pct = mentioned / total
    return f"{mentioned}/{total} ({pct:.0%})"


def _compute_summary_fields(
    prompt_ids_chats: dict[str, list[LabeledChat]], brand_name: str
) -> tuple[int, int, str, str, int, int, int]:
    """Returns (total_prompts, brand_mentioned_count, mention_rate, avg_sentiment_score, pos, neu, neg)."""
    total_prompts = len(prompt_ids_chats)
    brand_mentioned_count = 0
    qualifying_sentiments: list[float] = []
    positive_count = neutral_count = negative_count = 0

    for lcs in prompt_ids_chats.values():
        mentioned_flags = [_brand_mentioned(lc.chat, brand_name) for lc in lcs]
        if any(mentioned_flags):
            brand_mentioned_count += 1

        prompt_qualifying = [
            lc.chat.sentiment
            for lc, mentioned in zip(lcs, mentioned_flags)
            if mentioned and lc.chat.sentiment is not None
        ]
        qualifying_sentiments.extend(prompt_qualifying)

        if prompt_qualifying:
            per_prompt_avg = sum(prompt_qualifying) / len(prompt_qualifying)
            if per_prompt_avg >= SENTIMENT_POSITIVE_THRESHOLD:
                positive_count += 1
            elif per_prompt_avg <= SENTIMENT_NEGATIVE_THRESHOLD:
                negative_count += 1
            else:
                neutral_count += 1

    avg_sentiment_score = (
        f"{sum(qualifying_sentiments) / len(qualifying_sentiments):.1f}"
        if qualifying_sentiments
        else "-"
    )

    return (
        total_prompts,
        brand_mentioned_count,
        _mention_rate(brand_mentioned_count, total_prompts),
        avg_sentiment_score,
        positive_count,
        neutral_count,
        negative_count,
    )


def build_sentiment_cooccurrence(
    chats: list[LabeledChat],
    prompt_library: dict[str, PromptEntry],
    brand_name: str,
) -> tuple[list[SummaryRow], list[CoOccurrenceRow], list[DetailedSentimentRow]]:
    """Returns (summary_rows, cooccurrence_rows, detailed_sentiment_rows)."""

    # Group chats by (category, prompt_id)
    by_cat_prompt: dict[str, dict[str, list[LabeledChat]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for lc in chats:
        by_cat_prompt[lc.category][lc.prompt_id].append(lc)

    # --- SUMMARY ---
    summary_rows: list[SummaryRow] = []
    all_prompt_chats: dict[str, list[LabeledChat]] = defaultdict(list)

    for category in CATEGORIES_ORDERED:
        prompt_map = by_cat_prompt.get(category, {})
        total, mentioned, rate, avg_sent, pos, neu, neg = _compute_summary_fields(
            prompt_map, brand_name
        )
        summary_rows.append(SummaryRow(
            category=category,
            total_prompts=total,
            brand_mentioned_count=mentioned,
            mention_rate=rate,
            avg_sentiment_score=avg_sent,
            positive_count=pos,
            neutral_count=neu,
            negative_count=neg,
        ))
        for prompt_id, lcs in prompt_map.items():
            all_prompt_chats[prompt_id].extend(lcs)

    overall_total, overall_mentioned, overall_rate, overall_avg, overall_pos, overall_neu, overall_neg = (
        _compute_summary_fields(all_prompt_chats, brand_name)
    )
    summary_rows.append(SummaryRow(
        category="OVERALL",
        total_prompts=overall_total,
        brand_mentioned_count=overall_mentioned,
        mention_rate=overall_rate,
        avg_sentiment_score=overall_avg,
        positive_count=overall_pos,
        neutral_count=overall_neu,
        negative_count=overall_neg,
    ))

    # --- CO-OCCURRENCE ---
    bn_lower = brand_name.lower()
    coocc_counts: dict[str, int] = {}
    coocc_first_case: dict[str, str] = {}

    for lc in chats:
        seen_in_chat: set[str] = set()
        for m in lc.chat.mentions:
            m_lower = m.lower()
            if bn_lower in m_lower or m_lower in bn_lower:
                continue
            if m_lower not in seen_in_chat:
                seen_in_chat.add(m_lower)
                if m_lower not in coocc_counts:
                    coocc_counts[m_lower] = 0
                    coocc_first_case[m_lower] = m
                coocc_counts[m_lower] += 1

    coocc_sorted = sorted(coocc_counts.items(), key=lambda x: (-x[1], x[0]))[:MAX_COOCCURRENCE_ROWS]
    cooccurrence_rows: list[CoOccurrenceRow] = [
        CoOccurrenceRow(
            brand_or_entity=coocc_first_case[m_lower],
            cooccurrence_count=cnt,
            relationship_type="",
            typical_position="",
            key_associations="",
            opportunity_threat="",
        )
        for m_lower, cnt in coocc_sorted
    ]

    # --- DETAILED SENTIMENT ---
    all_lcs_by_prompt: dict[str, list[LabeledChat]] = defaultdict(list)
    for lc in chats:
        all_lcs_by_prompt[lc.prompt_id].append(lc)

    _category_order = {cat: i for i, cat in enumerate(CATEGORIES_ORDERED)}

    def _detail_sort_key(prompt_id: str) -> tuple:
        entry = prompt_library.get(prompt_id)
        cat = entry.category if entry else ""
        return (_category_order.get(cat, 99), _prompt_sort_key(prompt_id))

    detailed_rows: list[DetailedSentimentRow] = []
    for prompt_id in sorted(all_lcs_by_prompt.keys(), key=_detail_sort_key):
        lcs = all_lcs_by_prompt[prompt_id]
        n = len(lcs)
        mentioned_flags = [_brand_mentioned(lc.chat, brand_name) for lc in lcs]
        n_mentioned = sum(mentioned_flags)

        brand_mentioned_str = (
            f"Yes ({n_mentioned}/{n})" if n_mentioned > 0 else f"No (0/{n})"
        )

        qualifying = [
            lc.chat.sentiment
            for lc, mentioned in zip(lcs, mentioned_flags)
            if mentioned and lc.chat.sentiment is not None
        ]
        if qualifying:
            avg_sent = sum(qualifying) / len(qualifying)
            sentiment_score = f"{avg_sent:.1f}"
            sentiment_label = _sentiment_label(avg_sent)
        else:
            sentiment_score = "-"
            sentiment_label = "No Sentiment"

        entry = prompt_library.get(prompt_id)
        detailed_rows.append(DetailedSentimentRow(
            prompt_id=prompt_id,
            prompt=entry.text if entry else prompt_id,
            category=entry.category if entry else "",
            brand_mentioned=brand_mentioned_str,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            key_observations="",
        ))

    return summary_rows, cooccurrence_rows, detailed_rows
