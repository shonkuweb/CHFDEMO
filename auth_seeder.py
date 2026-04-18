import sqlite3
from passlib.hash import argon2

db_path = "chf_archive.db"

def init_auth():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Create admins table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Seed default user if not exists
    cur.execute("SELECT * FROM admins WHERE username = 'admin'")
    existing = cur.fetchone()
    
    if not existing:
        default_pwd = "ChfLuxury2026!"
        hashed_pwd = argon2.hash(default_pwd)
        cur.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", ('admin', hashed_pwd))
        print("Inserted default admin user.")
    else:
        print("Admin user already exists.")
        
    conn.commit()
    conn.close()
    print("Auth tables initialized.")

if __name__ == "__main__":
    init_auth()
