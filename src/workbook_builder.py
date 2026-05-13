"""Generates the output Reviews Signals .xlsx workbook from analyzer results."""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from src.analyzers.ai_platform_response import (
    CATEGORIES_ORDERED,
    PlatformResponseRow,
    build_ai_platform_response,
)
from src.analyzers.sentiment_cooccurrence import (
    CoOccurrenceRow,
    DetailedSentimentRow,
    SummaryRow,
    build_sentiment_cooccurrence,
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

    sc_summary, sc_coocc, sc_detailed = build_sentiment_cooccurrence(chats, prompt_library, brand_name)
    sc_ws = wb.create_sheet("Sentiment & Co-Occurrence")
    _build_sentiment_cooccurrence_sheet(sc_ws, sc_summary, sc_coocc, sc_detailed, brand_name, date_range_str)

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


_SC_N_COLS = 8
_SC_COL_WIDTHS = {1: 22, 2: 40, 3: 22, 4: 22, 5: 22, 6: 20, 7: 22, 8: 22}

_SC_SUMMARY_HEADERS_TPL = [
    "Category", "Total Prompts", "{brand} Mentioned", "Mention Rate",
    "Avg. Sentiment Score", "Positive", "Neutral", "Negative",
]
_SC_COOCC_HEADERS = [
    "Brand/Entity", "Co-Occurrence Count", "Relationship Type",
    "Typical Position vs {brand}", "Key Associations", "Opportunity/Threat",
]
_SC_DETAIL_HEADERS_TPL = [
    "Prompt ID", "Prompt", "Category", "{brand} Mentioned",
    "Sentiment Score", "Sentiment Label", "Key Observations",
]


def _sc_write_headers(ws: Worksheet, row: int, headers: list[str]) -> None:
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=col_idx, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = WRAP_TOP


def _build_sentiment_cooccurrence_sheet(
    ws: Worksheet,
    summary_rows: list[SummaryRow],
    coocc_rows: list[CoOccurrenceRow],
    detailed_rows: list[DetailedSentimentRow],
    brand_name: str,
    date_range_str: str,
) -> None:
    n = _SC_N_COLS
    r = 1

    # R1: title bar
    _merge_write(
        ws, r, n,
        f"Sentiment & Co-Occurrence — {brand_name} — {date_range_str}",
        TITLE_FONT, TITLE_FILL, height=24,
    )
    r += 1

    # R2: blank
    r += 1

    # --- Section 1: Sentiment Analysis Summary ---
    _merge_write(ws, r, n, "Sentiment Analysis Summary", SECTION_FONT, SECTION_FILL, height=20)
    r += 1
    summary_headers = [h.replace("{brand}", brand_name) for h in _SC_SUMMARY_HEADERS_TPL]
    _sc_write_headers(ws, r, summary_headers)
    r += 1
    for sr in summary_rows:
        values = [
            sr.category, sr.total_prompts, sr.brand_mentioned_count,
            sr.mention_rate, sr.avg_sentiment_score,
            sr.positive_count, sr.neutral_count, sr.negative_count,
        ]
        for col_idx, v in enumerate(values, start=1):
            c = ws.cell(row=r, column=col_idx, value=v)
            c.font = DATA_FONT
            c.alignment = WRAP_TOP
            c.border = THIN_GRAY
        r += 1

    r += 2  # 2 blank rows

    # --- Section 2: Co-Occurrence Analysis ---
    _merge_write(ws, r, n, "Co-Occurrence Analysis", SECTION_FONT, SECTION_FILL, height=20)
    r += 1
    coocc_headers = [h.replace("{brand}", brand_name) for h in _SC_COOCC_HEADERS]
    _sc_write_headers(ws, r, coocc_headers)
    r += 1
    if not coocc_rows:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=n)
        msg = ws.cell(row=r, column=1, value="No co-occurrence data in the selected date range.")
        msg.font = EMPTY_SECTION_FONT
        r += 1
    else:
        for cr in coocc_rows:
            values = [
                cr.brand_or_entity, cr.cooccurrence_count, cr.relationship_type,
                cr.typical_position, cr.key_associations, cr.opportunity_threat,
            ]
            for col_idx, v in enumerate(values, start=1):
                c = ws.cell(row=r, column=col_idx, value=v)
                c.font = DATA_FONT
                c.alignment = WRAP_TOP
                c.border = THIN_GRAY
            r += 1

    r += 2  # 2 blank rows

    # --- Section 3: Detailed Sentiment by Prompt ---
    _merge_write(ws, r, n, "Detailed Sentiment by Prompt", SECTION_FONT, SECTION_FILL, height=20)
    r += 1
    detail_headers = [h.replace("{brand}", brand_name) for h in _SC_DETAIL_HEADERS_TPL]
    _sc_write_headers(ws, r, detail_headers)
    r += 1
    if not detailed_rows:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=n)
        msg = ws.cell(row=r, column=1, value="No detailed sentiment data in the selected date range.")
        msg.font = EMPTY_SECTION_FONT
        r += 1
    else:
        for dr in detailed_rows:
            values = [
                dr.prompt_id, dr.prompt, dr.category, dr.brand_mentioned,
                dr.sentiment_score, dr.sentiment_label, dr.key_observations,
            ]
            for col_idx, v in enumerate(values, start=1):
                c = ws.cell(row=r, column=col_idx, value=v)
                c.font = DATA_FONT
                c.alignment = WRAP_TOP
                c.border = THIN_GRAY
            r += 1

    for col_idx, width in _SC_COL_WIDTHS.items():
        ws.column_dimensions[chr(ord("A") + col_idx - 1)].width = width


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
