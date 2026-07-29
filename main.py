import os
import json
import uuid
import sqlite3
import io
import re
import urllib.parse
import urllib.request
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse, HTMLResponse
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
import socket
from pydantic import BaseModel
import ccavenue_utils

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
    return data

def clear_cache():
    fetch_collection_data.cache_clear()
    fetch_site_content.cache_clear()

PORTFOLIO_TABS = ["villa", "terrace", "housing", "founders-era"]

PORTFOLIO_DEFAULT_IMAGES = {
    "villa": [
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/villa%20projects/1A8586D8-4B63-45A8-8499-7E6926501953.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/villa%20projects/43B31350-DA3C-422D-AFA3-626139C9E578.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/villa%20projects/79F1D9E2-1DC6-4BCA-A755-36D5E5585079.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/villa%20projects/917D98C1-D55E-459A-82DF-0483C62FF622.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/villa%20projects/AD34490C-109A-4FC7-AFDF-F29438D7E0EB.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/villa%20projects/E6BEDFF8-BD56-445B-B06F-66497110D62B.png"
    ],
    "terrace": [
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/14C3D11D-6A55-40A0-BDDE-9D87F6778B6D.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/2DF1E3ED-EC48-45AC-ADDC-890447876E11%20(2).png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/35CEA33A-08DB-4C89-B47F-765BA6246452.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/42185EE8-F3B3-4FA5-A186-CB1A2B557807%20(1).png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/48E40800-D3B8-4BF8-9D1C-F84AF93ADB0D.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/66BD27DB-5C07-40A5-B799-E3BE3A4135C7.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/7CC2240C-F179-411D-94EC-D6161CAE8B00.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/838984EF-9F5B-4FE2-B22C-BB9D9B0ED1A7.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/9CA486C0-6566-489C-B397-149E1E7FF13E%20(2).png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/CA4C5AC3-901D-43B6-8653-69AC16191A6F.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/terrace%20projects/E33B8408-A13B-4702-9FB6-129F47CCE582.png"
    ],
    "housing": [
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/housing%20projects/6292758B-D3AF-47E5-9470-64D584E40FF1.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/housing%20projects/ACFF5D17-19DC-4EF7-B097-20B8E5FEAC0F.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/housing%20projects/6292758B-D3AF-47E5-9470-64D584E40FF1.png"
    ],
    "founders-era": [
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/57A1B243-7B63-41E3-A88C-1F5114F3421F.jpg",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/5D264EDD-EBE5-4B70-ABB0-DFB0EB41CCEC.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/9D785DE4-1F57-4E99-B579-A8446ED2E812.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/A1682D49-3032-4A43-A1CC-7FFA3A84C344.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/E53541ED-6D22-49D6-8A1A-351BDD6C9A3E.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/0811CD69-AF7D-4729-8E0D-35451B3D2622.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/BEA7806C-3DE7-4786-BCCA-F1C07CEF4D2A.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/74D7D10D-B712-45D3-9B95-1ABFA411C00E.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/98487D03-D11B-430E-8840-1701C3D6E2F9.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/CB26DA90-9EE7-4303-997D-6D13D39D96D8.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/D798C7D7-7389-4038-B49F-04A12F029493.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/D36D8761-203E-42D3-9CD9-F57E432FDA57.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/98440DEA-9647-4996-868C-7D8F636B1190.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/E169FA42-2317-4D97-9F06-2B033E32004E.png",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/486C5605-D4F2-4B9D-8311-28A91BC2CF96.jpg",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/41057253-D0FA-4339-927A-AADC5F94B2F0.jpg",
        "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/portfolio/founders%20era%20projects/A6E2C193-9218-46D3-968C-3341F7E4C11F.jpg"
    ]
}

def fetch_portfolio_manifest(tab: str) -> list[str]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM site_content WHERE path = ?", (f"portfolio/{tab}/images",))
    row = cur.fetchone()
    conn.close()
    if not row or not row["value"]:
        return list(PORTFOLIO_DEFAULT_IMAGES.get(tab, []))
    try:
        data = json.loads(row["value"])
        urls = [url for url in data if isinstance(url, str) and url.strip()] if isinstance(data, list) else []
        return urls or list(PORTFOLIO_DEFAULT_IMAGES.get(tab, []))
    except json.JSONDecodeError:
        return list(PORTFOLIO_DEFAULT_IMAGES.get(tab, []))

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
ASSETS_CACHE_VERSION = "chf-no-img-zoom-1"
PEC_IMAGE_BASE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/plant%20experience%20center"
PEC_HERO_IMAGE = f"{PEC_IMAGE_BASE}/9BF51B5D-7851-4D44-BF1D-F2B521F61DB2%20(1).png"
PEC_PHILOSOPHY_IMAGE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/media_bcec5110.png?t=1780033476946"
ABOUT_FOUNDING_ERA_IMAGE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/founding-era-68896cb0.png"
ABOUT_FOUNDING_ERA_COPY = (
    "Calcutta Horticultural Farm is a plant-led design practice rooted in legacy, expertise "
    "and a deep respect for nature. Founded in 1982 by Mr. Gautam Bose, the practice began with "
    "a vision to integrate greenery into the evolving urban fabric—setting new benchmarks in "
    "landscape development and pioneering tree transplantation in the city."
)
ABOUT_DESIGN_PHILOSOPHY_IMAGE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/design-philosophy-1d66f8f2.png"
ABOUT_DESIGN_PHILOSOPHY_COPY = (
    "Our work is guided by an intrinsic understanding of plants—ensuring every space is thoughtfully "
    "designed, where aesthetics and ecology come together seamlessly. From bespoke residential landscapes "
    "to large-scale corporate environments, each project is created to thrive and evolve over time."
)
ABOUT_LEGACY_FORWARD_IMAGE = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/carrying-legacy-forward-dde8988b.png"
ABOUT_LEGACY_FORWARD_TITLE = "Carrying the Legacy Forward"
ABOUT_LEGACY_FORWARD_COPY = (
    "Today, the legacy is carried forward by Indra Bose and Apurba Bose, expanding the practice into "
    "contemporary formats while staying rooted in its core philosophy. Alongside design and consulting, "
    "we offer curated plant solutions, gardening essentials and a diverse range of products tailored "
    "for modern green living."
)
ABOUT_NURSERIES_IMAGE_1 = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/our-nurseries-1-25c9a8f0.png"
ABOUT_NURSERIES_IMAGE_2 = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/about/our-nurseries-2-6ff91b68.png"
ABOUT_NURSERIES_IMAGE_3 = "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/AliporeUnit.png"
ABOUT_NURSERIES_TITLE = "Our Nurseries"
ABOUT_NURSERIES_COPY = (
    "With two expansive nurseries in Alipore and Muchisha, spread across acres of cultivated land, "
    "we house a rich collection of indoor, outdoor and exotic plants, along with bonsais, topiaries "
    "and an extensive selection of pots and planters. Our plant experience centre in Alipore further "
    "brings this vision to life—an immersive space where clients can explore, interact and engage "
    "with plants in thoughtfully curated settings."
)
FIXED_ABOUT_MEDIA = {
    "about/story/image-1": {
        "value": ABOUT_FOUNDING_ERA_IMAGE,
        "type": "media",
    },
    "about/story/title-1": {
        "value": "The Founding Era (1982)",
        "type": "text",
    },
    "about/philosophy/patience-title": {
        "value": ABOUT_FOUNDING_ERA_COPY,
        "type": "longtext",
    },
    "about/story/image-2": {
        "value": ABOUT_DESIGN_PHILOSOPHY_IMAGE,
        "type": "media",
    },
    "about/story/title-2": {
        "value": "Design Philosophy",
        "type": "text",
    },
    "about/philosophy/precision-title": {
        "value": ABOUT_DESIGN_PHILOSOPHY_COPY,
        "type": "longtext",
    },
    "about/story/image-3": {
        "value": ABOUT_LEGACY_FORWARD_IMAGE,
        "type": "media",
    },
    "about/philosophy/presence-title": {
        "value": ABOUT_LEGACY_FORWARD_TITLE,
        "type": "text",
    },
    "about/philosophy/presence-body": {
        "value": ABOUT_LEGACY_FORWARD_COPY,
        "type": "longtext",
    },
    "about/nurseries/title": {
        "value": ABOUT_NURSERIES_TITLE,
        "type": "text",
    },
    "about/nurseries/body": {
        "value": ABOUT_NURSERIES_COPY,
        "type": "longtext",
    },
    "about/nurseries/image-1": {
        "value": ABOUT_NURSERIES_IMAGE_1,
        "type": "media",
    },
    "about/nurseries/image-2": {
        "value": ABOUT_NURSERIES_IMAGE_2,
        "type": "media",
    },
    "about/nurseries/image-3": {
        "value": ABOUT_NURSERIES_IMAGE_3,
        "type": "media",
    },
}
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
FIXED_PLANT_CENTER_EXPERIENCE_MEDIA = {
    "plant-center/experience/card1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/media_3e8de862.png?t=1780033750869",
        "type": "media",
    },
    "plant-center/experience/card2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/media_86eaa2e7.png?t=1780033657351",
        "type": "media",
    },
    "plant-center/experience/card3/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/media_a5400b81.png?t=1780033636789",
        "type": "media",
    },
    "plant-center/experience/card4/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/media_e2be27b2.png?t=1780039110785",
        "type": "media",
    },
}
FIXED_PLANT_CENTER_MEDIA = {
    **FIXED_PLANT_CENTER_HERO_MEDIA,
    **FIXED_PLANT_CENTER_EXPERIENCE_MEDIA,
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
PROTECTED_SITE_CONTENT_PATHS = set()
ADMIN_LOCKED_CONTENT_PREFIXES = ()


def is_admin_locked_content_path(path: str) -> bool:
    if not isinstance(path, str):
        return False
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in ADMIN_LOCKED_CONTENT_PREFIXES)

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
    "home/trends/badge_label": {
        "value": "The Current Landscape",
        "type": "text",
    },
    "home/trends/title_line1": {
        "value": "Botanical",
        "type": "text",
    },
    "home/trends/title_highlight": {
        "value": "Trends",
        "type": "text",
    },
    "home/trends/title_connector": {
        "value": "for the",
        "type": "text",
    },
    "home/trends/title_line3": {
        "value": "Modern Collector",
        "type": "text",
    },
    "home/trends/description": {
        "value": "An editorial exploration of nature's evolving role in high-end design.",
        "type": "longtext",
    },
    "biophilic-workspace/block1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimens.png",
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
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png",
        "type": "media",
    },
    "biophilic-workspace/block2/title": {
        "value": "Air and Acoustic Balance",
        "type": "text",
    },
    "biophilic-workspace/block2/body": {
        "value": "Plant-led layering softens hard interiors, improves perceived air quality and contributes to calmer acoustics across open-plan environments.",
        "type": "longtext",
    },
    "rare-specimen-sculptures/block1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/architectural_harmony.png",
        "type": "media",
    },
    "rare-specimen-sculptures/block1/title": {
        "value": "Architectural Presence",
        "type": "text",
    },
    "rare-specimen-sculptures/block1/body": {
        "value": "Each specimen is selected for maturity, silhouette and sculptural character to anchor space with botanical authority.",
        "type": "longtext",
    },
    "rare-specimen-sculptures/block2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_legacy.png",
        "type": "media",
    },
    "rare-specimen-sculptures/block2/title": {
        "value": "Collector-Led Curation",
        "type": "text",
    },
    "rare-specimen-sculptures/block2/body": {
        "value": "We align plant provenance, form and long-term care protocols with each collector's design intent and lifestyle rhythm.",
        "type": "longtext",
    },
    "living-walls/block1/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png",
        "type": "media",
    },
    "living-walls/block1/title": {
        "value": "Engineered Vertical Ecology",
        "type": "text",
    },
    "living-walls/block1/body": {
        "value": "We design irrigation, species layering and maintenance access as one integrated system so the wall remains healthy and visually composed over time.",
        "type": "longtext",
    },
    "living-walls/block2/image": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimens.png",
        "type": "media",
    },
    "living-walls/block2/title": {
        "value": "Spatial Softening",
        "type": "text",
    },
    "living-walls/block2/body": {
        "value": "Living walls soften rigid architecture, improve ambience and create an immersive natural experience in high-value interior environments.",
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
        "value": "Layered landscape compositions that bring structure, softness and living depth into contemporary spaces.",
        "type": "longtext",
    },
    "home/staging/cta": {
        "value": "EXPLORE THE EXPERIENCE",
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
        "value": FIXED_PLANT_CENTER_EXPERIENCE_MEDIA["plant-center/experience/card1/image"]["value"],
        "type": "media",
    },
    "plant-center/experience/card2/image": {
        "value": FIXED_PLANT_CENTER_EXPERIENCE_MEDIA["plant-center/experience/card2/image"]["value"],
        "type": "media",
    },
    "plant-center/experience/card3/image": {
        "value": FIXED_PLANT_CENTER_EXPERIENCE_MEDIA["plant-center/experience/card3/image"]["value"],
        "type": "media",
    },
    "plant-center/experience/card4/image": {
        "value": FIXED_PLANT_CENTER_EXPERIENCE_MEDIA["plant-center/experience/card4/image"]["value"],
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
    "about/story/image-1": {
        "value": ABOUT_FOUNDING_ERA_IMAGE,
        "type": "media",
    },
    "about/story/title-1": {
        "value": "The Founding Era (1982)",
        "type": "text",
    },
    "about/philosophy/patience-title": {
        "value": ABOUT_FOUNDING_ERA_COPY,
        "type": "longtext",
    },
    "about/story/image-2": {
        "value": ABOUT_DESIGN_PHILOSOPHY_IMAGE,
        "type": "media",
    },
    "about/story/title-2": {
        "value": "Design Philosophy",
        "type": "text",
    },
    "about/philosophy/precision-title": {
        "value": ABOUT_DESIGN_PHILOSOPHY_COPY,
        "type": "longtext",
    },
    "about/story/image-3": {
        "value": ABOUT_LEGACY_FORWARD_IMAGE,
        "type": "media",
    },
    "about/philosophy/presence-title": {
        "value": ABOUT_LEGACY_FORWARD_TITLE,
        "type": "text",
    },
    "about/philosophy/presence-body": {
        "value": ABOUT_LEGACY_FORWARD_COPY,
        "type": "longtext",
    },
    "about/nurseries/title": {
        "value": ABOUT_NURSERIES_TITLE,
        "type": "text",
    },
    "about/nurseries/body": {
        "value": ABOUT_NURSERIES_COPY,
        "type": "longtext",
    },
    "about/nurseries/image-1": {
        "value": ABOUT_NURSERIES_IMAGE_1,
        "type": "media",
    },
    "about/nurseries/image-2": {
        "value": ABOUT_NURSERIES_IMAGE_2,
        "type": "media",
    },
    "about/nurseries/image-3": {
        "value": ABOUT_NURSERIES_IMAGE_3,
        "type": "media",
    },
    "arch/block1/body": {
        "value": "In landscape architecture, drawings capture a moment—but gardens don't stand still. They grow, expand, compete and transform. Without a deep understanding of plant behaviour many designs begin to diverge from their original intent.",
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
        "value": "With the intent to not redefine but strengthen the designs, we as landscape developers work closely with landscape architects—either as consultants during the design phase or as collaborators during execution—to ensure that plant selections are informed, intentional and future-ready.",
        "type": "longtext",
    },
    "arch/tomorrow/title": {
        "value": "Design with Tomorrow in Mind.",
        "type": "text",
    },
    "arch/tomorrow/p1": {
        "value": "By bringing horticultural depth into the conversation early, we help align design vision with plant behaviour, site conditions and long-term growth patterns.",
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
        "value": "assets/plant-supply-finished.png",
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
        "value": "Integrating verdant life into professional sanctuaries for clarity, composure and spatial softness.",
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
        "value": "Plant-led layering softens hard interiors, improves perceived air quality and contributes to calmer acoustics across open-plan environments.",
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
        "value": "Each specimen is selected for maturity, silhouette and sculptural character to anchor space with botanical authority.",
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
        "value": "We align plant provenance, form and long-term care protocols with each collector's design intent and lifestyle rhythm.",
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
        "value": "We design irrigation, species layering and maintenance access as one integrated system so the wall remains healthy and visually composed over time.",
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
        "value": "Living walls soften rigid architecture, improve ambience and create an immersive natural experience in high-value interior environments.",
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
        "value": "Golden light, water reflections and a sculptural specimen create sensory calm — where negative ions, natural textures and biophilic balance reduce stress, slow the mind and elevate the entire outdoor experience.",
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
        "value": "Expansive light, open flow and a single curated plant enhance oxygen levels and visual calm — proven to reduce cortisol and improve focus, creating a breathable, emotionally warm living environment.",
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
        "value": "A refined interior anchored by a living specimen — naturally filtering air, softening acoustics and enhancing well-being through biophilic design, creating a welcoming space that feels calm, intentional and quietly premium.",
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
        "value": "Clean lines, controlled light and a sculptural plant improve cognitive performance and reduce fatigue — bringing clarity, calm and subtle vitality into a workspace designed for focus, decision-making and elevated thinking.",
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
    ("Canopy Continuity", "From boulevard medians to estate driveways, consistent canopy rhythm gives movement and coherence to long linear spaces. Each alignment is selected for mature spread, branching behaviour and maintenance practicality."),
    ("Root-Zone Intelligence", "Avenue trees fail early when underground conditions are ignored. We map soil depth, drainage and hardscape pressure before planting, so root systems establish with long-term structural stability."),
    ("Seasonal Character", "A layered avenue should evolve gracefully across seasons. We curate flowering cycles, leaf texture and tonal contrast so streetscapes retain visual depth beyond a single blooming window."),
    ("Wind and Exposure Planning", "Large-form trees must withstand corridor winds and reflected heat. Species choices are calibrated to site exposure, reducing failure risk while preserving the intended architectural silhouette."),
    ("Maintenance by Design", "Pruning regimes, irrigation access and replacement strategies are considered at planning stage. This keeps the avenue visually disciplined while reducing operational surprises over time."),
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
    ("Site-Led Concept Planning", "Every project begins with reading the land: light, soil, circulation and architectural language. We shape planting intent and hardscape rhythm so aesthetics and environmental logic align from day one.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_site_planning.jpg"),
    ("Material and Plant Integration", "Our design-development workflow unifies botanical palettes, grading, stone and built edges into one coherent system. This avoids disconnected execution and preserves spatial clarity.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_material_integration.jpg"),
    ("Execution-Level Detailing", "From planting density to irrigation zoning, details are developed for real-world buildability. The result is a landscape that performs as elegantly as it appears.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_execution_detailing.jpg"),
    ("Post-Completion Evolution", "We design for years ahead, not just launch day. Growth behavior, replacement strategy and seasonal transitions are considered upfront to keep the landscape refined over time.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_post_completion.jpg"),
]

LANDSCAPE_STAGING_BLOCKS = [
    ("Arrival Composition", "We stage entrances, patios, terraces and event-facing green zones so the first view feels balanced, lush and ready for use.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_site_planning.jpg"),
    ("Layered Visual Depth", "Tall forms, ground textures, planters and focal specimens are arranged to create depth without overwhelming the architecture.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_material_integration.jpg"),
    ("Event-Ready Greenery", "Plant material, containers and placement are coordinated for openings, photoshoots, residences and hospitality spaces that need immediate polish.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_execution_detailing.jpg"),
    ("Refinement After Placement", "After staging, we tune spacing, orientation, irrigation access and care notes so the composition remains composed beyond installation day.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/landscape_design_post_completion.jpg"),
]

PLANT_SUPPLY_BLOCKS = [
    ("Curated Plant Procurement", "We source healthy, structurally sound plant material from trusted growers, with species calibrated to project context, climate and desired visual maturity.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_procurement.jpg"),
    ("Nursery Quality Audit", "Before dispatch, every batch is evaluated for root health, branch structure, pest status and moisture condition to reduce replacement risk on site.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_quality_audit.jpg"),
    ("Climate-Matched Selection", "Species are shortlisted based on exposure, local humidity, soil profile and irrigation capacity so delivered plants establish quickly and reliably.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_climate_matched.jpg"),
    ("Logistics and Staging Control", "Transit sequencing, loading method and staging windows are planned to preserve plant vitality between nursery pickup and final placement.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/plant_supply_logistics_control.jpg"),
]

GARDEN_MAINTENANCE_BLOCKS = [
    ("Seasonal Maintenance Programming", "Care calendars are tuned to growth cycles, weather shifts and flowering behavior so each zone receives intervention at the right moment.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_seasonal_programming.jpg"),
    ("Pruning and Canopy Discipline", "Formative pruning, thinning and canopy balancing maintain proportion, sightlines and plant health without compromising architectural composition.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_canopy_discipline.jpg"),
    ("Nutrition and Soil Vitality", "Targeted nutrient plans and soil-conditioning routines restore vigor, support root stability and keep ornamental quality consistently high.", "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/garden_maintenance_soil_vitality.jpg"),
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

COMMA_BEFORE_AND_RE = re.compile(r",\s+and\b", re.IGNORECASE)


def strip_comma_before_and(text):
    if not isinstance(text, str) or not text:
        return text
    return COMMA_BEFORE_AND_RE.sub(" and", text)


def migrate_remove_comma_before_and():
    """Normalize stored CMS copy by removing commas that precede 'and'."""
    conn = get_db_connection()
    cur = conn.cursor()
    changed = 0

    cur.execute("SELECT path, value FROM site_content")
    for row in cur.fetchall():
        old_value = row["value"] or ""
        new_value = strip_comma_before_and(old_value)
        if new_value != old_value:
            cur.execute(
                "UPDATE site_content SET value = ? WHERE path = ?",
                (new_value, row["path"]),
            )
            changed += 1

    for column in ("label", "title", "description", "ctaText"):
        cur.execute(f"SELECT id, {column} AS value FROM categories")
        for row in cur.fetchall():
            old_value = row["value"] or ""
            new_value = strip_comma_before_and(old_value)
            if new_value != old_value:
                cur.execute(
                    f"UPDATE categories SET {column} = ? WHERE id = ?",
                    (new_value, row["id"]),
                )
                changed += 1

    for column in ("title", "titleLine1", "titleLine2", "subtitle", "breadcrumb"):
        cur.execute(f"SELECT slug, {column} AS value FROM pages")
        for row in cur.fetchall():
            old_value = row["value"] or ""
            new_value = strip_comma_before_and(old_value)
            if new_value != old_value:
                cur.execute(
                    f"UPDATE pages SET {column} = ? WHERE slug = ?",
                    (new_value, row["slug"]),
                )
                changed += 1

    for column in (
        "badge_label",
        "title_line1",
        "title_highlight",
        "title_connector",
        "title_line3",
        "description",
    ):
        cur.execute(f"SELECT id, {column} AS value FROM home_trends_section")
        for row in cur.fetchall():
            old_value = row["value"] or ""
            new_value = strip_comma_before_and(old_value)
            if new_value != old_value:
                cur.execute(
                    f"UPDATE home_trends_section SET {column} = ? WHERE id = ?",
                    (new_value, row["id"]),
                )
                changed += 1

    conn.commit()
    conn.close()
    if changed:
        clear_cache()
        bump_sync_version()
        print(f"[MIGRATE] Removed comma-before-and from {changed} stored content field(s).")


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

    # The Plant Experience Centre was rebuilt as an image-led landing page.
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

    cur.execute(
        "SELECT path, value, type FROM site_content WHERE path LIKE 'curated-planters/block%/image'"
    )
    for row in cur.fetchall():
        match = re.match(r"^curated-planters/block(\d+)/image$", row["path"])
        if not match:
            continue
        idx = match.group(1)
        image1_path = f"curated-planters/block{idx}/image1"
        cur.execute("SELECT value FROM site_content WHERE path = ?", (image1_path,))
        image1_row = cur.fetchone()
        if not image1_row or not str(image1_row["value"] or "").strip():
            cur.execute(
                "INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
                (image1_path, row["value"], row["type"] or "media"),
            )
        for suffix, field_type in (("image2", "media"), ("image3", "media"), ("highlights", "longtext")):
            field_path = f"curated-planters/block{idx}/{suffix}"
            cur.execute("SELECT 1 FROM site_content WHERE path = ?", (field_path,))
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO site_content (path, value, type) VALUES (?, ?, ?)",
                    (field_path, "", field_type),
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

    for tab in PORTFOLIO_TABS:
        path = f"portfolio/{tab}/images"
        cur.execute("SELECT value FROM site_content WHERE path = ?", (path,))
        row = cur.fetchone()
        value = (row["value"] if row else "") or ""
        if row is None or not value.strip() or value.strip() in {"[]", "null"}:
            cur.execute(
                "INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
                (path, json.dumps(PORTFOLIO_DEFAULT_IMAGES[tab]), "json"),
            )

    cur.execute(
        """
        UPDATE categories
        SET ctaLink = REPLACE(REPLACE(ctaLink, 'inquiry.html', 'enquiry.html'), 'inquiry', 'enquiry')
        WHERE ctaLink LIKE '%inquiry%'
        """
    )

    # Migrate any existing empty values to their actual default values so they show up in the admin panel
    for path, payload in SITE_CONTENT_DEFAULTS.items():
        default_value = str(payload.get("value") or "")
        if not default_value:
            continue
        cur.execute(
            "UPDATE site_content SET value = ? WHERE path = ? AND value = ?",
            (default_value, path, ""),
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
                (path, payload["value"], payload["type"]),
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

def ensure_leads_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            email TEXT,
            location TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def ensure_mobile_scans_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mobile_scans (
            session_id TEXT PRIMARY KEY,
            sku TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def ensure_device_auth_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_auth_sessions (
            session_id TEXT PRIMARY KEY,
            pin TEXT,
            is_verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def ensure_sku_catalog_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sku_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            price REAL DEFAULT 0.0,
            category TEXT DEFAULT '',
            description TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration safety for existing database
    try:
        cur.execute("ALTER TABLE sku_catalog ADD COLUMN image_url TEXT DEFAULT ''")
    except Exception:
        pass
    conn.commit()
    conn.close()

# ── Sub-Millisecond RAM Cache & Real-Time Event Router ─────
ACTIVE_WS_SESSIONS: dict = {}
ACTIVE_SCANS_BUFFER: dict = {}
SKU_CACHE: dict = {}

def refresh_sku_cache():
    """Populate SKU Catalog into RAM for sub-millisecond (0.001ms) lookups."""
    global SKU_CACHE
    try:
        ensure_sku_catalog_table()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, sku, name, price, category, description, image_url FROM sku_catalog")
        rows = cur.fetchall()
        SKU_CACHE = {
            r["sku"].upper(): {
                "id": r["id"],
                "sku": r["sku"],
                "name": r["name"],
                "price": r["price"],
                "category": r["category"],
                "description": r["description"],
                "image_url": r.get("image_url", "")
            } for r in rows
        }
        conn.close()
    except Exception as e:
        print(f"Failed to refresh SKU cache: {e}")

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

def ensure_invoice_payments_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoice_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT UNIQUE NOT NULL,
            order_id TEXT UNIQUE NOT NULL,
            client_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            amount REAL DEFAULT 0.0,
            payment_status TEXT DEFAULT 'PENDING',
            payment_link TEXT DEFAULT '',
            ccavenue_ref_no TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup_init_sync_state():
    migrate_legacy_site_content_keys()
    ensure_sync_state_table()
    ensure_home_trends_section_table()
    ensure_leads_table()
    ensure_mobile_scans_table()
    ensure_device_auth_table()
    ensure_sku_catalog_table()
    ensure_invoice_payments_table()
    refresh_sku_cache()
    migrate_remove_comma_before_and()
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

@app.post("/api/admin/change-invoice-password")
async def change_invoice_password(
    request: Request,
    admin: str = Depends(get_current_admin)
):
    body = await request.json()
    new_password = body.get("new_password", "")
    cf_turnstile_response = body.get("cf_turnstile_response")

    verify_turnstile_or_raise(cf_turnstile_response)

    if not new_password:
        raise HTTPException(status_code=400, detail="New password is required")


    new_hash = argon2.hash(new_password)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE admins SET password_hash = ? WHERE username = 'invoice_admin'", (new_hash,))
    if cur.rowcount == 0:
        cur.execute("INSERT INTO admins (username, password_hash) VALUES ('invoice_admin', ?)", (new_hash,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Invoice password updated"}


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
async def upload_file(request: Request):
    filename_header = request.headers.get('X-Filename', 'upload.jpg')
    old_url_header = request.headers.get('X-Old-Url', '').strip()
    cms_path_header = request.headers.get('X-Cms-Path', '').strip()
    folder_header = request.headers.get('X-Folder', '').strip('/')
    
    ext = os.path.splitext(filename_header)[1].lower()
    if not ext: ext = '.jpg'
    unique_name = f"media_{uuid.uuid4().hex[:8]}{ext}"
    
    file_data = await request.body()
    if len(file_data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")
    if old_url_header:
        delete_old_media_if_needed(old_url_header)

    r2_key = unique_name
    if folder_header:
        safe_folder = re.sub(r'[^a-zA-Z0-9/_\-]', '', folder_header).strip('/')
        r2_key = f"{safe_folder}/{unique_name}"
    elif cms_path_header:
        safe_cms_path = re.sub(r'[^a-zA-Z0-9/_\-]', '', cms_path_header).strip('/')
        if safe_cms_path:
            folder = '/'.join(['assets'] + safe_cms_path.split('/')[:-1])
            r2_key = f"{folder}/{unique_name}" if folder else unique_name
    
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
                Key=r2_key,
                Body=file_data,
                ContentType=content_type
            )
            return {"url": f"{R2_PUBLIC_URL}/{r2_key}", "storage": "r2"}
        except Exception as e:
            print(f"[R2 Error] {e}")
            pass
            
    # Local fallback
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(file_path, 'wb') as f:
        f.write(file_data)
        
    url_path = f"uploads/{unique_name}" if UPLOAD_DIR != os.path.join("assets", "images") else f"assets/images/{unique_name}"
    return {"url": url_path, "storage": "local"}

@app.get("/api/portfolio/{tab}")
async def get_portfolio_images(tab: str):
    if tab not in PORTFOLIO_TABS:
        raise HTTPException(status_code=400, detail="Invalid portfolio tab")
    return {"images": fetch_portfolio_manifest(tab)}

@app.post("/api/portfolio/{tab}/save")
async def save_portfolio_images(tab: str, request: Request, admin: str = Depends(get_current_admin)):
    if tab not in PORTFOLIO_TABS:
        raise HTTPException(status_code=400, detail="Invalid portfolio tab")
    data = await request.json()
    images = data.get('images', [])
    if not isinstance(images, list):
        raise HTTPException(status_code=400, detail="Images must be a list")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO site_content (path, value, type) VALUES (?, ?, ?)",
        (f"portfolio/{tab}/images", json.dumps(images), "json"),
    )
    conn.commit()
    conn.close()
    
    fetch_site_content.cache_clear()
    version = bump_sync_version()
    purge_cloudflare_cache()
    return {"status": "success", "version": version}

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
        if path not in PROTECTED_SITE_CONTENT_PATHS and not is_admin_locked_content_path(path)
    }

    # Determine which page prefixes are being edited in this save payload.
    # Example paths: avenue/block1/title, global/contact/email
    edited_prefixes = set()
    for path in updates.keys():
        if not isinstance(path, str) or "/" not in path:
            continue
        prefix = path.split("/", 1)[0]
        if prefix not in ADMIN_LOCKED_CONTENT_PREFIXES:
            edited_prefixes.add(prefix)

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
    for path, data in {**FIXED_HOME_HERO_MEDIA, **FIXED_HOME_STAGING_MEDIA, **FIXED_ABOUT_MEDIA}.items():
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

@app.post("/api/leads")
async def create_lead(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    name = data.get("name", "")
    phone = data.get("phone", "")
    email = data.get("email", "")
    location = data.get("location", "")
    message = data.get("message", "")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO leads (name, phone, email, location, message)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, phone, email, location, message))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/admin/leads")
async def admin_get_leads(admin: str = Depends(get_current_admin)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, phone, details, created_at, read FROM leads ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "email": r["email"], "phone": r["phone"], "details": r["details"], "created_at": r["created_at"], "read": bool(r["read"])} for r in rows]

class ScanPayload(BaseModel):
    session_id: str
    sku: Optional[str] = None
    raw_sku: Optional[str] = None

    @property
    def get_sku(self) -> str:
        return (self.sku or self.raw_sku or "").strip()

class DeviceAuthVerifyPayload(BaseModel):
    session_id: str
    pin: str

@app.get("/api/local-ip")
async def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return {"ip": IP}

@app.post("/api/scan/submit")
async def submit_scan(payload: ScanPayload):
    session_id = payload.session_id.strip()
    raw_sku = payload.get_sku
    
    # 0.001 ms RAM Lookup in SKU_CACHE
    sku_upper = raw_sku.upper()
    cached_sku = SKU_CACHE.get(sku_upper)
    
    if cached_sku:
        scan_event = {
            "sku": raw_sku,
            "name": cached_sku["name"],
            "price": cached_sku["price"],
            "category": cached_sku.get("category", ""),
            "image_url": cached_sku.get("image_url", ""),
            "timestamp": time.time()
        }
    else:
        scan_event = {
            "sku": raw_sku,
            "name": raw_sku,
            "price": 0.0,
            "category": "",
            "image_url": "",
            "timestamp": time.time()
        }
        
    # Instant WebSocket Push (<0.01 ms)
    sockets = ACTIVE_WS_SESSIONS.get(session_id, [])
    dead_sockets = []
    for ws in sockets:
        try:
            await ws.send_json(scan_event)
        except Exception:
            dead_sockets.append(ws)
            
    for ws in dead_sockets:
        if ws in sockets:
            sockets.remove(ws)
            
    # Buffer in RAM for HTTP polling fallback
    if session_id not in ACTIVE_SCANS_BUFFER:
        ACTIVE_SCANS_BUFFER[session_id] = []
    ACTIVE_SCANS_BUFFER[session_id].append(scan_event)
    
    # Non-blocking async DB backup log
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO mobile_scans (session_id, sku, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (session_id, raw_sku))
        conn.commit()
        conn.close()
    except Exception:
        pass
        
    return {"status": "success", "scan": scan_event}

@app.websocket("/ws/scan/{session_id}")
async def websocket_scan_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session_id = session_id.strip()
    if session_id not in ACTIVE_WS_SESSIONS:
        ACTIVE_WS_SESSIONS[session_id] = []
    ACTIVE_WS_SESSIONS[session_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if session_id in ACTIVE_WS_SESSIONS and websocket in ACTIVE_WS_SESSIONS[session_id]:
            ACTIVE_WS_SESSIONS[session_id].remove(websocket)
    except Exception:
        if session_id in ACTIVE_WS_SESSIONS and websocket in ACTIVE_WS_SESSIONS[session_id]:
            ACTIVE_WS_SESSIONS[session_id].remove(websocket)

@app.get("/api/scan/poll")
async def poll_scan(session_id: str):
    session_id = session_id.strip()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_verified FROM device_auth_sessions WHERE session_id = ?", (session_id,))
    auth_row = cur.fetchone()
    conn.close()
    
    if not auth_row:
        return {"error": "session_disconnected"}
        
    scan_event = None
    if session_id in ACTIVE_SCANS_BUFFER and ACTIVE_SCANS_BUFFER[session_id]:
        scan_event = ACTIVE_SCANS_BUFFER[session_id].pop(0)
        
    return {
        "scan": scan_event,
        "sku": scan_event["sku"] if scan_event else None
    }

import random

@app.post("/api/scan/auth/init")
async def init_device_auth():
    conn = get_db_connection()
    cur = conn.cursor()
    
    session_id = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16))
    pin = f"{random.randint(0, 9999):04d}"
    
    cur.execute(
        "INSERT INTO device_auth_sessions (session_id, pin, is_verified) VALUES (?, ?, 0)",
        (session_id, pin)
    )
    conn.commit()
    conn.close()
    return {"session_id": session_id, "pin": pin}

@app.get("/api/scan/auth/poll")
async def poll_device_auth(session_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Garbage collection of old sessions (> 1 hour)
    cur.execute("DELETE FROM device_auth_sessions WHERE created_at < datetime('now', '-1 hour')")
    
    cur.execute("SELECT is_verified FROM device_auth_sessions WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    
    if not row:
        return {"error": "session_disconnected"}
        
    is_verified = bool(row["is_verified"])
    return {"verified": is_verified}

class DisconnectPayload(BaseModel):
    session_id: str

@app.post("/api/scan/auth/disconnect")
async def disconnect_device_auth(payload: DisconnectPayload):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM device_auth_sessions WHERE session_id = ?", (payload.session_id,))
    cur.execute("DELETE FROM mobile_scans WHERE session_id = ?", (payload.session_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/scan/auth/verify")
async def verify_device_auth(payload: DeviceAuthVerifyPayload):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT pin FROM device_auth_sessions WHERE session_id = ?", (payload.session_id,))
    row = cur.fetchone()
    
    if not row or row["pin"] != payload.pin:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid session or PIN")
        
    cur.execute("UPDATE device_auth_sessions SET is_verified = 1 WHERE session_id = ?", (payload.session_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# ── Category Management Endpoints ─────────────────────────

def ensure_sku_categories_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sku_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    cur.execute("SELECT COUNT(*) as cnt FROM sku_categories")
    row = cur.fetchone()
    if row and row["cnt"] == 0:
        defaults = ["Indoor Plant", "Outdoor Plant", "Bonsai", "Planter / Pot", "Accessory", "Service", "Other"]
        for cat in defaults:
            cur.execute("INSERT OR IGNORE INTO sku_categories (name) VALUES (?)", (cat,))
    conn.commit()
    conn.close()

class CategoryPayload(BaseModel):
    name: str

@app.get("/api/categories")
async def list_categories():
    ensure_sku_categories_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sku_categories ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [r["name"] for r in rows]

@app.post("/api/categories")
async def add_category(payload: CategoryPayload):
    ensure_sku_categories_table()
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO sku_categories (name) VALUES (?)", (clean_name,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()
    return {"status": "success", "name": clean_name}

@app.delete("/api/categories/{category_name}")
async def delete_category(category_name: str):
    ensure_sku_categories_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sku_categories WHERE UPPER(name) = UPPER(?)", (category_name.strip(),))
    conn.commit()
    conn.close()
    return {"status": "success"}

# ── SKU Management Endpoints ───────────────────────────────

class SKUPayload(BaseModel):
    id: Optional[int] = None
    sku: Optional[str] = ""
    name: str
    price: float = 0.0
    category: Optional[str] = ""
    description: Optional[str] = ""
    image_url: Optional[str] = ""

@app.get("/api/skus")
async def list_skus():
    ensure_sku_catalog_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, sku, name, price, category, description, image_url, created_at FROM sku_catalog ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/skus")
async def save_sku(payload: SKUPayload):
    ensure_sku_catalog_table()
    clean_name = payload.name.strip()
    clean_sku = (payload.sku or "").strip().upper()
    if not clean_sku:
        prefix = (payload.category or "SKU")[:3].upper()
        import random
        clean_sku = f"{prefix}-{random.randint(1000, 9999)}"
    if not clean_name:
        raise HTTPException(status_code=400, detail="Product name is required")
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    if payload.id:
        cur.execute("""
            UPDATE sku_catalog
            SET sku = ?, name = ?, price = ?, category = ?, description = ?, image_url = ?
            WHERE id = ?
        """, (clean_sku, clean_name, payload.price, payload.category or "", payload.description or "", payload.image_url or "", payload.id))
    else:
        cur.execute("""
            INSERT INTO sku_catalog (sku, name, price, category, description, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET
                name = excluded.name,
                price = excluded.price,
                category = excluded.category,
                description = excluded.description,
                image_url = excluded.image_url
        """, (clean_sku, clean_name, payload.price, payload.category or "", payload.description or "", payload.image_url or ""))
        
    conn.commit()
    conn.close()
    refresh_sku_cache()
    return {"status": "success", "sku": clean_sku}

@app.delete("/api/skus/{sku_id}")
async def delete_sku(sku_id: int):
    ensure_sku_catalog_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sku_catalog WHERE id = ?", (sku_id,))
    conn.commit()
    conn.close()
    refresh_sku_cache()
    return {"status": "success"}

@app.get("/api/skus/lookup/{sku_code}")
async def lookup_sku(sku_code: str):
    ensure_sku_catalog_table()
    code_upper = sku_code.strip().upper()
    cached = SKU_CACHE.get(code_upper)
    if cached:
        return {"found": True, "sku": cached["sku"], "name": cached["name"], "price": cached["price"], "category": cached.get("category", ""), "image_url": cached.get("image_url", "")}
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, sku, name, price, category, description, image_url FROM sku_catalog WHERE UPPER(sku) = UPPER(?)", (code_upper,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"found": False, "sku": sku_code, "name": sku_code, "price": 0.0, "image_url": ""}
    d = dict(row)
    return {"found": True, "sku": d["sku"], "name": d["name"], "price": d["price"], "category": d.get("category", ""), "image_url": d.get("image_url", "")}

@app.get("/scan")
async def serve_scanner_alias():
    return FileResponse("scanner.html")

@app.delete("/api/admin/leads")
async def delete_leads(request: Request, admin: str = Depends(get_current_admin)):
    data = await request.json()
    lead_ids = data.get("lead_ids", [])
    if not lead_ids:
        return {"status": "success"}
    
    conn = get_db_connection()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(lead_ids))
    cur.execute(f"DELETE FROM leads WHERE id IN ({placeholders})", lead_ids)
    conn.commit()
    conn.close()
    return {"status": "success"}

# ── CCAvenue Payment Link & Status Verification ────────────────
class CreatePaymentLinkRequest(BaseModel):
    invoice_id: str
    client_name: str = ""
    phone: str = ""
    amount: float
    notes: str = ""

@app.post("/api/payment/create-link")
async def create_payment_link(payload: CreatePaymentLinkRequest, request: Request):
    ensure_invoice_payments_table()
    invoice_id = payload.invoice_id.strip()
    if not invoice_id:
        raise HTTPException(status_code=400, detail="invoice_id is required")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM invoice_payments WHERE invoice_id = ?", (invoice_id,))
    existing = cur.fetchone()

    if existing:
        order_id = existing["order_id"]
        payment_status = existing["payment_status"]
    else:
        order_id = f"ORD-{invoice_id}-{uuid.uuid4().hex[:6]}"
        payment_status = "PENDING"

    site_origin = os.environ.get("SITE_PUBLIC_ORIGIN", "").strip()
    if site_origin:
        base_url = site_origin.rstrip("/")
    else:
        base_url = str(request.base_url).rstrip("/")

    redirect_url = f"{base_url}/api/payment/ccavenue/response"
    
    creds = ccavenue_utils.get_ccavenue_credentials()
    working_key = creds["working_key"]
    access_code = creds["access_code"]

    plain_payload = ccavenue_utils.build_payment_payload(
        order_id=order_id,
        amount=payload.amount,
        currency="INR",
        redirect_url=redirect_url,
        cancel_url=redirect_url,
        client_name=payload.client_name,
        client_phone=payload.phone,
        merchant_id=creds["merchant_id"]
    )
    enc_request = ccavenue_utils.encrypt_ccavenue(plain_payload, working_key) if working_key else ""

    payment_link = f"{base_url}/pay/{invoice_id}"

    if existing:
        cur.execute("""
            UPDATE invoice_payments
            SET client_name = ?, phone = ?, amount = ?, payment_link = ?, updated_at = CURRENT_TIMESTAMP
            WHERE invoice_id = ?
        """, (payload.client_name, payload.phone, payload.amount, payment_link, invoice_id))
    else:
        cur.execute("""
            INSERT INTO invoice_payments (invoice_id, order_id, client_name, phone, amount, payment_status, payment_link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (invoice_id, order_id, payload.client_name, payload.phone, payload.amount, payment_status, payment_link))
    
    conn.commit()
    conn.close()

    return {
        "success": True,
        "invoice_id": invoice_id,
        "order_id": order_id,
        "amount": payload.amount,
        "payment_link": payment_link,
        "payment_status": payment_status,
        "enc_request": enc_request,
        "access_code": access_code,
        "mode": creds["mode"]
    }

@app.get("/pay/{invoice_id}")
async def pay_invoice_page(invoice_id: str, request: Request):
    ensure_invoice_payments_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM invoice_payments WHERE invoice_id = ?", (invoice_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return HTMLResponse(content="<h1 style='color:red;text-align:center;'>Invoice not found</h1>", status_code=404)

    payment_status = row["payment_status"]
    amount = float(row["amount"])
    client_name = row["client_name"]
    order_id = row["order_id"]

    creds = ccavenue_utils.get_ccavenue_credentials()
    working_key = creds["working_key"]
    access_code = creds["access_code"]
    ccavenue_url = creds["gateway_url"]
    mode = creds["mode"]

    site_origin = os.environ.get("SITE_PUBLIC_ORIGIN", "").strip()
    if site_origin:
        base_url = site_origin.rstrip("/")
    else:
        base_url = str(request.base_url).rstrip("/")

    redirect_url = f"{base_url}/api/payment/ccavenue/response"
    
    plain_payload = ccavenue_utils.build_payment_payload(
        order_id=order_id,
        amount=amount,
        currency="INR",
        redirect_url=redirect_url,
        cancel_url=redirect_url,
        client_name=client_name,
        client_phone=row["phone"],
        merchant_id=creds["merchant_id"]
    )
    enc_request = ccavenue_utils.encrypt_ccavenue(plain_payload, working_key) if working_key else ""

    test_simulator_html = f"""
    <div class="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-center space-y-3">
        <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 text-[10px] uppercase font-bold tracking-widest">
            <span>🧪</span> TEST / SANDBOX MODE
        </div>
        <p class="text-[11px] text-gray-400 leading-relaxed">System is running in local test mode. You can test CCAvenue redirect or simulate instant payment success below:</p>
        <form action="/api/payment/ccavenue/response" method="POST" class="pt-1">
            <input type="hidden" name="order_id" value="{order_id}">
            <input type="hidden" name="order_status" value="Success">
            <input type="hidden" name="tracking_id" value="TEST_SIMULATED_{uuid.uuid4().hex[:8].upper()}">
            <button type="submit" class="w-full bg-emerald-500 hover:bg-emerald-600 text-black font-bold text-xs uppercase tracking-widest py-3.5 rounded-full transition-all shadow-md">
                Simulate Payment Success (Local Test)
            </button>
        </form>
    </div>
    """ if mode == "TEST" else ""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Complete Payment — Plant Experience Centre</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background-color: #080808; color: #ffffff; }}
        .serif-title {{ font-family: 'Playfair Display', serif; }}
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-[#121212] border border-white/10 rounded-2xl p-8 text-center space-y-6 shadow-2xl">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-[#C5A073]/10 border border-[#C5A073]/30 text-[#C5A073] mb-2">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
        </div>
        <div>
            <span class="text-[10px] uppercase tracking-widest text-[#C5A073] font-bold">PLANT EXPERIENCE CENTRE</span>
            <h1 class="serif-title text-3xl font-normal mt-1">Invoice Payment</h1>
            <p class="text-xs text-gray-400 mt-1">Invoice #{invoice_id}</p>
        </div>

        <div class="bg-black/50 border border-white/5 p-5 rounded-xl space-y-3">
            <div class="flex justify-between text-xs text-gray-400">
                <span>Customer</span>
                <span class="text-white font-medium">{client_name or 'Valued Customer'}</span>
            </div>
            <div class="flex justify-between text-xs text-gray-400">
                <span>Status</span>
                <span class="font-bold uppercase {'text-emerald-400' if payment_status == 'SUCCESS' else 'text-amber-400'}">{payment_status}</span>
            </div>
            <div class="border-t border-white/10 pt-3 flex justify-between items-center">
                <span class="text-xs uppercase tracking-wider font-bold text-gray-300">Total Amount</span>
                <span class="serif-title text-2xl font-bold text-[#C5A073]">₹{amount:,.2f}</span>
            </div>
        </div>

        {test_simulator_html}

        {"<div class='bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 p-4 rounded-xl text-sm font-semibold'>✓ Payment Completed Successfully</div>" if payment_status == "SUCCESS" else f'''
        <form action="{ccavenue_url}" method="POST" id="ccavenue_form">
            <input type="hidden" name="encRequest" value="{enc_request}">
            <input type="hidden" name="access_code" value="{access_code}">
            <button type="submit" class="w-full bg-[#C5A073] hover:bg-[#b08c62] text-black font-bold text-xs uppercase tracking-widest py-4 rounded-full transition-all shadow-lg">
                Pay via CCAvenue Gateway (₹{amount:,.2f})
            </button>
        </form>
        '''}
        
        <p class="text-[11px] text-gray-500">Secured via CCAvenue SSL Encrypted Gateway ({mode} Mode)</p>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@app.api_route("/api/payment/ccavenue/response", methods=["GET", "POST"])
async def ccavenue_response_callback(request: Request):
    ensure_invoice_payments_table()
    data = {}
    if request.method == "POST":
        try:
            form = await request.form()
            data = dict(form)
        except Exception:
            try:
                data = await request.json()
            except Exception:
                pass
    else:
        data = dict(request.query_params)

    enc_resp = data.get("encResp", "")
    creds = ccavenue_utils.get_ccavenue_credentials()
    working_key = creds["working_key"]

    decrypted_text = ccavenue_utils.decrypt_ccavenue(enc_resp, working_key) if (enc_resp and working_key) else ""
    parsed_resp = ccavenue_utils.parse_ccavenue_response(decrypted_text)

    order_id = parsed_resp.get("order_id", data.get("order_id", ""))
    order_status = parsed_resp.get("order_status", data.get("order_status", "Success"))
    tracking_id = parsed_resp.get("tracking_id", data.get("tracking_id", ""))

    status_upper = str(order_status).upper()
    payment_status = "SUCCESS" if status_upper in {"SUCCESS", "PAID"} else "FAILED"

    if order_id:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE invoice_payments
            SET payment_status = ?, ccavenue_ref_no = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ? OR invoice_id = ?
        """, (payment_status, tracking_id, order_id, order_id))
        conn.commit()
        conn.close()

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Status — Plant Experience Centre</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-[#080808] text-white min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-[#121212] border border-white/10 rounded-2xl p-8 text-center space-y-5">
        <div class="w-16 h-16 rounded-full mx-auto flex items-center justify-center {'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' if payment_status == 'SUCCESS' else 'bg-red-500/10 text-red-400 border border-red-500/30'}">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{'M5 13l4 4L19 7' if payment_status == 'SUCCESS' else 'M6 18L18 6M6 6l12 12'}"></path></svg>
        </div>
        <h1 class="text-2xl font-bold">Payment {'Successful!' if payment_status == 'SUCCESS' else 'Failed'}</h1>
        <p class="text-xs text-gray-400">Order Ref: {order_id}</p>
        {f'<p class="text-xs text-gray-400">CCAvenue Ref: {tracking_id}</p>' if tracking_id else ''}
        <div class="pt-4">
            <a href="/invoice" class="inline-block bg-white/10 hover:bg-white/20 text-white font-semibold text-xs px-6 py-3 rounded-full transition-colors">Return to Dashboard</a>
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@app.get("/api/payment/status/{invoice_id}")
async def get_payment_status(invoice_id: str):
    ensure_invoice_payments_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM invoice_payments WHERE invoice_id = ?", (invoice_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"invoice_id": invoice_id, "payment_status": "UNPAID", "amount": 0.0}

    return {
        "invoice_id": row["invoice_id"],
        "order_id": row["order_id"],
        "amount": row["amount"],
        "payment_status": row["payment_status"],
        "payment_link": row["payment_link"],
        "ccavenue_ref_no": row["ccavenue_ref_no"],
        "updated_at": row["updated_at"]
    }

# ── WhatsApp Microservice Proxy Route ─────────────────────
@app.api_route("/api/whatsapp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def whatsapp_microservice_proxy(path: str, request: Request):
    body = await request.body()
    urls = [
        f"http://chf-whatsapp:3000/api/whatsapp/{path}",
        f"http://whatsapp:3000/api/whatsapp/{path}",
        f"http://127.0.0.1:3000/api/whatsapp/{path}",
        f"http://127.0.0.1:3001/api/whatsapp/{path}",
        f"http://localhost:3000/api/whatsapp/{path}",
        f"http://localhost:3001/api/whatsapp/{path}"
    ]
    
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                data=body if body else None,
                headers=headers,
                method=request.method
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                content = resp.read()
                return Response(
                    content=content,
                    status_code=resp.status,
                    headers=dict(resp.headers)
                )
        except Exception:
            continue
            
    return JSONResponse(
        content={
            "success": False,
            "ready": False,
            "qr": None,
            "error": "WhatsApp service is currently initializing or offline. Pay link created below."
        },
        status_code=200
    )

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
        
    if resolved_path.lower() == "admin-dashboard.html":
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
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

if __name__ == "__main__":
    import uvicorn
    print("Starting CHF FastAPI Secure Backend...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
