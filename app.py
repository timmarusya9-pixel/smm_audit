import streamlit as st
import pandas as pd

SHEET_URL = "CSV_LINK"

df = pd.read_csv(SHEET_URL)

st.title("SMM Agent Metrics")

# KPI

success_rate = (
    (df["status"] == "success").mean() * 100
)

avg_duration = df["duration_total_sec"].mean()

avg_completeness = df["completeness_pct"].mean()

col1, col2, col3 = st.columns(3)

col1.metric(
    "Success Rate",
    f"{success_rate:.1f}%"
)

col2.metric(
    "Avg Duration",
    f"{avg_duration:.1f} sec"
)

col3.metric(
    "Completeness",
    f"{avg_completeness:.1f}%"
)

# Table

st.dataframe(df)

# Charts

st.line_chart(df["duration_total_sec"])

st.line_chart(df["completeness_pct"])