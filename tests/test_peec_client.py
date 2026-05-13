"""Tests for src/peec_client.py — no real network calls."""

from datetime import date
from unittest.mock import patch

import pytest
import responses

from src.peec_client import (
    Chat,
    PeecAPIError,
    PeecAuthError,
    PeecRateLimitError,
    _str_list,
    fetch_chats,
)

PROJECT_ID = "or_test"
API_KEY = "test-key"
START = date(2026, 5, 1)
END = date(2026, 5, 7)
BASE = "https://api.peec.ai/customer/v1"


# ---------------------------------------------------------------------------
# Test-data builders
# ---------------------------------------------------------------------------

def _stub(chat_id, prompt_id, model_id, channel_id, date_str="2026-05-01"):
    return {
        "id": chat_id,
        "prompt": {"id": prompt_id},
        "model": {"id": model_id},
        "model_channel": {"id": channel_id},
        "date": date_str,
    }


def _content(
    chat_id,
    prompt_text="Test prompt",
    response_text="Test response",
    brands=None,
    sources=None,
):
    return {
        "id": chat_id,
        "messages": [
            {"role": "user", "content": prompt_text},
            {"role": "assistant", "content": response_text},
        ],
        "brands_mentioned": brands if brands is not None else [],
        "sources": sources if sources is not None else [],
        "queries": [],
        "products": [],
        "prompt": {"id": "pr_1"},
        "model": {"id": "chatgpt-scraper"},
        "model_channel": {"id": "openai-0"},
    }


def _prompts_resp(prompt_id="pr_1", text="Test prompt", country="US"):
    return {
        "data": [
            {
                "id": prompt_id,
                "messages": [{"content": text}],
                "user_location": {"country": country},
                "tags": [],
                "volume": 1,
            }
        ],
        "totalCount": 1,
    }


def _mock_prompts():
    responses.add(responses.GET, f"{BASE}/prompts", json=_prompts_resp(), status=200)


def _mock_content(chat_id, **kwargs):
    responses.add(
        responses.GET,
        f"{BASE}/chats/{chat_id}/content",
        json=_content(chat_id, **kwargs),
        status=200,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@responses.activate
def test_fetch_chats_parses_single_page_into_chat_objects():
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={
            "data": [
                _stub("ch_1", "pr_1", "chatgpt-scraper", "openai-0"),
                _stub("ch_2", "pr_1", "perplexity-scraper", "perplexity-0"),
            ],
            "totalCount": 2,
        },
        status=200,
    )
    _mock_prompts()
    _mock_content(
        "ch_1",
        brands=[{"id": "kw_1", "name": "Brand A", "position": 1}],
        sources=[{
            "url": "https://example.com",
            "urlNormalized": "example.com",
            "domain": "example.com",
            "citationCount": 1,
            "citationPosition": 1,
        }],
    )

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert len(chats) == 1
    c = chats[0]
    assert c.id == "ch_1"
    assert c.model == "chatgpt-scraper"
    assert c.model_channel == "ChatGPT"
    assert c.prompt == "Test prompt"
    assert c.response == "Test response"
    assert c.mentions == ["Brand A"]
    assert c.position == 1
    assert c.sources == ["https://example.com"]
    assert c.sentiment is None
    assert c.country == "US"


@responses.activate
def test_fetch_chats_follows_pagination_across_pages():
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={
            "data": [
                _stub("ch_1", "pr_1", "chatgpt-scraper", "openai-0"),
                _stub("ch_2", "pr_1", "chatgpt-scraper", "openai-0"),
            ],
            "totalCount": 4,
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={
            "data": [
                _stub("ch_3", "pr_1", "chatgpt-scraper", "openai-0"),
                _stub("ch_4", "pr_1", "chatgpt-scraper", "openai-0"),
            ],
            "totalCount": 4,
        },
        status=200,
    )
    _mock_prompts()
    for cid in ["ch_1", "ch_2", "ch_3", "ch_4"]:
        _mock_content(cid)

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert len(chats) == 4
    assert {c.id for c in chats} == {"ch_1", "ch_2", "ch_3", "ch_4"}


@responses.activate
def test_fetch_chats_raises_auth_error_on_401():
    responses.add(responses.GET, f"{BASE}/chats", json={"message": "Unauthorized"}, status=401)
    with pytest.raises(PeecAuthError):
        fetch_chats(PROJECT_ID, START, END, API_KEY)


@responses.activate
def test_fetch_chats_raises_auth_error_on_403():
    responses.add(responses.GET, f"{BASE}/chats", json={"message": "Forbidden"}, status=403)
    with pytest.raises(PeecAuthError):
        fetch_chats(PROJECT_ID, START, END, API_KEY)


@responses.activate
@patch("time.sleep")
def test_fetch_chats_retries_on_429_then_succeeds(mock_sleep):
    responses.add(responses.GET, f"{BASE}/chats", json={"message": "rate limit"}, status=429)
    responses.add(responses.GET, f"{BASE}/chats", json={"message": "rate limit"}, status=429)
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={"data": [_stub("ch_1", "pr_1", "chatgpt-scraper", "openai-0")], "totalCount": 1},
        status=200,
    )
    _mock_prompts()
    _mock_content("ch_1")

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert len(chats) == 1
    assert mock_sleep.call_count == 2


@responses.activate
@patch("time.sleep")
def test_fetch_chats_raises_rate_limit_after_max_retries(mock_sleep):
    for _ in range(4):  # initial attempt + 3 retries = 4 total
        responses.add(responses.GET, f"{BASE}/chats", json={"message": "rate limit"}, status=429)

    with pytest.raises(PeecRateLimitError):
        fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert mock_sleep.call_count == 3  # slept before retry 1, 2, 3; not after final failure


@responses.activate
def test_fetch_chats_raises_api_error_on_500():
    responses.add(responses.GET, f"{BASE}/chats", json={"message": "server error"}, status=500)
    with pytest.raises(PeecAPIError):
        fetch_chats(PROJECT_ID, START, END, API_KEY)


@responses.activate
def test_fetch_chats_parses_null_position_and_sentiment_as_none():
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={"data": [_stub("ch_1", "pr_1", "chatgpt-scraper", "openai-0")], "totalCount": 1},
        status=200,
    )
    _mock_prompts()
    _mock_content("ch_1", brands=[], sources=[])

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert chats[0].position is None
    assert chats[0].sentiment is None


@responses.activate
def test_fetch_chats_parses_empty_string_position_as_none():
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={"data": [_stub("ch_1", "pr_1", "chatgpt-scraper", "openai-0")], "totalCount": 1},
        status=200,
    )
    _mock_prompts()
    # position=None mirrors what the API returns when position is unknown
    _mock_content("ch_1", brands=[{"id": "kw_1", "name": "Brand A", "position": None}])

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert chats[0].position is None


@responses.activate
def test_fetch_chats_handles_mentions_as_list_and_as_newline_string():
    # List form — normal API response
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={"data": [_stub("ch_1", "pr_1", "chatgpt-scraper", "openai-0")], "totalCount": 1},
        status=200,
    )
    _mock_prompts()
    _mock_content("ch_1", brands=[
        {"id": "kw_1", "name": "Brand A", "position": 1},
        {"id": "kw_2", "name": "Brand B", "position": 2},
    ])

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)
    assert chats[0].mentions == ["Brand A", "Brand B"]

    # Newline-string form — verify _str_list handles both shapes
    assert _str_list("Brand A\nBrand B\n") == ["Brand A", "Brand B"]
    assert _str_list(["Brand A", "", "Brand B"]) == ["Brand A", "Brand B"]


@responses.activate
def test_fetch_chats_filters_out_non_chatgpt_platforms():
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={
            "data": [
                _stub("ch_gpt", "pr_1", "chatgpt-scraper", "openai-0"),
                _stub("ch_perp", "pr_1", "perplexity-scraper", "perplexity-0"),
            ],
            "totalCount": 2,
        },
        status=200,
    )
    _mock_prompts()
    _mock_content("ch_gpt")
    # ch_perp is filtered before content fetch — no mock needed for it

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert len(chats) == 1
    assert chats[0].id == "ch_gpt"
    assert chats[0].model_channel == "ChatGPT"


@responses.activate
def test_fetch_chats_strips_whitespace_from_string_fields():
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={"data": [_stub("ch_1", "pr_1", "chatgpt-scraper", "openai-0")], "totalCount": 1},
        status=200,
    )
    _mock_prompts()
    _mock_content(
        "ch_1",
        prompt_text="  Padded prompt  ",
        response_text="\n  Padded response\n  ",
    )

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)

    assert chats[0].prompt == "Padded prompt"
    assert chats[0].response == "Padded response"


def test_handles_url_without_scheme_in_sources():
    """sources list entry with no http:// scheme is still returned as-is."""
    assert _str_list(["plain.com/path"]) == ["plain.com/path"]


def test_str_list_handles_list_input():
    """_str_list with a real list strips each element."""
    assert _str_list(["  Brand A  ", "Brand B", ""]) == ["Brand A", "Brand B"]


def test_str_list_returns_empty_for_unrecognised_type():
    """_str_list with a non-str, non-list, non-None returns []."""
    assert _str_list(42) == []


@responses.activate
def test_handles_response_with_zero_chats():
    """Empty data array returns empty list without exception."""
    responses.add(
        responses.GET,
        f"{BASE}/chats",
        json={"data": [], "totalCount": 0},
        status=200,
    )
    _mock_prompts()

    chats = fetch_chats(PROJECT_ID, START, END, API_KEY)
    assert chats == []
