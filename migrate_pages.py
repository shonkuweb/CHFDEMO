import sqlite3
import os

db_path = "chf_archive.db"

def migrate():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Define the pages to register
    pages = [
        ('bonsai', 'Bonsai Collections', 'Bonsai', 'Collections', 'Curating nature\'s rarest botanical wonders for refined spaces.', 'Home / Collections / Bonsai'),
        ('full-grown-avenue-trees', 'Full Grown Avenue Trees', 'Full Grown', 'Avenue Trees', 'Curating nature\'s rarest botanical wonders for refined spaces.', 'Home / Collections / Avenue Trees'),
        ('exotic-indoor-plants', 'Exotic Indoor Plants', 'Exotic', 'Indoor Plants', 'Curating nature\'s rarest botanical wonders for refined spaces.', 'Home / Collections / Indoor Plants'),
        ('curated-planters', 'Curated Planters', 'Curated', 'Plants', 'Curating nature\'s rarest botanical wonders for refined spaces.', 'Home / Collections / Curated Planters'),
        ('curated-specimens', 'Curated Specimens', 'Curated', 'Specimens', 'Not added — introduced. Every specimen placed with purpose.', 'Home / Services / Curated Specimens')
    ]

    for slug, title, t1, t2, sub, bread in pages:
        cur.execute('''
            INSERT OR REPLACE INTO pages (slug, title, titleLine1, titleLine2, subtitle, breadcrumb)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (slug, title, t1, t2, sub, bread))
        print(f"✅ Registered page: {slug}")

    # Ensure categories table exists (just in case)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            page_slug TEXT,
            label TEXT, title TEXT, description TEXT,
            image TEXT, ctaText TEXT, ctaLink TEXT,
            display_order INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()
    print("\nMigration Complete! These pages are now editable in the Admin Panel.")

if __name__ == "__main__":
    migrate()
