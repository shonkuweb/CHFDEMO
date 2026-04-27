import sqlite3
import json

db_path = "chf_archive.db"

seeds = {
    # ── Architectural Harmony ──
    "arch/hero/title": {"value": "Architectural <span class='text-accent-bronze italic'>Harmony</span>", "type": "text"},
    "home/hero/subtitle": {"value": "Curating nature's rarest architectural wonders for refined spaces.", "type": "text"},
    "home/hero/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/videos/hero_vid.mp4", "type": "media"},
    "home/about/title": {"value": "The Botanical Sanctuary", "type": "text"},
    "home/philosophy/title": {"value": "The Art of Growth <br /><span class='italic text-primary'>in Deep Solitude</span>", "type": "text"},
    "home/philosophy/subtitle": {"value": "Not placed — revealed", "type": "text"},
    "home/philosophy/body": {"value": "<p>Some spaces exist.<br>Others breathe.</p><p>In the stillness of a well-composed environment, a single plant becomes more than presence — it becomes perception. It softens edges, absorbs noise, and introduces a living rhythm that architecture alone cannot achieve.</p><p>There is a science to this quiet influence — a natural ability to purify the air, regulate humidity, and restore balance to the senses. But beyond function, it carries something rarer: a feeling.</p><p>It doesn’t compete for attention.<br>It completes the space.</p><p>A subtle elevation —<br>one that lingers, quietly shaping how the space is seen, and how it is felt.</p>", "type": "longtext"},
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

    # ── Deep Solitude ──
    "deep/hero/title": {"value": "Deep <br />\n<span class='text-accent-bronze italic font-light drop-shadow-sm'>Solitude</span>", "type": "text"},
    "deep/hero/subtitle": {"value": "Bespoke landscapes designed for sensory calm and biophilic balance.", "type": "text"},
    "deep/block1/title": {"value": "Sensory Calm", "type": "text"},
    "deep/block1/body": {"value": "Golden light, water reflections, and a sculptural specimen create sensory calm — where negative ions, natural textures, and biophilic balance reduce stress, slow the mind, and elevate the entire outdoor experience.", "type": "longtext"},
    "deep/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_1.png", "type": "media"},
    "deep/block2/title": {"value": "Breathable Living", "type": "text"},
    "deep/block2/body": {"value": "Expansive light, open flow, and a single curated plant enhance oxygen levels and visual calm — proven to reduce cortisol and improve focus, creating a breathable, emotionally warm living environment.", "type": "longtext"},
    "deep/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_2.png", "type": "media"},
    "deep/block3/title": {"value": "Quietly Premium", "type": "text"},
    "deep/block3/body": {"value": "A refined interior anchored by a living specimen — naturally filtering air, softening acoustics, and enhancing well-being through biophilic design, creating a welcoming space that feels calm, intentional, and quietly premium.", "type": "longtext"},
    "deep/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_3.png", "type": "media"},
    "deep/block4/title": {"value": "Elevated Thinking", "type": "text"},
    "deep/block4/body": {"value": "Clean lines, controlled light, and a sculptural plant improve cognitive performance and reduce fatigue — bringing clarity, calm, and subtle vitality into a workspace designed for focus, decision-making, and elevated thinking.", "type": "longtext"},
    "deep/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_4.png", "type": "media"},
    "deep/closing/title": {"value": "A space that feels alive<br>\n<span class='text-accent-bronze italic mt-4 block'>is a space that inspires.</span>", "type": "longtext"},
    # ── Bonsai Collections ──
    "bonsai/hero/title": {"value": "Bonsai <span class='text-accent-bronze italic'>Collections</span>", "type": "text"},
    "bonsai/hero/subtitle": {"value": "Curating nature's rarest botanical wonders for refined spaces.", "type": "text"},
    "bonsai/block1/title": {"value": "A Living Architecture", "type": "text"},
    "bonsai/block1/body": {"value": "In landscape architecture, drawings capture a moment—but gardens don’t stand still. They grow, expand, compete, and transform.", "type": "longtext"},
    "bonsai/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_1.png", "type": "media"},
    "bonsai/block2/title": {"value": "Scale and Maturity", "type": "text"},
    "bonsai/block2/body": {"value": "As consulting horticulturists, we often see thoughtfully designed spaces challenged by plant selections that don’t account for scale or maturity.", "type": "longtext"},
    "bonsai/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_2.png", "type": "media"},
    "bonsai/block3/title": {"value": "Intentional Growth", "type": "text"},
    "bonsai/block3/body": {"value": "With the intent to not redefine but strengthen the designs, we ensure that plant selections are informed, intentional, and future-ready.", "type": "longtext"},
    "bonsai/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_3.png", "type": "media"},
    "bonsai/block4/title": {"value": "Enduring Vision", "type": "text"},
    "bonsai/block4/body": {"value": "With a strong foundation in plant knowledge, we ensure that every selection supports lasting architectural harmony.", "type": "longtext"},
    "bonsai/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_4.png", "type": "media"},
    "bonsai/closing/title": {"value": "We don’t just develop gardens.<br>\n<span class='text-accent-bronze italic mt-4 block'>We future-proof them.</span>", "type": "longtext"},

    # ── Full Grown Avenue Trees ──
    "avenue/hero/title": {"value": "Full Grown <span class='text-accent-bronze italic'>Avenue Trees</span>", "type": "text"},
    "avenue/hero/subtitle": {"value": "Curating nature's rarest botanical wonders for refined spaces.", "type": "text"},
    "avenue/block1/title": {"value": "A Living Architecture", "type": "text"},
    "avenue/block1/body": {"value": "In landscape architecture, drawings capture a moment—but gardens don’t stand still. They grow, expand, compete, and transform.", "type": "longtext"},
    "avenue/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_1.png", "type": "media"},
    "avenue/block2/title": {"value": "Scale and Maturity", "type": "text"},
    "avenue/block2/body": {"value": "As consulting horticulturists, we often see thoughtfully designed spaces challenged by plant selections that don’t account for scale or maturity.", "type": "longtext"},
    "avenue/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_2.png", "type": "media"},
    "avenue/block3/title": {"value": "Intentional Growth", "type": "text"},
    "avenue/block3/body": {"value": "With the intent to not redefine but strengthen the designs, we ensure that plant selections are informed, intentional, and future-ready.", "type": "longtext"},
    "avenue/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_3.png", "type": "media"},
    "avenue/block4/title": {"value": "Enduring Vision", "type": "text"},
    "avenue/block4/body": {"value": "With a strong foundation in plant knowledge, we ensure that every selection supports lasting architectural harmony.", "type": "longtext"},
    "avenue/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_4.png", "type": "media"},
    "avenue/closing/title": {"value": "We don’t just develop gardens.<br>\n<span class='text-accent-bronze italic mt-4 block'>We future-proof them.</span>", "type": "longtext"},

    # ── Exotic Indoor Plants ──
    "indoor/hero/title": {"value": "Exotic <span class='text-accent-bronze italic'>Indoor Plants</span>", "type": "text"},
    "indoor/hero/subtitle": {"value": "Curating nature's rarest botanical wonders for refined spaces.", "type": "text"},
    "indoor/block1/title": {"value": "A Living Architecture", "type": "text"},
    "indoor/block1/body": {"value": "In landscape architecture, drawings capture a moment—but gardens don’t stand still. They grow, expand, compete, and transform.", "type": "longtext"},
    "indoor/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_1.png", "type": "media"},
    "indoor/block2/title": {"value": "Scale and Maturity", "type": "text"},
    "indoor/block2/body": {"value": "As consulting horticulturists, we often see thoughtfully designed spaces challenged by plant selections that don’t account for scale or maturity.", "type": "longtext"},
    "indoor/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_2.png", "type": "media"},
    "indoor/block3/title": {"value": "Intentional Growth", "type": "text"},
    "indoor/block3/body": {"value": "With the intent to not redefine but strengthen the designs, we ensure that plant selections are informed, intentional, and future-ready.", "type": "longtext"},
    "indoor/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_3.png", "type": "media"},
    "indoor/block4/title": {"value": "Enduring Vision", "type": "text"},
    "indoor/block4/body": {"value": "With a strong foundation in plant knowledge, we ensure that every selection supports lasting architectural harmony.", "type": "longtext"},
    "indoor/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_4.png", "type": "media"},
    "indoor/closing/title": {"value": "We don’t just develop gardens.<br>\n<span class='text-accent-bronze italic mt-4 block'>We future-proof them.</span>", "type": "longtext"},

    # ── Curated Planters ──
    "curated-planters/hero/title": {"value": "Curated <span class='text-accent-bronze italic'>Plants</span>", "type": "text"},
    "curated-planters/hero/subtitle": {"value": "Curating nature's rarest botanical wonders for refined spaces.", "type": "text"},
    "curated-planters/block1/title": {"value": "A Living Architecture", "type": "text"},
    "curated-planters/block1/body": {"value": "In landscape architecture, drawings capture a moment—but gardens don’t stand still. They grow, expand, compete, and transform.", "type": "longtext"},
    "curated-planters/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_1.png", "type": "media"},
    "curated-planters/block2/title": {"value": "Scale and Maturity", "type": "text"},
    "curated-planters/block2/body": {"value": "As consulting horticulturists, we often see thoughtfully designed spaces challenged by plant selections that don’t account for scale or maturity.", "type": "longtext"},
    "curated-planters/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_2.png", "type": "media"},
    "curated-planters/block3/title": {"value": "Intentional Growth", "type": "text"},
    "curated-planters/block3/body": {"value": "With the intent to not redefine but strengthen the designs, we ensure that plant selections are informed, intentional, and future-ready.", "type": "longtext"},
    "curated-planters/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_3.png", "type": "media"},
    "curated-planters/block4/title": {"value": "Enduring Vision", "type": "text"},
    "curated-planters/block4/body": {"value": "With a strong foundation in plant knowledge, we ensure that every selection supports lasting architectural harmony.", "type": "longtext"},
    "curated-planters/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_4.png", "type": "media"},
    "curated-planters/closing/title": {"value": "We don’t just develop gardens.<br>\n<span class='text-accent-bronze italic mt-4 block'>We future-proof them.</span>", "type": "longtext"},

    # ── About Us ──
    "about/story/intro": {"value": "Calcutta Horticultural Farm (CHF) is more than a landscape firm; it is a living legacy—built on a deep, enduring respect for nature. Founded over four decades ago, we began with a simple belief: that plants are not mere decorations, but vital, dynamic entities that breathe life into any space.", "type": "longtext"},
    "about/story/title-1": {"value": "The Founding Era (1982)", "type": "text"},
    "about/story/image-1": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png", "type": "media"},
    "about/philosophy/patience-title": {"value": "Rooted in decades of horticultural mastery, CHF was established to bridge the gap between ornamental beauty and environmental harmony. Our early years were dedicated to cultivating rare, resilient plant species, establishing a foundation of trust with purists and enthusiasts alike. This was an era defined by patience, where understanding soil, climate, and growth patterns took precedence over rapid expansion.", "type": "longtext"},
    "about/story/title-2": {"value": "The Modern Vision", "type": "text"},
    "about/story/image-2": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/alipore_experience_center.png", "type": "media"},
    "about/philosophy/precision-title": {"value": "Today, CHF operates at the intersection of horticulture, landscape architecture, and lifestyle design. We curate botanical elements that elevate modern sanctuaries—from expansive estates to minimalist apartments. Our approach integrates rigorous botanical science with high-end aesthetic sensibilities, ensuring that every plant we introduce not only survives, but thrives within its architectural context.", "type": "longtext"},
    "about/philosophy/presence-title": {"value": "Cultivating Scale", "type": "text"},
    "about/story/image-3": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/expansive_nursery_muchisha.png", "type": "media"},
    "about/philosophy/presence-body": {"value": "Our operations are sustained by two expansive nurseries located in Alipore and Muchisha, encompassing acres of meticulously controlled environments. These facilities allow us to nurture full-grown avenue trees, exotic indoor plants, and delicate bonsai under the watchful eyes of expert agronomists. It is here that we prepare our plants for the transition from our care to your sanctuary, ensuring they arrive acclimatised and robust.", "type": "longtext"},
    
    # ── Global Settings ──
    "global/footer/copyright": {"value": "© 2026 CHF. All rights reserved. Crafted by Team ShonkuWeb", "type": "text"},
    "global/contact/email": {"value": "enquiry@chfbotanical.com", "type": "text"},
    "global/contact/phone": {"value": "+91 98300 98300", "type": "text"},
    # ── Curated Specimens ──
    "specimens/hero/title": {"value": "Curated <br />\n<span class='text-accent-bronze italic font-light drop-shadow-sm'>Specimens</span>", "type": "text"},
    "specimens/hero/subtitle": {"value": "Not added — introduced. Every specimen placed with purpose.", "type": "text"},
    "specimens/block1/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_1.png", "type": "media"},
    "specimens/block1/title": {"value": "Sensory Calm", "type": "text"},
    "specimens/block1/body": {"value": "Golden light, water reflections, and a sculptural specimen create sensory calm — where negative ions, natural textures, and biophilic balance reduce stress, slow the mind, and elevate the entire outdoor experience.", "type": "longtext"},
    "specimens/block2/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_2.png", "type": "media"},
    "specimens/block2/title": {"value": "Breathable Living", "type": "text"},
    "specimens/block2/body": {"value": "Expansive light, open flow, and a single curated plant enhance oxygen levels and visual calm — proven to reduce cortisol and improve focus, creating a breathable, emotionally warm living environment.", "type": "longtext"},
    "specimens/block3/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_3.png", "type": "media"},
    "specimens/block3/title": {"value": "Quietly Premium", "type": "text"},
    "specimens/block3/body": {"value": "A refined interior anchored by a living specimen — naturally filtering air, softening acoustics, and enhancing well-being through biophilic design, creating a welcoming space that feels calm, intentional, and quietly premium.", "type": "longtext"},
    "specimens/block4/image": {"value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_4.png", "type": "media"},
    "specimens/block4/title": {"value": "Collector's Edition", "type": "text"},
    "specimens/block4/body": {"value": "Singular botanical expressions reserved for spaces that demand rarity, permanence, and cultivated visual restraint.", "type": "longtext"},
    "specimens/closing/title": {"value": "Not just added.<br>\n<span class='text-accent-bronze italic font-light'>Introduced.</span>", "type": "text"},

}

# New Page/Collection style seeds
pages_seeds = [
]

categories_seeds = []


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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS home_trends_section (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            badge_label TEXT NOT NULL DEFAULT '',
            title_line1 TEXT NOT NULL DEFAULT '',
            title_highlight TEXT NOT NULL DEFAULT '',
            title_connector TEXT NOT NULL DEFAULT '',
            title_line3 TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def seed():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    init_schema(cur)
    
    # Seed Site Content
    for path, data in seeds.items():
        cur.execute("INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
                    (path, data['value'], data['type']))

    cur.execute('''
        INSERT OR IGNORE INTO home_trends_section
        (id, badge_label, title_line1, title_highlight, title_connector, title_line3, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        1,
        'The Current Landscape',
        'Botanical',
        'Trends',
        'for the',
        'Modern Collector',
        "An editorial exploration of nature's evolving role in high-end design."
    ))
    
    # Seed Pages
    for page in pages_seeds:
        cur.execute("INSERT OR REPLACE INTO pages (slug, title, titleLine1, titleLine2, subtitle, breadcrumb) VALUES (?, ?, ?, ?, ?, ?)",
                    (page['slug'], page['title'], page['titleLine1'], page['titleLine2'], page['subtitle'], page['breadcrumb']))
    
    # Seed Categories
    for cat in categories_seeds:
        # Generate a semi-stable ID from slug and title
        cat_id = f"{cat['page_slug']}-{cat['title'].lower().replace(' ', '-')}"
        cur.execute("INSERT OR REPLACE INTO categories (id, page_slug, label, title, description, image, ctaText, ctaLink) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (cat_id, cat['page_slug'], cat['label'], cat['title'], cat['description'], cat['image'], cat['ctaText'], cat['ctaLink']))
        
    conn.commit()
    conn.close()
    print("Database seeded with both Deep Solitude (Static) and Curated Specimens (Collection).")


if __name__ == "__main__":
    seed()
