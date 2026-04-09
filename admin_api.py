#!/usr/bin/env python3
"""
CHF Admin API Server
Zero-dependency Python API using stdlib only.
Serves static files AND provides REST API for content management.
Run: python3 admin_api.py
Access: http://localhost:8001
"""

import http.server
import json
import os
import uuid
import mimetypes
from urllib.parse import urlparse, unquote

PORT = 8001
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "assets", "images")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

PAGES = [
    "full-grown-avenue-trees",
    "exotic-indoor-plants",
    "bonsai",
    "curated-plants"
]


class AdminAPIHandler(http.server.SimpleHTTPRequestHandler):
    """Handles both static file serving and API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # CORS headers for local development
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/pages":
            self._list_pages()
        elif path.startswith("/api/pages/"):
            slug = path.split("/api/pages/")[1].rstrip("/")
            self._get_page(slug)
        else:
            # Serve static files
            super().do_GET()

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path.startswith("/api/pages/"):
            slug = path.split("/api/pages/")[1].rstrip("/")
            self._update_page(slug)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/upload":
            self._upload_image()
        elif path.startswith("/api/pages/") and "/categories" in path:
            parts = path.split("/api/pages/")[1].split("/categories")
            slug = parts[0]
            if len(parts) > 1 and parts[1]:
                # POST /api/pages/{slug}/categories/{id} — update specific category
                pass
            else:
                self._add_category(slug)
        else:
            self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path.startswith("/api/pages/") and "/categories/" in path:
            parts = path.split("/api/pages/")[1]
            slug = parts.split("/categories/")[0]
            cat_id = parts.split("/categories/")[1].rstrip("/")
            self._delete_category(slug, cat_id)
        else:
            self.send_error(404)

    # --- API Handlers ---

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        return json.loads(body) if body else {}

    def _load_page(self, slug):
        filepath = os.path.join(DATA_DIR, f"{slug}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r") as f:
            return json.load(f)

    def _save_page(self, slug, data):
        filepath = os.path.join(DATA_DIR, f"{slug}.json")
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def _list_pages(self):
        pages = []
        for slug in PAGES:
            data = self._load_page(slug)
            if data:
                pages.append({
                    "slug": slug,
                    "title": data["page"]["title"],
                    "categoryCount": len(data.get("categories", []))
                })
        self._send_json(pages)

    def _get_page(self, slug):
        if slug not in PAGES:
            self._send_json({"error": "Page not found"}, 404)
            return
        data = self._load_page(slug)
        if not data:
            self._send_json({"error": "Page data not found"}, 404)
            return
        self._send_json(data)

    def _update_page(self, slug):
        if slug not in PAGES:
            self._send_json({"error": "Page not found"}, 404)
            return
        try:
            new_data = self._read_body()
            self._save_page(slug, new_data)
            self._send_json({"success": True, "message": "Page updated"})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _add_category(self, slug):
        if slug not in PAGES:
            self._send_json({"error": "Page not found"}, 404)
            return
        data = self._load_page(slug)
        if not data:
            self._send_json({"error": "Page data not found"}, 404)
            return

        cat_num = len(data["categories"]) + 1
        new_cat = {
            "id": f"cat-{uuid.uuid4().hex[:8]}",
            "label": f"Category {self._to_roman(cat_num)}",
            "title": "New Category",
            "description": "Enter description here...",
            "image": "",
            "ctaText": "Learn More",
            "ctaLink": "inquiry.html"
        }
        data["categories"].append(new_cat)
        self._save_page(slug, data)
        self._send_json(new_cat, 201)

    def _delete_category(self, slug, cat_id):
        if slug not in PAGES:
            self._send_json({"error": "Page not found"}, 404)
            return
        data = self._load_page(slug)
        if not data:
            self._send_json({"error": "Page data not found"}, 404)
            return

        original_len = len(data["categories"])
        data["categories"] = [c for c in data["categories"] if c["id"] != cat_id]

        if len(data["categories"]) == original_len:
            self._send_json({"error": "Category not found"}, 404)
            return

        self._save_page(slug, data)
        self._send_json({"success": True, "message": "Category deleted"})

    def _upload_image(self):
        content_type = self.headers.get("Content-Type", "")

        if "multipart/form-data" in content_type:
            # Parse multipart form data
            boundary = content_type.split("boundary=")[1] if "boundary=" in content_type else None
            if not boundary:
                self._send_json({"error": "No boundary in multipart"}, 400)
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            # Simple multipart parser
            boundary_bytes = boundary.encode()
            parts = body.split(b"--" + boundary_bytes)

            for part in parts:
                if b"filename=" in part:
                    # Extract filename
                    header_end = part.find(b"\r\n\r\n")
                    if header_end == -1:
                        continue
                    header = part[:header_end].decode("utf-8", errors="ignore")
                    file_data = part[header_end + 4:]
                    # Remove trailing \r\n
                    if file_data.endswith(b"\r\n"):
                        file_data = file_data[:-2]
                    if file_data.endswith(b"--"):
                        file_data = file_data[:-2]
                    if file_data.endswith(b"\r\n"):
                        file_data = file_data[:-2]

                    # Extract original filename
                    fn_start = header.find('filename="') + 10
                    fn_end = header.find('"', fn_start)
                    original_name = header[fn_start:fn_end]

                    # Generate unique filename
                    ext = os.path.splitext(original_name)[1].lower() or ".jpg"
                    new_name = f"{uuid.uuid4().hex[:12]}{ext}"
                    filepath = os.path.join(UPLOAD_DIR, new_name)

                    with open(filepath, "wb") as f:
                        f.write(file_data)

                    relative_path = f"assets/images/{new_name}"
                    self._send_json({
                        "success": True,
                        "path": relative_path,
                        "filename": new_name
                    }, 201)
                    return

            self._send_json({"error": "No file found in upload"}, 400)
        else:
            self._send_json({"error": "Expected multipart/form-data"}, 400)

    @staticmethod
    def _to_roman(num):
        vals = [(10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]
        result = ''
        for v, r in vals:
            while num >= v:
                result += r
                num -= v
        return result

    def log_message(self, format, *args):
        """Custom log format."""
        print(f"\033[90m[API]\033[0m {args[0]} \033[33m{args[1]}\033[0m")


def run():
    print(f"""
\033[1m╔══════════════════════════════════════════╗
║     CHF Admin Panel — API Server         ║
╠══════════════════════════════════════════╣
║  Admin Panel:  http://localhost:{PORT}/admin.html
║  API Base:     http://localhost:{PORT}/api/
║  Public Site:  http://localhost:8000
╚══════════════════════════════════════════╝\033[0m
""")
    server = http.server.HTTPServer(("", PORT), AdminAPIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\033[90mServer stopped.\033[0m")
        server.server_close()


if __name__ == "__main__":
    run()
