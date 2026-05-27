import streamlit as st
import pandas as pd
import json
import tempfile
from pathlib import Path
import sys
import os
import requests
import re
import shutil
from tavily import TavilyClient
from bs4 import BeautifulSoup
from pandas.errors import ParserError

import logging
import logging_setup

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.archive_processor import process_nested_archive

st.set_page_config(page_title="Загрузка данных", page_icon="📊", layout="wide")
st.header('📤 Загрузка файла (CSV / Parquet)', divider='rainbow')

# ---------- Constants ----------
PROJECT_ROOT = Path(__file__).parent.parent.parent
METADATA_DIR = PROJECT_ROOT / "metadata"
DATA_DIR = PROJECT_ROOT / "data"
CSV_DATA_DIR = PROJECT_ROOT / "csv_data"

METADATA_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
CSV_DATA_DIR.mkdir(exist_ok=True)

SECTIONS_MAP_PATH = METADATA_DIR / "sections_map.json"

# ---------- Metadata generation ----------
@st.cache_data(show_spinner=False)
def generate_metadata(df: pd.DataFrame, base_stem: str) -> dict:
    metadata = {
        "file_stem": base_stem,
        "shape": [len(df), len(df.columns)],
        "columns": [],
        "missing_total": int(df.isnull().sum().sum()),
        "missing_per_column": df.isnull().sum().to_dict(),
        "memory_usage_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2)
    }
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    for col in df.columns:
        col_info = {
            "name": col,
            "dtype": str(df[col].dtype),
            "non_null_count": int(df[col].count()),
            "null_count": int(df[col].isnull().sum()),
            "null_percent": round(df[col].isnull().sum() / len(df) * 100, 2),
            "unique_count": int(df[col].nunique())
        }
        if col in numeric_cols:
            col_info["min"] = float(df[col].min()) if not df[col].isnull().all() else None
            col_info["max"] = float(df[col].max()) if not df[col].isnull().all() else None
            col_info["mean"] = float(df[col].mean()) if not df[col].isnull().all() else None
            col_info["median"] = float(df[col].median()) if not df[col].isnull().all() else None
        metadata["columns"].append(col_info)
    json_path = METADATA_DIR / f"{base_stem}_metadata.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    return metadata

# ---------- Section mapping ----------
def load_sections_map() -> dict:
    if SECTIONS_MAP_PATH.exists():
        try:
            return json.loads(SECTIONS_MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def extract_section_id(filename: str) -> str | None:
    m = re.search(r"data_section(\d+)_", filename)
    return m.group(1) if m else None

def get_display_name(filename: str, sections_map: dict) -> str:
    section_id = extract_section_id(filename)
    if section_id and sections_map.get(section_id):
        return sections_map[section_id]
    return filename

# ---------- CSV reader ----------
@st.cache_data(show_spinner=False)
def read_csv_smart(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    encodings = ['utf-8', 'cp1251', 'latin1', 'iso-8859-1']
    separators = [',', ';', '\t', '|']
    for enc in encodings:
        for sep in separators:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, nrows=5)
                if len(df.columns) > 1:
                    df = pd.read_csv(path, sep=sep, encoding=enc, low_memory=False)
                    return df
            except (ParserError, UnicodeDecodeError):
                continue
    df = pd.read_csv(path, sep=None, engine='python', encoding='utf-8', errors='replace')
    return df

# ---------- Unified reader with metadata ----------
def read_table(path_str: str, base_stem_for_metadata: str = None) -> tuple[pd.DataFrame, dict | None]:
    p = Path(path_str)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        df = read_csv_smart(str(p))
        stem = base_stem_for_metadata or p.stem
        metadata = generate_metadata(df, stem)
        return df, metadata
    if suffix == ".parquet":
        df = pd.read_parquet(p)
        stem = base_stem_for_metadata or p.stem
        metadata = generate_metadata(df, stem)
        return df, metadata
    if suffix == ".zip":
        data_dict = process_nested_archive(
            main_zip_path=str(p),
            output_csv_dir=None,
            metadata_dir=str(METADATA_DIR),
            prefer_parquet=True,
            save_dataframes=False,
            return_metadata_only=False
        )
        if not data_dict:
            raise ValueError("No .parquet or .csv files found in ZIP")
        first_key = list(data_dict.keys())[0]
        df = data_dict[first_key]
        meta_path = METADATA_DIR / f"{Path(first_key).stem}_metadata.json"
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            metadata = generate_metadata(df, Path(first_key).stem)
        return df, metadata
    raise ValueError(f"Unsupported format: {suffix}")

# ---------- Save to storage ----------
def save_to_storage(source_path: str, target_name: str) -> Path:
    target_dir = DATA_DIR
    target_dir.mkdir(exist_ok=True)
    target_path = target_dir / target_name
    with open(source_path, 'rb') as src, open(target_path, 'wb') as dst:
        dst.write(src.read())
    return target_path

# ---------- Session state ----------
if "load_method" not in st.session_state:
    st.session_state.load_method = None
if "zip_path" not in st.session_state:
    st.session_state.zip_path = None
if "file_name_display" not in st.session_state:
    st.session_state.file_name_display = None

st.markdown("### Выберите способ загрузки данных")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("💾 Выбрать из хранилища", width="stretch"):
        st.session_state.load_method = "storage"
        st.session_state.zip_path = None
        st.session_state.file_name_display = None
        st.rerun()
with col2:
    if st.button("🌐 Найти разделы на tochno.st", width="stretch"):
        st.session_state.load_method = "tochno"
        st.session_state.zip_path = None
        st.session_state.file_name_display = None
        st.rerun()    
with col3:    
    if st.button("📁 Загрузить ZIP через браузер", width="stretch"):
        st.session_state.load_method = "browser"
        st.session_state.zip_path = None
        st.session_state.file_name_display = None
        st.rerun()

st.markdown("---")

# ---------- Tochno.st helpers ----------
def clean_section_name(raw_name: str) -> str:
    cleaned = re.sub(r'^[\s"\'«»()\[\]{}]+|[\s"\'«»()\[\]{}]+$', '', raw_name)
    cleaned = re.sub(r'[,\s]+$', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def parse_sections_from_text(text: str) -> dict:
    sections = {}
    pattern_double = r'(\d+)\.\s+(.+?)\s+\(\[([^\]]+)\]\(([^)]+)\),\s+\[([^\]]+)\]\(([^)]+)\)\)'
    pattern_single = r'(\d+)\.\s+(.+?)\s+\(\[([^\]]+)\]\(([^)]+)\)\)'
    for match in re.finditer(pattern_double, text, re.DOTALL):
        section_name = clean_section_name(match.group(2))
        sections[section_name] = {'full': match.group(4), 'split': match.group(6)}
    for match in re.finditer(pattern_single, text, re.DOTALL):
        section_name = clean_section_name(match.group(2))
        if section_name not in sections:
            url = match.group(4)
            if 'by_section' in url:
                sections[section_name] = {'full': url, 'split': None}
            elif 'by_indicator' in url:
                sections[section_name] = {'full': None, 'split': url}
    return sections

# ========== 1. STORAGE ==========
if st.session_state.load_method == "storage":
    st.subheader("💾 Выбор файла из хранилища")
    sections_map = load_sections_map()
    primary_dir = CSV_DATA_DIR if (CSV_DATA_DIR.exists() and any(CSV_DATA_DIR.iterdir())) else DATA_DIR
#    st.caption(f"📂 Файлы из папки: `{primary_dir}`")
    files = []
    for ext in ['.zip', '.csv', '.parquet']:
        files.extend(primary_dir.glob(f"*{ext}"))
    files = sorted(files, key=lambda p: p.name)
    if not files:
        st.info(f"📭 В папке {primary_dir} нет файлов. Загрузите архив через первые два способа.")
    else:
        display_names = []
        name_counts = {}
        for f in files:
            base_display = get_display_name(f.name, sections_map)
            if base_display in name_counts:
                name_counts[base_display] += 1
                display_name = f"{base_display} [{name_counts[base_display]}]"
            else:
                name_counts[base_display] = 1
                display_name = base_display
            display_names.append(display_name)
        selected_display = st.selectbox("Доступные файлы:", display_names)
        idx = display_names.index(selected_display)
        selected_file = files[idx]
        if st.button("✅ Выбрать этот файл", width="stretch"):
            st.session_state.zip_path = str(selected_file)
            st.session_state.file_name_display = selected_file.name
            st.rerun()

# ========== 2. BROWSER ==========
elif st.session_state.load_method == "browser":
    st.subheader("📁 Загрузка ZIP-архива")
    uploaded_file = st.file_uploader("Выберите ZIP-файл", type=['zip'], label_visibility="collapsed")
    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        saved_path = save_to_storage(tmp_path, uploaded_file.name)
        st.session_state.zip_path = str(saved_path)
        st.session_state.file_name_display = uploaded_file.name
        os.unlink(tmp_path)
        st.success(f"Файл сохранён в {DATA_DIR.name}: {uploaded_file.name}")
        st.rerun()

# ========== 2. TOCHNO.ST ==========
elif st.session_state.load_method == "tochno":
    st.subheader("🌐 Поиск разделов на tochno.st")
    tavily_available = False
    try:
        tavily_client = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])
        tavily_available = True
    except Exception as e:
        st.warning(f"Tavily не доступен ({e}), будет использован прямой парсинг.")

    if st.button("📋 Загрузить список разделов", type="primary"):
        sections = None
        target_url = "https://tochno.st/datasets/bdmo"
        if tavily_available:
            with st.spinner("🤖 Tavily извлекает данные..."):
                try:
                    extract_result = tavily_client.extract(urls=[target_url], extract_html=True)
                    if extract_result and extract_result.get("results"):
                        raw_content = extract_result["results"][0].get("raw_content", "")
                        if raw_content:
                            sections = parse_sections_from_text(raw_content)
                except Exception as e:
                    st.info(f"Ошибка Tavily: {e}")
        if not sections:
            with st.spinner("🌐 Прямой запрос..."):
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    response = requests.get(target_url, headers=headers, timeout=15)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'lxml')
                    content_div = soup.find('div', class_='data-set-view-content')
                    text = content_div.get_text() if content_div else soup.get_text()
                    sections = parse_sections_from_text(text)
                except Exception as e:
                    st.error(f"Ошибка: {e}")
        if sections:
            cleaned = {name: links for name, links in sections.items() if not re.search(r'\[.*\]\(http', name)}
            st.session_state.tavily_sections = cleaned
            st.success(f"Найдено {len(cleaned)} разделов")
        else:
            st.error("Не удалось найти разделы")

    if st.session_state.get('tavily_sections'):
        sections = st.session_state.tavily_sections
        selected_name = st.selectbox("Выберите раздел", list(sections.keys()))
        col1, col2 = st.columns(2)
        download_url = None
        with col1:
            if sections[selected_name]["full"] and st.button("📦 Скачать полный архив", width="stretch"):
                download_url = sections[selected_name]["full"]
        with col2:
            if sections[selected_name]["split"] and st.button("📊 Скачать разбивку", width="stretch"):
                download_url = sections[selected_name]["split"]
        if download_url:
            with st.spinner("Скачивание..."):
                try:
                    response = requests.get(download_url, stream=True, timeout=30)
                    response.raise_for_status()
                    filename = download_url.split('/')[-1].split('?')[0]
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
                        for chunk in response.iter_content(chunk_size=8192):
                            tmp.write(chunk)
                        tmp_path = tmp.name
                    saved_path = save_to_storage(tmp_path, filename)
                    st.session_state.zip_path = str(saved_path)
                    st.session_state.file_name_display = filename
                    os.unlink(tmp_path)
                    st.success(f"Файл сохранён в {DATA_DIR.name}: {filename}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка скачивания: {e}")


# ========== PROCESS ==========
if st.session_state.zip_path and st.session_state.file_name_display:
    zip_path = st.session_state.zip_path
    file_name_display = st.session_state.file_name_display
    try:
        p = Path(zip_path)
        if p.suffix.lower() in [".csv", ".parquet"]:
            with st.spinner("Чтение таблицы..."):
                df, metadata = read_table(str(p), base_stem_for_metadata=Path(file_name_display).stem)
            data_dict = {p.name: df}
        else:
            with st.spinner("Обработка архива..."):
                data_dict_full = process_nested_archive(
                    main_zip_path=zip_path,
                    output_csv_dir=None,
                    metadata_dir=str(METADATA_DIR),
                    prefer_parquet=True,
                    save_dataframes=False,
                    return_metadata_only=False
                )
                if len(data_dict_full) > 1:
                    selected_key = st.selectbox("В архиве несколько файлов. Выберите:", list(data_dict_full.keys()))
                    df = data_dict_full[selected_key]
                    meta_path = METADATA_DIR / f"{Path(selected_key).stem}_metadata.json"
                    if meta_path.exists():
                        with open(meta_path) as f:
                            metadata = json.load(f)
                    else:
                        metadata = generate_metadata(df, Path(selected_key).stem)
                else:
                    selected_key = list(data_dict_full.keys())[0]
                    df = data_dict_full[selected_key]
                    meta_path = METADATA_DIR / f"{Path(selected_key).stem}_metadata.json"
                    if meta_path.exists():
                        with open(meta_path) as f:
                            metadata = json.load(f)
                    else:
                        metadata = generate_metadata(df, Path(selected_key).stem)
                data_dict = data_dict_full
        if df is None:
            st.error("❌ В файле нет табличных данных")
        else:
            st.session_state.df = df
            st.session_state.metadata = metadata
            st.session_state.data_loaded = True
            st.session_state.file_name = file_name_display
            st.markdown("---")
            st.subheader("📈 Основная информация")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Строк", f"{len(df):,}")
            with col2:
                st.metric("Столбцов", len(df.columns))
            with col3:
                missing = df.isnull().sum().sum()
                st.metric("Пропуски", f"{missing:,}")
            with col4:
                mem = df.memory_usage(deep=True).sum() / 1024 / 1024
                st.metric("Память", f"{mem:.1f} MB")
            if metadata:
                st.subheader("Структура колонок")
                cols_df = pd.DataFrame(metadata['columns'])
                display_cols = ['name', 'dtype', 'non_null_count', 'null_percent', 'unique_count']
                if 'mean' in cols_df.columns:
                    display_cols.extend(['min', 'max', 'mean'])
                st.dataframe(cols_df[display_cols], width="stretch")
            else:
                st.subheader("Типы колонок")
                st.dataframe(pd.DataFrame(df.dtypes.reset_index()).rename(columns={0:'Тип', 'index':'Колонка'}), width="stretch")
            st.subheader("Первые строки")
            st.dataframe(df.head(10), width="stretch")
            st.markdown("---")
            st.subheader("Дальнейшие действия")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📁 Обзор данных", width="stretch"):
                    st.switch_page("pages/2 Обзор данных.py")
            with col2:
                if st.button("🤖 Анализ с ИИ", type="primary", width="stretch"):
                    st.switch_page("pages/3 Анализ с ИИ.py")
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")
        st.exception(e)