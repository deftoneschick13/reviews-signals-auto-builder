# Troubleshooting

## Peec API key invalid

**Symptom:** "❌ Peec API key invalid or expired" error.

**Solutions in order:**
1. Verify your key by running: `curl -H "x-api-key: YOUR_KEY" "https://api.peec.ai/customer/v1/prompts"`. Should return JSON.
2. If 401/403: regenerate at https://app.peec.ai/api-keys. Make sure to use a Company-scoped key for multi-client use.
3. Confirm `.env` is in the project root and that `PEEC_API_KEY=...` has no quotes.
4. Restart the Streamlit app after editing `.env` (changes don't hot-reload).

---

## No chats fetched but I know there should be data

**Symptom:** "Fetched 0 chats" despite expecting data.

**Solutions:**
1. Verify the project_id is correct (check it in the Peec dashboard URL).
2. Expand the date range. AI engines don't always run daily for every prompt.
3. Check that the project's prompts are actively being tracked in Peec.
4. Inspect `logs/run.log` for any silent errors during fetch.

---

## Output workbook looks different from the reference

**Symptom:** Formatting doesn't match the Babylon template.

**Solutions:**
1. Run `pytest tests/test_workbook_builder.py::test_output_matches_reference_styling_at_key_cells -v`.
2. If that passes, the template likely changed since Step 10. Re-run Step 10 against the new reference.

---

## Streamlit won't start

**Symptom:** Error on `streamlit run main.py`.

**Solutions:**
1. Confirm the venv is activated (`which python` should show `.venv/bin/python`).
2. Reinstall: `pip install -r requirements.txt`.
3. Check Python version: `python --version` should be 3.11 or higher.
4. Port 8501 in use: `streamlit run main.py --server.port 8502`.

---

## Tests are failing

**Symptom:** `pytest` shows failures.

**Solutions:**
1. Confirm venv is activated.
2. Confirm `tests/fixtures/sample_peec_response.json` exists (created in Step 02).
3. If a test references the Babylon reference workbook, confirm it's at `tests/fixtures/reference_babylon.xlsx`.
4. Run a single failing test verbosely: `pytest tests/test_FILE.py::test_NAME -vv` to see the exact assertion that failed.

---

## Prompt Library parsing fails

**Symptom:** "❌ Prompt Library issue: [message]" on upload.

**Solutions:**
1. Confirm the tab is named exactly "Prompt Library" (case-insensitive, trailing whitespace tolerated).
2. Confirm each prompt row has both a Prompt ID (column A) AND a Prompt Text (column B).
3. Confirm prompt IDs are unique across the whole tab.
4. Confirm section headers are exactly: "Direct Brand Queries", "Category-Based Queries", "Comparison Queries".

---

## Build is slow

**Symptom:** Build takes >60 seconds.

**Solutions:**
1. Check the date range. 90+ days will fetch a lot of chats.
2. Check Peec API rate limit headers in `logs/run.log` — if hitting limits, the retry waits add up.
3. Profile: add timing prints around each phase. The bottleneck is almost always the network fetch, not the analysis.
