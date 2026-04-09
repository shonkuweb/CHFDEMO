import os
import json
import sqlite3

DB_PATH = 'chf_archive.db'
DATA_DIR = 'data'

def migrate():
    print("Starting migration to SQLite...")
    
    # Connect to (or create) the database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            slug TEXT PRIMARY KEY,
            title TEXT,
            titleLine1 TEXT,
            titleLine2 TEXT,
            subtitle TEXT,
            breadcrumb TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            page_slug TEXT,
            label TEXT,
            title TEXT,
            description TEXT,
            image TEXT,
            ctaText TEXT,
            ctaLink TEXT,
            display_order INTEGER,
            FOREIGN KEY (page_slug) REFERENCES pages (slug)
        )
    ''')
    
    # Iterate through JSON files
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            slug = filename.replace('.json', '')
            file_path = os.path.join(DATA_DIR, filename)
            
            print(f"Migrating {filename}...")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Insert page data
                page = data.get('page', {})
                cursor.execute('''
                    INSERT OR REPLACE INTO pages (slug, title, titleLine1, titleLine2, subtitle, breadcrumb)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    slug,
                    page.get('title', ''),
                    page.get('titleLine1', ''),
                    page.get('titleLine2', ''),
                    page.get('subtitle', ''),
                    page.get('breadcrumb', '')
                ))
                
                # Insert categories
                categories = data.get('categories', [])
                for idx, cat in enumerate(categories):
                    cursor.execute('''
                        INSERT OR REPLACE INTO categories (id, page_slug, label, title, description, image, ctaText, ctaLink, display_order)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        cat.get('id', f"{slug}-cat-{idx}"),
                        slug,
                        cat.get('label', ''),
                        cat.get('title', ''),
                        cat.get('description', ''),
                        cat.get('image', ''),
                        cat.get('ctaText', ''),
                        cat.get('ctaLink', ''),
                        idx
                    ))
                    
    conn.commit()
    conn.close()
    print("Migration complete. Database 'chf_archive.db' created.")

if __name__ == "__main__":
    migrate()
