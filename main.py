import tempfile
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from src.prompt_library import PromptLibraryError, read_prompt_library

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
    st.write({
        "project_id": project_id,
        "brand_name": brand_name,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "file": uploaded_file.name if uploaded_file else None,
    })
