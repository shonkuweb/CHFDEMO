import sqlite3
import os

db_path = os.environ.get("DB_PATH", "chf_archive.db")

# Page definitions
PAGES = [
    {
        "slug": "full-grown-avenue-trees",
        "title": "Full Grown Avenue Trees",
        "titleLine1": "Full Grown",
        "titleLine2": "Avenue Trees",
        "subtitle": "Stately specimens for monumental landscapes and grand entrances.",
        "breadcrumb": "Collections"
    },
    {
        "slug": "exotic-indoor-plants",
        "title": "Exotic Indoor Plants",
        "titleLine1": "Exotic",
        "titleLine2": "Indoor Plants",
        "subtitle": "Rare and refined botanicals that transform interior spaces into living sanctuaries.",
        "breadcrumb": "Collections"
    },
    {
        "slug": "bonsai",
        "title": "Bonsai Collections",
        "titleLine1": "Bonsai",
        "titleLine2": "Collections",
        "subtitle": "Living sculptures shaped by centuries of horticultural mastery.",
        "breadcrumb": "Collections"
    },
    {
        "slug": "curated-plants",
        "title": "Curated Plants",
        "titleLine1": "Curated",
        "titleLine2": "Plants",
        "subtitle": "A thoughtful selection of specimens chosen for their architectural merit and rarity.",
        "breadcrumb": "Collections"
    },
]

# Default category blocks shared across collection pages
DEFAULT_CATEGORIES = [
    {
        "id_suffix": "cat-1",
        "label": "Category I",
        "title": "Architectural Forms",
        "description": "Sculptural botanicals characterized by their geometric precision and structural integrity. These specimens serve as timeless focal points in minimalist environments.",
        "image": "",
        "ctaText": "Request Catalog",
        "ctaLink": "inquiry.html",
        "display_order": 0
    },
    {
        "id_suffix": "cat-2",
        "label": "Category II",
        "title": "Variegated Rarities",
        "description": "Exceptional specimens featuring unique biological pigments. From albino-patterned leaves to deep emerald hues, these are the crown jewels of our living archive.",
        "image": "",
        "ctaText": "Join Waitlist",
        "ctaLink": "inquiry.html",
        "display_order": 1
    },
    {
        "id_suffix": "cat-3",
        "label": "Category III",
        "title": "Vertical Ecosystems",
        "description": "Integrated living walls that redefine interior topography. A rhythmic integration of biodiversity that breathes life into static surfaces.",
        "image": "",
        "ctaText": "Consult on Design",
        "ctaLink": "inquiry.html",
        "display_order": 2
    },
]

def seed_collections():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure tables exist
    cur.execute('''CREATE TABLE IF NOT EXISTS pages (
        slug TEXT PRIMARY KEY,
        title TEXT, titleLine1 TEXT, titleLine2 TEXT,
        subtitle TEXT, breadcrumb TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS categories (
        id TEXT PRIMARY KEY,
        page_slug TEXT,
        label TEXT, title TEXT, description TEXT,
        image TEXT, ctaText TEXT, ctaLink TEXT,
        display_order INTEGER DEFAULT 0
    )''')

    for page in PAGES:
        cur.execute('''
            INSERT OR REPLACE INTO pages (slug, title, titleLine1, titleLine2, subtitle, breadcrumb)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (page["slug"], page["title"], page["titleLine1"], page["titleLine2"], page["subtitle"], page["breadcrumb"]))

        # Only insert categories if page doesn't already have custom ones
        cur.execute("SELECT COUNT(*) FROM categories WHERE page_slug = ?", (page["slug"],))
        count = cur.fetchone()[0]
        if count == 0:
            for cat in DEFAULT_CATEGORIES:
                cat_id = f"{page['slug']}-{cat['id_suffix']}"
                cur.execute('''
                    INSERT OR IGNORE INTO categories 
                    (id, page_slug, label, title, description, image, ctaText, ctaLink, display_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (cat_id, page["slug"], cat["label"], cat["title"],
                      cat["description"], cat["image"], cat["ctaText"], cat["ctaLink"], cat["display_order"]))

        print(f"✅ Seeded: {page['slug']}")

    conn.commit()
    conn.close()
    print("\nCollection seeding complete. All 4 pages are now editable via Admin Panel.")

if __name__ == "__main__":
    seed_collections()
