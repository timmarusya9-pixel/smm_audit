import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Дашборд анализов", layout="wide")
st.title("📊 Дашборд метрик аналитических операций")

@st.cache_data(ttl=600)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1J1vw_46jIQ9VFNQHCTUKVgKtDeT5z946kUsLvrXVESo/export?format=csv"
    df = pd.read_csv(url)
    
    # Даты уже в UTC (aware)
    df['started_at'] = pd.to_datetime(df['started_at'], format='ISO8601', utc=True)
    df['finished_at'] = pd.to_datetime(df['finished_at'], format='ISO8601', utc=True)
    
    # Конвертируем в МСК (Europe/Moscow) и затем убираем tzinfo для удобства отображения
    df['started_at_msk'] = df['started_at'].dt.tz_convert('Europe/Moscow').dt.tz_localize(None)
    df['finished_at_msk'] = df['finished_at'].dt.tz_convert('Europe/Moscow').dt.tz_localize(None)
    
    # Очистка числовых колонок
    df['duration_total_sec'] = df['duration_total_sec'].astype(str).str.replace(',', '.').astype(float)
    df['completeness_pct'] = pd.to_numeric(df['completeness_pct'], errors='coerce').fillna(0)
    
    # Вспомогательные колонки для группировки
    df['date'] = df['started_at_msk'].dt.date
    df['hour'] = df['started_at_msk'].dt.floor('H')
    return df

df = load_data()

if df.empty:
    st.stop()

# ==================== БОКОВАЯ ПАНЕЛЬ ФИЛЬТРОВ ====================
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
    mask_date = (df['started_at_msk'].dt.date >= start_date) & (df['started_at_msk'].dt.date <= end_date)
else:
    mask_date = pd.Series([True] * len(df))

statuses = sorted(df['status'].unique())
selected_statuses = st.sidebar.multiselect("Статус", options=statuses, default=statuses)
mask_status = df['status'].isin(selected_statuses)

analysis_ids = sorted(df['analysis_id'].unique())
selected_ids = st.sidebar.multiselect("analysis_id (опционально)", options=analysis_ids, default=[])
mask_id = df['analysis_id'].isin(selected_ids) if selected_ids else pd.Series([True] * len(df))

filtered_df = df[mask_date & mask_status & mask_id]

# ==================== КЛЮЧЕВЫЕ МЕТРИКИ ====================
st.subheader("📈 Ключевые показатели")
col1, col2, col3, col4, col5 = st.columns(5)

total_ops = len(filtered_df)
success_count = len(filtered_df[filtered_df['status'] == 'success'])
fail_count = total_ops - success_count
avg_duration = filtered_df['duration_total_sec'].mean()
median_duration = filtered_df['duration_total_sec'].median()
p95_duration = filtered_df['duration_total_sec'].quantile(0.95)
avg_completeness = filtered_df['completeness_pct'].mean()

col1.metric("Всего операций", f"{total_ops:,}")
col2.metric("✅ Успешно", success_count, delta=f"{(success_count/total_ops*100 if total_ops else 0):.1f}%")
col3.metric("❌ Не успешно", fail_count)
col4.metric("Средняя длительность (сек)", f"{avg_duration:.1f}")
col5.metric("Медиана (сек) / p95", f"{median_duration:.1f} / {p95_duration:.1f}")

st.caption(f"📊 Средняя полнота данных: {avg_completeness:.1f}% | Всего уникальных analysis_id: {filtered_df['analysis_id'].nunique()}")

# ==================== МЕТРИКИ ПО КАЖДОМУ ANALYSIS_ID ====================
st.subheader("📋 Метрики по каждому analysis_id")
metrics_by_id = filtered_df.groupby('analysis_id').agg(
    count=('status', 'count'),
    success_rate=('status', lambda x: (x == 'success').mean() * 100),
    avg_duration_sec=('duration_total_sec', 'mean'),
    p50_duration_sec=('duration_total_sec', 'median'),
    p95_duration_sec=('duration_total_sec', lambda x: x.quantile(0.95)),
    avg_completeness=('completeness_pct', 'mean')
).reset_index()

metrics_by_id['success_rate'] = metrics_by_id['success_rate'].round(1)
for col in ['avg_duration_sec', 'p50_duration_sec', 'p95_duration_sec', 'avg_completeness']:
    metrics_by_id[col] = metrics_by_id[col].round(1)

st.dataframe(metrics_by_id, use_container_width=True, hide_index=True)

# ==================== ГРАФИКИ ====================
st.subheader("📉 Динамика во времени")
group_by = st.radio("Группировать по:", ["День", "Час"], horizontal=True)
time_col = 'date' if group_by == "День" else 'hour'
title = "по дням" if group_by == "День" else "по часам"

agg_count = filtered_df.groupby(time_col).size().reset_index(name='count')
agg_duration = filtered_df.groupby(time_col)['duration_total_sec'].mean().reset_index(name='avg_duration')

fig1 = px.line(agg_count, x=time_col, y='count', title=f"Количество операций {title}",
               labels={time_col: "Время (МСК)", 'count': "Количество операций"}, markers=True)
fig2 = px.line(agg_duration, x=time_col, y='avg_duration', title=f"Средняя длительность операции {title}",
               labels={time_col: "Время (МСК)", 'avg_duration': "Секунды"}, markers=True)

col_graph1, col_graph2 = st.columns(2)
with col_graph1:
    st.plotly_chart(fig1, use_container_width=True)
with col_graph2:
    st.plotly_chart(fig2, use_container_width=True)

st.subheader("🥧 Распределение статусов")
status_counts = filtered_df['status'].value_counts().reset_index()
status_counts.columns = ['status', 'count']
fig_pie = px.pie(status_counts, values='count', names='status', title="Доля каждого статуса")
st.plotly_chart(fig_pie, use_container_width=True)

# ==================== ТАБЛИЦА И СКАЧИВАНИЕ ====================
st.subheader("📄 Детальная таблица")
display_cols = ['analysis_id', 'status', 'started_at_msk', 'finished_at_msk', 'duration_total_sec', 'completeness_pct']
display_df = filtered_df[display_cols].rename(columns={
    'started_at_msk': 'начало (МСК)',
    'finished_at_msk': 'окончание (МСК)',
    'duration_total_sec': 'длительность (сек)',
    'completeness_pct': 'полнота (%)'
})
st.dataframe(display_df, use_container_width=True)

st.subheader("💾 Скачать отфильтрованные данные")
csv = display_df.to_csv(index=False).encode('utf-8-sig')
st.download_button(
    label="📥 Скачать в CSV",
    data=csv,
    file_name=f"filtered_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)

st.sidebar.markdown("---")
st.sidebar.info(
    f"**Последнее обновление данных:** {df['started_at'].max().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
    "**Часовой пояс:** МСК (UTC+3)"
)
