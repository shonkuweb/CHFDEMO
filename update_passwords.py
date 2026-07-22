import sqlite3
from passlib.hash import argon2

db_path = "chf_archive.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

new_pwd = "password123"
hashed_pwd = argon2.hash(new_pwd)

cur.execute("UPDATE admins SET password_hash = ?", (hashed_pwd,))
conn.commit()
conn.close()
print("Passwords updated successfully to 'password123'")
