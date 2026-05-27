#!/usr/bin/env python
# coding: utf-8

import re
import json
import zipfile
from pathlib import Path
from typing import List, Optional
import pandas as pd


def json_data(file_path):
    with open(file_path) as file:
        data = json.load(file)
    return data


def list_zip_contents(zip_path: Path) -> List[str]:
    """
    List all files contained in a zip archive.

    Args:
        zip_path: Path object pointing to the zip file.

    Returns:
        List of file paths contained in the zip archive.

    Raises:
        FileNotFoundError: If the zip file does not exist.
        zipfile.BadZipFile: If the file is not a valid zip archive.
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        return zip_ref.namelist()


def display_zip_contents(zip_path: Path) -> None:
    """
    Display the contents of a zip file in a formatted manner.

    Args:
        zip_path: Path object pointing to the zip file.

    Raises:
        FileNotFoundError: If the zip file does not exist.
        zipfile.BadZipFile: If the file is not a valid zip archive.
    """
    try:
        contents = list_zip_contents(zip_path)
        print(f"Contents of '{zip_path}':")
        print("-" * 79)
        for i, file_path in enumerate(contents, 1):
            print(f"{i:3d}. {file_path}")
        print("-" * 79)
        print(f"Total files: {len(contents)}")
    except (FileNotFoundError, zipfile.BadZipFile) as e:
        print(f"Error: {e}")


def get_first_csv_from_zip(zip_path: Path) -> Optional[str]:
    """
    Get the name of the first CSV file in a zip archive.

    Args:
        zip_path: Path object pointing to the zip file.

    Returns:
        Name of the first CSV file found, or None if no CSV files exist.

    Raises:
        FileNotFoundError: If the zip file does not exist.
        zipfile.BadZipFile: If the file is not a valid zip archive.
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        csv_files = [f for f in zip_ref.namelist() if f.lower().endswith(".csv")]

    return csv_files[0] if csv_files else None


def read_first_csv_from_zip(zip_path: Path, **kwargs) -> pd.DataFrame:
    """
    Read the first CSV file from a zip archive into a DataFrame.

    Args:
        zip_path: Path object pointing to the zip file.
        **kwargs: Additional arguments passed to pd.read_csv().

    Returns:
        DataFrame containing the data from the first CSV file.

    Raises:
        FileNotFoundError: If the zip file does not exist.
        zipfile.BadZipFile: If the file is not a valid zip archive.
        ValueError: If no CSV files are found in the zip archive.
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")

    csv_file = get_first_csv_from_zip(zip_path)
    if csv_file is None:
        raise ValueError(f"No CSV files found in zip archive: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        with zip_ref.open(csv_file) as file:
            return pd.read_csv(file, **kwargs)


def extract_python_code(text: str) -> Optional[str]:
    """
    Extract Python code from markdown text containing code blocks.

    Args:
        markdown_text: String containing markdown with Python code blocks.

    Returns:
        Extracted Python code as a string, or None if no code blocks found.
    """
    pattern = r"```python\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL)
    
    if matches:
        return "\n".join(match.strip() for match in matches)
    
    return None
