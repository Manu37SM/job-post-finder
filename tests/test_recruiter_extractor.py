from extraction.recruiter_extractor import detect_hiring_signal, extract_company


def test_detects_hiring_word():
    assert detect_hiring_signal("We're hiring a Java Developer") is True


def test_detects_send_cv_phrase():
    assert detect_hiring_signal("Send CV to jobs@example.com") is True


def test_no_hiring_signal():
    assert detect_hiring_signal("Great weekend hike in Lonavala") is False


def test_empty_text_no_signal():
    assert detect_hiring_signal("") is False


def test_extracts_company_with_pvt_ltd_suffix():
    text = "Join ABC Technologies Pvt Ltd as a Java Developer"
    assert extract_company(text) == "ABC Technologies Pvt Ltd"


def test_extracts_company_with_llp_suffix():
    text = "Hiring at Bright Minds Consulting LLP"
    assert extract_company(text) == "Bright Minds Consulting LLP"


def test_no_company_suffix_returns_none():
    # "ABC" alone has no suffix pattern - must not be guessed as a company.
    text = "Hiring Java Developer at ABC in Mumbai"
    assert extract_company(text) is None


def test_empty_text_no_company():
    assert extract_company("") is None
