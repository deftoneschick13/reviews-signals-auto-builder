# Reviews Signals Auto-Builder

A local Streamlit tool that pulls Peec AI chat data via API and populates a
Reviews Signals .xlsx output workbook for Propellic.

## Data flow
1. User uploads a Reviews Signals workbook with the Prompt Library tab filled in.
2. User enters Peec project ID, brand name, date range.
3. Tool fetches chats from Peec REST API.
4. Tool matches chats to prompts by exact text match (case-insensitive fallback).
5. Four analyzers produce row-level data for each output tab.
6. workbook_builder writes a fresh .xlsx and offers it for download.

## v1 scope
- Data fields filled; judgment fields (Context Analysis, Notes, Topic,
  Content Type, Themes, Opportunity/Threat, etc.) left blank.
- AI Platform Response Tracking: ChatGPT only.
- Fresh xlsx output each run (does not edit the uploaded workbook).

## Module responsibilities
- `src/config.py` — thresholds and constants (sentiment thresholds, max competitors, max co-occurrence rows)
- `src/peec_client.py` — Peec REST API client; paginates, retries on 429, filters platforms; returns `list[Chat]`
- `src/prompt_library.py` — reads Prompt Library tab from uploaded workbook; raises `PromptLibraryError` on bad input
- `src/matchers.py` — labels Chats with prompt_id + category by text match; returns matched + unmatched lists
- `src/analyzers/source_attribution.py` — builds Source Attribution rows from citation sources
- `src/analyzers/ai_platform_response.py` — builds per-platform, per-category response rows; includes brand mention detection
- `src/analyzers/sentiment_cooccurrence.py` — builds summary, co-occurrence, and detailed sentiment rows
- `src/analyzers/benchmarking.py` — builds per-category brand comparison rows (focal brand + top competitors)
- `src/workbook_builder.py` — creates and saves the .xlsx; one function per sheet
- `src/styles.py` — openpyxl Font/Fill/Border/Alignment constants matched to reference workbook
- `main.py` — Streamlit UI: sidebar config, upload handling, validate, build, download

## Decisions made during the build

**Brand mention detection uses two signals:** the `mentions` list from the Peec API (primary) plus a substring scan of the response text (fallback). This handles cases where Peec's NER misses the brand but the response text clearly references it.

**Co-mention exclusion is bidirectional:** a competitor name that contains the focal brand (or vice versa) is excluded. Prevents "Babylon Tours" from appearing as a co-mention for "Babylon".

**Prompt ID sort is numeric within prefix:** DB-2 sorts before DB-10 (natural sort), not lexicographically.

**Sentiment thresholds live in config.py:** `SENTIMENT_POSITIVE_THRESHOLD = 0.3`, `SENTIMENT_NEGATIVE_THRESHOLD = -0.3`. Adjust there if the buckets feel off in practice.

**openpyxl colors require 8-char ARGB:** 6-char hex strings get stored with alpha=0 (invisible). All color constants in `styles.py` use the full `"FFrrggbb"` format.

**Source Attribution and Sentiment & Co-Occurrence tabs have no freeze panes.** Only the AI Platform Response Tracking tab freezes at A3.

**Rate limiting:** the Peec client retries up to 3 times on HTTP 429 with exponential backoff (5s, 10s, 20s). If you hit the limit repeatedly on large date ranges, split the request or add a delay between runs.
