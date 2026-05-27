import io
import tempfile
from datetime import datetime
import pandas as pd
import streamlit as st

def generate_overview_html(df: pd.DataFrame, metadata: dict, filename: str) -> str:
    """Generate an HTML report for the dataset overview."""
    # Basic info
    rows, cols = df.shape
    missing = df.isnull().sum().sum()
    mem = df.memory_usage(deep=True).sum() / 1024 / 1024
    
    html = f"""
    <html>
    <head><meta charset="utf-8"><title>Data Report: {filename}</title></head>
    <body>
    <h1>Отчёт по данным: {filename}</h1>
    <p><strong>Дата:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <hr>
    <h2>Основная информация</h2>
    <ul>
        <li>Строк: {rows:,}</li>
        <li>Столбцов: {cols}</li>
        <li>Пропусков: {missing:,}</li>
        <li>Память: {mem:.2f} MB</li>
    </ul>
    <h2>Структура колонок</h2>
    <table border="1" cellpadding="4" cellspacing="0">
    """
    # Header
    if metadata and "columns" in metadata:
        html += "<tr><th>Колонка</th><th>Тип</th><th>Непустых</th><th>Пропуски %</th><th>Уникальных</th>"
        if 'mean' in metadata['columns'][0]:
            html += "<th>Мин</th><th>Макс</th><th>Среднее</th>"
        html += "</tr>"
        for col in metadata['columns']:
            html += f"<tr><td>{col['name']}</td><td>{col['dtype']}</td><td>{col['non_null_count']}</td><td>{col['null_percent']}</td><td>{col['unique_count']}</td>"
            if 'mean' in col:
                html += f"<td>{col['min']}</td><td>{col['max']}</td><td>{col['mean']:.2f}</td>"
            html += "</tr>"
    else:
        # fallback
        for col in df.columns:
            html += f"<tr><td>{col}</td><td>{df[col].dtype}</td><td>{df[col].count()}</td><td>{(df[col].isnull().sum()/len(df)*100):.1f}%</td><td>{df[col].nunique()}</td>"
            if pd.api.types.is_numeric_dtype(df[col]):
                html += f"<td>{df[col].min()}</td><td>{df[col].max()}</td><td>{df[col].mean():.2f}</td>"
            html += "</tr>"
    
    html += """
    </table>
    <h2>Первые 10 строк данных</h2>
    """ + df.head(10).to_html() + """
    </body>
    </html>
    """
    return html

def export_chat_to_txt(chat_history: list) -> str:
    """Export chat history to plain text."""
    lines = []
    for msg in chat_history:
        if msg["role"] == "user":
            lines.append(f"Пользователь: {msg['content']}\n")
        else:
            lines.append(f"Ассистент: {msg['text']}\n")
            if msg.get("code"):
                lines.append(f"\nСгенерированный код:\n{msg['code']}\n")
            if msg.get("output"):
                lines.append(f"\nВывод:\n{msg['output']}\n")
            lines.append("-" * 50 + "\n")
    return "\n".join(lines)