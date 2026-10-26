import pytest

from core.models import EmailSource
from extraction.email_extractor import extract_emails, find_emails, normalize_obfuscation


def test_find_emails_basic():
    assert find_emails("Send CV to jobs@example.com") == ["jobs@example.com"]


def test_find_emails_lowercases_and_dedupes():
    text = "Contact Jobs@Example.com or JOBS@EXAMPLE.COM"
    assert find_emails(text) == ["jobs@example.com"]


def test_find_emails_none_present():
    assert find_emails("Hiring Java Developer in Mumbai") == []


def test_find_emails_empty_string():
    assert find_emails("") == []


def test_extract_emails_post_text_only():
    emails, primary, source = extract_emails("Send CV to jobs@example.com", "")
    assert emails == ["jobs@example.com"]
    assert primary == "jobs@example.com"
    assert source == EmailSource.POST_TEXT


def test_extract_emails_ocr_only():
    emails, primary, source = extract_emails("", "jobs@example.com")
    assert emails == ["jobs@example.com"]
    assert primary == "jobs@example.com"
    assert source == EmailSource.IMAGE_OCR


def test_extract_emails_both_sources():
    emails, primary, source = extract_emails(
        "Hiring Java Developer, send CV to hr@example.com",
        "URGENT HIRING jobs@example.com",
    )
    assert set(emails) == {"hr@example.com", "jobs@example.com"}
    assert source == EmailSource.BOTH
    # "send CV to" hint should pick hr@example.com over the OCR one
    assert primary == "hr@example.com"


def test_extract_emails_none_found():
    emails, primary, source = extract_emails("Hiring Java Developer in Mumbai", "")
    assert emails == []
    assert primary is None
    assert source == EmailSource.NONE


def test_extract_emails_never_fabricates_from_name():
    # No email anywhere in the text -> must stay empty even though a plausible
    # one could be guessed from the name.
    emails, primary, source = extract_emails("Contact John Doe, HR at Acme Corp", "")
    assert emails == []
    assert primary is None


# ---- TLD whitelist hardening: regression tests for a real bug ----
# These exact garbage strings came from a user's first live run - see
# extraction/email_extractor.py's module docstring and linkedin/posts.py's
# "TEXT-CONCATENATION BUG" note for the root cause (a <br> between an email
# and the following line got silently dropped during extraction, before
# that was fixed - this is the second, independent layer of defense).


def test_rejects_concatenated_garbage_gmail_commandatory():
    assert find_emails("dhanakrajput1011@gmail.commandatory") == []


def test_rejects_concatenated_garbage_gmail_complease():
    assert find_emails("dv2592889@gmail.complease") == []


def test_extracts_correct_email_despite_trailing_garbage_suffix():
    # "suman@grainwish.com.feel" - ".feel" isn't a real TLD, so the
    # whitelist should fall back to the shorter, genuinely valid email.
    assert find_emails("suman@grainwish.com.feel") == ["suman@grainwish.com"]


def test_still_extracts_normal_emails_unaffected():
    assert find_emails("cv.sushree@mindbrain.co.in") == ["cv.sushree@mindbrain.co.in"]
    assert find_emails("dm.amresh@agileventures.net") == ["dm.amresh@agileventures.net"]
    assert find_emails("lalit.sultania@grouptobias.com") == ["lalit.sultania@grouptobias.com"]


def test_bare_in_tld_still_works():
    assert find_emails("contact@example.in") == ["contact@example.in"]


def test_co_in_tried_before_bare_in():
    # Must not truncate "co.in" down to matching just "in" some other way -
    # the whole ".co.in" suffix should be part of the match.
    assert find_emails("hr@company.co.in") == ["hr@company.co.in"]


def test_unknown_tld_is_not_extracted_at_all():
    # ".feel" isn't whitelisted and there's no shorter valid fallback here -
    # correctly extracts nothing rather than guessing.
    assert find_emails("someone@example.feel") == []


# --- v11: recall fixes found by replaying a real export ---------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("share resume to:venkatesh@encore-itsolutions.comENCORE IT SOLUTIONS", "venkatesh@encore-itsolutions.com"),
        ("share their updated CV at:anas.shaikh@theittalent.comPlease mention Zoho", "anas.shaikh@theittalent.com"),
        ("mail hr[at]acme[dot]com today", "hr@acme.com"),
        ("mail hr (at) acme (dot) co.in", "hr@acme.co.in"),
        ("hr​@acme.com", "hr@acme.com"),
        ("hr＠acme.com is wrong but jobs＠acme.com", "jobs@acme.com"),
    ],
)
def test_recovers_real_world_variants(text, expected):
    assert expected in find_emails(text)


def test_all_lowercase_glue_is_still_rejected():
    assert find_emails("gmail.commandatory a@gmail.commandatory") == []


def test_prose_at_is_not_rewritten():
    assert normalize_obfuscation("meet at noon") == "meet at noon"
    assert find_emails("see you at home dot com") == []


def test_no_duplicates_between_strict_and_glued():
    assert find_emails("a@b.com and a@b.comThanks") == ["a@b.com"]
