import sqlite3
import os

db_path = os.environ.get("DB_PATH", "chf_archive.db")

home_seeds = {
    "home/hero/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/hero_image_new.jpeg", "type": "media"},
    "home/philosophy/title": {"value": "When a Space Begins to <br /><span class='italic text-primary'>Feel Alive</span>", "type": "text"},
    "home/philosophy/body": {"value": "<p>Some spaces are seen.<br>Others are felt.</p><p>A curated specimen has the power to shift that feeling — bringing calm, focus, and a subtle sense of luxury that cannot be replicated through excess.</p><p>It’s a quiet transformation, but a lasting one.</p>", "type": "longtext"}
}

about_seeds = {
    "about/story/intro": {"value": "Calcutta Horticultural Farm is a plant-led design practice rooted in legacy, expertise, and a deep respect for nature. We continue to shape greener spaces with intention and expertise—quietly leading a movement where every plant has a purpose, and every space has the potential to grow.", "type": "longtext"},
    "about/story/title-1": {"value": "The Founding Era (1982)", "type": "text"},
    "about/philosophy/patience-title": {"value": "Founded in 1982 by Mr. Gautam Bose, the practice began with a vision to integrate greenery into the evolving urban fabric—setting new benchmarks in landscape development and pioneering tree transplantation in the city.", "type": "longtext"},
    "about/story/title-2": {"value": "The Modern Vision", "type": "text"},
    "about/philosophy/precision-title": {"value": "Today, the legacy is carried forward by Indra Bose and Apurba Bose, expanding the practice into contemporary formats while staying rooted in its core philosophy.", "type": "longtext"},
    "about/philosophy/presence-title": {"value": "Cultivating Scale", "type": "text"},
    "about/philosophy/presence-body": {"value": "With two expansive nurseries in Alipore and Muchisha, spread across acres of cultivated land, we house a rich collection of indoor, outdoor and exotic plants. Our facilities cultivate bonsais, topiaries, and an extensive selection of architectural plants, ensuring we have the perfect specimen for any scale of project.", "type": "longtext"}
}

global_seeds = {
    "global/contact/email": {"value": "info@chfbotanical.com", "type": "text"},
    "global/contact/phone": {"value": "+91 98310 98310", "type": "text"}
}

def seed_core_content():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure table exists
    cur.execute('''CREATE TABLE IF NOT EXISTS site_content (
        path TEXT PRIMARY KEY,
        value TEXT,
        type TEXT
    )''')

    all_seeds = {**home_seeds, **about_seeds, **global_seeds}

    for path, data in all_seeds.items():
        # Only insert if it doesn't exist to prevent overwriting user edits
        cur.execute("SELECT COUNT(*) FROM site_content WHERE path = ?", (path,))
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO site_content (path, value, type) VALUES (?, ?, ?)", 
                        (path, data["value"], data["type"]))
            print(f"✅ Seeded: {path}")

    conn.commit()
    conn.close()
    print("\nCore content seeding complete (Home, About, Global).")

if __name__ == "__main__":
    seed_core_content()
