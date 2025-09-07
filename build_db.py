import sqlite3
import os
import sys

def read_sql_file(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQL file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def execute_sql_script(db_path, sql_script):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        conn.executescript(sql_script)
        conn.commit()
        print(f"Database created at: {db_path}")
    except sqlite3.Error as e:
        print("SQLite error during execution:")
        print(e)
        print("\nAttempting line-by-line execution for diagnostics...\n")
        troubleshoot_sql_lines(conn, sql_script)
    finally:
        conn.close()

def troubleshoot_sql_lines(conn, script):
    cursor = conn.cursor()
    lines = script.splitlines()
    buffer = ""
    for i, line in enumerate(lines, start=1):
        buffer += line + "\n"
        if line.strip().endswith(";"):
            try:
                cursor.executescript(buffer)
            except sqlite3.Error as e:
                print(f"⚠️ Error at line {i}: {line.strip()}")
                print(f"   ↳ {e}")
            buffer = ""
    conn.commit()

def inspect_database(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    def fetch_objects(obj_type):
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='{obj_type}';")
        return [row[0] for row in cursor.fetchall()]

    print("\nDatabase Contents:")
    print("Tables:", fetch_objects("table"))
    print("Views:", fetch_objects("view"))
    print("Indexes:", fetch_objects("index"))
    print("Triggers:", fetch_objects("trigger"))

    conn.close()

def main(sql_file="C:/Users/Administrator/Projects/taipy/database/oneoff.sql", output_db="modern_database.sqlite"):
    print(f"Reading SQL from: {sql_file}")
    sql_script = read_sql_file(sql_file)

    print(f"Creating SQLite DB: {output_db}")
    execute_sql_script(output_db, sql_script)

    print(f"\nInspecting database: {output_db}")
    inspect_database(output_db)

if __name__ == "__main__":
    main()
