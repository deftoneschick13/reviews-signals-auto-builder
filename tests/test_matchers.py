"""Tests for src/matchers.py."""

from src.matchers import LabeledChat, match_chats_to_prompts
from src.peec_client import Chat
from src.prompt_library import PromptEntry


def _chat(prompt: str, chat_id: str = "ch_1") -> Chat:
    return Chat(
        id=chat_id,
        model="chatgpt-scraper",
        model_channel="ChatGPT",
        prompt=prompt,
        response="response",
        country="US",
        position=None,
        mentions=[],
        sources=[],
        sentiment=None,
        created="2026-05-01",
    )


def _entry(prompt_id: str, text: str, category="Direct Brand Queries") -> PromptEntry:
    return PromptEntry(
        prompt_id=prompt_id,
        text=text,
        category=category,  # type: ignore[arg-type]
        intent="",
        priority="",
    )


def test_exact_match():
    chat = _chat("Tell me about Brand X")
    library = {"DB-01": _entry("DB-01", "Tell me about Brand X")}

    matched, unmatched = match_chats_to_prompts([chat], library)

    assert len(matched) == 1
    assert len(unmatched) == 0
    assert matched[0].prompt_id == "DB-01"
    assert matched[0].category == "Direct Brand Queries"


def test_case_insensitive_match_after_exact_fails():
    chat = _chat("tell me about brand x")  # lowercase
    library = {"DB-01": _entry("DB-01", "Tell me about Brand X")}

    matched, unmatched = match_chats_to_prompts([chat], library)

    assert len(matched) == 1
    assert matched[0].prompt_id == "DB-01"


def test_whitespace_collapsed_match():
    chat = _chat("Tell  me   about  Brand X")  # extra spaces
    library = {"DB-01": _entry("DB-01", "Tell me about Brand X")}

    matched, unmatched = match_chats_to_prompts([chat], library)

    assert len(matched) == 1
    assert matched[0].prompt_id == "DB-01"


def test_unmatched_chats_returned_in_unmatched_list():
    chat = _chat("Completely different question")
    library = {"DB-01": _entry("DB-01", "Tell me about Brand X")}

    matched, unmatched = match_chats_to_prompts([chat], library)

    assert len(matched) == 0
    assert len(unmatched) == 1
    assert unmatched[0] is chat


def test_empty_chat_list_returns_empty_results():
    library = {"DB-01": _entry("DB-01", "Tell me about Brand X")}

    matched, unmatched = match_chats_to_prompts([], library)

    assert matched == []
    assert unmatched == []


def test_empty_prompt_library_returns_all_unmatched():
    chats = [_chat("Tell me about Brand X", "ch_1"), _chat("Another question", "ch_2")]

    matched, unmatched = match_chats_to_prompts(chats, {})

    assert len(matched) == 0
    assert len(unmatched) == 2
