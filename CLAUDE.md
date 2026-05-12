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
- Data fields filled, judgment fields (Context Analysis, Notes, Topic,
  Content Type, Themes, Opportunity/Threat, etc.) left blank.
- AI Platform Response Tracking: ChatGPT only.
- Fresh xlsx output each run (does not edit the uploaded workbook).

## Module responsibilities
- src/config.py — thresholds, colors, constants
- src/peec_client.py — Peec REST API client, returns list[Chat]
- src/prompt_library.py — reads Prompt Library tab from uploaded workbook
- src/matchers.py — labels Chats with prompt_id + category
- src/analyzers/*.py — one analyzer per output tab
- src/workbook_builder.py — generates the output .xlsx
- src/styles.py — reusable openpyxl style objects
- main.py — Streamlit UI
