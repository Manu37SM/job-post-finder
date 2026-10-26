"""
Downloads post images to local files so ocr/tesseract.py (which reads from
disk, not URLs) can process them. Uses the already-authenticated Playwright
page's request context so LinkedIn CDN auth/cookies carry over correctly.

Isolated from the rest of the pipeline - returns a plain
{image_url: local_path} dict, exactly the shape pipeline.process_post
already expects for its image_downloads argument (see pipeline.py, already
built and tested against that contract).
"""

from pathlib import Path
from urllib.parse import urlparse


def download_images(page, image_urls: list[str], dest_dir: str | Path) -> dict[str, str]:
    """
    Failures are skipped, not raised - a single missing/broken image
    shouldn't stop the post from being processed on its text alone (OCR
    failures for images that DO download are handled separately, inside
    pipeline.process_post / ocr/tesseract.py).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloads: dict[str, str] = {}
    for i, url in enumerate(image_urls):
        try:
            response = page.request.get(url)
            if not response.ok:
                continue
            ext = Path(urlparse(url).path).suffix or ".jpg"
            local_path = dest_dir / f"img_{i}_{abs(hash(url))}{ext}"
            local_path.write_bytes(response.body())
            downloads[url] = str(local_path)
        except Exception:
            continue

    return downloads
