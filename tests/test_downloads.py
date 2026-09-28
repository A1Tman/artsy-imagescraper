from contextlib import contextmanager
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from PIL import Image
import requests

from config import ScraperConfig
from downloads import download_groups, OperationCancelledError
from image_selection import ImageGroup


def png(size, noise=False):
    image = Image.effect_noise(size, 100) if noise else Image.new("RGB", size, "red")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


class Response:
    def __init__(self, data=b"", status=200, headers=None, chunks=None):
        self.data = data
        self.status_code = status
        self.headers = {"content-type": "image/png", **(headers or {})}
        self.chunks = chunks
        self.closed = False
    def iter_content(self, chunk_size=8192):
        yield from (self.chunks() if self.chunks else [self.data])
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("dummy")
    def close(self): self.closed = True


class Manager:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
    @contextmanager
    def get_session(self): yield self
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses[url]


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = ScraperConfig(min_image_size=1)

    def download(self, responses, groups=None, **kwargs):
        self.manager = Manager(responses)
        return download_groups(groups or [ImageGroup(list(responses))], self.directory, "artwork", self.config, self.manager, **kwargs)

    def test_pixel_dimensions_win_over_file_size(self):
        small, large = png((100, 100), noise=True), png((600, 400))
        self.assertGreater(len(small), len(large))
        count = self.download({"https://example.com/small.png": Response(small), "https://example.com/large.png": Response(large)})
        self.assertEqual(count, 1)
        self.assertEqual((self.directory / "artwork.png").read_bytes(), large)
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_unavailable_original_falls_back_to_valid_advertised_file(self):
        expected = png((500, 300))
        self.assertEqual(self.download({"https://example.com/original.png": Response(status=404), "https://example.com/large.png": Response(expected)}), 1)
        self.assertEqual((self.directory / "artwork.png").read_bytes(), expected)

    def test_spoofed_image_header_is_not_saved(self):
        self.assertEqual(self.download({"https://example.com/fake.jpg": Response(b"<html>Error</html>")}), 0)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_actual_format_sets_extension_without_reencoding(self):
        data = png((20, 30))
        self.download({"https://example.com/photo.jpg": Response(data, headers={"content-type": "application/octet-stream"})})
        self.assertEqual((self.directory / "artwork.png").read_bytes(), data)

    def test_corrupt_candidate_preserves_valid_fallback(self):
        data = png((20, 30))
        self.assertEqual(self.download({"https://example.com/good.png": Response(data), "https://example.com/corrupt.png": Response(data[:40])}), 1)
        self.assertEqual((self.directory / "artwork.png").read_bytes(), data)

    def test_oversized_body_and_total_budget_remove_partial_files(self):
        self.config.max_download_size = 5
        self.config.max_total_download_size = 5
        self.assertEqual(self.download({"https://example.com/image": Response(b"123456")}), 0)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_pixel_limit_rejects_before_decoding(self):
        self.config.max_image_pixels = 100
        self.assertEqual(self.download({"https://example.com/image": Response(png((20, 20)))}), 0)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_cancel_midstream_removes_partial_file(self):
        event = threading.Event()
        def chunks():
            yield b"abc"
            event.set()
            yield b"def"
        with self.assertRaises(OperationCancelledError):
            self.download({"https://example.com/image": Response(chunks=chunks)}, cancel_event=event)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_slow_stream_deadline_removes_partial_file(self):
        self.config.download_deadline = 0.01
        def chunks():
            yield b"abc"
            time.sleep(0.02)
            yield b"def"
        self.assertEqual(self.download({"https://example.com/image": Response(chunks=chunks)}), 0)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_redirect_body_is_not_consumed(self):
        def chunks():
            raise AssertionError("Redirect body must not be consumed")
            yield
        redirect = Response(status=302, headers={"location": "/real.png"}, chunks=chunks)
        responses = {"https://example.com/redirect": redirect, "https://example.com/real.png": Response(png((10, 10)))}
        self.assertEqual(self.download(responses, [ImageGroup(["https://example.com/redirect"])]), 1)
        self.assertTrue(redirect.closed)
        self.assertTrue(all(not options["allow_redirects"] for _, options in self.manager.calls))

    def test_identical_files_in_two_groups_are_saved_once(self):
        data = png((20, 20))
        a, b = "https://example.com/a", "https://example.com/b"
        self.assertEqual(self.download({a: Response(data), b: Response(data)}, [ImageGroup([a]), ImageGroup([b])]), 1)

    def test_existing_file_is_not_overwritten(self):
        (self.directory / "artwork.png").write_bytes(b"preserve")
        self.download({"https://example.com/image": Response(png((20, 20)))})
        self.assertEqual((self.directory / "artwork.png").read_bytes(), b"preserve")
        self.assertTrue((self.directory / "artwork_1.png").exists())


if __name__ == "__main__":
    unittest.main()
