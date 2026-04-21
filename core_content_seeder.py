import sqlite3
import os

db_path = os.environ.get("DB_PATH", "chf_archive.db")

home_seeds = {
    "home/hero/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/hero_image_new.jpeg", "type": "media"},
    "home/philosophy/title": {"value": "The Art of Growth <br /><span class='italic text-primary'>with Curated Specimens</span>", "type": "text"},
    "home/philosophy/body": {"value": "<p>Some spaces are seen.<br>Others are experienced.</p><p>A curated specimen transforms a space in silence —<br>bringing calm, depth, and a quiet sense of luxury<br>that cannot be created through excess.</p><p>It doesn’t demand attention.<br>Yet, it changes everything.</p><p>A subtle transformation —<br>one that stays.</p>", "type": "longtext"}
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

plant_center_seeds = {
    "plant-center/hero/title": {"value": "Plant <br /><span class='text-accent-bronze italic font-light drop-shadow-sm'>Experience Center</span>", "type": "text"},
    "plant-center/hero/subtitle": {"value": "A curated space where architecture meets biodiversity. Experience the quiet power of nature through our multi-sensory botanical archive.", "type": "text"},
    "plant-center/hero/video": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/chf_video_placeholder.mp4", "type": "media"},
    "plant-center/intro/title": {"value": "An Immersive <br/>Botanical Archive", "type": "text"},
    "plant-center/intro/body": {"value": "Far beyond a traditional nursery, the Alipore Experience Center is designed as a living gallery. We invite architects, interior designers, and collectors to walk through staggered glasshouses, bonsai viewing decks, and rare specimen yards to visualize the scale, texture, and character of the plants in their ideal environment.", "type": "longtext"},
    "plant-center/gallery/img1": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimens.png", "type": "media"},
    "plant-center/gallery/img2": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png", "type": "media"},
    "plant-center/gallery/img3": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/architectural_harmony.png", "type": "media"}
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

    all_seeds = {**home_seeds, **about_seeds, **global_seeds, **plant_center_seeds}

    for path, data in all_seeds.items():
        # Only insert if it doesn't exist to prevent overwriting user edits
        cur.execute("SELECT COUNT(*) FROM site_content WHERE path = ?", (path,))
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO site_content (path, value, type) VALUES (?, ?, ?)", 
                        (path, data["value"], data["type"]))
            print(f"✅ Seeded: {path}")

    conn.commit()
    conn.close()
    print("\nCore content seeding complete (Home, About, Global, Plant Center).")

if __name__ == "__main__":
    seed_core_content()
