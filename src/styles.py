"""Reusable openpyxl style objects."""

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from src.config import ACCENT_FILL_COLOR, BRAND_FILL_COLOR, SUBTLE_GRAY

# Fonts
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
SECTION_FONT = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
DATA_FONT = Font(name="Calibri", size=11)
EMPTY_SECTION_FONT = Font(name="Calibri", size=11, italic=True, color="888888")

# Fills
TITLE_FILL = PatternFill("solid", start_color=BRAND_FILL_COLOR, end_color=BRAND_FILL_COLOR)
SECTION_FILL = PatternFill("solid", start_color=BRAND_FILL_COLOR, end_color=BRAND_FILL_COLOR)
HEADER_FILL = PatternFill("solid", start_color=BRAND_FILL_COLOR, end_color=BRAND_FILL_COLOR)
SUBTLE_FILL = PatternFill("solid", start_color=SUBTLE_GRAY, end_color=SUBTLE_GRAY)

# Alignment
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
WRAP_CENTER = Alignment(wrap_text=True, vertical="center", horizontal="center")
CENTER = Alignment(vertical="center", horizontal="center")

# Borders
THIN_GRAY = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)
