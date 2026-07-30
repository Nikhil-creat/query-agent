"""
schema_utils.py
----------------
Turns an uploaded CSV/XLSX into a queryable SQL table, and produces a
compact schema description the LLM can use to write correct SQL against
it (column names, types, and a few real sample values -- this is what
lets the agent know a column called "region" contains "APAC"/"EMEA"/"NA"
rather than guessing).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "datasets.sqlite3"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def sanitize_table_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"ds_{slug or 'dataset'}"


def load_file_to_table(file_path: str, table_name: str) -> tuple[pd.DataFrame, int]:
    """Loads a CSV or XLSX file into a fresh SQLite table (replacing any
    existing table of the same name) and returns the DataFrame + row count.
    """
    if file_path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    # Normalize column names to something SQL- and prompt-friendly.
    df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c).strip()) for c in df.columns]

    conn = get_connection()
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()

    return df, len(df)


def build_schema_json(df: pd.DataFrame, sample_rows: int = 3) -> dict:
    schema = {}
    for col in df.columns:
        dtype = str(df[col].dtype)
        samples = df[col].dropna().unique()[:sample_rows].tolist()
        # Keep sample values short and JSON-serializable.
        samples = [str(s)[:40] for s in samples]
        schema[col] = {"dtype": dtype, "sample_values": samples}
    return schema


def schema_to_prompt_block(table_name: str, schema_json: dict) -> str:
    """Renders the schema as compact text for the LLM's system prompt."""
    lines = [f"Table: {table_name}", "Columns:"]
    for col, info in schema_json.items():
        samples = ", ".join(info["sample_values"]) or "n/a"
        lines.append(f"  - {col} ({info['dtype']}) e.g. [{samples}]")
    return "\n".join(lines)


def run_select(sql: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()
