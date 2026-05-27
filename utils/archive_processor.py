#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Универсальный процессор ZIP-архивов и плоских файлов (CSV/Parquet).
Максимальная устойчивость к повреждённым и нестандартным ZIP.
"""
import zipfile
import pandas as pd
import json
from pathlib import Path
from io import BytesIO
from typing import Dict, Optional, Tuple, Union, List
import warnings
import os
import tempfile
import shutil
import subprocess
warnings.filterwarnings('ignore')

# ------------------------------------------------------------
# 1. Фильтрация macOS-мусора
# ------------------------------------------------------------
def filter_macos_files(file_list: List[str]) -> List[str]:
    return [f for f in file_list 
            if not ('__MACOSX' in f or f.startswith('._') or f.startswith('.DS_Store'))]

# ------------------------------------------------------------
# 2. Автоопределение CSV (разделитель + кодировка)
# ------------------------------------------------------------
def detect_csv_sep_and_encoding(content: bytes) -> Tuple[str, str]:
    encodings = ['utf-8', 'cp1251', 'latin-1', 'utf-16']
    separators = [';', ',', '\t', '|']
    
    best_enc = 'utf-8'
    for enc in encodings:
        try:
            sample = content[:4096].decode(enc)
            best_enc = enc
            break
        except:
            continue
    else:
        sample = content[:4096].decode('utf-8', errors='ignore')
    
    first_line = sample.split('\n')[0]
    sep_counts = {sep: first_line.count(sep) for sep in separators}
    best_sep = max(sep_counts, key=sep_counts.get) or ';'
    return best_sep, best_enc

def read_csv_from_stream(stream: BytesIO) -> pd.DataFrame:
    content = stream.read()
    sep, encoding = detect_csv_sep_and_encoding(content)
    try:
        return pd.read_csv(BytesIO(content), sep=sep, encoding=encoding)
    except:
        stream.seek(0)
        return pd.read_csv(stream, sep=None, engine='python')

# ------------------------------------------------------------
# 3. Чтение Parquet из потока
# ------------------------------------------------------------
def read_parquet_from_stream(stream: BytesIO) -> pd.DataFrame:
    return pd.read_parquet(stream)

# ------------------------------------------------------------
# 4. Извлечение метаданных из DataFrame
# ------------------------------------------------------------
def extract_metadata_from_df(df: pd.DataFrame, source_info: dict) -> dict:
    metadata = {
        'source': source_info,
        'basic_info': {
            'rows': len(df),
            'columns': len(df.columns),
            'memory_bytes': int(df.memory_usage(deep=True).sum()),
            'memory_mb': round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
            'missing_cells': int(df.isnull().sum().sum()),
            'duplicated_rows': int(df.duplicated().sum()),
            'total_cells': len(df) * len(df.columns),
            'missing_percent': round(df.isnull().sum().sum() / (len(df) * len(df.columns)) * 100, 2)
        },
        'columns': []
    }
    
    for col in df.columns:
        col_info = {
            'name': col,
            'dtype': str(df[col].dtype),
            'non_null_count': int(df[col].count()),
            'null_count': int(df[col].isnull().sum()),
            'null_percent': round(float(df[col].isnull().mean() * 100), 2),
            'unique_count': int(df[col].nunique())
        }
        if pd.api.types.is_numeric_dtype(df[col]):
            col_info['min'] = float(df[col].min()) if not pd.isna(df[col].min()) else None
            col_info['max'] = float(df[col].max()) if not pd.isna(df[col].max()) else None
            col_info['mean'] = float(df[col].mean()) if not pd.isna(df[col].mean()) else None
            col_info['std'] = float(df[col].std()) if not pd.isna(df[col].std()) else None
            col_info['quantiles'] = {
                '25%': float(df[col].quantile(0.25)),
                '50%': float(df[col].quantile(0.5)),
                '75%': float(df[col].quantile(0.75))
            }
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            col_info['min'] = df[col].min().isoformat() if not pd.isna(df[col].min()) else None
            col_info['max'] = df[col].max().isoformat() if not pd.isna(df[col].max()) else None
        else:
            top = df[col].value_counts().head(5).to_dict()
            col_info['top_values'] = {str(k): int(v) for k, v in top.items()}
        metadata['columns'].append(col_info)
    return metadata

# ------------------------------------------------------------
# 5. Сохранение метаданных в JSON
# ------------------------------------------------------------
def save_metadata_to_json(metadata: dict, output_dir: Union[str, Path], base_filename: str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = base_filename.replace('.zip', '').replace('.parquet', '').replace('.csv', '')
    safe_name = safe_name.replace('/', '_').replace('\\', '_').replace(':', '_')
    json_path = output_dir / f"{safe_name}_metadata.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    return json_path

# ------------------------------------------------------------
# 6. Вспомогательная функция для обработки списка файлов
# ------------------------------------------------------------
def _process_files(files: List[Path], source_archive_name: str, nested_name: Optional[str],
                   metadata_dir: Optional[Path], output_csv_dir: Optional[Path],
                   save_dataframes: bool, return_metadata_only: bool, prefer_parquet: bool) -> Dict:
    result = {}
    data_files = []
    for f in files:
        if prefer_parquet and f.suffix.lower() == '.parquet':
            data_files.append(f)
        elif f.suffix.lower() == '.csv':
            data_files.append(f)
    
    for f in data_files:
        try:
            if f.suffix.lower() == '.parquet':
                df = pd.read_parquet(f)
                ftype = 'parquet'
            else:
                with open(f, 'rb') as fp:
                    df = read_csv_from_stream(BytesIO(fp.read()))
                ftype = 'csv'
            
            src = {
                'main_archive': source_archive_name,
                'nested_archive': nested_name,
                'file_name': f.name,
                'file_type': ftype,
                'rows': len(df),
                'columns': len(df.columns)
            }
            metadata = extract_metadata_from_df(df, src)
            
            if metadata_dir:
                base = f"{Path(source_archive_name).stem}_{f.stem}" if not nested_name else f"{Path(nested_name).stem}_{f.stem}"
                save_metadata_to_json(metadata, metadata_dir, base)
            
            if save_dataframes and output_csv_dir:
                output_csv_dir.mkdir(parents=True, exist_ok=True)
                out_stem = f"{Path(source_archive_name).stem}_{f.stem}" if not nested_name else f"{Path(nested_name).stem}_{f.stem}"
                if ftype == 'parquet':
                    df.to_parquet(output_csv_dir / f"{out_stem}.parquet", index=False)
                else:
                    df.to_csv(output_csv_dir / f"{out_stem}.csv", index=False, sep=';', encoding='utf-8')
            
            key = f"{nested_name + '/' if nested_name else ''}{f.name}"
            result[key] = metadata if return_metadata_only else df
        except Exception as e:
            print(f"  ⚠️ Ошибка обработки {f}: {e}")
            continue
    return result

# ------------------------------------------------------------
# 7. Основная функция
# ------------------------------------------------------------
def process_nested_archive(
    main_zip_path: Union[str, Path],
    output_csv_dir: Optional[Union[str, Path]] = None,
    metadata_dir: Optional[Union[str, Path]] = "../metadata",
    prefer_parquet: bool = True,
    save_dataframes: bool = False,
    return_metadata_only: bool = False
) -> Dict[str, Union[pd.DataFrame, dict]]:
    """
    Универсальная обработка файла:
    - Если это ZIP (сигнатура PK), пытается открыть стандартным zipfile,
      при ошибке переходит к внешним распаковщикам.
    - Если не ZIP, читает как CSV/Parquet.
    """
    path = Path(main_zip_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    
    # Подготовка папок
    if metadata_dir:
        metadata_dir = Path(metadata_dir)
        metadata_dir.mkdir(parents=True, exist_ok=True)
    if output_csv_dir:
        output_csv_dir = Path(output_csv_dir)
    
    # --------------------------------------------------------
    # Проверка сигнатуры
    # --------------------------------------------------------
    with open(path, 'rb') as f:
        header = f.read(4)
    
    is_zip_signature = header.startswith(b'PK')
    
    # --------------------------------------------------------
    # Если это ZIP, пробуем разные методы
    # --------------------------------------------------------
    if is_zip_signature:
        # Метод 1: стандартный zipfile
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                # ... код обработки ZIP с вложенными архивами ...
                all_items = zf.namelist()
                filtered_items = filter_macos_files(all_items)
                nested_zips = [f for f in filtered_items if f.lower().endswith('.zip')]
                
                if nested_zips:
                    # Есть вложенные ZIP
                    result = {}
                    for nested_name in nested_zips:
                        with zf.open(nested_name) as nb:
                            nested_data = BytesIO(nb.read())
                            try:
                                with zipfile.ZipFile(nested_data, 'r') as nz:
                                    nested_files = nz.namelist()
                                    nested_filtered = filter_macos_files(nested_files)
                                    for fname in nested_filtered:
                                        if (prefer_parquet and fname.lower().endswith('.parquet')) or fname.lower().endswith('.csv'):
                                            with nz.open(fname) as dfh:
                                                stream = BytesIO(dfh.read())
                                                if fname.lower().endswith('.parquet'):
                                                    df = read_parquet_from_stream(stream)
                                                    ftype = 'parquet'
                                                else:
                                                    df = read_csv_from_stream(stream)
                                                    ftype = 'csv'
                                                src = {
                                                    'main_archive': path.name,
                                                    'nested_archive': nested_name,
                                                    'file_name': fname,
                                                    'file_type': ftype,
                                                    'rows': len(df),
                                                    'columns': len(df.columns)
                                                }
                                                meta = extract_metadata_from_df(df, src)
                                                if metadata_dir:
                                                    base = f"{Path(nested_name).stem}_{Path(fname).stem}"
                                                    save_metadata_to_json(meta, metadata_dir, base)
                                                if save_dataframes and output_csv_dir:
                                                    out_stem = f"{Path(nested_name).stem}_{Path(fname).stem}"
                                                    if ftype == 'parquet':
                                                        df.to_parquet(output_csv_dir / f"{out_stem}.parquet", index=False)
                                                    else:
                                                        df.to_csv(output_csv_dir / f"{out_stem}.csv", index=False, sep=';', encoding='utf-8')
                                                key = f"{nested_name}/{fname}"
                                                result[key] = meta if return_metadata_only else df
                            except zipfile.BadZipFile:
                                print(f"  ⚠️ Вложенный ZIP повреждён: {nested_name}")
                                continue
                    if result:
                        return result
                else:
                    # Простой ZIP
                    result = {}
                    if prefer_parquet:
                        data_files = [f for f in filtered_items if f.lower().endswith('.parquet')]
                        if not data_files:
                            data_files = [f for f in filtered_items if f.lower().endswith('.csv')]
                    else:
                        data_files = [f for f in filtered_items if f.lower().endswith('.csv')]
                    
                    for fname in data_files:
                        with zf.open(fname) as dfh:
                            stream = BytesIO(dfh.read())
                            if fname.lower().endswith('.parquet'):
                                df = read_parquet_from_stream(stream)
                                ftype = 'parquet'
                            else:
                                df = read_csv_from_stream(stream)
                                ftype = 'csv'
                            src = {
                                'main_archive': path.name,
                                'nested_archive': None,
                                'file_name': fname,
                                'file_type': ftype,
                                'rows': len(df),
                                'columns': len(df.columns)
                            }
                            meta = extract_metadata_from_df(df, src)
                            if metadata_dir:
                                base = f"{path.stem}_{Path(fname).stem}"
                                save_metadata_to_json(meta, metadata_dir, base)
                            if save_dataframes and output_csv_dir:
                                out_stem = f"{path.stem}_{Path(fname).stem}"
                                if ftype == 'parquet':
                                    df.to_parquet(output_csv_dir / f"{out_stem}.parquet", index=False)
                                else:
                                    df.to_csv(output_csv_dir / f"{out_stem}.csv", index=False, sep=';', encoding='utf-8')
                            key = fname
                            result[key] = meta if return_metadata_only else df
                    return result
        except zipfile.BadZipFile:
            # Не удалось открыть стандартным zipfile, переходим к альтернативам
            pass
    
    # --------------------------------------------------------
    # Метод 2: shutil.unpack_archive
    # --------------------------------------------------------
    if is_zip_signature:
        try:
            temp_dir = tempfile.mkdtemp()
            shutil.unpack_archive(str(path), temp_dir, format='zip')
            all_files = []
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    all_files.append(Path(root) / f)
            if all_files:
                res = _process_files(all_files, path.name, None, metadata_dir, output_csv_dir,
                                     save_dataframes, return_metadata_only, prefer_parquet)
                shutil.rmtree(temp_dir, ignore_errors=True)
                if res:
                    return res
        except Exception:
            pass
        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    # --------------------------------------------------------
    # Метод 3: patool
    # --------------------------------------------------------
    if is_zip_signature:
        try:
            import patoolib
            temp_dir = tempfile.mkdtemp()
            patoolib.extract_archive(str(path), outdir=temp_dir)
            all_files = []
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    all_files.append(Path(root) / f)
            if all_files:
                res = _process_files(all_files, path.name, None, metadata_dir, output_csv_dir,
                                     save_dataframes, return_metadata_only, prefer_parquet)
                shutil.rmtree(temp_dir, ignore_errors=True)
                if res:
                    return res
        except ImportError:
            pass
        except Exception:
            pass
        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    # --------------------------------------------------------
    # Метод 4: системный unzip
    # --------------------------------------------------------
    if is_zip_signature:
        try:
            temp_dir = tempfile.mkdtemp()
            subprocess.run(['unzip', str(path), '-d', temp_dir], 
                           capture_output=True, check=True, timeout=300)
            all_files = []
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    all_files.append(Path(root) / f)
            if all_files:
                res = _process_files(all_files, path.name, None, metadata_dir, output_csv_dir,
                                     save_dataframes, return_metadata_only, prefer_parquet)
                shutil.rmtree(temp_dir, ignore_errors=True)
                if res:
                    return res
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    # --------------------------------------------------------
    # Если всё ещё не получилось и это ZIP — ошибка
    # --------------------------------------------------------
    if is_zip_signature:
        raise ValueError(f"Файл {path.name} имеет ZIP-сигнатуру, но не может быть распакован ни одним методом. Возможно, он повреждён, зашифрован или требует ручной распаковки.")
    
    # --------------------------------------------------------
    # Не ZIP — читаем как плоский файл
    # --------------------------------------------------------
    # Определяем тип по расширению или содержимому
    ext = path.suffix.lower()
    if ext == '.parquet':
        df = pd.read_parquet(path)
        ftype = 'parquet'
    elif ext == '.csv':
        with open(path, 'rb') as f:
            df = read_csv_from_stream(BytesIO(f.read()))
        ftype = 'csv'
    else:
        # Проверка на Parquet по сигнатуре
        with open(path, 'rb') as f:
            magic = f.read(4)
        if magic.startswith(b'PAR1') or (magic[0:2] == b'PK' and path.name.lower().endswith('.parquet')):
            df = pd.read_parquet(path)
            ftype = 'parquet'
        else:
            # Пробуем как CSV
            with open(path, 'rb') as f:
                df = read_csv_from_stream(BytesIO(f.read()))
            ftype = 'csv'
    
    src = {
        'main_archive': path.name,
        'nested_archive': None,
        'file_name': path.name,
        'file_type': ftype,
        'rows': len(df),
        'columns': len(df.columns)
    }
    metadata = extract_metadata_from_df(df, src)
    if metadata_dir:
        save_metadata_to_json(metadata, metadata_dir, path.stem)
    if save_dataframes and output_csv_dir:
        output_csv_dir.mkdir(parents=True, exist_ok=True)
        out_stem = path.stem
        if ftype == 'parquet':
            df.to_parquet(output_csv_dir / f"{out_stem}.parquet", index=False)
        else:
            df.to_csv(output_csv_dir / f"{out_stem}.csv", index=False, sep=';', encoding='utf-8')
    key = path.name
    result = {key: metadata if return_metadata_only else df}
    return result