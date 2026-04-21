import os
import json
import uuid
import sqlite3
import io
import urllib.parse
import urllib.request
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from functools import lru_cache
from datetime import datetime, timedelta
from passlib.hash import argon2
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
    cursor.execute("SELECT path, value, type FROM site_content WHERE path LIKE ?", (f"{prefix}%",))
    rows = cursor.fetchall()
    conn.close()
    return {row['path']: {'value': row['value'], 'type': row['type']} for row in rows}

def clear_cache():
    fetch_collection_data.cache_clear()
    fetch_site_content.cache_clear()

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
    ensure_sync_state_table()

# ── Endpoints ───────────────────────────────

@app.post("/api/login")
async def login(
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
    
    try:
        if not argon2.verify(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception:
        raise HTTPException(status_code=401, detail="Error verifying credential")
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + access_token_expires
    to_encode = {"sub": username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    is_https = os.environ.get("HTTPS_ENABLED", "false").lower() == "true"
    response.set_cookie(
        key="admin_session", 
        value=encoded_jwt, 
        httponly=True, 
        secure=is_https, 
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

    try:
        if not argon2.verify(current_password, row["password_hash"]):
            conn.close()
            raise HTTPException(status_code=401, detail="Current password is incorrect")
    except HTTPException:
        raise
    except Exception:
        conn.close()
        raise HTTPException(status_code=401, detail="Failed to verify current password")

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
    ext = os.path.splitext(filename_header)[1].lower()
    if not ext: ext = '.jpg'
    unique_name = f"media_{uuid.uuid4().hex[:8]}{ext}"
    
    file_data = await request.body()
    
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
            
    return FileResponse(resolved_path)

if __name__ == "__main__":
    import uvicorn
    print("Starting CHF FastAPI Secure Backend...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
