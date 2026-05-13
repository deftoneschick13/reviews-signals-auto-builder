"""Tests for src/analyzers/source_attribution.py."""

from src.analyzers.source_attribution import SourceRow, build_source_attribution
from src.matchers import LabeledChat
from src.peec_client import Chat


def _chat(chat_id: str, sources: list[str], model_channel: str = "ChatGPT") -> Chat:
    return Chat(
        id=chat_id,
        model="chatgpt-scraper",
        model_channel=model_channel,
        prompt="test prompt",
        response="test response",
        country="US",
        position=None,
        mentions=[],
        sources=sources,
        sentiment=None,
        created="2026-05-01",
    )


def _labeled(chat: Chat) -> LabeledChat:
    return LabeledChat(chat=chat, prompt_id="DB-01", category="Direct Brand Queries")


def test_source_attribution_deduplicates_urls_across_chats():
    url = "https://example.com/page"
    chats = [
        _labeled(_chat("ch_1", [url])),
        _labeled(_chat("ch_2", [url])),
        _labeled(_chat("ch_3", [url])),
    ]
    rows = build_source_attribution(chats)
    assert len(rows) == 1
    assert rows[0].source_url == url


def test_source_attribution_counts_citations_correctly():
    url_a = "https://a.com"
    url_b = "https://b.com"
    chats = [
        _labeled(_chat("ch_1", [url_a, url_b])),
        _labeled(_chat("ch_2", [url_a])),
        _labeled(_chat("ch_3", [url_a])),
    ]
    rows = build_source_attribution(chats)
    by_url = {r.source_url: r for r in rows}
    assert by_url[url_a].citation_count == 3
    assert by_url[url_b].citation_count == 1


def test_source_attribution_joins_platforms_alphabetically_unique():
    url = "https://example.com"
    chats = [
        _labeled(_chat("ch_1", [url], model_channel="Perplexity")),
        _labeled(_chat("ch_2", [url], model_channel="ChatGPT")),
        _labeled(_chat("ch_3", [url], model_channel="ChatGPT")),  # duplicate platform
    ]
    rows = build_source_attribution(chats)
    assert rows[0].platform_citations == "ChatGPT, Perplexity"


def test_source_attribution_sorts_by_count_desc_then_domain_asc():
    chats = [
        _labeled(_chat("ch_1", ["https://b.com"])),
        _labeled(_chat("ch_2", ["https://a.com", "https://b.com"])),
        _labeled(_chat("ch_3", ["https://a.com", "https://b.com"])),
    ]
    rows = build_source_attribution(chats)
    # b.com appears 3 times, a.com appears 2 times
    assert rows[0].domain == "b.com"
    assert rows[1].domain == "a.com"


def test_source_attribution_content_type_and_topic_always_empty():
    chats = [_labeled(_chat("ch_1", ["https://example.com"]))]
    rows = build_source_attribution(chats)
    assert rows[0].content_type == ""
    assert rows[0].topic == ""


def test_source_attribution_handles_urls_without_scheme():
    url = "example.com/some/path"
    chats = [_labeled(_chat("ch_1", [url]))]
    rows = build_source_attribution(chats)
    assert rows[0].domain == "example.com"


def test_source_attribution_returns_empty_list_when_no_chats():
    assert build_source_attribution([]) == []


def test_source_attribution_returns_empty_list_when_chats_have_no_sources():
    chats = [
        _labeled(_chat("ch_1", [])),
        _labeled(_chat("ch_2", [])),
    ]
    assert build_source_attribution(chats) == []


def test_source_attribution_skips_empty_string_urls_in_sources_list():
    chats = [_labeled(_chat("ch_1", ["", "https://real.com", ""]))]
    rows = build_source_attribution(chats)
    assert len(rows) == 1
    assert rows[0].source_url == "https://real.com"
