# LinkedIn Recruiter Post Finder

Personal-use tool that searches LinkedIn **posts** (not job listings) for
Mumbai/Remote Java hiring opportunities, extracts recruiter contact info
(including from images via OCR), filters and deduplicates, and produces a
human-reviewed Excel file compatible with the existing `mass-mailer` project.

**Status: MVP pipeline complete except real LinkedIn scraping.** Every stage
from extraction through export is built, tested (222 tests), and runs
end-to-end today using a JSON fixture file in place of a live LinkedIn
session. See "Current limitations" below.

## Architecture

```
app.py (CLI) / gui.py (Tkinter)   <- two entry points, same underlying pipeline
        |
        v
linkedin/fixture_source.py (--fixture)  or  linkedin/search.py (--live, Playwright)
        |
        v
pipeline.py  (process_post)
        |
        +-- ocr/ (tesseract, image_hash)  -- image -> text, image -> perceptual hash
        +-- extraction/                   -- email, role, location, work mode, company, hiring signal
        +-- filtering/                    -- exclusions, location (Mumbai/Remote), role, relevance, dedup
        |
        v
storage/database.py (SQLite)  <-- also the dedup source of truth / resume state
        |
        v
export/ (excel, csv, text)    <- data/linkedin_recruiters.*
        |
        v
review/reviewer.py (CLI A/R/S)  or  gui.py's Review tab (same GuiController either way)
        |
        v
export/mailer_adapter.py      -> data/approved_recruiters.xlsx (Name/Email/Company/Title)
        |
        v
existing mass-mailer project (run separately, not touched by this project)
```

Every module boundary is a plain dataclass (`core/models.py`) - nothing
outside `linkedin/` knows about Playwright, nothing outside `storage/` knows
about SQLite rows.

## Installation

```bash
pip install -r requirements.txt
```

Tesseract OCR is a **system dependency**, not pip-installable:

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows
# https://github.com/UB-Mannheim/tesseract/wiki
```

**Windows-specific:** the installer above does not reliably add
`tesseract.exe` to PATH. If a real run reports `OCR successes: 0` with
every processed image showing up as a failure, this is almost always why -
`pytesseract` (the Python package) installed fine, but can't find the
actual OCR binary. Fixed two ways, in order of preference:
1. Nothing to do, usually - `ocr/tesseract.py` auto-detects the two common
   default install locations
   (`C:\Program Files\Tesseract-OCR\tesseract.exe` and the `(x86)` variant)
   if the bare `tesseract` command isn't on PATH.
2. If you installed it somewhere else, set `"tesseract_cmd"` in
   `config.json` to the full path of `tesseract.exe`. `logs/ocr-failures.csv`
   will show the real pytesseract error either way, with this fix appended
   to the message.

## Configuration

```bash
cp config.example.json config.json
```

Edit `search_terms`, `accepted_location_aliases`, `accepted_remote_terms`,
`target_roles`, `exclude_keywords` as needed. See `config.example.json` for
the full documented list with the project's defaults already filled in.

### Getting more emails out of one run

The Mumbai-or-explicit-remote filter is deliberately strict, so a run is a
funnel: in a real 125-row dataset, only ~53 were distinct jobs, and a
handful of those survived location/role filtering and review. More output
therefore means feeding the funnel more raw posts - not loosening the
filters. Three levers, biggest first:

```json
"max_scrolls": 40,
"max_posts": 300,
"scroll_pause_seconds": 2.0
```

- **`max_scrolls`** (default 15) - how deep each search term's results get
  scrolled. This was previously a hardcoded constant and was the real cap
  on posts discovered per term. Scrolling stops on its own once 4
  consecutive scrolls find nothing new, so a high ceiling only costs time
  when there genuinely are more results.
- **`max_posts`** (default 100) - overall cap across all search terms
  combined. Raise it alongside `max_scrolls`, or it becomes the new limit.
- **`search_terms`** - each term is its own search, so more distinct terms
  (e.g. `"Java Spring Developer"`, `"Backend Engineer Java"`, `"SDE Java"`)
  surface different posts. Posts found under more than one term are
  deduplicated.

**Tradeoffs, honestly:** a deeper scroll means a longer run and more
automated-looking activity on your LinkedIn account - the same account-risk
flagged at the start of this project. Keep `scroll_pause_seconds` at 1.5 or
above, and prefer a few big runs over many small ones in a day. How many
results LinkedIn will actually serve before the feed ends is LinkedIn's
call and hasn't been measured here - if raising `max_scrolls` stops
increasing "Posts discovered", that's the ceiling, not a bug.

## Running against real LinkedIn

The Playwright layer (`linkedin/session.py`, `search.py`, `posts.py`,
`images.py`) is built and unit-tested (with fake DOM objects, not a real
browser - see "Current limitations"). One-time setup:

```bash
playwright install chromium
python3 -c "from linkedin.session import save_session; save_session('session-linkedin.json')"
# a browser window opens - log in by hand, then press Enter in the terminal
```

Then:

```bash
python app.py --live --session session-linkedin.json
```

`--live` swaps the fixture source for `linkedin.search.discover_posts` -
same pipeline, same exports, same everything else. If the session has
expired you'll get a clear `SessionExpiredError` telling you to rerun
`save_session()`.

## GUI

```bash
python gui.py
```

Four tabs: **Run** (pick fixture/live source, dry-run toggle, live log),
**Review** (table of `NEW` records, click a row for full detail, Approve/
Reject/Skip), **Export** (status counts, one-click
`approved_recruiters.xlsx` export), **Config** (edit and save the handful
of `config.json` fields most worth changing without a text editor).

All logic lives in `gui_controller.py`, which is Tkinter-free and fully
unit-tested (14 tests) - `gui.py` itself is a thin shell that just wires
widgets to it. This split matters here specifically: this sandbox has no
display, so `gui.py` was verified by actually constructing and driving the
real widgets under a virtual framebuffer (Xvfb) rather than left
unverified (the same approach that later caught real bugs in the LinkedIn
layer too - see `linkedin/posts.py`'s docstring). That process caught two
real bugs before you'd have hit them - both fixed:
- Background-thread code was touching Tkinter widgets directly (`RuntimeError:
  main thread is not in main loop`) - fixed by routing run-completion
  through the same queue+poll pattern already used for the live log,
  instead of calling widget methods from the worker thread.
- The SQLite connection opened during a background run couldn't be reused
  from the main thread afterward (`sqlite3.ProgrammingError`) - fixed with
  `check_same_thread=False` in `storage/database.py`, safe here because
  the GUI never accesses the DB from two threads *simultaneously*, only
  sequentially (see that file's comment for the caveat if that ever
  changes).

## Running the demo (fixture source, no LinkedIn needed)

```bash
python app.py --fixture data/sample_posts.json
```

This runs the full pipeline (extraction -> OCR -> filtering -> dedup ->
export) and prints a summary:

```
Posts discovered:         4
Posts processed:          4
...
Records requiring review: 2
```

`data/linkedin_recruiters.xlsx` / `.csv` / `.txt` are written with **every**
processed post (accepted, rejected and excluded alike) for diagnosis - only
`status == NEW` rows are what a human still needs to look at.

To write your own fixture, see `data/sample_posts.json` for the shape: a
JSON list of objects with `post_url`, `post_text`, `image_urls` (local file
paths - no download step exists yet), `author_name`, `author_linkedin_url`,
`author_headline`, `post_date`.

### Review and mailer handoff

```bash
python app.py --fixture data/sample_posts.json --review
```

Runs the pipeline, then walks every `NEW` record for Approve/Reject/Skip in
the terminal, then (unless `--dry-run`) writes
`data/approved_recruiters.xlsx` in the exact schema the existing
`mass-mailer` project reads (`Name`, `Email`, `Company`, `Title`).

### Dry run

```bash
python app.py --dry-run
```

This project never sends email itself (that's `mass-mailer`'s job, run
separately after you've reviewed `approved_recruiters.xlsx`). `--dry-run`
here additionally skips writing `approved_recruiters.xlsx` as an extra
safety margin, even if some records are already `APPROVED` from an earlier
review session. Discovery/extraction/filtering/dedup and the three
general-purpose exports always run either way.

### Resuming

Nothing extra to do - `python app.py` again with the same fixture and the
same `data/linkedin_recruiters.db` automatically skips any `post_url`
already processed. `checkpoint.json` is written after each post as a
human-readable status marker, but the DB itself is the actual resume
mechanism (see `storage/checkpoint.py` docstring for why).

### Starting fresh

```bash
python reset.py
```

Deletes every generated artifact - the database (so resume/dedup history is
gone), all three general exports, `approved_recruiters.xlsx`, downloaded
images, debug captures, and the logs - and asks for confirmation first
(`--yes` to skip that). It does **not** touch `config.json`,
`session-linkedin.json`, or `data/sample_posts.json`, since those are
either your settings or expensive to recreate. It lists exactly what it's
about to delete before asking, so you can always back out.

## Why an email might still be missing

Run the summary and look at `...of which no email`. Most posts that hit it simply
have no address in them (they say "apply on LinkedIn" or "DM me"), and the tool
never invents one. What it does now recover (v11):

- addresses glued to the next word with no space, e.g. `...itsolutions.comENCORE` or `...theittalent.comPlease`
- `hr[at]acme[dot]com` / `hr (at) acme (dot) com`, zero-width characters, full-width `@`
- `mailto:` links that LinkedIn renders with different visible text (added as a `Contact:` line)
- text hidden behind "… more" (the tool now clicks it before reading the post)
- flyers where white text on a coloured background came out blank (OCR retries with gentler preprocessing)
- a valid Mumbai post wrongly dropped as an "email duplicate" of an earlier **skipped** post (e.g. the same recruiter's Pune job)

Still not recovered on purpose: `gmail.commandatory`-style all-lowercase run-ons,
and typos such as `sethijagjit@80gmail.com` - guessing would risk emailing the wrong person.

Rows already in your database are not re-read. To re-evaluate old posts with the
new extractor, run `python reset.py` (keeps `config.json` and your LinkedIn session) and scrape again.

## Continuous integration

`.github/workflows/ci.yml` runs on every push/PR: a guard that fails if `config.json`,
session files, databases or exported data are ever committed, `ruff check`, the full test
suite with warnings as errors (Ubuntu on Python 3.11-3.13 plus Windows), and `pip-audit`.
`.github/workflows/codeql.yml` adds weekly code scanning. `.github/dependabot.yml` opens
weekly grouped PRs for Python packages and for the GitHub Actions themselves.
Nothing in CI logs in to LinkedIn or needs secrets.

Local equivalents: `pip install -r requirements-dev.txt && ruff check . && python -m pytest -W error`.

## Testing

```bash
pytest
```

222 tests, no live LinkedIn or network calls - OCR tests use real Tesseract
against synthetically generated flyer images (Pillow), not mocks.

## Troubleshooting: `--live` prints "Posts discovered: 0"

**Already diagnosed and fixed once** (see `linkedin/posts.py`'s module
docstring for the full story): LinkedIn's post-search page turned out to
use per-build hashed CSS classes (unusable as selectors) and no static
post permalinks at all for ordinary posts. Extraction was rebuilt around
structural DOM traversal (`[role="listitem"]`, ARIA-stable, not a class
name) and validated against 36 real captured posts - 36/36 got usable post
text, 35/36 got author name+headline, 18/36 got a bonus structured
location line from an embedded job card. If `--live` still returns zero
posts after this fix, LinkedIn's markup has changed again since - the same
debug-and-fix process applies:

1. A zero-result run auto-saves a screenshot + HTML dump to
   `data/debug/<search_term>.png` / `.html`. Open the screenshot first:
   - **Posts visible on screen** -> `[role="listitem"]` (or the structural
     assumptions inside `_EXTRACT_JS`) no longer match. Share the `.html`
     and I can re-run the same validation process against it.
   - **Blank/loading/captcha** -> not a markup problem, see the load-timing
     and session notes below instead.
   - **LinkedIn's own "no results" message** -> the search term/URL itself,
     not the parsing.
2. `INITIAL_LOAD_TIMEOUT_MS` (10s, in `linkedin/search.py`) is a guess at
   LinkedIn's render time - increase it if the screenshot shows content
   that just arrived late.
3. You can sanity-check `linkedin/posts.py`'s `_EXTRACT_JS` yourself without
   involving Python at all: open LinkedIn in a real browser, open DevTools'
   Console, paste the function body, and run it against
   `document.querySelectorAll('[role="listitem"]')[0]` - if it returns a
   sensible object there, the extraction logic is fine and the problem is
   elsewhere (timing, session, pagination).

## Current limitations

- **Post permalinks don't exist in LinkedIn's current post-search markup
  for ordinary posts.** Confirmed against 36 real captured posts: only
  posts with an embedded job listing, article repost, or newsletter repost
  expose a real dereferenceable URL (22/36 in the sample) - a plain
  text/image post has no `/feed/update/`, no `/posts/`, no URN anywhere in
  the static DOM. When none of those exist, `post_url` is set to
  `synthetic:<author_profile_url>|<start of post text>` - **not a clickable
  LinkedIn link**, clearly prefixed so it can't be mistaken for one. It
  still works as this project's dedup/identity key throughout, but
  reviewing such a record means finding the post manually via the author's
  profile rather than clicking straight to it. See `linkedin/posts.py`'s
  module docstring for the full investigation.
- **Location and work-mode extraction are text-proximity heuristics, not
  real NLP** - they will misfire on unusual phrasing (see
  `extraction/location_extractor.py` docstring). Treat `job_location` as
  best-effort; the accept/reject decision itself
  (`filtering/location.py`) is exact once given a location and work mode.
- **Company extraction only looks at post text and OCR text**, not
  `author_headline`, even though a recruiter's job title/company often
  appears there. This is a deliberate v1 scope choice (post text is more
  reliably about the job, not the author) rather than an oversight - easy
  to extend `extraction/recruiter_extractor.py` if it turns out headline
  text is a good signal in practice.
- **Deduplication's company+role+location and image-hash fallback checks are
  O(n)** per new record (`db.all_records()` scan) - fine at hundreds/
  low-thousands of rows, would need an indexed hash column to scale further.
- **A synthetic `post_url` can still drift** for a post with no real
  job/pulse/newsletter link at all, if the same post renders with slightly
  different text across two encounters in one run. The much more common
  case - a real `/jobs/view/` link whose `?trackingId=...` query string
  changes on every render (confirmed against a real dataset: 57% of
  distinct jobs affected) - is fixed at the source by stripping the query
  string (see `linkedin/posts.py`'s docstring). `filtering/deduplication.py`'s
  `AUTHOR_SAME_TEXT` rule (same stable `author_linkedin_url` + a shared
  post-text prefix, even with no company/role/location extracted) remains
  as a downstream safety net for the remaining synthetic-URL case.
- **Image-hash dedup (`ocr/image_hash.py`) only compares images that passed
  the `is_worth_ocr` pre-filter** (same set OCR runs on) - deliberately
  consistent with OCR's own icon/logo exclusion, but means two flyer images
  that are both borderline-too-small won't be hash-compared either.
- **SQLite is one denormalized `records` table**, not the
  posts/contacts/extractions/reviews/processing_log split the original
  spec mentioned as a possibility - see `storage/database.py` docstring for
  the reasoning.
