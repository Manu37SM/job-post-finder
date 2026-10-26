"""
Deterministic email extraction. No fabrication, no name-based generation -
only what's literally present in the text.

TLD WHITELIST, added after a real bug: the original pattern used a
wide-open `[A-Za-z]{2,}` for the TLD, which doesn't know where a real TLD
ends - given "gmail.commandatory" (a genuine concatenation artifact from a
missing line-break separator upstream, see linkedin/posts.py's docstring),
it happily matched the whole thing as one "TLD". Restricting to a known-TLD
alternation plus a trailing (?![A-Za-z0-9]) boundary check means "com" can
match inside "commandatory" without a boundary problem on its own, but the
alternation engine must find literal "com" (or another whitelisted TLD) at
the parse position reached after backtracking the domain-part - for
"gmail.commandatory" there is only one literal "." in the string, so the
only attempt is matching "commandatory" against the whitelist, which fails
entirely (no alternative matches, and "com" + boundary-check also fails
since "m" immediately follows) -> correctly extracts NO email rather than
a wrong one. Preferring "missing" over "wrong" matches this project's
existing "never fabricate" principle, just extended to cover corrupted
input as well as absent input.

Not an exhaustive IANA TLD list (1500+) - a curated set covering common
global gTLDs plus Indian ccTLD combinations (this is an India-focused
hiring tool). A legitimate but unusual TLD not on this list will be missed
entirely rather than mis-extracted - add it to _KNOWN_TLDS below if that
turns out to matter in practice.
"""

import re

from core.models import EmailSource

_KNOWN_TLDS = sorted(
    [
        # Generic
        "com", "net", "org", "io", "co", "me", "info", "biz", "dev", "app",
        "tech", "xyz", "online", "site", "inc", "agency", "solutions",
        "cloud", "email", "edu", "gov", "mil", "int", "name", "pro",
        # India-focused ccTLD combinations
        "co.in", "org.in", "net.in", "gov.in", "edu.in", "ac.in", "res.in",
        "firm.in", "gen.in", "ind.in", "in",
        # Other common country TLDs
        "co.uk", "com.au", "us", "uk", "ca", "au", "de", "fr", "sg", "ae", "nl",
    ],
    key=len,
    reverse=True,  # longest first, so "co.in" is tried before bare "in"
)
_TLD_ALTERNATION = "|".join(re.escape(tld) for tld in _KNOWN_TLDS)
_EMAIL_RE = re.compile(
    rf"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.(?:{_TLD_ALTERNATION})(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Emails glued to the next word with no separator (a real pattern in LinkedIn
# posts, e.g. "...resume to:venkatesh@encore-itsolutions.comENCORE IT" or
# "...@theittalent.comPlease mention"). The strict pattern above refuses these
# because "com" is followed by a letter. We accept them ONLY when the TLD is
# lower-case and the glued text starts a new capitalised word ("Please",
# "ENCORE"), a camel-case boundary. All-lower-case runs such as
# "gmail.commandatory" stay rejected: that one is ambiguous, and we prefer
# missing over wrong. Matched case-sensitively on purpose.
_GLUED_RE = re.compile(
    rf"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.(?:{_TLD_ALTERNATION})(?=[A-Z][a-z]|[A-Z]{{2}})"
)

_INVISIBLE_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
_AT_WORD_RE = re.compile(r"\s*[\[\(\{<]\s*at\s*[\]\)\}>]\s*", re.IGNORECASE)
_DOT_WORD_RE = re.compile(r"\s*[\[\(\{<]\s*dot\s*[\]\)\}>]\s*", re.IGNORECASE)


def normalize_obfuscation(text: str) -> str:
    """
    Undo the common, unambiguous ways people hide an address from scrapers:
    zero-width characters, full-width '@', and bracketed "[at]" / "(dot)".
    A bare " at " / " dot " is NOT rewritten - too many false positives in
    ordinary prose.
    """
    text = _INVISIBLE_RE.sub("", text)
    text = text.replace("\uff20", "@").replace("\ufe6b", "@")
    text = _AT_WORD_RE.sub("@", text)
    text = _DOT_WORD_RE.sub(".", text)
    return text


# Best-effort proximity hint for picking a primary when several emails are present.
_CONTACT_HINTS = (
    "send cv",
    "send resume",
    "share cv",
    "share resume",
    "apply at",
    "apply to",
    "contact",
    "reach out",
)


def find_emails(text: str) -> list[str]:
    """Extract, lowercase-normalize and dedupe emails from a single string, order preserved."""
    if not text:
        return []
    text = normalize_obfuscation(text)
    found: list[tuple[int, str]] = []
    for rx in (_EMAIL_RE, _GLUED_RE):
        for m in rx.finditer(text):
            found.append((m.start(), m.group(0)))
    seen: list[str] = []
    for _, match in sorted(found):
        normalized = match.lower().rstrip(".")
        if normalized not in seen:
            seen.append(normalized)
    return seen


def extract_emails(
    post_text: str, ocr_text: str = ""
) -> tuple[list[str], str | None, EmailSource]:
    """
    Extract emails from post text and OCR text separately (so the source can be
    tagged), merge + dedupe for all_emails, and pick a primary_email.

    Returns ([], None, EmailSource.NONE) if nothing is found - never invents one.
    """
    from_text = find_emails(post_text)
    from_ocr = find_emails(ocr_text)

    all_emails: list[str] = []
    for e in from_text + from_ocr:
        if e not in all_emails:
            all_emails.append(e)

    if not all_emails:
        return [], None, EmailSource.NONE

    if from_text and from_ocr:
        source = EmailSource.BOTH
    elif from_text:
        source = EmailSource.POST_TEXT
    else:
        source = EmailSource.IMAGE_OCR

    primary = _pick_primary(f"{post_text}\n{ocr_text}", all_emails)
    return all_emails, primary, source


def _pick_primary(full_text: str, emails: list[str]) -> str:
    """Prefer the email nearest a 'send CV to' style phrase; else the first one found."""
    lowered = full_text.lower()
    for hint in _CONTACT_HINTS:
        idx = lowered.find(hint)
        if idx == -1:
            continue
        window = lowered[max(0, idx - 20) : idx + 120]
        for email in emails:
            if email in window:
                return email
    return emails[0]
