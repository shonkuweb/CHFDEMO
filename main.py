import os
import json
import uuid
import sqlite3
import io
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Form, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from functools import lru_cache
from datetime import datetime, timedelta
from passlib.hash import argon2
from jose import jwt, JWTError

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

# ── Endpoints ───────────────────────────────

@app.post("/api/login")
async def login(
    response: Response, 
    username: str = Form(...), 
    password: str = Form(...),
    cf_turnstile_response: str = Form(None)
):
    import urllib.request
    import urllib.parse
    
    # Verify Turnstile
    TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET")
    if TURNSTILE_SECRET and cf_turnstile_response:
        url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        data = urllib.parse.urlencode({
            'secret': TURNSTILE_SECRET,
            'response': cf_turnstile_response
        }).encode('utf-8')
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req) as res:
                outcome = json.loads(res.read())
                if not outcome.get("success"):
                    raise HTTPException(status_code=403, detail="Bot protection validation failed")
        except Exception:
            raise HTTPException(status_code=403, detail="Bot protection network error")

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
    
    response.set_cookie(
        key="admin_session", 
        value=encoded_jwt, 
        httponly=True, 
        secure=True, 
        samesite="strict", 
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    return {"message": "Success"}

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("admin_session")
    return {"message": "Logged out"}

@app.get("/api/site-content")
async def get_site_content(page: str = ''):
    return fetch_site_content(page)

@app.get("/api/data")
async def get_data(slug: str):
    data = fetch_collection_data(slug)
    if not data:
        raise HTTPException(status_code=404, detail="Not found")
    return data

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), admin: str = Depends(get_current_admin)):
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else '.jpg'
    unique_name = f"media_{uuid.uuid4().hex[:8]}{ext}"
    
    file_data = await file.read()
    
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
    return {"status": "success"}

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
    return {"status": "success"}

@app.get("/{path:path}")
async def serve_static(request: Request, path: str):
    if not path or path == "/":
        path = "index.html"
        
    if path.endswith(".py") or path.endswith(".db") or path == ".env" or path.startswith("."):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    if path == "admin.html":
        token = request.cookies.get("admin_session")
        if not token:
            return RedirectResponse("/admin-login.html")
        try:
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            return RedirectResponse("/admin-login.html")
            
    if os.path.isfile(path):
        return FileResponse(path)
        
    raise HTTPException(status_code=404, detail="Not Found")

if __name__ == "__main__":
    import uvicorn
    print("Starting CHF FastAPI Secure Backend...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
