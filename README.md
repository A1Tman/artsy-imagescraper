# Image Scraper

A desktop and command-line tool for downloading high-quality images from Artsy.net and other websites. Downloads are organized by artist/site and artwork/page title.

## Features

- Scrapes images from Artsy.net using JSON-LD structured data for reliable extraction
- Downloads original high-resolution images (not scaled-down versions)
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
pip install -r requirements.txt
```

Run the GUI:
```bash
python gui.py
```

## Usage

### GUI Mode
1. Run `python gui.py`
2. Enter an Artsy URL or select one from the examples dropdown
3. Choose where to save the images
4. Use `Check Environment` to compare installed packages against `requirements.txt` when needed
5. Use `Sync Dependencies` to install the exact pinned dependency set from the lock file
6. Click `Start Scraping`
7. Check the Logs tab to monitor progress

Images are saved to: `{save_location}/{artist_name}/{artwork_title}.jpg`

### Command-Line Mode
Run `python scraper.py` for an interactive command-line interface with verbose output.

### Example URLs
Try these pages:
- https://www.artsy.net/artwork/ellen-von-unwerth-isabelle
- https://www.artsy.net/artwork/ed-ruscha-history-kids-236
- https://www.artsy.net/artwork/shepard-fairey-shepard-fairey-screenprint-opt-art-green-gradient-street-contemporary-art-obey-giant
- https://arstechnica.com/tech-policy/2026/03/trumps-doj-is-not-falling-for-sam-bankman-frieds-maga-makeover-on-x/

## Project Structure

```
artsy-imagescraper/
├── scraper.py             # Core scraping engine
├── gui.py                 # PyQt5 desktop app
├── config.py              # Configuration settings
├── resources.py           # Resource management (WebDriver, HTTP sessions)
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
