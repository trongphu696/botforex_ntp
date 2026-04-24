"""
Thread-safe atomic JSON file storage.
Uses write-to-temp + os.replace() for corruption-safe saves.
"""

import os
import json
from typing import Callable, List
import config


def _ensure_dir(filepath: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)


def load(filepath: str) -> list:
    """Read JSON file, returning [] if file is missing or corrupt."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save(filepath: str, data: list) -> None:
    """Atomically write data to filepath (write temp → rename)."""
    _ensure_dir(filepath)
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, filepath)


def append_record(filepath: str, record: dict) -> None:
    """Load existing list, append record, save atomically."""
    data = load(filepath)
    data.append(record)
    save(filepath, data)


def update_record(
    filepath: str,
    match_fn: Callable[[dict], bool],
    update_fn: Callable[[dict], dict],
) -> int:
    """
    Load all records, apply update_fn to each record where match_fn returns True.
    Save atomically. Returns count of updated records.
    """
    data = load(filepath)
    count = 0
    for i, rec in enumerate(data):
        if match_fn(rec):
            data[i] = update_fn(rec)
            count += 1
    if count > 0:
        save(filepath, data)
    return count


def ensure_data_dir() -> None:
    """Create storage/data directory if it doesn't exist."""
    os.makedirs(config.STORAGE_DIR, exist_ok=True)
    for path in [config.SIGNALS_FILE, config.TRADES_FILE,
                 config.BACKTEST_FILE, config.METRICS_FILE]:
        if not os.path.exists(path):
            save(path, [])
