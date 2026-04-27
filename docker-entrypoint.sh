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
    cur.execute('''CREATE TABLE IF NOT EXISTS home_trends_section (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        badge_label TEXT NOT NULL DEFAULT '',
        title_line1 TEXT NOT NULL DEFAULT '',
        title_highlight TEXT NOT NULL DEFAULT '',
        title_connector TEXT NOT NULL DEFAULT '',
        title_line3 TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    cur.execute('''INSERT OR IGNORE INTO home_trends_section
        (id, badge_label, title_line1, title_highlight, title_connector, title_line3, description)
        VALUES (1, 'The Current Landscape', 'Botanical', 'Trends', 'for the', 'Modern Collector',
        'An editorial exploration of nature and design in premium spaces.')
    ''')
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
