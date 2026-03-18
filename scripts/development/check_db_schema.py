#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('custom-cvp.db')
cursor = conn.cursor()

# Get all table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]

print("Existing tables:")
for table in tables:
    print(f"  - {table}")
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"    {col[1]} ({col[2]})")
    print()

conn.close()
