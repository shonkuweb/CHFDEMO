import sqlite3
import json

db_path = "chf_archive.db"

seeds = {
    # ── Architectural Harmony ──
    "arch/hero/title": {"value": "Architectural <span class='text-accent-bronze italic'>Harmony</span>", "type": "text"},
    "arch/hero/subtitle": {"value": "Design is Instant. Growth is Inevitable. We Plan for Both.", "type": "text"},
    "arch/block1/title": {"value": "A Living Architecture", "type": "text"},
    "arch/block1/body": {"value": "In landscape architecture, drawings capture a moment—but gardens don’t stand still. They grow, expand, compete, and transform. Without a deep understanding of plant behaviour many designs begin to diverge from their original intent.", "type": "longtext"},
    "arch/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_1.png", "type": "media"},
    "arch/block2/title": {"value": "Scale and Maturity", "type": "text"},
    "arch/block2/body": {"value": "As consulting horticulturists, we often see thoughtfully designed spaces challenged by plant selections that don’t account for scale or maturity. Fast growers are placed where restraint is essential. Foreground hedges are composed of species that eventually outgrow and obscure the very layers they were meant to frame. What appears harmonious on day one can lose its proportion and clarity with time.", "type": "longtext"},
    "arch/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_2.png", "type": "media"},
    "arch/block3/title": {"value": "Intentional Growth", "type": "text"},
    "arch/block3/body": {"value": "With the intent to not redefine but strengthen the designs, we as landscape developers work closely with landscape architects—either as consultants during the design phase or as collaborators during execution—to ensure that plant selections are informed, intentional, and future-ready. By bringing horticultural depth into the conversation early, we help align design vision with plant behaviour, site conditions, and long-term growth patterns.", "type": "longtext"},
    "arch/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_3.png", "type": "media"},
    "arch/block4/title": {"value": "Enduring Vision", "type": "text"},
    "arch/block4/body": {"value": "With a strong foundation in plant knowledge, we ensure that every selection supports lasting architectural harmony—not just immediate visual appeal. Because a successful landscape is not just about how it looks when installed—it’s about how it evolves.", "type": "longtext"},
    "arch/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_4.png", "type": "media"},

    # ── Plant Experience Center ──
    "plant-center/hero/title": {"value": "Plant <br /> \n<span class='text-accent-bronze italic font-light drop-shadow-sm'>Experience Center</span>", "type": "text"},
    "plant-center/hero/subtitle": {"value": "A curated space where architecture meets biodiversity. Experience the quiet power of nature through our multi-sensory botanical archive.", "type": "longtext"},
    "plant-center/hero/media": {"value": "", "type": "media"}, # Blank for wireframe
    # ── White Glove Service ──
    "whiteglove/hero/title": {"value": "White Glove <br />\n<span class='text-accent-bronze italic font-light drop-shadow-sm'>Service</span>", "type": "text"},
    "whiteglove/hero/subtitle": {"value": "From nursery to installation — precision, care, and craft at every step.", "type": "text"},
    "whiteglove/block1/title": {"value": "Seamless Logistics", "type": "text"},
    "whiteglove/block1/body": {"value": "Seamless logistics meets craftsmanship. From nursery to installation, we transport and position premium specimens with precision, preserving their form and character while elevating your landscape into a refined visual experience.", "type": "longtext"},
    "whiteglove/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_1.png", "type": "media"},
    "whiteglove/block2/title": {"value": "Handled Like Living Art", "type": "text"},
    "whiteglove/block2/body": {"value": "Our specialists deliver and place statement plants with care and control, ensuring every curated specimen arrives safely and integrates flawlessly into your luxury outdoor space.", "type": "longtext"},
    "whiteglove/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_2.png", "type": "media"},
    "whiteglove/block3/title": {"value": "Foundation of Excellence", "type": "text"},
    "whiteglove/block3/body": {"value": "Crafting the foundation of excellence. Rich soil preparation ensures long-term vitality, giving each curated specimen the perfect start — combining expertise, care, and precision for landscapes that thrive beautifully over time.", "type": "longtext"},
    "whiteglove/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_3.png", "type": "media"},
    "whiteglove/block4/title": {"value": "Precision Planting", "type": "text"},
    "whiteglove/block4/body": {"value": "Our team carefully positions curated specimens, blending architecture and nature seamlessly, creating refined outdoor environments that feel intentional, balanced, and effortlessly luxurious.", "type": "longtext"},
    "whiteglove/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/white_glove_4.png", "type": "media"},
    "whiteglove/closing/title": {"value": "Every detail considered.<br>\n<span class='text-accent-bronze italic mt-4 block'>Every specimen placed with purpose.</span>", "type": "longtext"},

    # ── Curated Specimens ──
    "curated/hero/title": {"value": "Curated <br />\n<span class='text-accent-bronze italic font-light drop-shadow-sm'>Specimens</span>", "type": "text"},
    "curated/hero/subtitle": {"value": "Not added — introduced. Every specimen placed with purpose.", "type": "text"},
    "curated/block1/title": {"value": "Sensory Calm", "type": "text"},
    "curated/block1/body": {"value": "Golden light, water reflections, and a sculptural specimen create sensory calm — where negative ions, natural textures, and biophilic balance reduce stress, slow the mind, and elevate the entire outdoor experience.", "type": "longtext"},
    "curated/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_1.png", "type": "media"},
    "curated/block2/title": {"value": "Breathable Living", "type": "text"},
    "curated/block2/body": {"value": "Expansive light, open flow, and a single curated plant enhance oxygen levels and visual calm — proven to reduce cortisol and improve focus, creating a breathable, emotionally warm living environment.", "type": "longtext"},
    "curated/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_2.png", "type": "media"},
    "curated/block3/title": {"value": "Quietly Premium", "type": "text"},
    "curated/block3/body": {"value": "A refined interior anchored by a living specimen — naturally filtering air, softening acoustics, and enhancing well-being through biophilic design, creating a welcoming space that feels calm, intentional, and quietly premium.", "type": "longtext"},
    "curated/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_3.png", "type": "media"},
    "curated/block4/title": {"value": "Elevated Thinking", "type": "text"},
    "curated/block4/body": {"value": "Clean lines, controlled light, and a sculptural plant improve cognitive performance and reduce fatigue — bringing clarity, calm, and subtle vitality into a workspace designed for focus, decision-making, and elevated thinking.", "type": "longtext"},
    "curated/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_4.png", "type": "media"},
    "curated/closing/title": {"value": "A space that feels alive<br>\n<span class='text-accent-bronze italic mt-4 block'>is a space that inspires.</span>", "type": "longtext"},

}

def init_schema(cur):
    """Create all tables if they don't exist yet (safe on fresh VPS)."""
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            slug TEXT PRIMARY KEY,
            title TEXT, titleLine1 TEXT, titleLine2 TEXT,
            subtitle TEXT, breadcrumb TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            page_slug TEXT,
            label TEXT, title TEXT, description TEXT,
            image TEXT, ctaText TEXT, ctaLink TEXT,
            display_order INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS site_content (
            path TEXT PRIMARY KEY,
            value TEXT,
            type TEXT DEFAULT 'text'
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

def seed():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    init_schema(cur)
    for path, data in seeds.items():
        cur.execute("INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
                    (path, data['value'], data['type']))
    conn.commit()
    conn.close()
    print("Database seeded with new core pages.")

if __name__ == "__main__":
    seed()
