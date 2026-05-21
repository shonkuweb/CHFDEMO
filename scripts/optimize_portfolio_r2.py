#!/usr/bin/env python3
"""
One-off: download portfolio carousel PNGs from R2, generate WebP/AVIF variants,
upload under assets/portfolio/optimized/ (originals unchanged).

Usage (from CHFDEMO-server):
  pip install pillow boto3 python-dotenv
  python scripts/optimize_portfolio_r2.py
  python scripts/optimize_portfolio_r2.py --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip('"')
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID", "").strip('"')
R2_SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip('"')
R2_BUCKET = os.environ.get("R2_BUCKET_NAME", "chf-media").strip('"')
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "").strip('"').rstrip("/")

WIDTHS = [320, 480, 640, 960]
WEBP_QUALITY = 85
AVIF_QUALITY = 65
SIZES_ATTR = "(max-width:768px) 45vw, 240px"

PORTFOLIO_HTML_PATHS = [
    ROOT / "portfolio.html",
    Path(__file__).resolve().parents[2] / "CHFDEMO" / "portfolio.html",
]


def extract_portfolio_png_urls(html_path: Path) -> list[str]:
    text = html_path.read_text(encoding="utf-8")
    urls = set(
        re.findall(
            r"https://pub-[^/]+\.r2\.dev/assets/portfolio/[^\"'\s]+\.png",
            text,
            flags=re.IGNORECASE,
        )
    )
    return sorted(urls)


def png_url_to_r2_key(png_url: str) -> str:
    path = unquote(urlparse(png_url).path.lstrip("/"))
    if not path.startswith("assets/portfolio/"):
        raise ValueError(f"Not a portfolio asset path: {png_url}")
    return path


def optimized_r2_key(png_url: str, width: int, ext: str) -> str:
    key = png_url_to_r2_key(png_url)
    folder_rel = key[len("assets/portfolio/") :]
    folder, filename = folder_rel.rsplit("/", 1)
    stem, _ = os.path.splitext(filename)
    return f"assets/portfolio/optimized/{folder}/{stem}-{width}w.{ext}"


def optimized_public_url(png_url: str, width: int, ext: str) -> str:
    key = optimized_r2_key(png_url, width, ext)
    encoded = "/".join(quote(part, safe="") for part in key.split("/"))
    base = R2_PUBLIC_URL or png_url.split("/assets/")[0]
    return f"{base}/{encoded}"


def srcset_for(png_url: str, ext: str) -> str:
    return ", ".join(f"{optimized_public_url(png_url, w, ext)} {w}w" for w in WIDTHS)


def picture_html(
    png_url: str,
    alt: str,
    *,
    loading: str = "lazy",
    fetchpriority: str | None = None,
) -> str:
    avif = srcset_for(png_url, "avif")
    webp = srcset_for(png_url, "webp")
    fp = f' fetchpriority="{fetchpriority}"' if fetchpriority else ""
    ld = f' loading="{loading}"'
    return (
        f'<picture>'
        f'<source type="image/avif" srcset="{avif}" sizes="{SIZES_ATTR}">'
        f'<source type="image/webp" srcset="{webp}" sizes="{SIZES_ATTR}">'
        f'<img src="{png_url}" alt="{alt}" width="240" height="360" decoding="async"{ld}{fp}>'
        f"</picture>"
    )


def resize_encode(img, width: int, fmt: str) -> bytes:
    from PIL import Image

    w, h = img.size
    if w > width:
        nh = max(1, round(h * width / w))
        resized = img.resize((width, nh), Image.Resampling.LANCZOS)
    else:
        resized = img.copy()

    buf = io.BytesIO()
    if fmt == "webp":
        resized.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
        mime = "image/webp"
    elif fmt == "avif":
        resized.save(buf, format="AVIF", quality=AVIF_QUALITY)
        mime = "image/avif"
    else:
        raise ValueError(fmt)
    return buf.getvalue(), mime


def get_r2_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def download_png(url: str, dest: Path) -> int:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return len(r.content)


def process_image(r2, png_url: str, dry_run: bool) -> dict:
    from PIL import Image

    stats = {
        "png_url": png_url,
        "original_bytes": 0,
        "variant_bytes": 0,
        "uploaded": 0,
        "errors": [],
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "source.png"
        try:
            stats["original_bytes"] = download_png(png_url, tmp_path)
        except Exception as e:
            stats["errors"].append(f"download: {e}")
            return stats

        img = Image.open(tmp_path).convert("RGB")

        for width in WIDTHS:
            for ext in ("webp", "avif"):
                key = optimized_r2_key(png_url, width, ext)
                try:
                    body, mime = resize_encode(img, width, ext)
                    stats["variant_bytes"] += len(body)
                    if dry_run:
                        print(f"  [dry-run] would upload {key} ({len(body)} B)")
                        continue
                    r2.put_object(
                        Bucket=R2_BUCKET,
                        Key=key,
                        Body=body,
                        ContentType=mime,
                        CacheControl="public, max-age=31536000, immutable",
                    )
                    stats["uploaded"] += 1
                    print(f"  ✅ {key} ({len(body):,} B)")
                except Exception as e:
                    stats["errors"].append(f"{key}: {e}")
                    print(f"  ❌ {key}: {e}")

    return stats


def patch_portfolio_html(html_path: Path) -> bool:
    if not html_path.is_file():
        print(f"  ⚠️ Skip missing {html_path}")
        return False

    text = html_path.read_text(encoding="utf-8")
    original = text

    # Preload WebP for spotlight (480w)
    first_png = None
    m0 = re.search(
        r'portfolio-feature-card is-spotlight[^>]*>.*?src="(https://[^"]+/assets/portfolio/[^"]+\.png)"',
        text,
        flags=re.DOTALL,
    )
    if m0:
        first_png = m0.group(1)
        preload_webp = optimized_public_url(first_png, 480, "webp")
        text = re.sub(
            r'<link rel="preload" as="image" href="[^"]+" fetchpriority="high">',
            f'<link rel="preload" as="image" href="{preload_webp}" type="image/webp" fetchpriority="high">',
            text,
            count=1,
        )

    # Replace <img> inside portfolio-feature-card blocks (carousel PNGs only)
    def img_replacer(m: re.Match) -> str:
        tag = m.group(0)
        if "/assets/portfolio/" not in tag or ".png" not in tag:
            return tag
        src_m = re.search(r'src="([^"]+)"', tag)
        if not src_m:
            return tag
        src = src_m.group(1)
        alt_m = re.search(r'alt="([^"]*)"', tag)
        alt = alt_m.group(1) if alt_m else "Portfolio project"
        loading = "eager" if 'loading="eager"' in tag else "lazy"
        fp = None
        if 'fetchpriority="high"' in tag:
            fp = "high"
        elif 'fetchpriority="low"' in tag:
            fp = "low"
        return picture_html(src, alt, loading=loading, fetchpriority=fp)

    # Only replace imgs in portfolio-feature-card blocks
    def replace_cards_block(block: re.Match) -> str:
        chunk = block.group(0)
        return re.sub(r"<img[^>]+/assets/portfolio/[^>]+>", img_replacer, chunk)

    text = re.sub(
        r'<div class="portfolio-feature-card[^"]*"[^>]*>.*?</div>',
        replace_cards_block,
        text,
        flags=re.DOTALL,
    )

    # Picture helper + createCard uses portfolioCreatePicture
    helper = """
        // ── Portfolio carousel responsive images (WebP/AVIF on R2) ──
        (function initPortfolioOptimizedImages() {
            var WIDTHS = [320, 480, 640, 960];
            var SIZES = '(max-width:768px) 45vw, 240px';
            var R2_ORIGIN = 'https://pub-ce8688bc6c654bcfb99716f7c9373bcd.r2.dev';

            function optimizedSrcset(pngSrc, ext) {
                try {
                    var u = new URL(pngSrc);
                    var match = u.pathname.match(/\\/assets\\/portfolio\\/(.+)\\/([^/]+)\\.png$/i);
                    if (!match) return '';
                    var folder = decodeURIComponent(match[1]);
                    var stem = decodeURIComponent(match[2]);
                    var encFolder = folder.split('/').map(function (s) { return encodeURIComponent(s); }).join('/');
                    return WIDTHS.map(function (w) {
                        return R2_ORIGIN + '/assets/portfolio/optimized/' + encFolder + '/'
                            + encodeURIComponent(stem) + '-' + w + 'w.' + ext + ' ' + w + 'w';
                    }).join(', ');
                } catch (e) {
                    return '';
                }
            }

            window.portfolioCreatePicture = function (pngSrc, opts) {
                opts = opts || {};
                var picture = document.createElement('picture');
                var avif = document.createElement('source');
                avif.type = 'image/avif';
                avif.srcset = optimizedSrcset(pngSrc, 'avif');
                avif.sizes = SIZES;
                var webp = document.createElement('source');
                webp.type = 'image/webp';
                webp.srcset = optimizedSrcset(pngSrc, 'webp');
                webp.sizes = SIZES;
                var img = document.createElement('img');
                img.src = pngSrc;
                img.alt = opts.alt || '';
                img.width = 240;
                img.height = 360;
                img.decoding = 'async';
                img.loading = opts.loading || 'lazy';
                if (opts.fetchpriority) img.fetchPriority = opts.fetchpriority;
                picture.appendChild(avif);
                picture.appendChild(webp);
                picture.appendChild(img);
                return picture;
            };
        })();

"""
    marker = "// ── Portfolio carousel: lazy-inject slides"
    if marker in text and "portfolioCreatePicture" not in text:
        text = text.replace(marker, helper + "        " + marker)

    if "portfolioCreatePicture" in text and "createCard" in text:
        text = re.sub(
            r"const img = document\.createElement\('img'\);\s*"
            r"img\.src = slide\.src;\s*"
            r"img\.alt = slide\.alt;\s*"
            r"img\.width = CARD_W;\s*"
            r"img\.height = CARD_H;\s*"
            r"img\.decoding = 'async';\s*"
            r"img\.loading = 'lazy';\s*"
            r"img\.fetchPriority = 'low';\s*"
            r"card\.appendChild\(img\);",
            "card.appendChild(window.portfolioCreatePicture(slide.src, { alt: slide.alt, loading: 'lazy', fetchpriority: 'low' }));",
            text,
        )

    # CSS: picture fills card
    if ".portfolio-feature-card picture" not in text:
        text = text.replace(
            ".portfolio-feature-card img {\n            width: 100%;",
            ".portfolio-feature-card picture,\n        .portfolio-feature-card img {\n            width: 100%;",
        )
        text = text.replace(
            ".portfolio-feature-card.is-spotlight img {",
            ".portfolio-feature-card.is-spotlight picture img,\n        .portfolio-feature-card.is-spotlight img {",
        )
        text = text.replace(
            ".portfolio-feature-card.is-spotlight:hover img {",
            ".portfolio-feature-card.is-spotlight:hover picture img,\n        .portfolio-feature-card.is-spotlight:hover img {",
        )

    if text != original:
        html_path.write_text(text, encoding="utf-8")
        print(f"  📝 Patched {html_path}")
        return True
    print(f"  (no HTML changes) {html_path}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize portfolio carousel images on R2")
    parser.add_argument("--dry-run", action="store_true", help="Skip uploads")
    parser.add_argument("--html-only", action="store_true", help="Only patch portfolio HTML")
    parser.add_argument("--portfolio-html", type=Path, action="append", default=[])
    args = parser.parse_args()

    html_paths = args.portfolio_html or PORTFOLIO_HTML_PATHS
    source_html = next((p for p in html_paths if p.is_file()), ROOT / "portfolio.html")
    urls = extract_portfolio_png_urls(source_html)
    print(f"Found {len(urls)} unique portfolio PNG URLs in {source_html.name}")

    for p in html_paths:
        patch_portfolio_html(p)

    if args.html_only:
        return 0

    creds_ok = all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY, R2_PUBLIC_URL])
    if not creds_ok:
        print("\n❌ R2 credentials missing in CHFDEMO-server/.env")
        print("   HTML references optimized URLs; run this script after adding credentials.")
        print("\nSrcset pattern:")
        print(f"   {{R2_PUBLIC_URL}}/assets/portfolio/optimized/{{folder}}/{{stem}}-{{width}}w.{{webp|avif}}")
        return 1

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("❌ Install Pillow: pip install pillow")
        return 1

    r2 = get_r2_client()
    total_orig = 0
    total_var = 0
    total_uploaded = 0
    all_stats = []

    print(f"\n🚀 Processing {len(urls)} images → bucket {R2_BUCKET}\n")
    for url in urls:
        print(f"\n📷 {url}")
        st = process_image(r2, url, args.dry_run)
        all_stats.append(st)
        total_orig += st["original_bytes"]
        total_var += st["variant_bytes"]
        total_uploaded += st["uploaded"]

    manifest = {
        "widths": WIDTHS,
        "sizes": SIZES_ATTR,
        "webp_quality": WEBP_QUALITY,
        "avif_quality": AVIF_QUALITY,
        "url_pattern": f"{R2_PUBLIC_URL}/assets/portfolio/optimized/{{folder}}/{{stem}}-{{w}}w.{{ext}}",
        "images": len(urls),
        "variants_uploaded": total_uploaded,
        "original_bytes": total_orig,
        "variant_bytes": total_var,
        "stats": all_stats,
    }
    manifest_path = ROOT / "scripts" / "portfolio_optimization_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    saved = total_orig * len(WIDTHS) * 2 - total_var if total_var else 0
    print("\n── Summary ──")
    print(f"  Images: {len(urls)}")
    print(f"  Variants uploaded: {total_uploaded} (expected {len(urls) * len(WIDTHS) * 2})")
    print(f"  Original PNG bytes (download total): {total_orig:,}")
    print(f"  Generated variant bytes: {total_var:,}")
    if total_orig and total_var:
        print(f"  Est. bytes saved vs serving PNG at same widths: ~{max(0, saved):,}")
    print(f"  Manifest: {manifest_path}")
    return 0 if total_uploaded or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
