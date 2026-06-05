import os
import json
import uuid
import sqlite3
import io
import re
import urllib.parse
import urllib.request
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from functools import lru_cache
from datetime import datetime, timedelta
from passlib.hash import argon2
import hashlib
from jose import jwt, JWTError
from typing import Optional
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
    print('[ENV] .env file loaded successfully.')
except ImportError:
    print('[ENV] python-dotenv not installed')

# ── Cloudflare R2 Setup ──────────────────────
try:
    import boto3
    from botocore.config import Config
    R2_ACCOUNT_ID   = os.environ.get('R2_ACCOUNT_ID')
    R2_ACCESS_KEY   = os.environ.get('R2_ACCESS_KEY_ID')
    R2_SECRET_KEY   = os.environ.get('R2_SECRET_ACCESS_KEY')
    R2_BUCKET       = os.environ.get('R2_BUCKET_NAME', 'chf-media')
    R2_PUBLIC_URL   = os.environ.get('R2_PUBLIC_URL', '').rstrip('/')

    R2_ENABLED = all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY])
    if R2_ENABLED:
        r2_client = boto3.client(
            's3',
            endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        print(f'[R2] Connected to bucket: {R2_BUCKET}')
    else:
        r2_client = None
except ImportError:
    R2_ENABLED = False
    r2_client = None

# ── FastAPI App & Auth Settings ─────────────
app = FastAPI(title="CHF API")
# Compress text responses to reduce transfer time.
app.add_middleware(GZipMiddleware, minimum_size=500)

SECRET_KEY = os.environ.get("JWT_SECRET", "DEV_Fallback_Secret_2026_!@#")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 Day

DB_PATH = os.environ.get("DB_PATH", "chf_archive.db")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join("assets", "images"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "80")) * 1024 * 1024

# Mount both the core assets and the uploads directory (if they differ)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
if UPLOAD_DIR != os.path.join("assets", "images"):
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# DB Handling
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# JWT Dependency
def get_current_admin(request: Request):
    token = request.cookies.get("admin_session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@lru_cache(maxsize=32)
def fetch_collection_data(slug):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE slug = ?", (slug,))
    page_row = cursor.fetchone()
    if not page_row:
        conn.close()
        return None
    cursor.execute("SELECT * FROM categories WHERE page_slug = ? ORDER BY display_order ASC", (slug,))
    cat_rows = cursor.fetchall()
    data = {"page": dict(page_row), "categories": [dict(row) for row in cat_rows]}
    conn.close()
    return data

@lru_cache(maxsize=64)
def fetch_site_content(prefix):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT path, value, type FROM site_content WHERE path LIKE ? ORDER BY path ASC", (f"{prefix}%",))
    rows = cursor.fetchall()
    conn.close()
    data = {row['path']: {'value': row['value'], 'type': row['type']} for row in rows}
    if prefix == "home":
        data.update(FIXED_HOME_HERO_MEDIA)
        data.update(FIXED_HOME_STAGING_MEDIA)
    if prefix == "arch":
        data.update(FIXED_ARCH_MEDIA)
    if prefix == "plant-center":
        data.update(FIXED_PLANT_CENTER_MEDIA)
    return data

def clear_cache():
    fetch_collection_data.cache_clear()
    fetch_site_content.cache_clear()

FIXED_HOME_HERO_MEDIA = {
    "home/hero/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/hero%20image%20desk%20and%20mobile%20view/chfherodesk.png",
        "type": "media",
    },
    "home/hero/mobile_media": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/hero%20image%20desk%20and%20mobile%20view/chfheromob.png",
        "type": "media",
    },
}
FIXED_HOME_STAGING_MEDIA = {
    "home/staging/feature1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/landscape%20staging/1%20(1).png",
        "type": "media",
    },
    "home/staging/feature2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/landscape%20staging/2%20(1).png",
        "type": "media",
    },
    "home/staging/feature3/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/landscape%20staging/3.png",
        "type": "media",
    },
}
ASSETS_CACHE_VERSION = "chf-closing-1"
PEC_IMAGE_BASE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/plant%20experience%20center"
PEC_HERO_IMAGE = f"{PEC_IMAGE_BASE}/9BF51B5D-7851-4D44-BF1D-F2B521F61DB2%20(1).png"
PEC_PHILOSOPHY_IMAGE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/media_bcec5110.png?t=1780033476946"
FIXED_PLANT_CENTER_COLLECT_MEDIA = {
    "plant-center/collect/plants/image": {
        "value": f"{PEC_IMAGE_BASE}/WhatsApp%20Image%202026-06-03%20at%202.29.19%20AM.jpeg",
        "type": "media",
    },
    "plant-center/collect/pots/image": {
        "value": f"{PEC_IMAGE_BASE}/WhatsApp%20Image%202026-06-03%20at%202.29.19%20AM%20(1).jpeg",
        "type": "media",
    },
    "plant-center/collect/figurines/image": {
        "value": f"{PEC_IMAGE_BASE}/WhatsApp%20Image%202026-06-03%20at%202.29.20%20AM.jpeg",
        "type": "media",
    },
    "plant-center/collect/garden-objects/image": {
        "value": f"{PEC_IMAGE_BASE}/WhatsApp%20Image%202026-06-03%20at%202.29.20%20AM%20(1).jpeg",
        "type": "media",
    },
}
FIXED_PLANT_CENTER_PHILOSOPHY_MEDIA = {
    "plant-center/philosophy/image": {
        "value": PEC_PHILOSOPHY_IMAGE,
        "type": "media",
    },
}
FIXED_PLANT_CENTER_HERO_MEDIA = {
    "plant-center/hero/image": {
        "value": PEC_HERO_IMAGE,
        "type": "media",
    },
}
FIXED_PLANT_CENTER_MEDIA = {
    **FIXED_PLANT_CENTER_HERO_MEDIA,
    **FIXED_PLANT_CENTER_COLLECT_MEDIA,
    **FIXED_PLANT_CENTER_PHILOSOPHY_MEDIA,
}
ARCH_IMAGE_BASE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/architectural-harmony"
FIXED_ARCH_MEDIA = {
    "arch/block1/image": {
        "value": f"{ARCH_IMAGE_BASE}/B75F2C1E-AE3A-4A10-9F6E-2F88CD2A0A15.png",
        "type": "media",
    },
    "arch/block3/image": {
        "value": f"{ARCH_IMAGE_BASE}/1B513C2D-3F24-4051-A8AE-DE5EA4609581.png",
        "type": "media",
    },
    "arch/timeline/year1/image": {
        "value": f"{ARCH_IMAGE_BASE}/1FC8B58D-15F6-429D-9493-1FBB93608635.png",
        "type": "media",
    },
    "arch/timeline/year34/image": {
        "value": f"{ARCH_IMAGE_BASE}/6A9FCFBF-63C2-43B7-8311-81F798D6DC87.png",
        "type": "media",
    },
    "arch/tomorrow/leaf": {
        "value": "assets/arch-harmony-leaf.png",
        "type": "media",
    },
}
PROTECTED_SITE_CONTENT_PATHS = (
    set(FIXED_HOME_HERO_MEDIA)
    | set(FIXED_HOME_STAGING_MEDIA)
    | set(FIXED_ARCH_MEDIA)
    | set(FIXED_PLANT_CENTER_MEDIA)
)

SITE_CONTENT_DEFAULTS = {
    "home/hero/image": {
        "value": FIXED_HOME_HERO_MEDIA["home/hero/image"]["value"],
        "type": "media",
    },
    "home/hero/mobile_media": {
        "value": FIXED_HOME_HERO_MEDIA["home/hero/mobile_media"]["value"],
        "type": "media",
    },
    "home/trends/card1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimens.png",
        "type": "media",
    },
    "home/trends/card1/title": {
        "value": "Biophilic Workspace",
        "type": "text",
    },
    "home/trends/card1/body": {
        "value": "Integrating verdant life into the professional sanctuary for cognitive clarity and architectural softness.",
        "type": "longtext",
    },
    "home/trends/card2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/architectural_harmony.png",
        "type": "media",
    },
    "home/trends/card2/title": {
        "value": "Rare Specimen Sculptures",
        "type": "text",
    },
    "home/trends/card2/body": {
        "value": "Curating singular botanical forms that serve as the focal point of minimalist, high-ceiling environments.",
        "type": "longtext",
    },
    "home/trends/card3/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png",
        "type": "media",
    },
    "home/trends/card3/title": {
        "value": "Living Walls",
        "type": "text",
    },
    "home/trends/card3/body": {
        "value": "Vertical ecosystems that redefine internal boundaries, offering a rhythmic pulse to static architecture.",
        "type": "longtext",
    },
    "home/staging/eyebrow": {
        "value": "Service as an Art Form",
        "type": "text",
    },
    "home/staging/title": {
        "value": "Landscape Staging",
        "type": "text",
    },
    "home/staging/body": {
        "value": "Layered landscape compositions that bring structure, softness, and living depth into contemporary spaces.",
        "type": "longtext",
    },
    "home/staging/cta": {
        "value": "Let's Create Something Living",
        "type": "text",
    },
    "home/staging/feature1/image": {
        "value": FIXED_HOME_STAGING_MEDIA["home/staging/feature1/image"]["value"],
        "type": "media",
    },
    "home/staging/feature1/title": {
        "value": "Intentional Layering",
        "type": "text",
    },
    "home/staging/feature1/body": {
        "value": "Thoughtful plant selection and spatial layering.",
        "type": "longtext",
    },
    "home/staging/feature2/image": {
        "value": FIXED_HOME_STAGING_MEDIA["home/staging/feature2/image"]["value"],
        "type": "media",
    },
    "home/staging/feature2/title": {
        "value": "Natural Integration",
        "type": "text",
    },
    "home/staging/feature2/body": {
        "value": "Seamless harmony between nature and architecture.",
        "type": "longtext",
    },
    "home/staging/feature3/image": {
        "value": FIXED_HOME_STAGING_MEDIA["home/staging/feature3/image"]["value"],
        "type": "media",
    },
    "home/staging/feature3/title": {
        "value": "Sensory Experience",
        "type": "text",
    },
    "home/staging/feature3/body": {
        "value": "Landscapes that engage the senses and elevate daily life.",
        "type": "longtext",
    },
    "home/philosophy/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/deepsolitudehero.png",
        "type": "media",
    },
    "plant-center/hero/image": {
        "value": PEC_HERO_IMAGE,
        "type": "media",
    },
    "plant-center/experience/card1/image": {
        "value": "",
        "type": "media",
    },
    "plant-center/experience/card2/image": {
        "value": "",
        "type": "media",
    },
    "plant-center/experience/card3/image": {
        "value": "",
        "type": "media",
    },
    "plant-center/experience/card4/image": {
        "value": "",
        "type": "media",
    },
    "plant-center/philosophy/image": {
        "value": PEC_PHILOSOPHY_IMAGE,
        "type": "media",
    },
    "plant-center/collect/plants/image": {
        "value": FIXED_PLANT_CENTER_COLLECT_MEDIA["plant-center/collect/plants/image"]["value"],
        "type": "media",
    },
    "plant-center/collect/pots/image": {
        "value": FIXED_PLANT_CENTER_COLLECT_MEDIA["plant-center/collect/pots/image"]["value"],
        "type": "media",
    },
    "plant-center/collect/figurines/image": {
        "value": FIXED_PLANT_CENTER_COLLECT_MEDIA["plant-center/collect/figurines/image"]["value"],
        "type": "media",
    },
    "plant-center/collect/garden-objects/image": {
        "value": FIXED_PLANT_CENTER_COLLECT_MEDIA["plant-center/collect/garden-objects/image"]["value"],
        "type": "media",
    },
    "arch/block1/body": {
        "value": "In landscape architecture, drawings capture a moment—but gardens don't stand still. They grow, expand, compete, and transform. Without a deep understanding of plant behaviour many designs begin to diverge from their original intent.",
        "type": "longtext",
    },
    "arch/intro/headline": {
        "value": "Design is Instant. Growth is Inevitable. We Plan for Both.",
        "type": "text",
    },
    "arch/intro/p2": {
        "value": "As consulting horticulturists, we often see thoughtfully designed spaces challenged by plant selections that don't account for scale or maturity. Fast growers are placed where restraint is essential. Foreground hedges are composed of species that eventually outgrow and obscure the very layers they were meant to frame. What appears harmonious on day one can lose its proportion and clarity with time.",
        "type": "longtext",
    },
    "arch/intro/callout": {
        "value": "This is where collaboration becomes critical.",
        "type": "text",
    },
    "arch/collab/title": {
        "value": "Our Collaborative Approach",
        "type": "text",
    },
    "arch/collab/body": {
        "value": "With the intent to not redefine but strengthen the designs, we as landscape developers work closely with landscape architects—either as consultants during the design phase or as collaborators during execution—to ensure that plant selections are informed, intentional, and future-ready.",
        "type": "longtext",
    },
    "arch/tomorrow/title": {
        "value": "Design with Tomorrow in Mind.",
        "type": "text",
    },
    "arch/tomorrow/p1": {
        "value": "By bringing horticultural depth into the conversation early, we help align design vision with plant behaviour, site conditions, and long-term growth patterns.",
        "type": "longtext",
    },
    "arch/tomorrow/body": {
        "value": "With a strong foundation in plant knowledge, we ensure that every selection supports lasting architectural harmony—not just immediate visual appeal.",
        "type": "longtext",
    },
    "arch/tomorrow/quote": {
        "value": "Because a successful landscape is not just about how it looks when installed—it's about how it evolves.",
        "type": "longtext",
    },
    "arch/block1/image": {
        "value": f"{ARCH_IMAGE_BASE}/B75F2C1E-AE3A-4A10-9F6E-2F88CD2A0A15.png",
        "type": "media",
    },
    "arch/block3/image": {
        "value": f"{ARCH_IMAGE_BASE}/1B513C2D-3F24-4051-A8AE-DE5EA4609581.png",
        "type": "media",
    },
    "arch/timeline/year1/image": {
        "value": f"{ARCH_IMAGE_BASE}/1FC8B58D-15F6-429D-9493-1FBB93608635.png",
        "type": "media",
    },
    "arch/timeline/year34/image": {
        "value": f"{ARCH_IMAGE_BASE}/6A9FCFBF-63C2-43B7-8311-81F798D6DC87.png",
        "type": "media",
    },
    "arch/tomorrow/leaf": {
        "value": "assets/arch-harmony-leaf.png",
        "type": "media",
    },
    "whiteglove/hero/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/whiteglove/0F00B042-06A1-4DFD-A901-187491BC03F0.png",
        "type": "media",
    },
    "whiteglove/beyond/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/whiteglove/B617BE96-4A0A-489F-A1F1-8A55C3350BC8.png",
        "type": "media",
    },
    "whiteglove/distinguished/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/whiteglove/560FC3C2-359F-46EB-8CA4-88FED5E5D0AE.png",
        "type": "media",
    },
    "landscaping-design/hero/title": {
        "value": "Landscaping Design <span class=\"text-accent-bronze italic\">&amp; Development</span>",
        "type": "text",
    },
    "landscaping-design/hero/subtitle": {
        "value": "Conceptual precision translated into enduring green environments.",
        "type": "text",
    },
    "landscape-staging/hero/title": {
        "value": "Living Landscape,<br>Beautifully Composed",
        "type": "text",
    },
    "landscape-staging/hero/subtitle": {
        "value": "Carefully orchestrated plant palettes<br>that introduce texture, movement and<br>natural harmony into modern spaces.",
        "type": "text",
    },
    "plant-supply/hero/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/plant%20supply/C1BC3826-BEC5-4D93-BB44-74EA3345E674.png",
        "type": "media",
    },
    "plant-supply/climate/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/plant%20supply/60103D44-2E2A-41C0-AF4E-A00060F0D52C.png",
        "type": "media",
    },
    "plant-supply/quality/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/plant%20supply/F578408D-701F-46E5-84F7-F298AC4586F4.png",
        "type": "media",
    },
    "plant-supply/finished/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/plant%20supply/53F55AD3-A8A0-4401-9C10-93292959586A.png",
        "type": "media",
    },
    "plant-supply/hero/title": {
        "value": "Plant <span class=\"text-accent-bronze italic\">Supply</span>",
        "type": "text",
    },
    "plant-supply/hero/subtitle": {
        "value": "Sourcing resilient plant material for premium landscapes.",
        "type": "text",
    },
    "garden-maintenance/hero/title": {
        "value": "Garden <span class=\"text-accent-bronze italic\">Maintenance</span>",
        "type": "text",
    },
    "garden-maintenance/hero/subtitle": {
        "value": "Disciplined care routines that protect design intent year-round.",
        "type": "text",
    },
    "biophilic-workspace/hero/title": {
        "value": "Biophilic <span class=\"text-accent-bronze italic\">Workspace</span>",
        "type": "text",
    },
    "biophilic-workspace/hero/subtitle": {
        "value": "Integrating verdant life into professional sanctuaries for clarity, composure, and spatial softness.",
        "type": "text",
    },
    "biophilic-workspace/block1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_1.png",
        "type": "media",
    },
    "biophilic-workspace/block1/title": {
        "value": "Focused Work Zones",
        "type": "text",
    },
    "biophilic-workspace/block1/body": {
        "value": "Strategic greenery near desks and transition corridors reduces visual fatigue and helps teams sustain deeper focus throughout long work cycles.",
        "type": "longtext",
    },
    "biophilic-workspace/block2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_2.png",
        "type": "media",
    },
    "biophilic-workspace/block2/title": {
        "value": "Air and Acoustic Balance",
        "type": "text",
    },
    "biophilic-workspace/block2/body": {
        "value": "Plant-led layering softens hard interiors, improves perceived air quality, and contributes to calmer acoustics across open-plan environments.",
        "type": "longtext",
    },
    "rare-specimen-sculptures/hero/title": {
        "value": "Rare Specimen <span class=\"text-accent-bronze italic\">Sculptures</span>",
        "type": "text",
    },
    "rare-specimen-sculptures/hero/subtitle": {
        "value": "Singular botanical forms curated as statement pieces for refined residential and hospitality architecture.",
        "type": "text",
    },
    "rare-specimen-sculptures/block1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_3.png",
        "type": "media",
    },
    "rare-specimen-sculptures/block1/title": {
        "value": "Architectural Presence",
        "type": "text",
    },
    "rare-specimen-sculptures/block1/body": {
        "value": "Each specimen is selected for maturity, silhouette, and sculptural character to anchor space with botanical authority.",
        "type": "longtext",
    },
    "rare-specimen-sculptures/block2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_4.png",
        "type": "media",
    },
    "rare-specimen-sculptures/block2/title": {
        "value": "Collector-Led Curation",
        "type": "text",
    },
    "rare-specimen-sculptures/block2/body": {
        "value": "We align plant provenance, form, and long-term care protocols with each collector's design intent and lifestyle rhythm.",
        "type": "longtext",
    },
    "living-walls/hero/title": {
        "value": "Living <span class=\"text-accent-bronze italic\">Walls</span>",
        "type": "text",
    },
    "living-walls/hero/subtitle": {
        "value": "Vertical ecosystems that transform boundaries into breathing surfaces with lasting visual rhythm.",
        "type": "text",
    },
    "living-walls/block1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/architectural_harmony.png",
        "type": "media",
    },
    "living-walls/block1/title": {
        "value": "Engineered Vertical Ecology",
        "type": "text",
    },
    "living-walls/block1/body": {
        "value": "We design irrigation, species layering, and maintenance access as one integrated system so the wall remains healthy and visually composed over time.",
        "type": "longtext",
    },
    "living-walls/block2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png",
        "type": "media",
    },
    "living-walls/block2/title": {
        "value": "Spatial Softening",
        "type": "text",
    },
    "living-walls/block2/body": {
        "value": "Living walls soften rigid architecture, improve ambience, and create an immersive natural experience in high-value interior environments.",
        "type": "longtext",
    },
    "deep/hero/title": {
        "value": "Deep <br /><span class=\"text-accent-bronze italic font-light drop-shadow-sm\">Solitude</span>",
        "type": "text",
    },
    "deep/hero/subtitle": {
        "value": "Not added — introduced. Every specimen placed with purpose.",
        "type": "text",
    },
    "deep/block1/title": {
        "value": "Sensory Calm",
        "type": "text",
    },
    "deep/block1/body": {
        "value": "Golden light, water reflections, and a sculptural specimen create sensory calm — where negative ions, natural textures, and biophilic balance reduce stress, slow the mind, and elevate the entire outdoor experience.",
        "type": "longtext",
    },
    "deep/block1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_1.png",
        "type": "media",
    },
    "deep/block2/title": {
        "value": "Breathable Living",
        "type": "text",
    },
    "deep/block2/body": {
        "value": "Expansive light, open flow, and a single curated plant enhance oxygen levels and visual calm — proven to reduce cortisol and improve focus, creating a breathable, emotionally warm living environment.",
        "type": "longtext",
    },
    "deep/block2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_2.png",
        "type": "media",
    },
    "deep/block3/title": {
        "value": "Quietly Premium",
        "type": "text",
    },
    "deep/block3/body": {
        "value": "A refined interior anchored by a living specimen — naturally filtering air, softening acoustics, and enhancing well-being through biophilic design, creating a welcoming space that feels calm, intentional, and quietly premium.",
        "type": "longtext",
    },
    "deep/block3/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_3.png",
        "type": "media",
    },
    "deep/block4/title": {
        "value": "Elevated Thinking",
        "type": "text",
    },
    "deep/block4/body": {
        "value": "Clean lines, controlled light, and a sculptural plant improve cognitive performance and reduce fatigue — bringing clarity, calm, and subtle vitality into a workspace designed for focus, decision-making, and elevated thinking.",
        "type": "longtext",
    },
    "deep/block4/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimen_4.png",
        "type": "media",
    },

}

HOME_TRENDS_DEFAULTS = {
    "badge_label": "The Current Landscape",
    "title_line1": "Botanical",
    "title_highlight": "Trends",
    "title_connector": "for the",
    "title_line3": "Modern Collector",
    "description": "An editorial exploration of nature's evolving role in high-end design.",
}

AVENUE_EXTRA_BLOCKS = [
    ("Canopy Continuity", "From boulevard medians to estate driveways, consistent canopy rhythm gives movement and coherence to long linear spaces. Each alignment is selected for mature spread, branching behaviour, and maintenance practicality."),
    ("Root-Zone Intelligence", "Avenue trees fail early when underground conditions are ignored. We map soil depth, drainage, and hardscape pressure before planting, so root systems establish with long-term structural stability."),
    ("Seasonal Character", "A layered avenue should evolve gracefully across seasons. We curate flowering cycles, leaf texture, and tonal contrast so streetscapes retain visual depth beyond a single blooming window."),
    ("Wind and Exposure Planning", "Large-form trees must withstand corridor winds and reflected heat. Species choices are calibrated to site exposure, reducing failure risk while preserving the intended architectural silhouette."),
    ("Maintenance by Design", "Pruning regimes, irrigation access, and replacement strategies are considered at planning stage. This keeps the avenue visually disciplined while reducing operational surprises over time."),
    ("Arrival Experience", "The first 30 seconds of arrival define perception. We use tree sequencing and spacing to create a composed procession that feels both grand and grounded."),
    ("Legacy-Scale Outcomes", "A successful avenue is measured in decades, not months. Our approach combines horticultural foresight and execution discipline so the landscape matures with clarity and intent."),
]

for idx, (title, body) in enumerate(AVENUE_EXTRA_BLOCKS, start=5):
    image_seed = ((idx - 1) % 4) + 1
    SITE_CONTENT_DEFAULTS[f"avenue/block{idx}/image"] = {
        "value": f"https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/arch_zigzag_{image_seed}.png",
        "type": "media",
    }
    SITE_CONTENT_DEFAULTS[f"avenue/block{idx}/title"] = {
        "value": title,
        "type": "text",
    }
    SITE_CONTENT_DEFAULTS[f"avenue/block{idx}/body"] = {
        "value": body,
        "type": "longtext",
    }

LANDSCAPING_BLOCKS = [
    ("Site-Led Concept Planning", "Every project begins with reading the land: light, soil, circulation, and architectural language. We shape planting intent and hardscape rhythm so aesthetics and environmental logic align from day one.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_site_planning.jpg"),
    ("Material and Plant Integration", "Our design-development workflow unifies botanical palettes, grading, stone, and built edges into one coherent system. This avoids disconnected execution and preserves spatial clarity.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_material_integration.jpg"),
    ("Execution-Level Detailing", "From planting density to irrigation zoning, details are developed for real-world buildability. The result is a landscape that performs as elegantly as it appears.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_execution_detailing.jpg"),
    ("Post-Completion Evolution", "We design for years ahead, not just launch day. Growth behavior, replacement strategy, and seasonal transitions are considered upfront to keep the landscape refined over time.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_post_completion.jpg"),
]

LANDSCAPE_STAGING_BLOCKS = [
    ("Arrival Composition", "We stage entrances, patios, terraces, and event-facing green zones so the first view feels balanced, lush, and ready for use.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_site_planning.jpg"),
    ("Layered Visual Depth", "Tall forms, ground textures, planters, and focal specimens are arranged to create depth without overwhelming the architecture.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_material_integration.jpg"),
    ("Event-Ready Greenery", "Plant material, containers, and placement are coordinated for openings, photoshoots, residences, and hospitality spaces that need immediate polish.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_execution_detailing.jpg"),
    ("Refinement After Placement", "After staging, we tune spacing, orientation, irrigation access, and care notes so the composition remains composed beyond installation day.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_post_completion.jpg"),
]

PLANT_SUPPLY_BLOCKS = [
    ("Curated Plant Procurement", "We source healthy, structurally sound plant material from trusted growers, with species calibrated to project context, climate, and desired visual maturity.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_procurement.jpg"),
    ("Nursery Quality Audit", "Before dispatch, every batch is evaluated for root health, branch structure, pest status, and moisture condition to reduce replacement risk on site.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_quality_audit.jpg"),
    ("Climate-Matched Selection", "Species are shortlisted based on exposure, local humidity, soil profile, and irrigation capacity so delivered plants establish quickly and reliably.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_climate_matched.jpg"),
    ("Logistics and Staging Control", "Transit sequencing, loading method, and staging windows are planned to preserve plant vitality between nursery pickup and final placement.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_logistics_control.jpg"),
]

GARDEN_MAINTENANCE_BLOCKS = [
    ("Seasonal Maintenance Programming", "Care calendars are tuned to growth cycles, weather shifts, and flowering behavior so each zone receives intervention at the right moment.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_seasonal_programming.jpg"),
    ("Pruning and Canopy Discipline", "Formative pruning, thinning, and canopy balancing maintain proportion, sightlines, and plant health without compromising architectural composition.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_canopy_discipline.jpg"),
    ("Nutrition and Soil Vitality", "Targeted nutrient plans and soil-conditioning routines restore vigor, support root stability, and keep ornamental quality consistently high.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_soil_vitality.jpg"),
    ("Preventive Plant Health Monitoring", "Routine scouting identifies stress signals early, enabling low-impact corrective action before issues spread across the landscape.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_health_monitoring.jpg"),
]

for idx, (title, body, image_url) in enumerate(LANDSCAPING_BLOCKS, start=1):
    SITE_CONTENT_DEFAULTS[f"landscaping-design/block{idx}/image"] = {
        "value": image_url,
        "type": "media",
    }
    SITE_CONTENT_DEFAULTS[f"landscaping-design/block{idx}/title"] = {
        "value": title,
        "type": "text",
    }
    SITE_CONTENT_DEFAULTS[f"landscaping-design/block{idx}/body"] = {
        "value": body,
        "type": "longtext",
    }

for idx, (title, body, image_url) in enumerate(LANDSCAPE_STAGING_BLOCKS, start=1):
    SITE_CONTENT_DEFAULTS[f"landscape-staging/block{idx}/image"] = {
        "value": image_url,
        "type": "media",
    }
    SITE_CONTENT_DEFAULTS[f"landscape-staging/block{idx}/title"] = {
        "value": title,
        "type": "text",
    }
    SITE_CONTENT_DEFAULTS[f"landscape-staging/block{idx}/body"] = {
        "value": body,
        "type": "longtext",
    }

for idx, (title, body, image_url) in enumerate(PLANT_SUPPLY_BLOCKS, start=1):
    SITE_CONTENT_DEFAULTS[f"plant-supply/block{idx}/image"] = {
        "value": image_url,
        "type": "media",
    }
    SITE_CONTENT_DEFAULTS[f"plant-supply/block{idx}/title"] = {
        "value": title,
        "type": "text",
    }
    SITE_CONTENT_DEFAULTS[f"plant-supply/block{idx}/body"] = {
        "value": body,
        "type": "longtext",
    }

for idx, (title, body, image_url) in enumerate(GARDEN_MAINTENANCE_BLOCKS, start=1):
    SITE_CONTENT_DEFAULTS[f"garden-maintenance/block{idx}/image"] = {
        "value": image_url,
        "type": "media",
    }
    SITE_CONTENT_DEFAULTS[f"garden-maintenance/block{idx}/title"] = {
        "value": title,
        "type": "text",
    }
    SITE_CONTENT_DEFAULTS[f"garden-maintenance/block{idx}/body"] = {
        "value": body,
        "type": "longtext",
    }

def migrate_legacy_site_content_keys():
    """
    Keeps DB paths aligned with data-cms keys used by live templates.
    This prevents admin updates from writing to orphaned keys.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT value, type FROM site_content WHERE path = ?", ("plant-center/hero/media",))
    legacy_row = cur.fetchone()
    cur.execute("SELECT 1 FROM site_content WHERE path = ?", ("plant-center/hero/video",))
    has_new_video_key = cur.fetchone() is not None

    if legacy_row and not has_new_video_key:
        cur.execute(
            "INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
            ("plant-center/hero/video", legacy_row["value"], legacy_row["type"] or "media"),
        )
    if legacy_row:
        cur.execute("DELETE FROM site_content WHERE path = ?", ("plant-center/hero/media",))

    # The Plant Experience Center was rebuilt as an image-led landing page.
    # Remove legacy video/intro/gallery keys so the admin panel shows only
    # image slots that are still used by the live template.
    obsolete_plant_center_paths = (
        "plant-center/hero/video",
        "plant-center/hero/title",
        "plant-center/hero/subtitle",
        "plant-center/intro/title",
        "plant-center/intro/body",
        "plant-center/gallery/img1",
        "plant-center/gallery/img2",
        "plant-center/gallery/img3",
    )
    cur.executemany(
        "DELETE FROM site_content WHERE path = ?",
        [(path,) for path in obsolete_plant_center_paths],
    )

    # Closing copy is hardcoded in templates; purge CMS keys.
    cur.execute("DELETE FROM site_content WHERE path LIKE '%/closing/%'")

    # Curated Planters rename migration:
    # - site_content path prefix curated/* -> curated-planters/*
    # - page slug curated-plants -> curated-planters
    # - categories page_slug curated-plants -> curated-planters
    cur.execute(
        """
        UPDATE site_content
        SET path = REPLACE(path, 'curated/', 'curated-planters/')
        WHERE path LIKE 'curated/%'
        """
    )
    cur.execute(
        "UPDATE pages SET slug = ?, breadcrumb = REPLACE(breadcrumb, 'Curated Plants', 'Curated Planters') WHERE slug = ?",
        ("curated-planters", "curated-plants")
    )
    cur.execute(
        "UPDATE categories SET page_slug = ? WHERE page_slug = ?",
        ("curated-planters", "curated-plants")
    )

    # The homepage Landscape Staging image slots intentionally start blank.
    # Clear only the earlier built-in defaults; preserve any custom URLs added later.
    stale_staging_images = {
        "home/staging/feature1/image": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_site_planning.jpg",
        "home/staging/feature2/image": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_material_integration.jpg",
        "home/staging/feature3/image": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_execution_detailing.jpg",
    }
    for path, stale_value in stale_staging_images.items():
        cur.execute(
            "UPDATE site_content SET value = ? WHERE path = ? AND value = ?",
            ("", path, stale_value),
        )

    for path, payload in FIXED_HOME_STAGING_MEDIA.items():
        cur.execute(
            "UPDATE site_content SET value = ? WHERE path = ? AND (value = '' OR value IS NULL)",
            (payload["value"], path),
        )
        cur.execute("SELECT 1 FROM site_content WHERE path = ?", (path,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO site_content (path, value, type) VALUES (?, ?, ?)",
                (path, payload["value"], payload["type"]),
            )


    # Remove bundled placeholder media from CMS rows. Public pages should show
    # only URLs that were intentionally published through admin.
    stale_media_patterns = [
        "%/assets/arch_zigzag_%.png",
        "%/assets/images/deepsolitudehero.png",
        "%/assets/images/services/architectural_harmony.png",
        "%/assets/images/services/curated_specimen_%.png",
        "%/assets/images/services/curated_specimens.png",
        "%/assets/images/services/garden_maintenance_%.jpg",
        "%/assets/images/services/landscape_design_%.jpg",
        "%/assets/images/services/plant_supply_%.jpg",
        "%/assets/images/services/white_glove_%.png",
    ]
    for pattern in stale_media_patterns:
        cur.execute(
            "UPDATE site_content SET value = ? WHERE type = ? AND value LIKE ?",
            ("", "media", pattern),
        )

    # Architectural Harmony uses a fixed image set. Drop legacy block keys and
    # purge stale placeholder media so production cannot resurrect old backgrounds.
    obsolete_arch_paths = (
        "arch/block2/image",
        "arch/block2/title",
        "arch/block2/body",
        "arch/block4/image",
        "arch/block4/title",
        "arch/block4/body",
        "arch/block1/title",
        "arch/block3/title",
        "arch/hero/title",
    )
    cur.executemany(
        "DELETE FROM site_content WHERE path = ?",
        [(path,) for path in obsolete_arch_paths],
    )
    cur.execute(
        """
        DELETE FROM site_content
        WHERE path LIKE 'arch/%'
          AND type = 'media'
          AND path NOT IN ({})
        """.format(",".join("?" * len(FIXED_ARCH_MEDIA))),
        tuple(FIXED_ARCH_MEDIA.keys()),
    )
    for path, payload in FIXED_ARCH_MEDIA.items():
        cur.execute(
            "INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
            (path, payload["value"], payload["type"]),
        )

    cur.execute(
        """
        UPDATE categories
        SET ctaLink = REPLACE(REPLACE(ctaLink, 'inquiry.html', 'enquiry.html'), 'inquiry', 'enquiry')
        WHERE ctaLink LIKE '%inquiry%'
        """
    )

    # If a row still exactly matches a bundled default, treat it as seed content,
    # not authored CMS content. This preserves any admin-published value that
    # differs from the old defaults while preventing old copy from resurfacing.
    protected_default_prefixes = ("global/", "home/staging/")
    for path, payload in SITE_CONTENT_DEFAULTS.items():
        if path in PROTECTED_SITE_CONTENT_PATHS or path.startswith(protected_default_prefixes):
            continue
        default_value = str(payload.get("value") or "")
        if not default_value:
            continue
        cur.execute(
            "UPDATE site_content SET value = ? WHERE path = ? AND value = ?",
            ("", path, default_value),
        )

    for path, payload in SITE_CONTENT_DEFAULTS.items():
        cur.execute("SELECT value FROM site_content WHERE path = ?", (path,))
        row = cur.fetchone()
        if path in PROTECTED_SITE_CONTENT_PATHS:
            cur.execute(
                "INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
                (path, payload["value"], payload["type"]),
            )
            continue

        if row is None:
            cur.execute(
                "INSERT INTO site_content (path, value, type) VALUES (?, ?, ?)",
                (path, "", payload["type"]),
            )
            continue

    conn.commit()
    conn.close()
    clear_cache()

def ensure_sync_state_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            version INTEGER NOT NULL
        )
    """)
    cur.execute("INSERT OR IGNORE INTO sync_state (key, version) VALUES (?, ?)", ("global", int(time.time() * 1000)))
    conn.commit()
    conn.close()

def ensure_home_trends_section_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS home_trends_section (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            badge_label TEXT NOT NULL DEFAULT '',
            title_line1 TEXT NOT NULL DEFAULT '',
            title_highlight TEXT NOT NULL DEFAULT '',
            title_connector TEXT NOT NULL DEFAULT '',
            title_line3 TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(
        """
        INSERT OR IGNORE INTO home_trends_section
            (id, badge_label, title_line1, title_highlight, title_connector, title_line3, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            HOME_TRENDS_DEFAULTS["badge_label"],
            HOME_TRENDS_DEFAULTS["title_line1"],
            HOME_TRENDS_DEFAULTS["title_highlight"],
            HOME_TRENDS_DEFAULTS["title_connector"],
            HOME_TRENDS_DEFAULTS["title_line3"],
            HOME_TRENDS_DEFAULTS["description"],
        ),
    )
    conn.commit()
    conn.close()

def fetch_home_trends_section():
    ensure_home_trends_section_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT badge_label, title_line1, title_highlight, title_connector, title_line3, description
        FROM home_trends_section
        WHERE id = 1
        """
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return HOME_TRENDS_DEFAULTS.copy()
    return {
        "badge_label": row["badge_label"],
        "title_line1": row["title_line1"],
        "title_highlight": row["title_highlight"],
        "title_connector": row["title_connector"],
        "title_line3": row["title_line3"],
        "description": row["description"],
    }

def get_sync_version():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT version FROM sync_state WHERE key = ?", ("global",))
    row = cur.fetchone()
    conn.close()
    if not row:
        return int(time.time() * 1000)
    return int(row["version"])

def bump_sync_version():
    ensure_sync_state_table()
    version = int(time.time() * 1000)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE sync_state SET version = ? WHERE key = ?", (version, "global"))
    conn.commit()
    conn.close()
    return version

def purge_cloudflare_cache(urls: list[str] = None):
    """
    Optional Cloudflare cache purge for production CDN consistency.
    Enabled only when CF_API_TOKEN and CF_ZONE_ID are configured.
    """
    cf_api_token = os.environ.get("CF_API_TOKEN")
    cf_zone_id = os.environ.get("CF_ZONE_ID")
    if not cf_api_token or not cf_zone_id:
        return

    endpoint = f"https://api.cloudflare.com/client/v4/zones/{cf_zone_id}/purge_cache"
    payload = {"files": urls} if urls else {"purge_everything": True}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {cf_api_token}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            response_payload = json.loads(res.read() or b"{}")
            if not response_payload.get("success"):
                print(f"[Cloudflare] Purge failed: {response_payload}")
            else:
                print("[Cloudflare] Cache purge successful.")
    except Exception as e:
        print(f"[Cloudflare] Cache purge error: {e}")

MANAGED_MEDIA_FILENAME_RE = re.compile(r"^media_[a-f0-9]{8}\.[a-z0-9]+$", re.IGNORECASE)

def _sanitize_media_reference(raw_url: str) -> str:
    if not raw_url:
        return ""
    cleaned = str(raw_url).strip().split("?", 1)[0].split("#", 1)[0].strip()
    if not cleaned:
        return ""
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme in ("http", "https"):
        return parsed.path.lstrip("/")
    return cleaned.lstrip("/")

def _is_managed_media_filename(path: str) -> bool:
    return bool(path) and bool(MANAGED_MEDIA_FILENAME_RE.match(os.path.basename(path)))

def delete_old_media_if_needed(old_url: str):
    """
    Deletes previously uploaded managed media before replacing it.
    Only auto-generated media_<id>.* objects are eligible for deletion.
    """
    path = _sanitize_media_reference(old_url)
    if not _is_managed_media_filename(path):
        return

    # R2-managed upload URLs
    if R2_ENABLED and r2_client and R2_PUBLIC_URL:
        absolute_base = R2_PUBLIC_URL.rstrip("/") + "/"
        if str(old_url).startswith(absolute_base):
            try:
                r2_client.delete_object(Bucket=R2_BUCKET, Key=path)
                print(f"[R2] Deleted replaced media: {path}")
            except Exception as e:
                print(f"[R2] Failed deleting old media {path}: {e}")
            return

    # Local managed upload URLs
    local_file_path = None
    if path.startswith("assets/images/"):
        local_file_path = path
    elif path.startswith("uploads/"):
        local_file_path = os.path.join(UPLOAD_DIR, path[len("uploads/"):])

    if local_file_path:
        try:
            if os.path.isfile(local_file_path):
                os.remove(local_file_path)
                print(f"[LOCAL] Deleted replaced media: {local_file_path}")
        except Exception as e:
            print(f"[LOCAL] Failed deleting old media {local_file_path}: {e}")

def verify_turnstile_or_raise(turnstile_response: Optional[str]):
    turnstile_secret = os.environ.get("TURNSTILE_SECRET")
    # If Turnstile is not configured, allow local/dev flows.
    if not turnstile_secret:
        return
    if not turnstile_response:
        raise HTTPException(status_code=403, detail="Missing bot protection token")
    verify_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    payload = urllib.parse.urlencode({
        "secret": turnstile_secret,
        "response": turnstile_response
    }).encode("utf-8")
    try:
        req = urllib.request.Request(verify_url, data=payload)
        with urllib.request.urlopen(req) as res:
            outcome = json.loads(res.read())
            if not outcome.get("success"):
                raise HTTPException(status_code=403, detail="Bot protection validation failed")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="Bot protection network error")

@app.middleware("http")
async def add_api_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif path.startswith("/assets/") or path.startswith("/uploads/"):
        # Long-lived immutable cache for static assets.
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    elif (
        response.headers.get("content-type", "").startswith("text/html")
        and not path.startswith("/admin")
        and not path.startswith("/api/")
    ):
        # Avoid serving stale HTML from edge cache (prevents old inline fallbacks flashing before CMS).
        response.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        response.headers.setdefault("Pragma", "no-cache")
    return response

def purge_deploy_asset_cache():
    """Purge versioned static assets from Cloudflare after code deploys."""
    origin = os.environ.get("SITE_PUBLIC_ORIGIN", "").strip().rstrip("/")
    if not origin:
        return
    purge_cloudflare_cache(
        [
            f"{origin}/assets/animations.css",
            f"{origin}/assets/animations.css?v={ASSETS_CACHE_VERSION}",
        ]
    )

@app.on_event("startup")
def startup_init_sync_state():
    migrate_legacy_site_content_keys()
    ensure_sync_state_table()
    ensure_home_trends_section_table()
    purge_deploy_asset_cache()

# ── Endpoints ───────────────────────────────

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verify password against Argon2 or SHA256 fallback hash."""
    if stored_hash.startswith("$argon2"):
        return argon2.verify(plain_password, stored_hash)
    elif stored_hash.startswith("sha256$"):
        # Fallback format: sha256$<salt>$<hex_digest>
        parts = stored_hash.split("$")
        if len(parts) == 3:
            salt = parts[1]
            expected_hex = parts[2]
            computed = hashlib.sha256((salt + plain_password).encode()).hexdigest()
            return computed == expected_hex
    return False

def upgrade_hash_if_needed(username: str, plain_password: str, stored_hash: str):
    """Auto-upgrade SHA256 hashes to Argon2 on successful login."""
    if not stored_hash.startswith("$argon2"):
        try:
            new_hash = argon2.hash(plain_password)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE admins SET password_hash = ? WHERE username = ?", (new_hash, username))
            conn.commit()
            conn.close()
            print(f"[AUTH] Upgraded password hash to Argon2 for user: {username}")
        except Exception as e:
            print(f"[AUTH] Hash upgrade failed (non-critical): {e}")

@app.post("/api/login")
async def login(
    request: Request,
    response: Response, 
    username: str = Form(...), 
    password: str = Form(...),
    cf_turnstile_response: str = Form(None)
):
    verify_turnstile_or_raise(cf_turnstile_response)

    # Verify credentials
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM admins WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    stored_hash = row["password_hash"]
    if not verify_password(password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Auto-upgrade old SHA256 hashes to Argon2
    upgrade_hash_if_needed(username, password, stored_hash)
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + access_token_expires
    to_encode = {"sub": username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    # Detect HTTPS from nginx X-Forwarded-Proto header, fall back to env var
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    is_https = forwarded_proto == "https" or os.environ.get("HTTPS_ENABLED", "false").lower() == "true"
    # Only set Secure flag if the end-user is actually on HTTPS
    use_secure = forwarded_proto == "https" if forwarded_proto else is_https
    response.set_cookie(
        key="admin_session", 
        value=encoded_jwt, 
        httponly=True, 
        secure=use_secure, 
        samesite="lax", 
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    return {"message": "Success"}

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("admin_session")
    return {"message": "Logged out"}

@app.get("/api/admin/me")
async def admin_me(admin: str = Depends(get_current_admin)):
    return {"username": admin}

@app.post("/api/admin/change-password")
async def change_admin_password(
    request: Request,
    admin: str = Depends(get_current_admin)
):
    body = await request.json()
    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")
    cf_turnstile_response = body.get("cf_turnstile_response")

    verify_turnstile_or_raise(cf_turnstile_response)

    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Current and new passwords are required")
    if len(new_password) < 10:
        raise HTTPException(status_code=400, detail="New password must be at least 10 characters")
    if new_password == current_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM admins WHERE username = ?", (admin,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Admin account not found")

    if not verify_password(current_password, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = argon2.hash(new_password)
    cur.execute("UPDATE admins SET password_hash = ? WHERE username = ?", (new_hash, admin))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Password updated"}

@app.get("/api/site-content")
async def get_site_content(page: str = ''):
    return fetch_site_content(page)

@app.get("/api/data")
async def get_data(slug: str):
    data = fetch_collection_data(slug)
    if not data:
        raise HTTPException(status_code=404, detail="Not found")
    return data

@app.get("/api/sync-version")
async def get_sync_version_api():
    return {"version": get_sync_version()}

@app.get("/api/home-trends-section")
async def get_home_trends_section_api():
    return fetch_home_trends_section()

@app.get("/api/r2-media")
async def get_r2_media(url: str):
    """
    Streams private/public R2 objects through the backend.
    This keeps Cloudflare-hosted video visible even when direct object access is blocked.
    """
    if not R2_ENABLED or not r2_client:
        raise HTTPException(status_code=503, detail="R2 is not configured")

    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host.endswith(".r2.dev"):
        raise HTTPException(status_code=400, detail="Only r2.dev URLs are supported")

    key = parsed.path.lstrip("/")
    key = urllib.parse.unquote(key)
    if not key:
        raise HTTPException(status_code=400, detail="Invalid R2 object key")

    try:
        obj = r2_client.get_object(Bucket=R2_BUCKET, Key=key)
        content_type = obj.get("ContentType") or "application/octet-stream"
        body = obj["Body"]
        return StreamingResponse(body, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"R2 media not found: {str(e)}")

@app.post("/api/upload")
async def upload_file(request: Request, admin: str = Depends(get_current_admin)):
    filename_header = request.headers.get('X-Filename', 'upload.jpg')
    old_url_header = request.headers.get('X-Old-Url', '').strip()
    ext = os.path.splitext(filename_header)[1].lower()
    if not ext: ext = '.jpg'
    unique_name = f"media_{uuid.uuid4().hex[:8]}{ext}"
    
    file_data = await request.body()
    if len(file_data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")
    if old_url_header:
        delete_old_media_if_needed(old_url_header)
    
    if R2_ENABLED and r2_client:
        mime_map = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png',  '.webp': 'image/webp',
            '.gif': 'image/gif',  '.svg': 'image/svg+xml',
            '.mp4': 'video/mp4'
        }
        content_type = mime_map.get(ext, 'application/octet-stream')
        try:
            r2_client.put_object(
                Bucket=R2_BUCKET,
                Key=unique_name,
                Body=file_data,
                ContentType=content_type
            )
            return {"url": f"{R2_PUBLIC_URL}/{unique_name}", "storage": "r2"}
        except Exception as e:
            print(f"[R2 Error] {e}")
            pass
            
    # Local fallback
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(file_path, 'wb') as f:
        f.write(file_data)
        
    url_path = f"uploads/{unique_name}" if UPLOAD_DIR != os.path.join("assets", "images") else f"assets/images/{unique_name}"
    return {"url": url_path, "storage": "local"}

@app.post("/api/save")
async def save_data(request: Request, admin: str = Depends(get_current_admin)):
    data = await request.json()
    slug = data.get('file')
    payload = data.get('payload')
    if not slug or not payload:
        raise HTTPException(status_code=400, detail="Missing data")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    page = payload.get('page', {})
    cursor.execute('''
        UPDATE pages SET 
            title = ?, titleLine1 = ?, titleLine2 = ?, subtitle = ?, breadcrumb = ?
        WHERE slug = ?
    ''', (page.get('title', ''), page.get('titleLine1', ''), page.get('titleLine2', ''), page.get('subtitle', ''), page.get('breadcrumb', ''), slug))
    
    cursor.execute("DELETE FROM categories WHERE page_slug = ?", (slug,))
    for idx, cat in enumerate(payload.get('categories', [])):
        cursor.execute('''
            INSERT INTO categories (id, page_slug, label, title, description, image, ctaText, ctaLink, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cat.get('id', f"{slug}-cat-{idx}"), slug, cat.get('label', ''), cat.get('title', ''), cat.get('description', ''), cat.get('image', ''), cat.get('ctaText', ''), cat.get('ctaLink', ''), idx))
    conn.commit()
    conn.close()
    clear_cache()
    version = bump_sync_version()
    purge_cloudflare_cache()
    return {"status": "success", "version": version}

@app.post("/api/site-content/save")
async def save_site_content(request: Request, admin: str = Depends(get_current_admin)):
    updates = await request.json()
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    updates = {
        path: data
        for path, data in updates.items()
        if path not in PROTECTED_SITE_CONTENT_PATHS
    }

    # Determine which page prefixes are being edited in this save payload.
    # Example paths: avenue/block1/title, global/contact/email
    edited_prefixes = set()
    for path in updates.keys():
        if not isinstance(path, str) or "/" not in path:
            continue
        edited_prefixes.add(path.split("/", 1)[0])

    conn = get_db_connection()
    cursor = conn.cursor()

    # Remove stale keys for the edited page prefix(es) so UI deletions
    # (e.g. removing avenue/blockN/*) are persisted in DB.
    for prefix in edited_prefixes:
        keep_paths = [path for path in updates.keys() if isinstance(path, str) and path.startswith(f"{prefix}/")]
        if keep_paths:
            placeholders = ",".join(["?"] * len(keep_paths))
            cursor.execute(
                f"DELETE FROM site_content WHERE path LIKE ? AND path NOT IN ({placeholders})",
                [f"{prefix}/%"] + keep_paths
            )
        else:
            cursor.execute("DELETE FROM site_content WHERE path LIKE ?", (f"{prefix}/%",))

    for path, data in updates.items():
        cursor.execute('''
            INSERT OR REPLACE INTO site_content (path, value, type)
            VALUES (?, ?, ?)
        ''', (path, data.get('value'), data.get('type')))
    for path, data in {**FIXED_HOME_HERO_MEDIA, **FIXED_HOME_STAGING_MEDIA}.items():
        cursor.execute('''
            INSERT OR REPLACE INTO site_content (path, value, type)
            VALUES (?, ?, ?)
        ''', (path, data["value"], data["type"]))
    conn.commit()
    conn.close()
    clear_cache()
    version = bump_sync_version()
    purge_cloudflare_cache()
    return {"status": "success", "version": version}

@app.post("/api/home-trends-section/save")
async def save_home_trends_section(request: Request, admin: str = Depends(get_current_admin)):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    normalized = {
        "badge_label": str(payload.get("badge_label", "")).strip(),
        "title_line1": str(payload.get("title_line1", "")).strip(),
        "title_highlight": str(payload.get("title_highlight", "")).strip(),
        "title_connector": str(payload.get("title_connector", "")).strip(),
        "title_line3": str(payload.get("title_line3", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
    }

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO home_trends_section
            (id, badge_label, title_line1, title_highlight, title_connector, title_line3, description, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            badge_label = excluded.badge_label,
            title_line1 = excluded.title_line1,
            title_highlight = excluded.title_highlight,
            title_connector = excluded.title_connector,
            title_line3 = excluded.title_line3,
            description = excluded.description,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            normalized["badge_label"],
            normalized["title_line1"],
            normalized["title_highlight"],
            normalized["title_connector"],
            normalized["title_line3"],
            normalized["description"],
        ),
    )
    conn.commit()
    conn.close()

    clear_cache()
    version = bump_sync_version()
    purge_cloudflare_cache()
    return {"status": "success", "version": version}

@app.get("/{path:path}")
async def serve_static(request: Request, path: str):
    if not path or path == "/":
        path = "index.html"

    if path in {"deep-solitude", "deep-solitude.html"}:
        return RedirectResponse("/curated-specimens", status_code=301)

    if path in {"inquiry", "inquiry.html"}:
        return RedirectResponse("/enquiry", status_code=301)
        
    if path.endswith(".py") or path.endswith(".db") or path == ".env" or path.startswith("."):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    resolved_path = None
    if os.path.isfile(path):
        resolved_path = path
    elif os.path.isfile(path + ".html"):
        resolved_path = path + ".html"
        
    if not resolved_path:
        raise HTTPException(status_code=404, detail="Not Found")
        
    if resolved_path.lower() == "admin.html":
        token = request.cookies.get("admin_session")
        if not token:
            return RedirectResponse("/admin-login")
        try:
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            return RedirectResponse("/admin-login")

    response = FileResponse(resolved_path)
    # Cache public HTML briefly to speed repeat navigations.
    if resolved_path.lower().endswith(".html"):
        if resolved_path.lower() in {"admin.html", "admin-login.html"}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        else:
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
    return response

if __name__ == "__main__":
    import uvicorn
    print("Starting CHF FastAPI Secure Backend...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
