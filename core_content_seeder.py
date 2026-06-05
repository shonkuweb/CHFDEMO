import sqlite3
import os

db_path = os.environ.get("DB_PATH", "chf_archive.db")

home_seeds = {
    "home/hero/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/hero_image_new.jpeg", "type": "media"},
    "home/philosophy/title": {"value": "The Art of Growth <br /><span class='italic text-primary'>with Curated Specimens</span>", "type": "text"},
    "home/philosophy/body": {"value": "<p>Some spaces are seen.<br>Others are experienced.</p><p>A curated specimen transforms a space in silence —<br>bringing calm, depth, and a quiet sense of luxury<br>that cannot be created through excess.</p><p>It doesn’t demand attention.<br>Yet, it changes everything.</p><p>A subtle transformation —<br>one that stays.</p>", "type": "longtext"}
}

about_seeds = {
    "about/story/title-1": {"value": "The Founding Era (1982)", "type": "text"},
    "about/philosophy/patience-title": {"value": "Calcutta Horticultural Farm is a plant-led design practice rooted in legacy, expertise, and a deep respect for nature. Founded in 1982 by Mr. Gautam Bose, the practice began with a vision to integrate greenery into the evolving urban fabric—setting new benchmarks in landscape development and pioneering tree transplantation in the city.", "type": "longtext"},
    "about/story/title-2": {"value": "Design Philosophy", "type": "text"},
    "about/story/image-2": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/design-philosophy-1d66f8f2.png", "type": "media"},
    "about/philosophy/precision-title": {"value": "Our work is guided by an intrinsic understanding of plants—ensuring every space is thoughtfully designed, where aesthetics and ecology come together seamlessly. From bespoke residential landscapes to large-scale corporate environments, each project is created to thrive and evolve over time.", "type": "longtext"},
    "about/philosophy/presence-title": {"value": "Carrying the Legacy Forward", "type": "text"},
    "about/philosophy/presence-body": {"value": "Today, the legacy is carried forward by Indra Bose and Apurba Bose, expanding the practice into contemporary formats while staying rooted in its core philosophy. Alongside design and consulting, we offer curated plant solutions, gardening essentials, and a diverse range of products tailored for modern green living.", "type": "longtext"},
    "about/nurseries/title": {"value": "Our Nurseries", "type": "text"},
    "about/nurseries/body": {"value": "With two expansive nurseries in Alipore and Muchisha, spread across acres of cultivated land, we house a rich collection of indoor, outdoor and exotic plants, along with bonsais, topiaries and an extensive selection of pots and planters. Our plant experience centre in Alipore further brings this vision to life—an immersive space where clients can explore, interact, and engage with plants in thoughtfully curated settings.", "type": "longtext"},
    "about/nurseries/image-1": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/our-nurseries-1-25c9a8f0.png", "type": "media"},
    "about/nurseries/image-2": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/our-nurseries-2-6ff91b68.png", "type": "media"},
}

global_seeds = {
    "global/contact/email": {"value": "support@chfexperience.com", "type": "text"},
    "global/contact/phone": {"value": "+91 79807 83108", "type": "text"}
}

plant_center_seeds = {
    "plant-center/hero/title": {"value": "Plant <br /><span class='text-accent-bronze italic font-light drop-shadow-sm'>Experience Centre</span>", "type": "text"},
    "plant-center/hero/subtitle": {"value": "A curated space where architecture meets biodiversity. Experience the quiet power of nature through our multi-sensory botanical archive.", "type": "text"},
    "plant-center/hero/video": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/chf_video_placeholder.mp4", "type": "media"},
    "plant-center/intro/title": {"value": "An Immersive <br/>Botanical Archive", "type": "text"},
    "plant-center/intro/body": {"value": "Far beyond a traditional nursery, the Alipore Experience Centre is designed as a living gallery. We invite architects, interior designers, and collectors to walk through staggered glasshouses, bonsai viewing decks, and rare specimen yards to visualize the scale, texture, and character of the plants in their ideal environment.", "type": "longtext"},
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
    print("\nCore content seeding complete (Home, About, Global, Plant Centre).")

if __name__ == "__main__":
    seed_core_content()
