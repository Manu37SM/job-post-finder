"""
Perceptual hashing (pHash) for catching the case the other four dedup rules
(post_url/email/author+job/company+role+location) miss: the same flyer
graphic reposted under a different author, different caption text, and a
different contact email - the graphic itself is the only thing in common.

This was deferred out of MVP (see filtering/deduplication.py's original
docstring) as a narrow case not worth the extra dependency until the other
four rules were proven. Built now on request - genuinely additive, nothing
above pipeline.py needed to change.
"""

from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError


def compute_phash(image_path: str | Path) -> str | None:
    """
    Returns the perceptual hash as a hex string, or None if the image can't
    be read - never raises, matching every other function in ocr/ that
    touches image files (a bad image shouldn't stop the post from
    processing on its other signals).
    """
    try:
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        return None


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """
    Bit distance between two hex-string pHashes - 0 means identical, higher
    means more different. A 64-bit pHash tops out at 64. Raises ValueError
    on a malformed hash string rather than silently returning a misleading
    distance - callers should already only be comparing hashes this module
    itself produced.
    """
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def is_near_duplicate(hash_a: str, hash_b: str, max_distance: int) -> bool:
    return hamming_distance(hash_a, hash_b) <= max_distance
