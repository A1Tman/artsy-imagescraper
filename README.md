# Image Scraper

A desktop and command-line tool for downloading high-quality images from Artsy.net and other websites. Downloads are organized by artist/site and artwork/page title.

## Features

- Scrapes images from Artsy.net using JSON-LD structured data for reliable extraction
- Selects the main artwork/page image and compares available variants using their actual pixel dimensions
- Saves one best verified file per selected image, with no upscaling or recompression
- Validates image files and filters unrelated previews, navigation images and duplicates
- PyQt5 GUI with progress tracking and download history
- Command-line interface for scripting and automation
- Configurable settings for different websites
- Automatic filtering of logos, icons, and thumbnails

## Installation

### Prerequisites
- Python 3.11 or higher
- Google Chrome browser (for Selenium WebDriver)

### Setup

Clone the repository:
```bash
git clone https://github.com/A1Tman/artsy-imagescraper.git
cd artsy-imagescraper
```

Install dependencies:
```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the GUI on Windows:
```powershell
.\.venv\Scripts\python.exe gui.py
```

`python scraper_gui.py` also launches the maintained GUI. Desktop/CLI entry points
prefer the local `.venv` when present. In VS Code, select `.venv\Scripts\python.exe`
as the Python interpreter. The global Python installation is not updated.
On macOS/Linux use `.venv/bin/python` in the corresponding commands.

## Usage

### GUI Mode
1. Run `python gui.py`
2. Enter the page URL you want to scrape
3. Choose where to save the images
4. Use `Check Environment` to compare installed packages against `requirements.txt` when needed
5. Use `Sync Dependencies` to install the exact pinned dependency set from the lock file
6. Keep `Main image only (best available resolution)` selected for a single artwork. Use `Images in the main content` for a gallery or article with multiple images.
7. Click `Start Scraping`.
8. Check the Logs tab for candidate dimensions and the final saved dimensions.

Images are saved to `{save_location}/{artist_name}/{artwork_title}.{actual_format}`.
The downloaded bytes are preserved. A filename such as `large.jpg` does not prove
that it is the highest-resolution version: the app compares successfully decoded
candidates and keeps the one with the greatest pixel count. Unavailable originals
fall back to valid advertised versions. The site may not expose the original file;
the app does not upscale images, bypass access controls or reconstruct zoom tiles.

Artsy selection uses matching artwork metadata and the artwork image container.
Generic pages use structured metadata and main/article content, including lazy
images, `picture`, `srcset` and links to full-size files. Arbitrary preloads and CSS
backgrounds are excluded. Unusual layouts may need a site-specific adapter.

Only public HTTP(S) destinations on ports 80/443 are supported. Both Chrome and
image downloads use a local proxy that rejects private/special-use DNS addresses
and connects to the checked IP, including after redirects. It does not intercept
TLS. Corporate proxies and private intranet scraping are not supported by this
configuration. Browser challenges/sign-in pages may prevent scraping.

Downloads have byte, pixel and time limits. The Cancel button interrupts the
network relay and removes unfinished temporary files. History and logs omit URL
credentials, query strings and fragments, and log messages are rendered as plain
text. Limits and `image_selection` can also be configured in `ScraperConfig`.

### Command-Line Mode
Run `python scraper.py` for an interactive command-line interface with verbose output.

## Project Structure

```
artsy-imagescraper/
├── scraper.py             # Core scraping engine
├── gui.py                 # PyQt5 desktop app
├── config.py              # Configuration settings
├── resources.py           # WebDriver and HTTP session lifecycle
├── image_selection.py     # Page identity and resolution candidates
├── downloads.py           # Bounded downloads and image validation
├── network.py             # Public-destination proxy shared by browser and downloader
├── security.py            # URL validation and redaction
├── scraper_gui.py         # Compatibility GUI launcher
├── improved_scraper.py    # Compatibility scraper module
├── requirements.in        # Direct runtime dependencies
├── requirements.txt       # Pinned runtime lock file
└── README.md              # This file
```

## Dependency Management

Dependencies are managed with `pip-tools`.

- Install the pinned runtime environment: `python -m pip install -r requirements.txt`
- Refresh the lock file after changing direct dependencies: `powershell -ExecutionPolicy Bypass -File scripts/update-deps.ps1`
- Reinstall the current pinned environment: `powershell -ExecutionPolicy Bypass -File scripts/sync-deps.ps1`
- The GUI exposes the same workflow with `Check Environment` and `Sync Dependencies` buttons

`requirements.in` is the hand-edited list of direct dependencies. `requirements.txt` is generated from it and should not be edited manually.

## Configuration

Settings are defined in `config.py` and can be customized:

```python
config = ScraperConfig(
    output_directory="Scraped",
    browser_headless=True,
    render_wait_time=3,
    min_image_size=10000,
    # ... more options
)
```

Site-specific configs for Artsy.net are in the `site_configs` dict and can be extended for other sites.

## What's New in v2.4

Bug fix and security hardening release:

- Fixed verbose mode being silently broken during image extraction (argument order bug)
- Fixed cancel operation showing an error dialog instead of a clean cancellation
- Fixed domain-matching false-positive that could apply the wrong site config
- Fixed h4 headings never being searched (off-by-one in range)
- Fixed start button re-enabling after operations even with an invalid URL in the input
- Windows system-directory protection now uses `%SystemRoot%` / `%ProgramFiles%` env vars instead of hardcoded `C:\` paths
- Config loader now validates field types before applying values from JSON

See [CHANGELOG.md](CHANGELOG.md) for full details.

## What's New in v2.2

Major improvements to reliability and code quality:

- Uses JSON-LD structured data extraction for more reliable artist/artwork identification
- Better high-res image URL extraction from Artsy's CDN wrappers
- Multi-tier fallback system: JSON-LD → Preload Links → Meta Tags → IMG tags → URL parsing
- Fixed security issues: path traversal protection, command injection prevention
- Fixed bare except clauses with proper error handling
- Enhanced filename sanitization for cross-platform compatibility
- Added comprehensive type hints and docstrings
- Verbose logging shows which extraction method worked

Technical changes:
- Added JSON-LD parsing functions to extract data from `<script type="application/ld+json">` tags
- Regex-based CDN URL unwrapping to get original image URLs from Artsy's wrapper URLs
- Better error messages when things go wrong

See [CHANGELOG.md](CHANGELOG.md) for full version history.

## Dependencies

- selenium - Browser automation
- beautifulsoup4 + lxml - HTML parsing
- requests - HTTP downloads
- webdriver-manager - ChromeDriver installer
- PyQt5 - GUI
- appdirs - Config directories
- Pillow - Image decoding, validation and actual pixel dimensions

## Troubleshooting

**Images not downloading:**
- Make sure Chrome is installed
- Check the verbose logs to see what extraction method was used
- Verify the URL is an artwork page (has `/artwork/` in it)

**GUI won't start:**
- Install PyQt5: `pip install PyQt5`
- Check Python version (needs 3.11+)

**ChromeDriver errors:**
- The app downloads ChromeDriver automatically on first run
- Make sure you have internet connection

## License

Educational purposes only. Respect website terms of service and copyright laws.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt --no-deps --disable-pip
```

Install `pip-audit` in the project environment if needed. Tests use local fixtures
and controlled loopback servers, not live websites. GitHub Actions runs the suite
and audits the pinned runtime dependencies. Live validation on 24 September 2026
selected one 2425 x 3113 JPEG for Artsy's Edvard Munch *Madonna* page, instead of its
499 x 640 `large.jpg` variant. That result is specific to the publicly available
files tested, not a guarantee about every site or artwork.
