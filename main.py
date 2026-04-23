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
    return {row['path']: {'value': row['value'], 'type': row['type']} for row in rows}

def clear_cache():
    fetch_collection_data.cache_clear()
    fetch_site_content.cache_clear()

SITE_CONTENT_DEFAULTS = {
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
    "plant-center/hero/video": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/chf_video_placeholder.mp4",
        "type": "media",
    },
    "plant-center/intro/title": {
        "value": "An Immersive <br/>Botanical Archive",
        "type": "text",
    },
    "plant-center/intro/body": {
        "value": "Far beyond a traditional nursery, the Alipore Experience Center is designed as a living gallery. We invite architects, interior designers, and collectors to walk through staggered glasshouses, bonsai viewing decks, and rare specimen yards to visualize the scale, texture, and character of the plants in their ideal environment.",
        "type": "longtext",
    },
    "plant-center/gallery/img1": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/curated_specimens.png",
        "type": "media",
    },
    "plant-center/gallery/img2": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/about/aboutus_legacy.png",
        "type": "media",
    },
    "plant-center/gallery/img3": {
        "value": "https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev/assets/images/services/architectural_harmony.png",
        "type": "media",
    },
    "arch/hero/subtitle": {
        "value": "Design is Instant. Growth is Inevitable. We Plan for Both.",
        "type": "text",
    },
    "arch/closing/title": {
        "value": "We don\u2019t just develop gardens.<br><span class=\"text-accent-bronze italic mt-4 block\">We future-proof them.</span>",
        "type": "text",
    },
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

    for path, payload in SITE_CONTENT_DEFAULTS.items():
        cur.execute("SELECT 1 FROM site_content WHERE path = ?", (path,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO site_content (path, value, type) VALUES (?, ?, ?)",
                (path, payload["value"], payload["type"]),
            )

    conn.commit()
    conn.close()

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
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.on_event("startup")
def startup_init_sync_state():
    migrate_legacy_site_content_keys()
    ensure_sync_state_table()

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
    conn = get_db_connection()
    cursor = conn.cursor()
    for path, data in updates.items():
        cursor.execute('''
            INSERT OR REPLACE INTO site_content (path, value, type)
            VALUES (?, ?, ?)
        ''', (path, data.get('value'), data.get('type')))
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
    # Keep HTML always fresh to avoid stale shell flashes after publish.
    if resolved_path.lower().endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    import uvicorn
    print("Starting CHF FastAPI Secure Backend...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
