import sqlite3
import os

DB_PATH = 'chf_archive.db'

def expand():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create the universal site_content table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS site_content (
            path TEXT PRIMARY KEY,
            value TEXT,
            type TEXT -- text, longtext, media
        )
    ''')
    
    # Seed initial Home Page content (Aesthetics and Values)
    initial_content = [
        # Global Settings
        ('global/site/name', 'CHF', 'text'),
        ('global/contact/email', 'hello@chfbotanical.com', 'text'),
        ('global/social/instagram', 'https://instagram.com/chf', 'text'),
        
        # Home Page Hero
        ('home/hero/title-1', 'Slow Luxury', 'text'),
        ('home/hero/title-2', 'Botanical Specimens', 'text'),
        ('home/hero/subtitle', 'Curating nature\'s rarest architectural wonders for refined spaces.', 'text'),
        ('home/hero/image', 'assets/images/deskchf.png', 'media'),
        
        # Home Page Philosophy
        ('home/philosophy/title', 'Nature, Orchestrated.', 'text'),
        ('home/philosophy/body', 'At CHF, we believe interior flora shouldn\'t just inhabit a room—it should command it. We source full-grown, heritage specimens that bring an immediate sense of permanence and prestige to the world\'s most distinguished residences.', 'longtext'),
    ]
    
    for path, val, ctype in initial_content:
        cursor.execute('INSERT OR IGNORE INTO site_content (path, value, type) VALUES (?, ?, ?)', (path, val, ctype))
        
    conn.commit()
    conn.close()
    print("Database expanded with site_content table.")

if __name__ == "__main__":
    expand()
