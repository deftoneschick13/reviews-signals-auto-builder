import streamlit as st
from datetime import date, timedelta

st.title("Reviews Signals Auto-Builder")

with st.sidebar:
    project_id = st.text_input("Peec Project ID")
    brand_name = st.text_input("Brand Name")
    start_date = st.date_input("Start Date", value=date.today() - timedelta(days=30))
    end_date = st.date_input("End Date", value=date.today())
    uploaded_file = st.file_uploader("Upload Reviews Signals Workbook", type=["xlsx"])

if st.button("Build Workbook"):
    st.write({
        "project_id": project_id,
        "brand_name": brand_name,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "file": uploaded_file.name if uploaded_file else None,
    })
