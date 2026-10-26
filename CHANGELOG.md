# Changelog

## v11
- Email recall: glued-on text, `[at]`/`[dot]`, zero-width/full-width characters, `mailto:` links, auto-expand "… more", OCR retry for low-contrast flyers.
- Dedup no longer treats skipped (filtered-out) records as duplicates - fixes valid posts lost as "EMAIL" duplicates.
- Fixed: Excel export crashed on control characters in OCR text; CSV now written with a BOM so Excel shows names correctly.
- Fixed: one failing search term (e.g. a goto timeout) no longer discards posts from the other terms; navigation waits for `domcontentloaded` (60s).
- Fixed: GUI Stop button now ends the run between posts.
- Mailer export de-duplicates by email (case-insensitive).
- Summary shows how many posts awaiting review have no email.
- Database closes its connection on garbage collection (clean under `-W error` on Python 3.13).
- Added Dependabot, CI (secret guard, ruff, tests on 3.10-3.13 + Windows, pip-audit), CodeQL, `pyproject.toml`, `requirements-dev.txt`.
