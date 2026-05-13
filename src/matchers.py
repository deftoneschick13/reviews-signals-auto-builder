"""Labels Chat objects with prompt_id and category by matching against the Prompt Library."""

from dataclasses import dataclass

from src.peec_client import Chat
from src.prompt_library import Category, PromptEntry


@dataclass(frozen=True)
class LabeledChat:
    """A Chat that's been matched to a PromptEntry."""
    chat: Chat
    prompt_id: str
    category: Category


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def match_chats_to_prompts(
    chats: list[Chat],
    prompt_library: dict[str, PromptEntry],
) -> tuple[list[LabeledChat], list[Chat]]:
    """Match each chat to a PromptEntry by prompt text.

    Matching strategy (try in order):
    1. Exact text match (chat.prompt == entry.text)
    2. Case-insensitive + whitespace-collapsed match

    Returns (matched: list[LabeledChat], unmatched: list[Chat]).
    """
    exact: dict[str, PromptEntry] = {e.text: e for e in prompt_library.values()}
    normalized: dict[str, PromptEntry] = {
        _normalize(e.text): e for e in prompt_library.values()
    }

    matched: list[LabeledChat] = []
    unmatched: list[Chat] = []

    for chat in chats:
        entry = exact.get(chat.prompt)
        if entry is None:
            entry = normalized.get(_normalize(chat.prompt))
        if entry is not None:
            matched.append(LabeledChat(
                chat=chat,
                prompt_id=entry.prompt_id,
                category=entry.category,
            ))
        else:
            unmatched.append(chat)

    return matched, unmatched
