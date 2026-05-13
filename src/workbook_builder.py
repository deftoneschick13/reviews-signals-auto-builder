"""Generates the output Reviews Signals .xlsx workbook from analyzer results."""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from src.analyzers.ai_platform_response import (
    CATEGORIES_ORDERED,
    PlatformResponseRow,
    build_ai_platform_response,
)
from src.analyzers.source_attribution import SourceRow, build_source_attribution
from src.matchers import LabeledChat
from src.prompt_library import PromptEntry
from src.styles import (
    DATA_FONT,
    EMPTY_SECTION_FONT,
    HEADER_FILL,
    HEADER_FONT,
    SECTION_FILL,
    SECTION_FONT,
    THIN_GRAY,
    TITLE_FILL,
    TITLE_FONT,
    WRAP_TOP,
)

_APR_HEADERS = [
    "Prompt ID", "Prompt", "Brand Mentioned?", "Position",
    "Context Analysis", "Sentiment Score", "Sentiment",
    "Co-Mentions", "Sources/Citations", "Chat Snapshot", "Notes",
]
_APR_COL_WIDTHS = {
    1: 10, 2: 40, 3: 18, 4: 10, 5: 35, 6: 14,
    7: 12, 8: 35, 9: 50, 10: 50, 11: 25,
}
_APR_COLS = len(_APR_HEADERS)


def build_workbook(
    chats: list[LabeledChat],
    prompt_library: dict[str, PromptEntry],
    brand_name: str,
    date_range_str: str,
    output_path: Path | str,
) -> Path:
    """Create the output workbook at output_path. Returns the path."""
    wb = Workbook()
    wb.remove(wb.active)

    sa_rows = build_source_attribution(chats)
    sa_ws = wb.create_sheet("Source Attribution Tracking")
    _build_source_attribution_sheet(sa_ws, sa_rows, brand_name, date_range_str)

    apr_data = build_ai_platform_response(chats, prompt_library, brand_name)
    apr_ws = wb.create_sheet("AI Platform Response Tracking")
    _build_ai_platform_response_sheet(apr_ws, apr_data, brand_name, date_range_str)

    sc_ws = wb.create_sheet("Sentiment & Co-Occurrence")
    _build_stub(sc_ws, "Sentiment & Co-Occurrence", brand_name, date_range_str)

    bm_ws = wb.create_sheet("Benchmarking")
    _build_stub(bm_ws, "Benchmarking", brand_name, date_range_str)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


def _merge_write(ws: Worksheet, row: int, n_cols: int, value, font, fill=None, height=None):
    end_col_letter = chr(ord("A") + n_cols - 1)
    ws.merge_cells(f"A{row}:{end_col_letter}{row}")
    c = ws[f"A{row}"]
    c.value = value
    c.font = font
    if fill:
        c.fill = fill
    if height:
        ws.row_dimensions[row].height = height


def _build_stub(ws: Worksheet, title: str, brand_name: str, date_range_str: str) -> None:
    ws.merge_cells("A1:F1")
    cell = ws["A1"]
    cell.value = f"{title} — {brand_name} — {date_range_str}"
    cell.font = TITLE_FONT
    cell.fill = TITLE_FILL
    ws.row_dimensions[1].height = 24
    ws["A2"] = "(populated in a later step)"
    ws["A2"].font = EMPTY_SECTION_FONT


def _build_ai_platform_response_sheet(
    ws: Worksheet,
    data: dict,
    brand_name: str,
    date_range_str: str,
) -> None:
    n = _APR_COLS
    current_row = 1

    # R1: title bar
    _merge_write(
        ws, current_row, n,
        f"AI Platform Response Tracking — {brand_name} — {date_range_str}",
        TITLE_FONT, TITLE_FILL, height=24,
    )
    current_row += 1

    # R2: blank
    current_row += 1

    for platform in sorted(data.keys()):
        # Platform section header
        _merge_write(ws, current_row, n, f"Platform: {platform}", SECTION_FONT, SECTION_FILL, height=20)
        current_row += 1

        for category in CATEGORIES_ORDERED:
            # Sub-section header
            _merge_write(
                ws, current_row, n,
                f"Platform: {platform} | {category}",
                SECTION_FONT, SECTION_FILL, height=20,
            )
            current_row += 1

            # Column headers
            for col_idx, header in enumerate(_APR_HEADERS, start=1):
                c = ws.cell(row=current_row, column=col_idx, value=header)
                c.font = HEADER_FONT
                c.fill = HEADER_FILL
                c.alignment = WRAP_TOP
            current_row += 1

            rows: list[PlatformResponseRow] = data[platform].get(category, [])
            if not rows:
                end_col_letter = chr(ord("A") + n - 1)
                ws.merge_cells(
                    start_row=current_row, start_column=1,
                    end_row=current_row, end_column=n,
                )
                msg = ws.cell(
                    row=current_row, column=1,
                    value="No data for this category in the selected date range.",
                )
                msg.font = EMPTY_SECTION_FONT
                current_row += 1
            else:
                for pr in rows:
                    values = [
                        pr.prompt_id, pr.prompt, pr.brand_mentioned, pr.position,
                        pr.context_analysis, pr.sentiment_score, pr.sentiment_label,
                        pr.co_mentions, pr.sources_citations, pr.chat_snapshot, pr.notes,
                    ]
                    for col_idx, v in enumerate(values, start=1):
                        c = ws.cell(row=current_row, column=col_idx, value=v)
                        c.font = DATA_FONT
                        c.alignment = WRAP_TOP
                        c.border = THIN_GRAY
                    current_row += 1

            # Blank row separator
            current_row += 1

    # Column widths
    for col_idx, width in _APR_COL_WIDTHS.items():
        ws.column_dimensions[chr(ord("A") + col_idx - 1)].width = width

    ws.freeze_panes = "A3"


def _build_source_attribution_sheet(
    ws: Worksheet,
    rows: list[SourceRow],
    brand_name: str,
    date_range_str: str,
) -> None:
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = f"Source Attribution Tracking — {brand_name} — {date_range_str}"
    title_cell.font = TITLE_FONT
    title_cell.fill = TITLE_FILL
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:F2")
    sub_cell = ws["A2"]
    sub_cell.value = "Client Sources"
    sub_cell.font = SECTION_FONT
    sub_cell.fill = SECTION_FILL
    ws.row_dimensions[2].height = 20

    headers = [
        "Domain", "Source URL", "Content Type", "Topic",
        "Platform Citations", "Citation Count",
    ]
    for col_idx, header in enumerate(headers, start=1):
        c = ws.cell(row=3, column=col_idx, value=header)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = WRAP_TOP

    if not rows:
        msg = ws.cell(row=4, column=1, value="No source data in the selected date range.")
        msg.font = EMPTY_SECTION_FONT
        ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=6)
    else:
        for row_idx, sr in enumerate(rows, start=4):
            values = [
                sr.domain, sr.source_url, sr.content_type,
                sr.topic, sr.platform_citations, sr.citation_count,
            ]
            for col_idx, v in enumerate(values, start=1):
                c = ws.cell(row=row_idx, column=col_idx, value=v)
                c.font = DATA_FONT
                c.alignment = WRAP_TOP
                c.border = THIN_GRAY

    widths = {1: 25, 2: 60, 3: 25, 4: 30, 5: 30, 6: 15}
    for col_idx, width in widths.items():
        ws.column_dimensions[chr(ord("A") + col_idx - 1)].width = width

    ws.freeze_panes = "A4"
