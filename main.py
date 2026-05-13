import tempfile
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
import os

from src.prompt_library import PromptLibraryError, read_prompt_library
from src.peec_client import fetch_chats, PeecError
from src.matchers import match_chats_to_prompts
from src.workbook_builder import build_workbook

load_dotenv()

st.title("Reviews Signals Auto-Builder")

with st.sidebar:
    project_id = st.text_input("Peec Project ID")
    brand_name = st.text_input("Brand Name")
    start_date = st.date_input("Start Date", value=date.today() - timedelta(days=30))
    end_date = st.date_input("End Date", value=date.today())
    uploaded_file = st.file_uploader("Upload Reviews Signals Workbook", type=["xlsx"])

if uploaded_file is not None:
    upload_key = uploaded_file.name + str(uploaded_file.size)
    if st.session_state.get("_upload_key") != upload_key:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = Path(tmp.name)
        try:
            library = read_prompt_library(tmp_path)
            st.session_state.prompt_library = library
            st.session_state._upload_key = upload_key
        except PromptLibraryError as e:
            st.error(f"Prompt Library error: {e}")
            st.session_state.pop("prompt_library", None)
        finally:
            tmp_path.unlink(missing_ok=True)

    if "prompt_library" in st.session_state:
        library = st.session_state.prompt_library
        direct = sum(1 for e in library.values() if e.category == "Direct Brand Queries")
        category = sum(1 for e in library.values() if e.category == "Category-Based Queries")
        comparison = sum(1 for e in library.values() if e.category == "Comparison Queries")
        st.success(
            f"Found {len(library)} prompts: {direct} Direct Brand, "
            f"{category} Category-Based, {comparison} Comparison."
        )

if st.button("Build Workbook"):
    errors = []
    if not project_id:
        errors.append("Peec Project ID is required.")
    if not brand_name:
        errors.append("Brand Name is required.")
    if "prompt_library" not in st.session_state:
        errors.append("Upload a Reviews Signals workbook first.")
    if errors:
        for e in errors:
            st.error(e)
        st.stop()

    api_key = os.environ.get("PEEC_API_KEY", "")
    if not api_key:
        st.error("PEEC_API_KEY not found in .env file.")
        st.stop()

    date_range_str = f"{start_date} to {end_date}"

    with st.spinner("Fetching chats from Peec…"):
        try:
            chats = fetch_chats(project_id, start_date, end_date, api_key)
        except PeecError as e:
            st.error(f"Peec API error: {e}")
            st.stop()

    st.info(f"Fetched {len(chats)} ChatGPT chats.")

    with st.spinner("Matching chats to prompts…"):
        matched, unmatched = match_chats_to_prompts(chats, st.session_state.prompt_library)

    st.info(f"Matched {len(matched)} chats ({len(unmatched)} unmatched).")

    with st.spinner("Building workbook…"):
        output_path = Path("/tmp/output.xlsx")
        build_workbook(matched, st.session_state.prompt_library, brand_name, date_range_str, output_path)
        xlsx_bytes = output_path.read_bytes()

    st.success("Workbook ready!")
    st.download_button(
        label="Download Reviews Signals Workbook",
        data=xlsx_bytes,
        file_name=f"Reviews_Signals_{brand_name.replace(' ', '_')}_{end_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
