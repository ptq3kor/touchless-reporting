import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "touchless_reporting.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
