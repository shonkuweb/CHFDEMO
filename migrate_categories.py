import sqlite3
import os

db_path = "chf_archive.db"

def migrate():
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    try:
        cur.execute("ALTER TABLE categories ADD COLUMN features TEXT")
        print("✅ Added 'features' column to 'categories' table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("ℹ️ 'features' column already exists.")
        else:
            print(f"❌ Error during migration: {e}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
