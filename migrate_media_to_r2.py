import os
import sqlite3
import mimetypes
import glob
from dotenv import load_dotenv

load_dotenv()

R2_ACCOUNT_ID   = os.environ.get('R2_ACCOUNT_ID', '').strip('"')
R2_ACCESS_KEY   = os.environ.get('R2_ACCESS_KEY_ID', '').strip('"')
R2_SECRET_KEY   = os.environ.get('R2_SECRET_ACCESS_KEY', '').strip('"')
R2_BUCKET       = os.environ.get('R2_BUCKET_NAME', 'chf-media').strip('"')
R2_PUBLIC_URL   = os.environ.get('R2_PUBLIC_URL', '').strip('"').rstrip('/')

MEDIA_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.mp4', '.webm', '.mov'}

def get_all_local_media():
    """Recursively find all media files in the project (excluding node_modules etc)."""
    media_files = []
    for ext in MEDIA_EXTENSIONS:
        media_files.extend(glob.glob(f"**/*{ext}", recursive=True))
        media_files.extend(glob.glob(f"**/*{ext.upper()}", recursive=True))
    # Exclude common non-project folders
    media_files = [f for f in media_files if not any(skip in f for skip in ['node_modules', 'venv', 'env', '.git'])]
    return list(set(media_files))

def upload_to_r2(r2_client, local_path):
    """Upload a single file to R2. Returns the public URL or None on failure."""
    mime_t, _ = mimetypes.guess_type(local_path)
    if not mime_t:
        mime_t = 'application/octet-stream'
    
    # Use the relative path as the R2 key (preserves folder structure)
    r2_key = local_path.replace('\\', '/')
    
    try:
        with open(local_path, 'rb') as f:
            r2_client.put_object(
                Bucket=R2_BUCKET,
                Key=r2_key,
                Body=f,
                ContentType=mime_t
            )
        public_url = f"{R2_PUBLIC_URL}/{r2_key}"
        print(f"  ✅ {local_path} → {public_url}")
        return r2_key, public_url
    except Exception as e:
        print(f"  ❌ Failed: {local_path} ({e})")
        return r2_key, None

def update_db(cur, old_path, new_url):
    cur.execute("UPDATE site_content SET value = ? WHERE value = ?", (new_url, old_path))
    cur.execute("UPDATE categories SET image = ? WHERE image = ?", (new_url, old_path))

def update_html_files(mapping):
    """Replace all old local paths with R2 URLs in HTML and Python files."""
    files_to_update = glob.glob("*.html") + glob.glob("*.py")
    for file_path in files_to_update:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            original = content
            for old, new in mapping.items():
                content = content.replace(f"'{old}'", f"'{new}'")
                content = content.replace(f'"{old}"', f'"{new}"')
                content = content.replace(f"url({old})", f"url({new})")
                content = content.replace(f"url('{old}')", f"url('{new}')")
                content = content.replace(f'url("{old}")', f'url("{new}")')
            if content != original:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  📝 Updated references in {file_path}")
        except Exception as e:
            print(f"  ⚠️ Could not update {file_path}: {e}")

def run_migration():
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY, R2_PUBLIC_URL]):
        print("❌ Missing Cloudflare R2 credentials in .env")
        print(f"   R2_ACCOUNT_ID: {'✓' if R2_ACCOUNT_ID else '✗ MISSING'}")
        print(f"   R2_ACCESS_KEY_ID: {'✓' if R2_ACCESS_KEY else '✗ MISSING'}")
        print(f"   R2_SECRET_ACCESS_KEY: {'✓' if R2_SECRET_KEY else '✗ MISSING'}")
        print(f"   R2_PUBLIC_URL: {'✓' if R2_PUBLIC_URL else '✗ MISSING'}")
        return

    import boto3
    from botocore.config import Config

    r2 = boto3.client(
        's3',
        endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto'
    )

    # Discover all local media files
    all_media = get_all_local_media()
    print(f"\n🔍 Found {len(all_media)} media files to migrate:\n")
    for f in sorted(all_media):
        print(f"   {f}")
    
    print(f"\n🚀 Starting upload to R2 bucket: {R2_BUCKET}\n")

    # Upload all files and track the mapping
    mapping = {}  # old_local_path -> new_r2_url
    conn = sqlite3.connect('chf_archive.db')
    cur = conn.cursor()

    for local_path in sorted(all_media):
        r2_key, public_url = upload_to_r2(r2, local_path)
        if public_url:
            mapping[local_path] = public_url
            # Update the DB for this file
            update_db(cur, local_path, public_url)
            # Also try without leading "./"
            clean = local_path.lstrip('./')
            if clean != local_path:
                update_db(cur, clean, public_url)

    conn.commit()
    conn.close()

    # Update all HTML/py references
    print(f"\n📝 Updating codebase references...\n")
    update_html_files(mapping)
    # Also add cleaned paths to mapping
    clean_mapping = {k.lstrip('./'): v for k, v in mapping.items()}
    update_html_files(clean_mapping)

    print(f"\n✅ Migration Complete!")
    print(f"   {len(mapping)} files uploaded to Cloudflare R2")
    print(f"   Database and HTML references updated")
    print(f"\n🌐 Your media is now live at: {R2_PUBLIC_URL}/")

if __name__ == "__main__":
    run_migration()
