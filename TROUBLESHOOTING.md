# Troubleshooting

## App won't start / "ModuleNotFoundError"

Activate the virtual environment before running Streamlit:

```bash
source .venv/bin/activate
streamlit run main.py
```

If a package is still missing, install it:

```bash
.venv/bin/pip install -r requirements.txt
```

---

## "PEEC_API_KEY not found in environment"

Create (or edit) `sentiment-builder/.env`:

```
PEEC_API_KEY=your_key_here
```

Then restart the Streamlit app. The app reads `.env` on startup via `python-dotenv`.

---

## "Peec API key invalid or expired"

The key in `.env` is wrong or has been rotated. Obtain a fresh key from Peec and update `.env`, then restart the app.

---

## "No 'Prompt Library' tab found in workbook"

The uploaded `.xlsx` must contain a sheet tab named exactly **Prompt Library** (case-insensitive). Check that the tab exists and is not hidden.

---

## "No prompt entries found in 'Prompt Library' tab"

The tab exists but all rows were skipped. Verify that:

- Prompt IDs start with `DB-`, `CB-`, or `CO-`.
- Each prompt row appears under a section header (`Direct Brand Queries`, `Category-Based Queries`, or `Comparison Queries`).
- The prompt text column (column B) is not empty.

---

## Matched 0 chats / all chats unmatched

The prompt text in Peec must exactly match the text in the Prompt Library tab (whitespace is collapsed; case is ignored). If Peec was queried with different wording, update the Prompt Library tab to match.

---

## Date range warning (>365 days)

Fetching more than a year of data may be slow. Confirm the checkbox that appears in the UI to proceed, then click **Build Workbook** again.

---

## Output workbook looks blank / missing tabs

Check `logs/run.log` for errors. Common cause: `build_workbook` raised an exception that was caught and logged but Streamlit still showed the download button with an empty file. Rerun and watch for red error banners in the UI.

---

## Running tests

```bash
source .venv/bin/activate
pytest --cov=src --cov-report=term-missing
```

All tests should pass with ≥ 90% coverage per module and ≥ 80% overall.
