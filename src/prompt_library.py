"""Reads the Prompt Library tab from the uploaded Reviews Signals workbook."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

import openpyxl

Category = Literal[
    "Direct Brand Queries",
    "Category-Based Queries",
    "Comparison Queries",
]

_CATEGORIES: tuple[str, ...] = (
    "Direct Brand Queries",
    "Category-Based Queries",
    "Comparison Queries",
)

_PREFIXES: tuple[str, ...] = ("DB-", "CB-", "CO-")


@dataclass(frozen=True)
class PromptEntry:
    prompt_id: str    # "DB-01", "CB-03", "CO-02", etc.
    text: str         # the actual prompt text sent to AI engines
    category: Category
    intent: str       # may be empty string
    priority: str     # may be empty string


class PromptLibraryError(Exception):
    """Raised when the Prompt Library tab is missing or malformed."""


def _normalize_tab(name: str) -> str:
    return name.strip().lower()


def _cell_str(cell) -> str:
    return str(cell.value).strip() if cell.value is not None else ""


def read_prompt_library(workbook_path: Path | str) -> dict[str, PromptEntry]:
    """Parse the 'Prompt Library' tab of the uploaded workbook.

    Returns a dict keyed by prompt_id.

    Raises PromptLibraryError if:
    - The workbook cannot be opened.
    - No tab named 'Prompt Library' (case-insensitive, whitespace-tolerant) exists.
    - Zero entries found.
    - Duplicate prompt IDs.
    - A row has a prompt_id but no text.
    """
    log.info("read_prompt_library: opening %s", workbook_path)
    try:
        wb = openpyxl.load_workbook(workbook_path, data_only=True)
    except Exception as exc:
        log.error("read_prompt_library: cannot open workbook: %s", exc)
        raise PromptLibraryError(f"Cannot open workbook: {exc}") from exc

    target = next(
        (ws for ws in wb.worksheets if _normalize_tab(ws.title) == "prompt library"),
        None,
    )
    if target is None:
        raise PromptLibraryError("No 'Prompt Library' tab found in workbook.")

    entries: dict[str, PromptEntry] = {}
    current_category: Category | None = None

    for row_idx, row in enumerate(target.iter_rows(), start=1):
        col_a = _cell_str(row[0]) if row else ""

        if not col_a:
            continue

        col_a_lower = col_a.lower()

        # Section title rows
        category_match = next(
            (c for c in _CATEGORIES if c.lower() == col_a_lower), None
        )
        if category_match:
            current_category = category_match  # type: ignore[assignment]
            continue

        # Column-header row
        if col_a_lower == "prompt id":
            continue

        # Data rows
        if any(col_a.startswith(p) for p in _PREFIXES):
            prompt_id = col_a
            text = _cell_str(row[1]) if len(row) > 1 else ""
            if not text:
                raise PromptLibraryError(
                    f"Row {row_idx}: prompt_id '{prompt_id}' has no text."
                )
            if prompt_id in entries:
                raise PromptLibraryError(
                    f"Duplicate prompt_id '{prompt_id}' found."
                )
            if current_category is None:
                raise PromptLibraryError(
                    f"Row {row_idx}: data row found before any section header."
                )
            entries[prompt_id] = PromptEntry(
                prompt_id=prompt_id,
                text=text,
                category=current_category,
                intent=_cell_str(row[2]) if len(row) > 2 else "",
                priority=_cell_str(row[3]) if len(row) > 3 else "",
            )

    if not entries:
        raise PromptLibraryError("No prompt entries found in 'Prompt Library' tab.")

    by_cat = {}
    for e in entries.values():
        by_cat[e.category] = by_cat.get(e.category, 0) + 1
    log.info("read_prompt_library: loaded %d prompts — %s", len(entries), by_cat)
    return entries
