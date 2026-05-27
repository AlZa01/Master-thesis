import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import sys
import os
import re
import io
from base64 import b64encode
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from export_utils import export_chat_to_txt

try:
    from yandexgpt_client import YandexGPTClient
    from municipal_utils import json_data, extract_python_code
except ImportError:
    st.error("Модули не загружены. Используются заглушки.")
    import json
    def json_data(file_path):
        with open(file_path) as f:
            return json.load(f)
    def extract_python_code(text):
        m = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
        return m.group(1) if m else None
    class YandexGPTClient:
        def __init__(self, folder_id, api_key, instruction_text):
            self.folder_id = folder_id
            self.api_key = api_key
            self.instruction_text = instruction_text
        def call_yandexgpt(self, prompt, **kwargs):
            return "```python\nprint('Заглушка YandexGPT')\n```"

st.set_page_config(page_title="Анализ с ИИ", page_icon="🤖", layout="wide")
st.header("🤖 ИИ-агент", divider="rainbow")

if "data_loaded" not in st.session_state or not st.session_state.data_loaded:
    st.warning("Сначала загрузите данные на странице 'Загрузка файла'")
    if st.button("Перейти к загрузке"):
        st.switch_page("pages/1 Загрузка файла.py")
    st.stop()

df = st.session_state.df
metadata = st.session_state.metadata

config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".accessyagpt")
if not os.path.exists(config_path):
    st.error("Файл .accessyagpt не найден.")
    st.stop()

access_data = json_data(config_path)

instruction_code = """
Ты — помощник по анализу данных. Напиши Python-код для решения вопроса пользователя.
Код выполнится автоматически. Переменная `df` уже загружена.
Верни **только код** в формате ```python ... ```. Без пояснений.
Используй print() для вывода. Для графиков — plotly (fig = px.bar(...)) или matplotlib.
"""

instruction_analysis = """
Ты — аналитик данных. Тебе передадут вопрос, код и результаты его выполнения.
Дай человеческий анализ результатов: объясни цифры, выводы, на что обратить внимание.
Обращайся "Ваше Величество". Не повторяй код, не вставляй новые блоки кода.
"""

yaclient = YandexGPTClient(
    folder_id=access_data["folder_id"],
    api_key=access_data["api_key"],
    instruction_text=instruction_code
)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ---------- Serialization ----------
def serialize_plotly_figure(fig):
    return pio.to_json(fig)

def deserialize_plotly_figure(fig_json):
    return pio.from_json(fig_json)

def serialize_matplotlib_figure(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    encoded = b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return encoded

# ---------- Code execution ----------
def execute_code_auto(code: str):
    local_vars = {
        "df": df,
        "pd": pd,
        "plt": plt,
        "sns": sns,
        "px": px,
        "go": go,
    }
    import sys
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    figures = []
    plotly_fig = None
    result_df = None
    error = None
    try:
        exec(code, {}, local_vars)
        output = sys.stdout.getvalue()
        if plt.get_fignums():
            for num in plt.get_fignums():
                figures.append(plt.figure(num))
        if "fig" in local_vars and hasattr(local_vars["fig"], "show"):
            plotly_fig = local_vars["fig"]
        if "result_df" in local_vars and isinstance(local_vars["result_df"], pd.DataFrame):
            result_df = local_vars["result_df"]
        elif "result" in local_vars and isinstance(local_vars["result"], pd.DataFrame):
            result_df = local_vars["result"]
    except Exception as e:
        error = str(e)
        output = ""
    finally:
        sys.stdout = old_stdout
    return output, figures, plotly_fig, result_df, error

# ---------- Context with metadata ----------
def build_context_with_metadata(df: pd.DataFrame, metadata: dict | None) -> str:
    context = f"Данные: {df.shape[0]} строк, {df.shape[1]} столбцов.\n"
    context += f"Столбцы: {list(df.columns)}\n"
    context += f"Типы данных: {df.dtypes.to_dict()}\n"
    if metadata and "columns" in metadata:
        context += "\nДетальная статистика по колонкам:\n"
        for col_info in metadata["columns"]:
            col_name = col_info["name"]
            context += f"- {col_name}: тип {col_info['dtype']}, "
            context += f"пропуски {col_info['null_percent']}%, уникальных {col_info['unique_count']}"
            if "min" in col_info and col_info["min"] is not None:
                context += f", мин={col_info['min']}, макс={col_info['max']}, среднее={col_info['mean']:.2f}"
            context += "\n"
    else:
        context += f"\nПервые 3 строки:\n{df.head(3).to_string()}\n"
        context += f"\nКраткая статистика:\n{df.describe().to_string()}\n"
    return context

# ---------- Sample questions ----------
def generate_dynamic_questions(df):
    questions = []
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    all_cols = df.columns.tolist()
    questions.append("Расскажи общую информацию о данных (размер, столбцы, типы)")
    questions.append("Покажи первые 5 строк данных")
    questions.append("Есть ли пропуски в данных? Если да, то в каких колонках?")
    if numeric_cols:
        first_num = numeric_cols[0]
        questions.append(f"Какая статистика (среднее, медиана, мин, макс) для колонки '{first_num}'?")
        if len(numeric_cols) >= 2:
            second_num = numeric_cols[1]
            questions.append(f"Построй scatter plot между '{first_num}' и '{second_num}'")
        if len(numeric_cols) >= 3:
            questions.append("Построй тепловую карту корреляций между числовыми переменными")
    if categorical_cols:
        first_cat = categorical_cols[0]
        if len(questions) < 5:
            questions.append(f"Сколько уникальных значений в колонке '{first_cat}'?")
    date_like = [col for col in all_cols if 'год' in col.lower() or 'year' in col.lower() or 'дата' in col.lower() or 'date' in col.lower()]
    if date_like and numeric_cols and len(questions) < 5:
        questions.append(f"Построй линейный график изменения '{numeric_cols[0]}' по годам (колонка '{date_like[0]}')")
    unique_questions = []
    for q in questions:
        if q not in unique_questions:
            unique_questions.append(q)
    return unique_questions[:5]

# ---------- Process question ----------
def process_question(question):
    context = build_context_with_metadata(df, metadata)
    prompt_code = f"""
Вопрос пользователя: {question}
Контекст данных: {context}
Напиши только код Python в блоке ```python ... ```.
"""
    with st.spinner("Генерация кода..."):
        yaclient.instruction_text = instruction_code
        response_code = yaclient.call_yandexgpt(prompt_code, temperature=0.6, max_tokens=2000)
        code = extract_python_code(response_code)
    if not code:
        st.session_state.chat_history.append({
            "role": "assistant",
            "text": "Ошибка генерации кода.",
            "code": None,
            "output": None,
            "plotly_json": None,
            "matplotlib_images": [],
            "result_df_csv": None,
            "error": "Не удалось извлечь код"
        })
        st.rerun()
        return
    with st.spinner("Выполнение кода..."):
        output, figures, plotly_fig, result_df, error = execute_code_auto(code)
    if error:
        results_summary = f"Ошибка: {error}"
    else:
        results_summary = (f"Вывод print(): {output if output else 'Нет'}\n"
                           f"Графиков matplotlib: {len(figures)}\n"
                           f"Plotly графиков: {1 if plotly_fig else 0}\n"
                           f"Датафреймов: {'Да' if result_df is not None else 'Нет'}")
    with st.spinner("ИИ анализирует результаты..."):
        yaclient.instruction_text = instruction_analysis
        prompt_analysis = (
            f"Вопрос пользователя: {question}\n\n"
            f"Сгенерированный код:\n```python\n{code}\n```\n\n"
            f"Результаты выполнения:\n{results_summary}\n\n"
            f"Содержимое вывода (если есть):\n{output if output else 'Нет вывода'}\n\n"
            "Дай подробный человеческий анализ этих результатов. Объясни, что означают цифры, "
            "какие выводы можно сделать, на что обратить внимание. Обращайся к пользователю 'Ваше Величество'."
        )
        analysis = yaclient.call_yandexgpt(prompt_analysis, temperature=0.7, max_tokens=1500)
    plotly_json = serialize_plotly_figure(plotly_fig) if plotly_fig else None
    matplotlib_images = [serialize_matplotlib_figure(fig) for fig in figures]
    result_df_csv = result_df.to_csv(index=False) if result_df is not None else None
    st.session_state.chat_history.append({
        "role": "assistant",
        "text": analysis,
        "code": code,
        "output": output,
        "plotly_json": plotly_json,
        "matplotlib_images": matplotlib_images,
        "result_df_csv": result_df_csv,
        "error": error
    })
    st.rerun()

# ---------- Display chat history ----------
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            st.markdown(msg["text"])
            if msg.get("code"):
                with st.expander("📄 Исходный код (выполнен автоматически)", expanded=False):
                    st.code(msg["code"], language="python")
            if msg.get("output") and msg["output"].strip():
                with st.expander("📤 Вывод выполнения", expanded=False):
                    st.code(msg["output"], language="text")
            if msg.get("error"):
                st.error(f"Ошибка: {msg['error']}")
            if msg.get("matplotlib_images"):
                for img_b64 in msg["matplotlib_images"]:
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        st.image(f"data:image/png;base64,{img_b64}", width=800)
            if msg.get("plotly_json"):
                fig = deserialize_plotly_figure(msg["plotly_json"])
                col1, col2, col3 = st.columns([1, 3, 1])
                with col2:
                    st.plotly_chart(fig, use_container_width=True, height=500)
            if msg.get("result_df_csv"):
                df_restored = pd.read_csv(io.StringIO(msg["result_df_csv"]))
                st.dataframe(df_restored.head(20), width="stretch")

# ---------- Chat input ----------
if question := st.chat_input("Задайте вопрос о данных..."):
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    process_question(question)
    st.rerun()

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### 💡 Примерные вопросы")
    dynamic_questions = generate_dynamic_questions(df)
    for i, q in enumerate(dynamic_questions):
        if st.button(q, key=f"sample_q_{i}", width="stretch"):
            st.session_state.chat_history.append({"role": "user", "content": q})
            process_question(q)
            st.rerun()
    st.markdown("---")
    if st.button("🗑️ Очистить чат", width="stretch"):
        st.session_state.chat_history = []
        st.rerun()
    # Export chat to TXT
    if st.button("📄 Экспорт чата (TXT)", width="stretch"):
        if len(st.session_state.chat_history) == 0:
            st.warning("Чат пуст")
        else:
            txt_content = export_chat_to_txt(st.session_state.chat_history)
            st.download_button(
                label="✅ Сохранить TXT",
                data=txt_content,
                file_name=f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                width="stretch"
            )
    st.markdown("---")
    if st.button("📁 Обзор данных", width="stretch"):
        st.switch_page("pages/2 Обзор данных.py")
    if st.button("📥 Загрузка файла", width="stretch"):
        st.switch_page("pages/1 Загрузка файла.py")
    st.markdown("---")
    superset_url = "https://analytics-gsom.pu.ru/superset/dashboard/8/?native_filters_key=PKcWWa4gvNQ"
    st.markdown(f'<a href="{superset_url}" target="_blank"><button style="width:100%; background-color:#ff4b4b; color:white; padding:0.5rem; border-radius:0.5rem; border:none; cursor:pointer;">📈 Открыть Superset</button></a>', unsafe_allow_html=True)
    st.caption("Откроется в новой вкладке")