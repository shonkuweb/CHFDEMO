import os
import json
import uuid
import sqlite3
import io
from http.server import SimpleHTTPRequestHandler, HTTPServer
import urllib.parse
from functools import lru_cache

# ── Cloudflare R2 Setup (S3-compatible) ──────────────────────
# Reads credentials from environment variables / .env file.
# If not set, uploads fall back to local disk automatically.
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
        print(f'[R2] Cloudflare R2 connected → bucket: {R2_BUCKET}')
    else:
        r2_client = None
        print('[R2] R2 credentials not set — using local disk fallback.')
except ImportError:
    R2_ENABLED = False
    r2_client = None
    print('[R2] boto3 not installed — using local disk fallback.')

PORT = 8000
DB_PATH = 'chf_archive.db'
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'assets', 'images')

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Database Helper Functions
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@lru_cache(maxsize=32)
def fetch_collection_data(slug):
    """Fetches collection data from DB. Results are cached in memory for extreme speed."""
    print(f"[DB] Cache Miss: Fetching {slug}")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get page meta
    cursor.execute("SELECT * FROM pages WHERE slug = ?", (slug,))
    page_row = cursor.fetchone()
    if not page_row:
        conn.close()
        return None
    
    # Get categories
    cursor.execute("SELECT * FROM categories WHERE page_slug = ? ORDER BY display_order ASC", (slug,))
    cat_rows = cursor.fetchall()
    
    data = {
        "page": dict(page_row),
        "categories": [dict(row) for row in cat_rows]
    }
    
    conn.close()
    return data

@lru_cache(maxsize=64)
def fetch_site_content(prefix):
    """Fetches generic content blocks starting with a prefix."""
    print(f"[DB] Cache Miss: Site Content {prefix}")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT path, value, type FROM site_content WHERE path LIKE ?", (f"{prefix}%",))
    rows = cursor.fetchall()
    conn.close()
    return {row['path']: {'value': row['value'], 'type': row['type']} for row in rows}

def clear_cache():
    fetch_collection_data.cache_clear()
    fetch_site_content.cache_clear()
    print("[CACHE] Memory cleared on update.")

class AdminHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Prevent caching on API requests so updates show immediately
        if self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        super().end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        # API: Site Content Fetching
        if parsed_path.path == '/api/site-content':
            params = urllib.parse.parse_qs(parsed_path.query)
            page = params.get('page', [''])[0]
            data = fetch_site_content(page)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return

        # API: Data Fetching (Legacy Collections)
        if parsed_path.path == '/api/data':
            params = urllib.parse.parse_qs(parsed_path.query)
            slug = params.get('slug', [None])[0]
            
            if not slug:
                self.send_error(400, "Missing slug parameter")
                return
                
            data = fetch_collection_data(slug)
            if not data:
                self.send_error(404, f"Slug {slug} not found in database")
                return
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return
            
        super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        
        # ── High-Speed Upload: R2 first, local fallback ─────────
        if self.path == '/api/upload':
            filename_header = self.headers.get('X-Filename', 'uploaded_media.jpg')
            ext = os.path.splitext(filename_header)[1].lower()
            if not ext: ext = '.jpg'

            unique_name = f"media_{uuid.uuid4().hex[:8]}{ext}"

            # Detect content type for R2
            mime_map = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png',  '.webp': 'image/webp',
                '.gif': 'image/gif',  '.svg': 'image/svg+xml',
                '.mp4': 'video/mp4',  '.webm': 'video/webm',
                '.mov': 'video/quicktime'
            }
            content_type = mime_map.get(ext, 'application/octet-stream')

            # Read entire upload into memory buffer (needed for R2 client)
            file_data = self.rfile.read(content_length)

            if R2_ENABLED and r2_client:
                # ── Upload to Cloudflare R2 ──────────────────────
                try:
                    r2_client.put_object(
                        Bucket=R2_BUCKET,
                        Key=unique_name,
                        Body=file_data,
                        ContentType=content_type
                    )
                    public_url = f"{R2_PUBLIC_URL}/{unique_name}"
                    print(f'[R2] Uploaded: {unique_name} → {public_url}')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'url': public_url, 'storage': 'r2'}).encode('utf-8'))
                    return
                except Exception as r2_err:
                    print(f'[R2] Upload failed ({r2_err}), falling back to local disk.')

            # ── Local Disk Fallback ──────────────────────────────
            file_path = os.path.join(UPLOAD_DIR, unique_name)
            with open(file_path, 'wb') as f:
                f.write(file_data)

            print(f'[LOCAL] Saved: {file_path}')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'url': f'assets/images/{unique_name}', 'storage': 'local'}).encode('utf-8'))
            return
            
        # SQLite Content Saving
        elif self.path == '/api/save':
            raw_body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(raw_body)
                slug = data.get('file')
                payload = data.get('payload')
                
                if not slug or not payload:
                    raise ValueError("Missing slug (file) or payload")
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Update Page Meta
                page = payload.get('page', {})
                cursor.execute('''
                    UPDATE pages SET 
                        title = ?, titleLine1 = ?, titleLine2 = ?, subtitle = ?, breadcrumb = ?
                    WHERE slug = ?
                ''', (
                    page.get('title', ''), page.get('titleLine1', ''), 
                    page.get('titleLine2', ''), page.get('subtitle', ''), 
                    page.get('breadcrumb', ''), slug
                ))
                
                # Categorical reconciliation: Delete old, Insert new (Atomic Replacement)
                cursor.execute("DELETE FROM categories WHERE page_slug = ?", (slug,))
                for idx, cat in enumerate(payload.get('categories', [])):
                    cursor.execute('''
                        INSERT INTO categories (id, page_slug, label, title, description, image, ctaText, ctaLink, display_order)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        cat.get('id', f"{slug}-cat-{idx}"), slug,
                        cat.get('label', ''), cat.get('title', ''), 
                        cat.get('description', ''), cat.get('image', ''),
                        cat.get('ctaText', ''), cat.get('ctaLink', ''), idx
                    ))
                
                conn.commit()
                conn.close()
                
                # Invalidate high-speed cache
                clear_cache()
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'success'}).encode('utf-8'))
                
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8'))
            return
            
        # Site Content Batch Saving
        elif self.path == '/api/site-content/save':
            raw_body = self.rfile.read(content_length).decode('utf-8')
            try:
                updates = json.loads(raw_body) # Expected { path: {value, type}, ... }
                
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
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'success'}).encode('utf-8'))
                
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8'))
            return
            
        else:
            self.send_error(404, "Not Found")

if __name__ == '__main__':
    print(f"Starting CHF Database-Backed Server on port {PORT}...")
    print("In-Memory caching active for extremely fast reads.")
    server = HTTPServer(('', PORT), AdminHTTPRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    print("Server stopped.")
