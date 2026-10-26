"""
Per-post DOM extraction.

REPLACES an earlier version built on guessed CSS class names
(`div.feed-shared-update-v2` etc.), which returned zero results against a
real LinkedIn session. Real captured HTML (5 search-result pages, 36 posts,
supplied by the user) showed LinkedIn's current post-search page:
  - uses per-build hashed utility classes ("m6fmft", "m6fa49", ...) that are
    NOT selector-stable - guessing at them is a dead end.
  - exposes no post permalink (no /feed/update/, no /posts/, no embedded
    URN) anywhere in the static DOM for ordinary posts. Only a same-author
    embedded job listing (/jobs/view/...) or article/newsletter repost
    (/pulse/, /newsletters/) gives a real dereferenceable URL - present on
    22/36 sampled posts. See _EXTRACT_JS's post_url fallback chain below.

Given that, extraction here uses STRUCTURAL DOM traversal (ARIA role,
element containment, text shape) rather than class-name selectors, executed
as JS via Playwright's element.evaluate() - this kind of "walk up the tree
until a container has the right shape" logic is far cleaner to express in
JS run in-browser than through chained Python Locator calls. The JS itself
was validated by running it (via Node + jsdom, not simulated) against all
36 real sampled posts before being embedded here: 36/36 got usable post
text, 35/36 got name+headline (the one miss was a LinkedIn Group post,
structurally different from a personal-profile post and out of scope),
18/36 got a clean structured "<City> (<Mode>)" location line from an
embedded job card, 22/36 got a real post_url.

TEXT-CONCATENATION BUG, FOUND AND FIXED after initial live use: all text
reads originally used `.textContent`, which does NOT insert a separator
across a `<br>` tag - confirmed directly: an element containing
"...jobs@example.com<br>Please apply..." gives `textContent` ==
"...jobs@example.comPlease apply..." (mashed together) but `innerText` ==
"...jobs@example.com\nPlease apply..." (correct). LinkedIn posts commonly
use `<br>` for line breaks, so any post with a line break right after an
email produced garbage like "gmail.commandatory" or "grainwish.com.feel" -
a real user's first live run surfaced exactly this in its exported
Name/Email/Company/Title sheet. Every text read below now uses
`.innerText` instead, which requires actual rendered layout (this is why
the Node+jsdom validation above couldn't have caught it - jsdom has no
layout engine - but tests/test_linkedin_posts_real_browser.py, which uses
real Chromium, now carries a regression test for this exact case).
extraction/email_extractor.py also got a second, independent layer of
defense against the same symptom - see that module's docstring.

TRACKING-ID URL BUG, FOUND AND FIXED against a real user's full dataset:
the `/jobs/view/` link capture originally kept the full href, including
LinkedIn's `?trackingId=...&isJobSearch=...` query string - which changes
on EVERY render of the same job card, even within one page/scroll. In a
real 125-row dataset, this meant 30 of 53 distinct jobs (57%) appeared as
2-6 "separate" post_url rows each, since post_url is this project's
dedup/identity key throughout. Fixed by stripping the query string and
fragment from job/pulse/newsletter links before using them as post_url -
the canonical path alone is stable and still a fully working link.
filtering/deduplication.py's AUTHOR_SAME_TEXT rule (added as a downstream
safety net before this was root-caused) still helps for genuinely
synthetic post_urls, but this fix is what actually stops the volatility at
its source for the much more common case of a real job link.

"SEE MORE" SUFFIX BUG: the trailing-truncation strip pattern only matched
"\u2026more" with no space; real captured text showed "\u2026 more" (with a
space) just as often, leaving "... more" appended to extracted post_text.
Fixed by allowing optional whitespace between the ellipsis and "more".

POST_URL NOTE: when no real permalink exists, post_url is set to
"synthetic:<author_url>|<start of post text>" - NOT a clickable LinkedIn
link. This is intentional and clearly flagged (the "synthetic:" prefix)
rather than fabricating a fake-looking URL - it still works as this
project's dedup/identity key, but a human reviewing such a record needs to
find the post manually (via the author's profile) rather than clicking
through. See README "Current limitations".
"""

POST_CONTAINER_SELECTOR = '[role="listitem"]'

# Executed in-browser via el.evaluate(_EXTRACT_JS). Keep this in sync with
# /home/claude/js_extract_test/extract.js if you re-validate against new
# captures - that standalone copy is what gets tested via Node+jsdom
# without needing a real LinkedIn session.
_EXTRACT_JS = r"""
(el) => {
    const timeRe = /^(?:\d+[smhdwy]|now|just now|[A-Za-z]{3}\s+\d{1,2})(?:\s*\u2022\s*Edited)?$/i;
    const degreeRe = /^\u2022?\s*(1st|2nd|3rd\+?|\d+(st|nd|rd|th))$/i;
    const locModeRe = /^(.+?)\s*\((On-site|Onsite|Remote|Hybrid)\)$/i;

    const allAuthorLinks = Array.from(el.querySelectorAll('a[href*="/in/"]'));
    let authorLink = null;
    for (const a of allAuthorLinks) {
        if (a.innerText.trim()) { authorLink = a; break; }
    }

    let authorName = null, authorLinkedinUrl = null, authorHeadline = null;
    let headerContainer = null;

    if (authorLink) {
        authorLinkedinUrl = authorLink.getAttribute('href');
        let node = authorLink;
        for (let level = 0; level < 6; level++) {
            node = node.parentElement;
            if (!node) break;
            const spans = Array.from(node.querySelectorAll('span'))
                .map(s => s.innerText.trim())
                .filter(t => t.length > 0);
            const timeIdx = spans.findIndex(t => timeRe.test(t));
            if (spans.length >= 3 && timeIdx !== -1) {
                authorName = spans[0];
                for (let i = 1; i < timeIdx; i++) {
                    if (!degreeRe.test(spans[i])) { authorHeadline = spans[i]; break; }
                }
                headerContainer = node;
                break;
            }
        }
    }

    let postText = "";
    const candidates = Array.from(el.querySelectorAll('span, p'));
    for (const c of candidates) {
        if (headerContainer && headerContainer.contains(c)) continue;
        const text = c.innerText.trim();
        if (text.length > postText.length) postText = text;
    }
    // Strips LinkedIn's "see more" toggle text trailing the real content.
    // \s* between the ellipsis and "more" because real captured text showed
    // "\u2026 more" (with a space) as often as "\u2026more" (no space) -
    // the original version without \s* here missed the spaced form,
    // leaving "... more" appended to extracted post_text.
    postText = postText.replace(/\u2026\s*more\s*$/i, '').trim();

    let jobLocationLine = null;
    for (const c of candidates) {
        const text = c.innerText.trim();
        if (locModeRe.test(text) && text.length < 80) {
            if (jobLocationLine === null || text.length < jobLocationLine.length) {
                jobLocationLine = text;
            }
        }
    }
    // Fold the structured job-card location line into post_text as a
    // labeled line so extraction/location_extractor.py's existing
    // "Location:" regex picks it up at HIGH confidence for free - no
    // extractor changes needed for this to take effect.
    if (jobLocationLine) {
        postText = postText + "\nLocation: " + jobLocationLine;
    }

    // mailto: links: LinkedIn sometimes renders the address as a link whose
    // visible text is shortened or styled differently, so the plain-text
    // pass can miss it. Appended AFTER the first 80 chars are used for the
    // synthetic URL below, so adding them never changes a post's identity.
    const mailtos = [];
    for (const a of el.querySelectorAll('a[href^="mailto:"]')) {
        const addr = decodeURIComponent((a.getAttribute('href') || '').slice(7).split('?')[0]).trim();
        if (addr && !postText.toLowerCase().includes(addr.toLowerCase())
                 && !mailtos.includes(addr)) mailtos.push(addr);
    }
    const identityText = postText;
    if (mailtos.length) postText = postText + "\nContact: " + mailtos.join(", ");

    const imageUrls = [];
    for (const img of el.querySelectorAll('img')) {
        if (headerContainer && headerContainer.contains(img)) continue;
        const src = img.getAttribute('src');
        if (src) imageUrls.push(src);
    }

    const allHrefs = Array.from(el.querySelectorAll('a[href]')).map(a => a.getAttribute('href'));
    let postUrl = allHrefs.find(h => h && h.includes('/jobs/view/'))
        || allHrefs.find(h => h && h.includes('/pulse/'))
        || allHrefs.find(h => h && h.includes('/newsletters/'))
        || null;

    // Strip query string and fragment - LinkedIn appends a per-render
    // tracking parameter (?trackingId=...&isJobSearch=...) to /jobs/view/
    // links that changes EVERY time the same job card renders, even within
    // one page/scroll. Keeping it made the same real job look like a
    // different post_url each time it was encountered - confirmed against
    // a real dataset where this caused 30 of 53 distinct jobs to appear as
    // 2-6 "separate" rows each. The canonical path alone
    // (.../jobs/view/<id>/) is stable and still a fully working link.
    if (postUrl) {
        postUrl = postUrl.split('?')[0].split('#')[0];
    }

    if (!postUrl) {
        const base = (authorLinkedinUrl || "unknown-author") + "|" + identityText.slice(0, 80);
        postUrl = "synthetic:" + base;
    }

    return {
        post_url: postUrl,
        post_text: postText,
        image_urls: imageUrls,
        author_name: authorName,
        author_linkedin_url: authorLinkedinUrl,
        author_headline: authorHeadline,
        post_date: null,
    };
}
"""


# Clicks LinkedIn's "… more" / "see more" toggle so text hidden behind it
# (very often the "send your CV to ..." line, i.e. the email) is in the DOM
# before extraction. Best-effort: returns how many toggles it pressed.
_EXPAND_JS = r"""
(el) => {
    let clicked = 0;
    for (const b of el.querySelectorAll('button, span[role="button"]')) {
        const label = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).trim();
        if (/(\u2026|\.\.\.)\s*(see\s+)?more\s*$/i.test(label) || /^see\s+more\b/i.test(label)) {
            try { b.click(); clicked++; } catch (e) {}
        }
    }
    return clicked;
}
"""


def expand_post(el, settle_ms: int = 150) -> int:
    """Expand a truncated post; never raises. Returns the number of toggles clicked."""
    try:
        clicked = el.evaluate(_EXPAND_JS)
        if clicked:
            el.page.wait_for_timeout(settle_ms)
        return int(clicked or 0)
    except Exception:  # noqa: BLE001 - expansion is an optimisation only
        return 0


def parse_post_element(el) -> dict | None:
    """
    Best-effort extraction from one post's DOM element (a Playwright
    Locator matching POST_CONTAINER_SELECTOR). Returns None (skip this
    post) if evaluation fails or no post_url could be produced at all -
    any single malformed post shouldn't stop the rest of the search.
    """
    expand_post(el)
    try:
        result = el.evaluate(_EXTRACT_JS)
        if not result or not result.get("post_url"):
            return None
        return result
    except Exception:
        return None
