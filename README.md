# Prototyping Web Platform for Analysis and Visualization of Municipal Data

Prototype of a web-platform on Streamlit for analysis and visualization powered with AI on the example of municipal data.

## Features

- **Data loading**:
  - ZIP-archive (CSV/Parquet inside)
  - File choice from the storage
  - Search and loading of files from the website [tochno.st](https://tochno.st)

- **Data overview**:
  - Structure overview, statistics, metadata
  - Automatic generation of HTML reports
  - Interaction with variables

- **AI-agent (YandexGPT)**:
  - Ask questions in Russian language
  - Generation and execution of code
  - Visualization with Plotly и Matplotlib
  - Friendly responses with the address "Your Majesty"

- **Export**:
  - HTML-report with statistics
  - TXT-file of chat history

## Technologies

- Python 3.9+
- Streamlit
- Pandas / NumPy
- Plotly / Matplotlib / Seaborn
- YandexGPT API
- BeautifulSoup4 / Tavily

## Note
Folder csv_data contains limited number of datasets due to their large size.
