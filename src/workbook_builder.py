"""Generates the output Reviews Signals .xlsx workbook from analyzer results."""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

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


def build_workbook(
    chats: list[LabeledChat],
    prompt_library: dict[str, PromptEntry],
    brand_name: str,
    date_range_str: str,
    output_path: Path | str,
) -> Path:
    """Create the output workbook at output_path. Returns the path.

    In Step 5, only 'Source Attribution Tracking' is fully populated.
    The other three tabs are created as stubs to be filled in Steps 6-8.
    """
    wb = Workbook()
    wb.remove(wb.active)

    sa_rows = build_source_attribution(chats)
    sa_ws = wb.create_sheet("Source Attribution Tracking")
    _build_source_attribution_sheet(sa_ws, sa_rows, brand_name, date_range_str)

    apr_ws = wb.create_sheet("AI Platform Response Tracking")
    _build_stub(apr_ws, "AI Platform Response Tracking", brand_name, date_range_str)

    sc_ws = wb.create_sheet("Sentiment & Co-Occurrence")
    _build_stub(sc_ws, "Sentiment & Co-Occurrence", brand_name, date_range_str)

    bm_ws = wb.create_sheet("Benchmarking")
    _build_stub(bm_ws, "Benchmarking", brand_name, date_range_str)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


def _build_stub(ws: Worksheet, title: str, brand_name: str, date_range_str: str) -> None:
    """Title bar only — used for tabs not yet implemented."""
    ws.merge_cells("A1:F1")
    cell = ws["A1"]
    cell.value = f"{title} — {brand_name} — {date_range_str}"
    cell.font = TITLE_FONT
    cell.fill = TITLE_FILL
    ws.row_dimensions[1].height = 24
    ws["A2"] = "(populated in a later step)"
    ws["A2"].font = EMPTY_SECTION_FONT


def _build_source_attribution_sheet(
    ws: Worksheet,
    rows: list[SourceRow],
    brand_name: str,
    date_range_str: str,
) -> None:
    """Layout:
    R1: title bar (merged A:F)
    R2: subsection 'Client Sources' (merged A:F)
    R3: column headers
    R4+: data rows
    """
    # Title row
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = f"Source Attribution Tracking — {brand_name} — {date_range_str}"
    title_cell.font = TITLE_FONT
    title_cell.fill = TITLE_FILL
    ws.row_dimensions[1].height = 24

    # Subsection row
    ws.merge_cells("A2:F2")
    sub_cell = ws["A2"]
    sub_cell.value = "Client Sources"
    sub_cell.font = SECTION_FONT
    sub_cell.fill = SECTION_FILL
    ws.row_dimensions[2].height = 20

    # Column headers
    headers = [
        "Domain", "Source URL", "Content Type", "Topic",
        "Platform Citations", "Citation Count",
    ]
    for col_idx, header in enumerate(headers, start=1):
        c = ws.cell(row=3, column=col_idx, value=header)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = WRAP_TOP

    # Data rows
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

    # Column widths
    widths = {1: 25, 2: 60, 3: 25, 4: 30, 5: 30, 6: 15}
    for col_idx, width in widths.items():
        ws.column_dimensions[chr(ord("A") + col_idx - 1)].width = width

    # Freeze top 3 rows
    ws.freeze_panes = "A4"
