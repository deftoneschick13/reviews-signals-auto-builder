# Reviews Signals Auto-Builder

A local Streamlit tool that pulls Peec AI chat data via API and produces a
populated Reviews Signals .xlsx workbook for Propellic.

## What it does

Replaces the manual data-entry portion of building a Reviews Signals workbook
for a client. Pulls ChatGPT chat data from Peec for a given project and date
range, then populates four output tabs in a downloadable .xlsx:

- Source Attribution Tracking
- AI Platform Response Tracking (ChatGPT only in v1)
- Sentiment & Co-Occurrence
- Benchmarking

## What v1 fills vs. leaves blank

| Tab | Data fields (auto) | Judgment fields (left blank) |
|---|---|---|
| Source Attribution | Domain, URL, Platform Citations, Citation Count | Content Type, Topic |
| AI Platform Response | Brand Mentioned?, Position, Sentiment Score, Sentiment, Co-Mentions, Sources/Citations, Chat Snapshot | Context Analysis, Notes |
| Sentiment & Co-Occurrence | Summary counts, Mention rates, Avg sentiment, Per-prompt sentiment scores, Co-occurrence counts | Relationship Type, Typical Position, Key Associations, Opportunity/Threat, Key Observations |
| Benchmarking | Mention Rate, Avg. Position, Avg. Sentiment per brand per category | Dominant Themes |

## Setup

```bash
git clone <repo url>
cd sentiment-builder
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set PEEC_API_KEY=<your key from app.peec.ai/api-keys>
```

## Run

```bash
source .venv/bin/activate
streamlit run main.py
```

The app opens at http://localhost:8501.

## How to use

1. In the sidebar, enter the Peec project ID for the client.
2. Enter the brand name (used for matching and column labels).
3. Pick a date range (defaults to last 30 days).
4. Upload the client's Reviews Signals workbook (must have a "Prompt Library" tab).
5. Click "Validate Configuration" to dry-check that everything connects.
6. Click "Build Workbook".
7. Download the .xlsx.

## Architecture

```
Uploaded .xlsx (Prompt Library tab)
        │
        ▼
 prompt_library.py ──► dict[prompt_id → PromptEntry]
                                  │
Peec REST API                     │
        │                         │
        ▼                         ▼
  peec_client.py ──► list[Chat] ──► matchers.py ──► list[LabeledChat]
                                                            │
                        ┌───────────────────────────────────┤
                        ▼           ▼           ▼           ▼
               source_attribution  ai_platform  sentiment   benchmarking
                    _rows         _response    _cooccurrence   _rows
                        │           │           │           │
                        └───────────┴───────────┴───────────┘
                                        │
                                        ▼
                              workbook_builder.py
                                        │
                                        ▼
                              output .xlsx (download)
```

## Tests

```bash
pytest -v
pytest --cov=src --cov-report=term-missing
```

## What's next

- v1.1: LLM-drafted Context Analysis and Notes columns (clearly marked as drafts)
- v1.2: Multi-platform AI Platform Response Tracking (currently ChatGPT only)
- v1.3: Topic/Content Type classification via rule-based + LLM hybrid
- v2: Multi-client config and team-hosted deployment

## Troubleshooting

See TROUBLESHOOTING.md.

## Built with

Python, Streamlit, openpyxl, requests, Peec REST API, Claude Code.
