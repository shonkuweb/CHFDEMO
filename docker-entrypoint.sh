#!/bin/sh
set -e

# Ensure persistent data directories exist.
mkdir -p /app/data/uploads

# Seed database into persistent volume on first boot.
if [ ! -f "${DB_PATH:-/app/data/chf_archive.db}" ] && [ -f /app/chf_archive.db ]; then
  cp /app/chf_archive.db "${DB_PATH:-/app/data/chf_archive.db}"
fi

# Auto-seed admin user if admins table is empty (first boot on VPS).
python3 -c "
import sqlite3, os
db = os.environ.get('DB_PATH', '/app/data/chf_archive.db')
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cur.execute('SELECT COUNT(*) FROM admins')
    if cur.fetchone()[0] == 0:
        from passlib.hash import argon2
        h = argon2.hash('ChfLuxury2026!')
        cur.execute('INSERT INTO admins (username, password_hash) VALUES (?, ?)', ('admin', h))
        conn.commit()
        print('[BOOT] Default admin user seeded.')
    else:
        print('[BOOT] Admin user already exists.')
    conn.close()
" 2>&1 || echo '[BOOT] Admin seed skipped (non-critical).'

exec "$@"
