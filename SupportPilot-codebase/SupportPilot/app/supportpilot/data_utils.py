"""Dataset helpers shared by training scripts and tests."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
import pandas as pd

TEXT_COLUMNS = ("subject", "body")
TARGET_COLUMNS = ("queue", "type", "priority")
TAG_COLUMNS = tuple(f"tag_{i}" for i in range(1, 9))


def load_tickets(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path}. Copy the provided CSV to data/ or set SUPPORTPILOT_DATA_PATH."
        )
    df = pd.read_csv(path)
    required = {"subject", "body", "queue", "type", "priority", "language"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    return prepare_dataframe(df)


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Preserve Unicode; never apply ASCII-only cleaning to multilingual text."""
    df = df.copy()
    for column in TEXT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("").astype(str)
    df["text"] = (df["subject"].str.strip() + "\n\n" + df["body"].str.strip()).str.strip()
    df = df[df["text"].str.len() > 0].copy()
    for column in TARGET_COLUMNS:
        if column in df.columns:
            df[column] = df[column].astype("string").str.strip()
            df.loc[df[column].isin(["", "nan", "None"]), column] = pd.NA
    if "language" in df.columns:
        df["language"] = df["language"].fillna("unknown").astype(str).str.lower()
    for column in TAG_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = df[column].astype("string").str.strip()
        df.loc[df[column].isin(["", "nan", "None"]), column] = pd.NA
    return df.reset_index(drop=True)


def tags_for_row(row: pd.Series | dict) -> list[str]:
    tags: list[str] = []
    for column in TAG_COLUMNS:
        value = row.get(column)
        if pd.notna(value):
            value = str(value).strip()
            if value and value.lower() not in {"nan", "none"} and value not in tags:
                tags.append(value)
    return tags


def build_tag_lists(df: pd.DataFrame) -> list[list[str]]:
    return [tags_for_row(row) for _, row in df.iterrows()]


def top_tag_vocabulary(tag_lists: Iterable[list[str]], limit: int = 50) -> list[str]:
    from collections import Counter
    counts: Counter[str] = Counter()
    for tags in tag_lists:
        counts.update(sorted(set(tags), key=str.casefold))
    return [tag for tag, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:limit]]
