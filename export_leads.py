import sqlite3
import csv
import os

db_path = "database/phn_agent.db"
csv_path = "interested_students.csv"

if not os.path.exists(db_path):
    print("No database found yet.")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    c.execute("SELECT id, phone, name, email, interested_course, created_at FROM students")
    rows = c.fetchall()
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["ID", "Phone", "Name", "Email", "Course Interested", "Registered At"])
        w.writerows(rows)
    print(f"Successfully exported {len(rows)} leads to {csv_path}!")
except Exception as e:
    print("Export failed:", e)
finally:
    conn.close()
