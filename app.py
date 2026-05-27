import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz

# ==================== НАСТРОЙКИ СТРАНИЦЫ ====================
st.set_page_config(page_title="Дашборд анализов", layout="wide")
st.title("📊 Дашборд метрик аналитических операций")

# ==================== ЗАГРУЗКА ДАННЫХ (с кэшированием) ====================
@st.cache_data(ttl=600)  # кэш на 10 минут
def load_data():
    # Публичный CSV-экспорт Google Sheets
    url = "https://docs.google.com/spreadsheets/d/1J1vw_46jIQ9VFNQHCTUKVgKtDeT5z946kUsLvrXVESo/export?format=csv"
    
    try:
        df = pd.read_csv(url)
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame()
    
    # 1. Преобразование дат из ISO в datetime (UTC)
    df['started_at'] = pd.to_datetime(df['started_at'], format='ISO8601')
    df['finished_at'] = pd.to_datetime(df['finished_at'], format='ISO8601')
    
    # 2. Конвертация в МСК (UTC+3)
    msk_tz = pytz.timezone('Europe/Moscow')
    df['started_at_msk'] = df['started_at'].dt.tz_localize('UTC').dt.tz_convert(msk_tz).dt.tz_localize(None)
    df['finished_at_msk'] = df['finished_at'].dt.tz_localize('UTC').dt.tz_convert(msk_tz).dt.tz_localize(None)
    
    # 3. Очистка duration_total_sec (замена запятой на точку и преобразование в float)
    df['duration_total_sec'] = df['duration_total_sec'].astype(str).str.replace(',', '.').astype(float)
    
    # 4. completeness_pct как число (можно оставить как есть, но убедимся, что нет запятых)
    df['completeness_pct'] = pd.to_numeric(df['completeness_pct'], errors='coerce').fillna(0)
    
    # 5. Добавим вспомогательные колонки для группировки
    df['date'] = df['started_at_msk'].dt.date
    df['hour'] = df['started_at_msk'].dt.floor('H')
    
    return df

df = load_data()

if df.empty:
    st.stop()

# ==================== БОКОВАЯ ПАНЕЛЬ ФИЛЬТРОВ ====================
st.sidebar.header("🔍 Фильтры")

# 1. Выбор периода по started_at_msk
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

# 2. Выбор статуса
statuses = sorted(df['status'].unique())
selected_statuses = st.sidebar.multiselect(
    "Статус",
    options=statuses,
    default=statuses
)
mask_status = df['status'].isin(selected_statuses)

# 3. Дополнительный фильтр по analysis_id (пользователь сказал "ничего больше", но сделаем опционально для удобства)
analysis_ids = sorted(df['analysis_id'].unique())
selected_ids = st.sidebar.multiselect(
    "analysis_id (опционально)",
    options=analysis_ids,
    default=[]
)
mask_id = df['analysis_id'].isin(selected_ids) if selected_ids else pd.Series([True] * len(df))

# Объединяем все фильтры
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

# Дополнительная строка метрик
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

# Форматирование
metrics_by_id['success_rate'] = metrics_by_id['success_rate'].round(1)
metrics_by_id['avg_duration_sec'] = metrics_by_id['avg_duration_sec'].round(1)
metrics_by_id['p50_duration_sec'] = metrics_by_id['p50_duration_sec'].round(1)
metrics_by_id['p95_duration_sec'] = metrics_by_id['p95_duration_sec'].round(1)
metrics_by_id['avg_completeness'] = metrics_by_id['avg_completeness'].round(1)

st.dataframe(metrics_by_id, use_container_width=True, hide_index=True)

# ==================== ГРАФИКИ ====================
st.subheader("📉 Динамика во времени")

# Выбор группировки: день или час
group_by = st.radio("Группировать по:", ["День", "Час"], horizontal=True)

if group_by == "День":
    time_col = 'date'
    title = "по дням"
else:
    time_col = 'hour'
    title = "по часам"

# Агрегация для графика количества операций
agg_count = filtered_df.groupby(time_col).size().reset_index(name='count')
# Агрегация для графика средней длительности
agg_duration = filtered_df.groupby(time_col)['duration_total_sec'].mean().reset_index(name='avg_duration')

# График 1: Количество операций
fig1 = px.line(agg_count, x=time_col, y='count', 
               title=f"Количество операций {title}",
               labels={time_col: "Время (МСК)", 'count': "Количество операций"},
               markers=True)
fig1.update_layout(xaxis_tickangle=-45)

# График 2: Средняя длительность
fig2 = px.line(agg_duration, x=time_col, y='avg_duration',
               title=f"Средняя длительность операции {title}",
               labels={time_col: "Время (МСК)", 'avg_duration': "Секунды"},
               markers=True)
fig2.update_layout(xaxis_tickangle=-45)

col_graph1, col_graph2 = st.columns(2)
with col_graph1:
    st.plotly_chart(fig1, use_container_width=True)
with col_graph2:
    st.plotly_chart(fig2, use_container_width=True)

# График распределения статусов
st.subheader("🥧 Распределение статусов")
status_counts = filtered_df['status'].value_counts().reset_index()
status_counts.columns = ['status', 'count']
fig_pie = px.pie(status_counts, values='count', names='status', title="Доля каждого статуса")
st.plotly_chart(fig_pie, use_container_width=True)

# ==================== ТАБЛИЦА С ДАННЫМИ ====================
st.subheader("📄 Детальная таблица")
# Выбираем колонки для отображения в удобном порядке
display_cols = ['analysis_id', 'status', 'started_at_msk', 'finished_at_msk', 
                'duration_total_sec', 'completeness_pct']
display_df = filtered_df[display_cols].rename(columns={
    'started_at_msk': 'начало (МСК)',
    'finished_at_msk': 'окончание (МСК)',
    'duration_total_sec': 'длительность (сек)',
    'completeness_pct': 'полнота (%)'
})
st.dataframe(display_df, use_container_width=True)

# ==================== СКАЧИВАНИЕ ДАННЫХ ====================
st.subheader("💾 Скачать отфильтрованные данные")

@st.cache_data
def convert_df_to_csv(df_to_convert):
    return df_to_convert.to_csv(index=False).encode('utf-8-sig')

csv = convert_df_to_csv(display_df)
st.download_button(
    label="📥 Скачать в CSV (текущие фильтры)",
    data=csv,
    file_name=f"filtered_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)

# ==================== ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ====================
st.sidebar.markdown("---")
st.sidebar.info(
    f"**Дата последнего обновления данных:**\n{df['started_at'].max().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
    "**Источник:** Google Sheets (публичный)\n\n"
    "**Часовой пояс графиков и таблиц:** МСК (UTC+3)"
)