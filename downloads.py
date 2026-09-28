"""Bounded downloads with file validation and measured resolution selection."""
import hashlib
import os
from pathlib import Path
import tempfile
import time
import warnings
import shutil
from urllib.parse import urljoin

from PIL import Image, UnidentifiedImageError
import requests
from urllib3.exceptions import HTTPError as TransportError

from image_selection import ImageGroup
from security import redact_url, validate_url

FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif", "BMP": ".bmp", "TIFF": ".tif", "AVIF": ".avif"}


class OperationCancelledError(Exception):
    """The user cancelled the active scrape."""


def check_cancel(event):
    if event is not None and event.is_set():
        raise OperationCancelledError("Scraping cancelled.")


def validate_image(path, max_pixels):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            width, height = image.size
            if width * height > max_pixels or width < 1 or height < 1:
                raise ValueError("Image dimensions exceed the configured limit")
            extension = FORMATS.get(image.format)
            if not extension:
                raise ValueError("Unsupported image format")
            image.verify()
        # verify() alone does not detect every truncated JPEG/WEBP. Decode the
        # bounded first frame before accepting it, without recompressing output.
        with Image.open(path) as image:
            image.load()
        return width, height, extension


def response_chunks(response):
    raw = getattr(response, "raw", None)
    if raw is not None and hasattr(raw, "read1"):
        while True:
            chunk = raw.read1(65536, decode_content=False)
            if not chunk:
                return
            yield chunk
    else:
        yield from response.iter_content(chunk_size=8192)


def fetch_candidate(url, directory, session, config, budget, cancel_event):
    started = time.monotonic()
    current = url
    response = None
    temp_path = None
    try:
        for _ in range(6):
            check_cancel(cancel_event)
            validate_url(current)
            remaining = config.download_deadline - (time.monotonic() - started)
            if remaining <= 0:
                raise ValueError("Download deadline exceeded")
            response = session.get(current, timeout=min(config.download_timeout, remaining),
                                   stream=True, allow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                response.close()  # Do not drain an unbounded redirect body.
                response = None
                if not location:
                    raise ValueError("Redirect has no destination")
                current = urljoin(current, location)
                continue
            break
        else:
            raise ValueError("Too many redirects")
        response.raise_for_status()
        if response.headers.get("content-encoding", "identity").lower() not in ("", "identity"):
            raise ValueError("Compressed HTTP response rejected; requested original image bytes")
        # Accept octet-stream/missing MIME only if the actual file is a supported
        # image. HTML/error pages cannot become images merely by spoofing a header.
        mime = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if mime and not (mime.startswith("image/") or mime == "application/octet-stream"):
            raise ValueError("Response is not an image")
        length = response.headers.get("content-length")
        if length and length.isdigit() and int(length) > min(config.max_download_size, budget[0]):
            raise ValueError("Download exceeds byte limit")
        handle, name = tempfile.mkstemp(prefix=".image-", suffix=".part", dir=directory)
        temp_path = Path(name)
        received = 0
        digest = hashlib.sha256()
        with os.fdopen(handle, "wb") as output:
            for chunk in response_chunks(response):
                check_cancel(cancel_event)
                if time.monotonic() - started > config.download_deadline:
                    raise ValueError("Download deadline exceeded")
                received += len(chunk)
                budget[0] -= len(chunk)
                if received > config.max_download_size or budget[0] < 0:
                    raise ValueError("Download exceeds byte limit")
                output.write(chunk)
                digest.update(chunk)
        check_cancel(cancel_event)
        if received < config.min_image_size:
            raise ValueError("Image is below the configured minimum file size")
        width, height, extension = validate_image(temp_path, config.max_image_pixels)
        return temp_path, width, height, extension, digest.hexdigest()
    except BaseException:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        if response is not None:
            response.close()


def download_groups(groups, artist_dir, artwork_name, config, manager, verbose=False,
                    progress_callback=None, cancel_event=None):
    if isinstance(groups, (set, frozenset)):
        groups = [ImageGroup([url]) for url in sorted(groups)]
    count = 0
    budget = [config.max_total_download_size]
    seen_hashes = set()
    directory = Path(artist_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    def emit(message):
        if verbose:
            print(message)
        if progress_callback:
            progress_callback({"type": "message", "value": message})
    with manager.get_session() as session:
        for index, group in enumerate(groups[:config.max_images]):
            check_cancel(cancel_event)
            best = None
            try:
                for url in group.urls[:10]:
                    check_cancel(cancel_event)
                    if budget[0] <= 0:
                        emit("Total download byte limit reached.")
                        break
                    candidate = None
                    try:
                        emit(f"Checking image: {redact_url(url)} ({group.reason})")
                        candidate = fetch_candidate(url, directory, session, config, budget, cancel_event)
                        _, width, height, _, _ = candidate
                        emit(f"Verified candidate: {width} x {height} pixels")
                        if best is None or width * height > best[1] * best[2]:
                            if best:
                                best[0].unlink(missing_ok=True)
                            best, candidate = candidate, None
                    except OperationCancelledError:
                        raise
                    except (requests.RequestException, TransportError, OSError, ValueError, UnidentifiedImageError,
                            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                        check_cancel(cancel_event)
                        # Exception text from HTTP clients may expose signed query
                        # parameters. Report type and a redacted URL instead.
                        emit(f"Candidate unavailable or invalid ({type(exc).__name__}): {redact_url(url)}")
                    finally:
                        if candidate:
                            candidate[0].unlink(missing_ok=True)
                check_cancel(cancel_event)
                if best and best[4] not in seen_hashes:
                    stem = artwork_name or "artwork"
                    suffix = 0
                    while True:
                        destination = directory / f"{stem}{'_' + str(suffix) if suffix else ''}{best[3]}"
                        if destination.parent.resolve() != directory:
                            raise ValueError("Output path escaped the selected directory")
                        try:
                            # Exclusive creation also works on FAT/exFAT and network
                            # shares. Copy the source bytes without recompression.
                            with destination.open("xb") as output:
                                try:
                                    with best[0].open("rb") as source:
                                        shutil.copyfileobj(source, output, 65536)
                                except BaseException:
                                    output.close()
                                    destination.unlink(missing_ok=True)
                                    raise
                            break
                        except FileExistsError:
                            suffix += 1
                    count += 1
                    seen_hashes.add(best[4])
                    emit(f"Saved {destination.name}: {best[1]} x {best[2]} pixels (best verified available version)")
                elif best:
                    emit("Skipped a duplicate image file.")
                else:
                    emit("No valid image file was available for this selection.")
                if progress_callback:
                    progress_callback({"type": "percentage", "value": int((index + 1) / len(groups) * 100)})
            finally:
                if best:
                    best[0].unlink(missing_ok=True)
    return count
