"""
Export the generated Touchless Reporting database to CSV.

Writes one CSV file per table into the csv_export/ directory, with a header
row of column names. Run after generate_db.py.
"""

import csv
import os
import sqlite3

DB_PATH = "touchless_reporting.db"
OUT_DIR = "csv_export"

# Internal SQLite bookkeeping tables we don't want to export.
SKIP_TABLES = {"sqlite_sequence"}


def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"Database not found: {DB_PATH} (run generate_db.py first)")

    os.makedirs(OUT_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    tables = [
        r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        if r[0] not in SKIP_TABLES
    ]

    for table in tables:
        rows = cur.execute(f"SELECT * FROM {table}")
        columns = [d[0] for d in rows.description]
        out_path = os.path.join(OUT_DIR, f"{table}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            n = 0
            for row in rows:
                writer.writerow(row)
                n += 1
        print(f"{table:25s} {n:>8,} rows -> {out_path}")

    con.close()
    print(f"\nCSV files written to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
