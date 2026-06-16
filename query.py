import sqlite3
con = sqlite3.connect("touchless_reporting.db")
rows = con.execute("""
    SELECT *
    FROM fact_financials
""").fetchall()
print(rows)