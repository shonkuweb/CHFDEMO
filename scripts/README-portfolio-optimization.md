# Portfolio carousel image optimization

## Upload optimized variants to R2

1. Copy `.env.example` → `.env` and set R2 credentials (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`).
2. Install deps: `pip install -r requirements.txt`
3. Run: `python scripts/optimize_portfolio_r2.py`

Original PNGs under `assets/portfolio/` are **not** deleted. Variants are written to:

```
assets/portfolio/optimized/{category}/{filename-stem}-{width}w.{webp|avif}
```

Public URL pattern (matches `portfolio.html` srcset):

```
https://pub-….r2.dev/assets/portfolio/optimized/housing%20projects/6292758B-…-480w.webp
```

Widths: **320, 480, 640, 960** · WebP quality **85** · AVIF quality **65**

## HTML only (no upload)

```bash
python scripts/optimize_portfolio_r2.py --html-only
```

Patches `CHFDEMO-server/portfolio.html` and `CHFDEMO/portfolio.html`.
