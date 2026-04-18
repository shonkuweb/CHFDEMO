import sqlite3
import sys

db_path = "chf_archive.db"

def init_auth():
    # Import schema builder from the main seeder
    from database_seeder import init_schema
    
    # Hash the password - use passlib if available, else hashlib
    default_pwd = "ChfLuxury2026!"
    try:
        from passlib.hash import argon2
        hashed_pwd = argon2.hash(default_pwd)
        print("Using Argon2 hashing.")
    except ImportError:
        import hashlib, secrets
        salt = secrets.token_hex(16)
        hashed_pwd = f"sha256${salt}${hashlib.sha256((salt + default_pwd).encode()).hexdigest()}"
        print("Warning: passlib not installed. Using fallback SHA256. Run 'pip install passlib[argon2]' for production security.")
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    init_schema(cur)
    
    cur.execute("SELECT * FROM admins WHERE username = 'admin'")
    existing = cur.fetchone()
    
    if not existing:
        cur.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", ('admin', hashed_pwd))
        print(f"✅ Inserted default admin user.")
        print(f"   Username: admin")
        print(f"   Password: {default_pwd}")
    else:
        print("Admin user already exists.")
        
    conn.commit()
    conn.close()
    print("Auth tables initialized.")

if __name__ == "__main__":
    init_auth()
