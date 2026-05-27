import streamlit as st
import pandas as pd
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from export_utils import generate_overview_html

st.set_page_config(page_title="Обзор данных", page_icon="📁", layout="wide")
st.header('📁 Обзор данных', divider='rainbow')

if 'data_loaded' not in st.session_state or not st.session_state.data_loaded:
    st.warning("⚠️ Данные не загружены!")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("📥 Перейти к загрузке данных", type="primary", width="stretch"):
            st.switch_page("pages/1 Загрузка файла.py")
    st.stop()

df = st.session_state.df
metadata = st.session_state.metadata

st.subheader("ℹ️ Информация о загруженном файле")
info_col1, info_col2 = st.columns(2)
with info_col1:
    st.info(f"**Имя файла:**\n{st.session_state.file_name}")
with info_col2:
    st.info(f"**Размер данных:**\n{df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")

st.markdown("---")
st.subheader("Основная статистика данных")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Количество строк", f"{len(df):,}")
with col2:
    st.metric("Количество столбцов", len(df.columns))
with col3:
    st.metric("Пропущенные значения", f"{df.isnull().sum().sum():,}")
with col4:
    st.metric("Размер памяти", f"{df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")

st.markdown("---")
st.subheader("Ключевые показатели")
col_left, col_right = st.columns(2)

with col_left:
    if 'indicator_section' in df.columns:
        st.write("## Раздел")
        unique_sections = df['indicator_section'].unique()
        st.metric("Уникальных значений", len(unique_sections))
        sections_df = pd.DataFrame({'Разделы': unique_sections})
        with st.expander("Показать уникальные значения"):
            st.dataframe(sections_df, width="stretch")
    else:
        st.warning("Колонка 'indicator_section' не найдена")
    if 'indicator_name' in df.columns:
        st.write("## Индикаторы")
        st.metric("Уникальных показателей", df['indicator_name'].nunique())
        indicator_values = df['indicator_name'].unique()
        with st.expander(f"Показать уникальные значения (всего {len(indicator_values)})"):
            st.dataframe(pd.DataFrame({'indicator_name': indicator_values}), width="stretch")

with col_right:
    if 'region_name' in df.columns:
        st.write("## Регионы")
        st.metric("Уникальных регионов", df['region_name'].nunique())
        region_values = df['region_name'].unique()
        with st.expander(f"Показать уникальные значения (всего {len(region_values)})"):
            st.dataframe(pd.DataFrame({'region_name': region_values}), width="stretch")
    if 'year' in df.columns:
        st.write("## Год")
        year_col1, year_col2 = st.columns(2)
        if pd.api.types.is_numeric_dtype(df['year']):
            year_min = int(df['year'].min())
            year_max = int(df['year'].max())
            with year_col1:
                st.metric("Диапазон лет", f"{year_min} – {year_max}")
            with year_col2:
                st.metric("Уникальных годов", len(df['year'].dropna().unique()))
        else:
            with year_col1:
                st.metric("Уникальных значений", df['year'].nunique())
        with st.expander("Показать уникальные значения"):
            st.dataframe(pd.DataFrame({'year': sorted(df['year'].dropna().unique())}), width="stretch")

st.markdown("---")
st.subheader("Структура данных")
columns_info = []
for col in df.columns:
    col_info = {
        'Столбец': col,
        'Тип данных': str(df[col].dtype),
        'Непустых значений': df[col].count(),
        'Уникальных значений': df[col].nunique(),
        'Пропущенных значений': df[col].isnull().sum()
    }
    columns_info.append(col_info)
columns_df = pd.DataFrame(columns_info)
st.dataframe(columns_df, width="stretch")

st.subheader("Статистика числовых колонок")
numeric_cols = df.select_dtypes(include=['number']).columns
if len(numeric_cols) > 0:
    st.dataframe(df[numeric_cols].describe().T, width="stretch")
else:
    st.info("Числовые колонки не обнаружены")

st.subheader("Статистика категориальных колонок")
categorical_cols = df.select_dtypes(include=['object', 'category', 'string', 'bool']).columns
if len(categorical_cols) > 0:
    cat_stats = []
    for col in categorical_cols:
        mode_value = df[col].mode().iloc[0] if not df[col].mode().empty else 'N/A'
        mode_count = (df[col] == mode_value).sum() if mode_value != 'N/A' else 0
        cat_stats.append({
            'Колонка': col,
            'Мода (наиболее част.)': mode_value,
            'Частота моды': mode_count,
            'Уникальных значений': df[col].nunique()
        })
    st.dataframe(pd.DataFrame(cat_stats), width="stretch")
else:
    st.info("Категориальные колонки не обнаружены")

st.subheader("Просмотр данных")
view_option = st.radio(
    "Выберите режим просмотра:",
    ["Первые 10 строк", "Последние 10 строк", "Случайная выборка (10 строк)"],
    horizontal=True
)
if view_option == "Первые 10 строк":
    st.dataframe(df.head(10), width="stretch")
elif view_option == "Последние 10 строк":
    st.dataframe(df.tail(10), width="stretch")
else:
    st.dataframe(df.sample(10, random_state=42), width="stretch")

# ---------- EXPORT HTML ----------
st.markdown("---")

if st.button("📄 Сгенерировать HTML-отчёт", width="stretch"):
    if metadata is None:
        st.warning("Метаданные отсутствуют. Экспорт невозможен.")
    else:
        with st.spinner("Формирование отчёта... Подождите секунду"):
            html_content = generate_overview_html(df, metadata, st.session_state.file_name)

            st.download_button(
                label="📥 Скачать отчёт (HTML)",
                data=html_content.encode('utf-8'),
                file_name=f"data_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html",
                width="stretch"
            )

        
# Navigation
st.markdown("---")
st.subheader("Навигация")
col1, col2 = st.columns(2)
with col1:
    if st.button("⬅️ Назад к загрузке", width="stretch"):
        st.switch_page("pages/1 Загрузка файла.py")
with col2:
    if st.button("🤖 Анализ с ИИ", type="primary", width="stretch"):
        st.switch_page("pages/3 Анализ с ИИ.py")