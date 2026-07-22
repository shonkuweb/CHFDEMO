import sqlite3
from passlib.hash import argon2

db_path = "chf_archive.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

new_pwd = "password123"
hashed_pwd = argon2.hash(new_pwd)

# Check if invoice_admin exists
cur.execute("SELECT * FROM admins WHERE username = 'invoice_admin'")
existing = cur.fetchone()

if existing:
    cur.execute("UPDATE admins SET password_hash = ? WHERE username = 'invoice_admin'", (hashed_pwd,))
else:
    cur.execute("INSERT INTO admins (username, password_hash) VALUES ('invoice_admin', ?)", (hashed_pwd,))
    
conn.commit()
conn.close()
print("Invoice admin password reset to 'password123'")
