import os
import re
import tempfile
import traceback
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.matchers import match_chats_to_prompts
from src.peec_client import (
    PeecAPIError,
    PeecAuthError,
    PeecRateLimitError,
    fetch_chats,
)
from src.prompt_library import PromptLibraryError, read_prompt_library
from src.workbook_builder import build_workbook

load_dotenv()

st.set_page_config(page_title="Reviews Signals Auto-Builder", layout="wide")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _render_sidebar() -> dict:
    with st.sidebar:
        st.header("Configuration")
        project_id = st.text_input(
            "Peec Project ID",
            key="project_id",
            help="The Peec project ID for the client you're analyzing.",
        )
        brand_name = st.text_input(
            "Brand Name",
            key="brand_name",
            help="The focal brand. Used for matching mentions, excluding from competitor lists, and labeling columns.",
        )
        start_date = st.date_input(
            "Start Date",
            key="start_date",
            value=date.today() - timedelta(days=30),
        )
        end_date = st.date_input(
            "End Date",
            key="end_date",
            value=date.today(),
        )
        uploaded = st.file_uploader(
            "Reviews Signals Workbook (.xlsx)",
            key="workbook_upload",
            type=["xlsx"],
            help="Upload the client's Reviews Signals workbook with the Prompt Library tab filled in.",
        )
        st.divider()

        build_ready = bool(
            project_id
            and brand_name
            and st.session_state.get("prompt_library")
            and start_date < end_date
        )
        st.button("Validate Configuration", key="validate_btn")
        st.button("Build Workbook", key="build_btn", type="primary", disabled=not build_ready)

    return {
        "project_id": project_id,
        "brand_name": brand_name,
        "start_date": start_date,
        "end_date": end_date,
        "uploaded": uploaded,
    }


def _handle_upload(uploaded) -> None:
    if uploaded is None:
        return

    cache_key = uploaded.name + str(uploaded.size)
    if st.session_state.get("last_uploaded_filename") == cache_key:
        return

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = Path(tmp.name)

    try:
        library = read_prompt_library(tmp_path)
        st.session_state.prompt_library = library
        st.session_state.last_uploaded_filename = cache_key
    except PromptLibraryError as e:
        st.session_state.pop("prompt_library", None)
        st.session_state.last_uploaded_filename = cache_key
        st.session_state["_library_error"] = str(e)
    finally:
        tmp_path.unlink(missing_ok=True)


def _render_prompt_library_status() -> None:
    if "_library_error" in st.session_state:
        err = st.session_state.pop("_library_error")
        st.error(f"❌ Could not parse Prompt Library tab\n{err}")
        return

    library = st.session_state.get("prompt_library")
    if library:
        direct = sum(1 for e in library.values() if e.category == "Direct Brand Queries")
        category = sum(1 for e in library.values() if e.category == "Category-Based Queries")
        comparison = sum(1 for e in library.values() if e.category == "Comparison Queries")
        st.success(
            f"✅ Parsed Prompt Library: {len(library)} total prompts\n"
            f"- {direct} Direct Brand Queries\n"
            f"- {category} Category-Based Queries\n"
            f"- {comparison} Comparison Queries"
        )


def _get_api_key() -> str | None:
    key = os.environ.get("PEEC_API_KEY", "")
    if not key:
        st.error(
            "❌ PEEC_API_KEY not found in environment. "
            "Add it to sentiment-builder/.env and restart the app."
        )
        return None
    return key


def _handle_validate(inputs: dict) -> None:
    issues = []
    if not inputs["project_id"]:
        issues.append("Peec Project ID is required.")
    if not inputs["brand_name"]:
        issues.append("Brand Name is required.")
    if not st.session_state.get("prompt_library"):
        issues.append("Upload a Reviews Signals workbook with a valid Prompt Library tab.")
    if inputs["start_date"] >= inputs["end_date"]:
        issues.append("Start Date must be before End Date.")

    if issues:
        st.error("Issues found:\n" + "\n".join(f"• {i}" for i in issues))
        return

    api_key = _get_api_key()
    if not api_key:
        return

    with st.spinner("Checking Peec API auth…"):
        try:
            today = date.today()
            chats = fetch_chats(inputs["project_id"], today - timedelta(days=1), today, api_key)
            st.success(
                f"✅ Configuration valid. Ready to build.\n"
                f"API auth OK — {len(chats)} chats returned for the last 1 day."
            )
        except PeecAuthError:
            st.error("❌ Peec API key invalid or expired. Check sentiment-builder/.env.")
        except PeecRateLimitError:
            st.warning("⏱ Peec rate limit hit. Try again in a moment.")
        except PeecAPIError as e:
            st.error(f"❌ Peec API error: {e}")


def _handle_build(inputs: dict) -> None:
    api_key = _get_api_key()
    if not api_key:
        st.session_state.last_build_path = None
        return

    library = st.session_state.prompt_library
    brand_name = inputs["brand_name"]
    start_date = inputs["start_date"]
    end_date = inputs["end_date"]
    date_range_str = f"{start_date.isoformat()} to {end_date.isoformat()}"

    try:
        with st.spinner("Fetching chats from Peec…"):
            chats = fetch_chats(inputs["project_id"], start_date, end_date, api_key)
        st.info(f"Fetched {len(chats)} chats.")

        with st.spinner("Matching chats to prompts…"):
            matched, unmatched = match_chats_to_prompts(chats, library)
        st.info(f"Matched {len(matched)} chats ({len(unmatched)} unmatched).")
        if unmatched:
            st.warning(f"⚠ {len(unmatched)} chats could not be matched to a prompt.")
            with st.expander("Show first 10 unmatched prompts"):
                for c in unmatched[:10]:
                    st.write(c.chat.prompt[:200])

        with st.spinner("Analyzing…"):
            pass  # analyzers run inside build_workbook

        import time as _time
        timestamp = int(_time.time())
        slug = _slugify(brand_name)
        output_path = Path(f"/tmp/reviews_signals_{slug}_{timestamp}.xlsx")

        with st.spinner("Building workbook…"):
            build_workbook(matched, library, brand_name, date_range_str, output_path)

        st.session_state.last_build_path = str(output_path)
        st.success(f"✅ Workbook built: {output_path.name}")
        st.download_button(
            label="📥 Download Workbook",
            data=output_path.read_bytes(),
            file_name=output_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_{timestamp}",
        )

    except PeecAuthError:
        st.session_state.last_build_path = None
        st.error("❌ Peec API key invalid or expired. Check sentiment-builder/.env.")
    except PeecRateLimitError:
        st.session_state.last_build_path = None
        st.warning("⏱ Peec rate limit hit. Try a smaller date range or wait a minute.")
    except PeecAPIError as e:
        st.session_state.last_build_path = None
        st.error(f"❌ Peec API error: {e}")
    except PromptLibraryError as e:
        st.session_state.last_build_path = None
        st.error(f"❌ Prompt Library issue: {e}")
    except FileNotFoundError as e:
        st.session_state.last_build_path = None
        st.error(f"❌ File not found: {e}")
    except Exception:
        st.session_state.last_build_path = None
        st.error("❌ Unexpected error. See details below.")
        with st.expander("Show stack trace"):
            st.code(traceback.format_exc())


# --- Main ---

inputs = _render_sidebar()
_handle_upload(inputs["uploaded"])

st.title("Reviews Signals Auto-Builder")
st.caption("Pulls AI chat data from Peec and produces a populated Reviews Signals workbook.")

_render_prompt_library_status()

if st.session_state.get("validate_btn"):
    _handle_validate(inputs)

if st.session_state.get("build_btn"):
    _handle_build(inputs)

st.divider()
st.caption("Reviews Signals Auto-Builder · v0.1 · Built for Propellic")
