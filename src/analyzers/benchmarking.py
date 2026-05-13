"""Benchmarking analyzer."""

from collections import defaultdict
from dataclasses import dataclass

from src.analyzers.ai_platform_response import CATEGORIES_ORDERED, _brand_mentioned
from src.config import MAX_COMPETITORS_PER_BENCHMARK
from src.matchers import LabeledChat
from src.prompt_library import Category, PromptEntry


@dataclass(frozen=True)
class BenchmarkRow:
    brand: str
    mention_rate: str
    avg_position: str
    avg_sentiment: str
    dominant_themes: str


def _fmt_rate(n: int, total: int) -> str:
    if total == 0:
        return "0/0 (—)"
    return f"{n}/{total} ({n / total:.0%})"


def _fmt_avg(values: list[float]) -> str:
    return f"{sum(values) / len(values):.1f}" if values else "-"


def build_benchmarking(
    chats: list[LabeledChat],
    prompt_library: dict[str, PromptEntry],
    brand_name: str,
) -> dict[Category, list[BenchmarkRow]]:
    """For each category, produce rows for the focal brand and top competitors."""
    bn_lower = brand_name.lower()

    # Group chats by category
    by_category: dict[str, list[LabeledChat]] = defaultdict(list)
    for lc in chats:
        by_category[lc.category].append(lc)

    result: dict[Category, list[BenchmarkRow]] = {}

    for category in CATEGORIES_ORDERED:
        cat_chats = by_category.get(category, [])

        # Distinct prompt_ids with at least 1 chat
        prompt_ids_in_cat: set[str] = {lc.prompt_id for lc in cat_chats}
        total_prompts = len(prompt_ids_in_cat)

        # --- Focal brand ---
        focal_prompt_ids: set[str] = set()
        focal_positions: list[float] = []
        focal_sentiments: list[float] = []

        for lc in cat_chats:
            if _brand_mentioned(lc.chat, brand_name):
                focal_prompt_ids.add(lc.prompt_id)
                if lc.chat.position is not None:
                    focal_positions.append(lc.chat.position)
                if lc.chat.sentiment is not None:
                    focal_sentiments.append(lc.chat.sentiment)

        focal_row = BenchmarkRow(
            brand=brand_name,
            mention_rate=_fmt_rate(len(focal_prompt_ids), total_prompts),
            avg_position=_fmt_avg(focal_positions),
            avg_sentiment=_fmt_avg(focal_sentiments),
            dominant_themes="",
        )

        # --- Competitors (mentions list only) ---
        # Per competitor: set of prompt_ids, chat count, positions, sentiments
        comp_prompt_ids: dict[str, set[str]] = defaultdict(set)
        comp_chat_count: dict[str, int] = defaultdict(int)
        comp_positions: dict[str, list[float]] = defaultdict(list)
        comp_sentiments: dict[str, list[float]] = defaultdict(list)
        comp_first_case: dict[str, str] = {}

        for lc in cat_chats:
            seen_in_chat: set[str] = set()
            for m in lc.chat.mentions:
                m_lower = m.lower()
                if bn_lower in m_lower or m_lower in bn_lower:
                    continue
                if m_lower in seen_in_chat:
                    continue
                seen_in_chat.add(m_lower)
                if m_lower not in comp_first_case:
                    comp_first_case[m_lower] = m
                comp_prompt_ids[m_lower].add(lc.prompt_id)
                comp_chat_count[m_lower] += 1
                if lc.chat.position is not None:
                    comp_positions[m_lower].append(lc.chat.position)
                if lc.chat.sentiment is not None:
                    comp_sentiments[m_lower].append(lc.chat.sentiment)

        sorted_comps = sorted(
            comp_chat_count.keys(),
            key=lambda k: (-comp_chat_count[k], k),
        )[:MAX_COMPETITORS_PER_BENCHMARK]

        comp_rows = [
            BenchmarkRow(
                brand=comp_first_case[k],
                mention_rate=_fmt_rate(len(comp_prompt_ids[k]), total_prompts),
                avg_position=_fmt_avg(comp_positions[k]),
                avg_sentiment=_fmt_avg(comp_sentiments[k]),
                dominant_themes="",
            )
            for k in sorted_comps
        ]

        result[category] = [focal_row] + comp_rows

    return result
