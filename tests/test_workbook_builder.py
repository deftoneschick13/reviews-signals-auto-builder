"""Tests for src/workbook_builder.py."""

import openpyxl
import pytest

from src.matchers import LabeledChat
from src.peec_client import Chat
from src.workbook_builder import build_workbook

BRAND = "Test Brand"
DATE_RANGE = "2026-04-01 to 2026-05-01"
SHEET_NAMES = [
    "Source Attribution Tracking",
    "AI Platform Response Tracking",
    "Sentiment & Co-Occurrence",
    "Benchmarking",
]


def _chat(chat_id: str, sources: list[str]) -> Chat:
    return Chat(
        id=chat_id,
        model="chatgpt-scraper",
        model_channel="ChatGPT",
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


@pytest.fixture
def built_path(tmp_path):
    chats = [_labeled(_chat("ch_1", ["https://example.com", "https://other.com"]))]
    return build_workbook(chats, {}, BRAND, DATE_RANGE, tmp_path / "output.xlsx")


@pytest.fixture
def built_wb(built_path):
    return openpyxl.load_workbook(built_path)


def test_build_workbook_creates_file_at_output_path(tmp_path):
    path = tmp_path / "output.xlsx"
    result = build_workbook([], {}, BRAND, DATE_RANGE, path)
    assert result == path
    assert path.exists()


def test_build_workbook_has_all_four_sheets_in_correct_order(built_wb):
    assert built_wb.sheetnames == SHEET_NAMES


def test_source_attribution_tab_title_in_A1(built_wb):
    ws = built_wb["Source Attribution Tracking"]
    assert "Source Attribution Tracking" in ws["A1"].value
    assert BRAND in ws["A1"].value
    assert DATE_RANGE in ws["A1"].value


def test_source_attribution_tab_subsection_in_A2(built_wb):
    ws = built_wb["Source Attribution Tracking"]
    assert ws["A2"].value == "Client Sources"


def test_source_attribution_tab_headers_in_row_3(built_wb):
    ws = built_wb["Source Attribution Tracking"]
    headers = [ws.cell(row=3, column=i).value for i in range(1, 7)]
    assert headers == [
        "Domain", "Source URL", "Content Type", "Topic",
        "Platform Citations", "Citation Count",
    ]


def test_source_attribution_tab_data_starts_at_row_4(built_wb):
    ws = built_wb["Source Attribution Tracking"]
    # Row 4 should have a domain value (data, not a header or empty)
    assert ws.cell(row=4, column=1).value is not None
    assert ws.cell(row=4, column=1).value != "Domain"


def test_source_attribution_tab_freeze_panes_at_A4(built_wb):
    ws = built_wb["Source Attribution Tracking"]
    assert str(ws.freeze_panes) == "A4"


def test_stub_tabs_have_only_title_and_placeholder(built_wb):
    for name in SHEET_NAMES[1:]:  # skip source attribution
        ws = built_wb[name]
        assert name in ws["A1"].value
        assert ws["A2"].value == "(populated in a later step)"
        # Row 3 should be empty (no headers in stubs)
        assert ws.cell(row=3, column=1).value is None


def test_build_workbook_with_empty_chats_produces_valid_file(tmp_path):
    path = tmp_path / "empty.xlsx"
    build_workbook([], {}, BRAND, DATE_RANGE, path)
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == SHEET_NAMES
    # Source attribution tab should show the "no data" message
    ws = wb["Source Attribution Tracking"]
    assert ws.cell(row=4, column=1).value == "No source data in the selected date range."
