from linkedin.images import download_images


class FakeResponse:
    def __init__(self, ok: bool, body: bytes = b""):
        self.ok = ok
        self._body = body

    def body(self):
        return self._body


class FakeRequest:
    def __init__(self, responses: dict):
        self._responses = responses  # url -> FakeResponse (or an Exception instance to raise)

    def get(self, url):
        result = self._responses.get(url)
        if isinstance(result, Exception):
            raise result
        if result is None:
            return FakeResponse(ok=False)
        return result


class FakePage:
    def __init__(self, responses: dict):
        self.request = FakeRequest(responses)


def test_downloads_successful_images(tmp_path):
    page = FakePage(
        {
            "https://media.licdn.com/img1.jpg": FakeResponse(ok=True, body=b"fake-jpeg-bytes"),
        }
    )
    result = download_images(page, ["https://media.licdn.com/img1.jpg"], tmp_path)

    assert "https://media.licdn.com/img1.jpg" in result
    local_path = result["https://media.licdn.com/img1.jpg"]
    assert local_path.endswith(".jpg")
    with open(local_path, "rb") as f:
        assert f.read() == b"fake-jpeg-bytes"


def test_skips_non_ok_response(tmp_path):
    page = FakePage({"https://media.licdn.com/broken.jpg": FakeResponse(ok=False)})
    result = download_images(page, ["https://media.licdn.com/broken.jpg"], tmp_path)
    assert result == {}


def test_skips_on_exception(tmp_path):
    page = FakePage({"https://media.licdn.com/img.jpg": ConnectionError("network down")})
    result = download_images(page, ["https://media.licdn.com/img.jpg"], tmp_path)
    assert result == {}


def test_one_bad_image_does_not_stop_others(tmp_path):
    page = FakePage(
        {
            "https://media.licdn.com/bad.jpg": ConnectionError("network down"),
            "https://media.licdn.com/good.png": FakeResponse(ok=True, body=b"png-bytes"),
        }
    )
    result = download_images(
        page,
        ["https://media.licdn.com/bad.jpg", "https://media.licdn.com/good.png"],
        tmp_path,
    )
    assert "https://media.licdn.com/bad.jpg" not in result
    assert "https://media.licdn.com/good.png" in result


def test_empty_image_list(tmp_path):
    page = FakePage({})
    assert download_images(page, [], tmp_path) == {}


def test_creates_dest_dir_if_missing(tmp_path):
    dest = tmp_path / "nested" / "images"
    page = FakePage({"https://media.licdn.com/img1.jpg": FakeResponse(ok=True, body=b"x")})
    download_images(page, ["https://media.licdn.com/img1.jpg"], dest)
    assert dest.exists()
