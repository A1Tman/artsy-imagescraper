# Artsy Image Scraper

A tool for downloading high-quality artwork images from Artsy.net and other art websites. Automatically organizes downloads by artist and artwork name.

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
python scraper_gui.py
```

## Usage

### GUI Mode
1. Run `python scraper_gui.py`
2. Enter an Artsy URL or select one from the examples dropdown
3. Choose where to save the images
4. Click "Start Scraping"
5. Check the Logs tab to monitor progress

Images are saved to: `{save_location}/{artist_name}/{artwork_title}.jpg`

### Command-Line Mode
Run `python improved_scraper.py` for an interactive command-line interface with verbose output.

### Example URLs
Try these Artsy artwork pages:
- https://www.artsy.net/artwork/ellen-von-unwerth-isabelle
- https://www.artsy.net/artwork/ed-ruscha-history-kids-236
- https://www.artsy.net/artwork/shepard-fairey-shepard-fairey-screenprint-opt-art-green-gradient-street-contemporary-art-obey-giant

## Project Structure

```
artsy-imagescraper/
├── improved_scraper.py    # Core scraping engine
├── config.py              # Configuration settings
├── resources.py           # Resource management (WebDriver, HTTP sessions)
├── scraper_gui.py         # PyQt5 GUI
├── requirements.txt       # Dependencies
└── README.md              # This file
```

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