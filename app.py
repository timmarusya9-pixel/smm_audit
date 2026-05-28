```python
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# =========================================
# CONFIG
# =========================================

st.set_page_config(
    page_title="SMM Analytics Dashboard",
    layout="wide"
)

st.title("📊 Дашборд метрик SMM-анализа")

# Автообновление каждые 30 сек
st_autorefresh(interval=30000, key="refresh")

# =========================================
# LOAD DATA
# =========================================

@st.cache_data(ttl=300)
def load_data():

    url = "https://docs.google.com/spreadsheets/d/1J1vw_46jIQ9VFNQHCTUKVgKtDeT5z946kUsLvrXVESo/export?format=csv"

    df = pd.read_csv(url)

    # -------------------------------------
    # DATETIME
    # -------------------------------------

    df['started_at'] = pd.to_datetime(
        df['started_at'],
        utc=True,
        errors='coerce'
    )

    df['finished_at'] = pd.to_datetime(
        df['finished_at'],
        utc=True,
        errors='coerce'
    )

    # -------------------------------------
    # MOSCOW TIME
    # -------------------------------------

    df['started_at_msk'] = (
        df['started_at']
        .dt.tz_convert('Europe/Moscow')
        .dt.tz_localize(None)
    )

    df['finished_at_msk'] = (
        df['finished_at']
        .dt.tz_convert('Europe/Moscow')
        .dt.tz_localize(None)
    )

    # -------------------------------------
    # NUMBERS
    # -------------------------------------

    df['duration_total_sec'] = (
        df['duration_total_sec']
        .astype(str)
        .str.replace(',', '.', regex=False)
    )

    df['duration_total_sec'] = pd.to_numeric(
        df['duration_total_sec'],
        errors='coerce'
    )

    df['completeness_pct'] = pd.to_numeric(
        df['completeness_pct'],
        errors='coerce'
    )

    # -------------------------------------
    # FILL NULLS
    # -------------------------------------

    df['duration_total_sec'] = (
        df['duration_total_sec']
        .fillna(0)
    )

    df['completeness_pct'] = (
        df['completeness_pct']
        .fillna(0)
    )

    # -------------------------------------
    # EXTRA COLUMNS
    # -------------------------------------

    df['date'] = df['started_at_msk'].dt.date

    df['hour'] = (
        df['started_at_msk']
        .dt.floor('h')
    )

    return df


# =========================================
# GET DATA
# =========================================

try:
    df = load_data()

except Exception as e:
    st.error(f"Ошибка загрузки данных: {e}")
    st.stop()

if df.empty:
    st.warning("Нет данных")
    st.stop()

# =========================================
# SIDEBAR FILTERS
# =========================================

st.sidebar.header("🔍 Фильтры")

min_date = df['started_at_msk'].min().date()
max_date = df['started_at_msk'].max().date()

date_range = st.sidebar.date_input(
    "Период",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

if len(date_range) == 2:
    start_date, end_date = date_range

    mask_date = (
        (df['started_at_msk'].dt.date >= start_date)
        &
        (df['started_at_msk'].dt.date <= end_date)
    )

else:
    mask_date = pd.Series(
        [True] * len(df),
        index=df.index
    )

# STATUS FILTER

statuses = sorted(
    df['status']
    .dropna()
    .unique()
)

selected_statuses = st.sidebar.multiselect(
    "Статус",
    options=statuses,
    default=statuses
)

mask_status = df['status'].isin(selected_statuses)

# ANALYSIS ID FILTER

analysis_ids = sorted(
    df['analysis_id']
    .dropna()
    .unique()
)

selected_ids = st.sidebar.multiselect(
    "analysis_id",
    options=analysis_ids,
    default=[]
)

if selected_ids:
    mask_id = df['analysis_id'].isin(selected_ids)
else:
    mask_id = pd.Series(
        [True] * len(df),
        index=df.index
    )

# FINAL FILTER

filtered_df = df[
    mask_date &
    mask_status &
    mask_id
]

# =========================================
# KPI
# =========================================

st.subheader("📈 Ключевые показатели")

col1, col2, col3, col4, col5 = st.columns(5)

total_ops = len(filtered_df)

success_count = len(
    filtered_df[
        filtered_df['status'] == 'success'
    ]
)

fail_count = total_ops - success_count

success_pct = (
    success_count / total_ops * 100
    if total_ops > 0 else 0
)

avg_duration = filtered_df[
    'duration_total_sec'
].mean()

median_duration = filtered_df[
    'duration_total_sec'
].median()

p95_duration = filtered_df[
    'duration_total_sec'
].quantile(0.95)

avg_completeness = filtered_df[
    'completeness_pct'
].mean()

# KPI BLOCKS

col1.metric(
    "Всего операций",
    total_ops
)

col2.metric(
    "✅ Успешно",
    success_count,
    delta=f"{success_pct:.1f}%"
)

col3.metric(
    "❌ Ошибки",
    fail_count
)

col4.metric(
    "⏱ Средняя длительность",
    f"{avg_duration:.1f} сек"
)

col5.metric(
    "📌 P95",
    f"{p95_duration:.1f} сек"
)

st.caption(
    f"""
Средняя полнота данных:
{avg_completeness:.1f}%

Уникальных analysis_id:
{filtered_df['analysis_id'].nunique()}
"""
)

# =========================================
# TABLE BY ANALYSIS ID
# =========================================

st.subheader("📋 Метрики по analysis_id")

metrics_by_id = filtered_df.groupby(
    'analysis_id'
).agg(
    count=('status', 'count'),

    success_rate=(
        'status',
        lambda x:
        (x == 'success').mean() * 100
    ),

    avg_duration_sec=(
        'duration_total_sec',
        'mean'
    ),

    median_duration_sec=(
        'duration_total_sec',
        'median'
    ),

    p95_duration_sec=(
        'duration_total_sec',
        lambda x:
        x.quantile(0.95)
    ),

    avg_completeness=(
        'completeness_pct',
        'mean'
    )

).reset_index()

# ROUNDING

for col in [
    'success_rate',
    'avg_duration_sec',
    'median_duration_sec',
    'p95_duration_sec',
    'avg_completeness'
]:
    metrics_by_id[col] = (
        metrics_by_id[col]
        .round(1)
    )

st.dataframe(
    metrics_by_id,
    use_container_width=True,
    hide_index=True
)

# =========================================
# CHARTS
# =========================================

st.subheader("📉 Динамика")

group_by = st.radio(
    "Группировка",
    ["День", "Час"],
    horizontal=True
)

time_col = (
    'date'
    if group_by == "День"
    else 'hour'
)

title_suffix = (
    "по дням"
    if group_by == "День"
    else "по часам"
)

# COUNT

agg_count = (
    filtered_df
    .groupby(time_col)
    .size()
    .reset_index(name='count')
)

fig_count = px.line(
    agg_count,
    x=time_col,
    y='count',
    title=f"Количество операций {title_suffix}",
    markers=True
)

# DURATION

agg_duration = (
    filtered_df
    .groupby(time_col)['duration_total_sec']
    .mean()
    .reset_index(name='avg_duration')
)

fig_duration = px.line(
    agg_duration,
    x=time_col,
    y='avg_duration',
    title=f"Средняя длительность {title_suffix}",
    markers=True
)

graph_col1, graph_col2 = st.columns(2)

with graph_col1:
    st.plotly_chart(
        fig_count,
        use_container_width=True
    )

with graph_col2:
    st.plotly_chart(
        fig_duration,
        use_container_width=True
    )

# =========================================
# STATUS PIE
# =========================================

st.subheader("🥧 Распределение статусов")

status_counts = (
    filtered_df['status']
    .value_counts()
    .reset_index()
)

status_counts.columns = [
    'status',
    'count'
]

fig_pie = px.pie(
    status_counts,
    values='count',
    names='status',
    title="Статусы"
)

st.plotly_chart(
    fig_pie,
    use_container_width=True
)

# =========================================
# DETAILED TABLE
# =========================================

st.subheader("📄 Детальная таблица")

display_cols = [
    'analysis_id',
    'status',
    'started_at_msk',
    'finished_at_msk',
    'duration_total_sec',
    'completeness_pct'
]

display_df = filtered_df[
    display_cols
].rename(columns={
    'started_at_msk': 'начало',
    'finished_at_msk': 'окончание',
    'duration_total_sec': 'длительность',
    'completeness_pct': 'полнота'
})

st.dataframe(
    display_df,
    use_container_width=True
)

# =========================================
# DOWNLOAD CSV
# =========================================

st.subheader("💾 Скачать CSV")

csv = display_df.to_csv(
    index=False
).encode('utf-8-sig')

st.download_button(
    label="📥 Скачать",
    data=csv,
    file_name=f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)

# =========================================
# FOOTER
# =========================================

st.sidebar.markdown("---")

last_update = df['started_at'].max()

if pd.notnull(last_update):

    st.sidebar.info(
        f"""
Последнее обновление:

{last_update.strftime('%Y-%m-%d %H:%M:%S')} UTC

Часовой пояс:
МСК (UTC+3)
"""
    )
```
