# Artsy Image Scraper

A powerful, user-friendly tool for scraping and organizing high-quality artwork images from Artsy.net and other art websites.

## 🎨 Features

### Core Functionality
- **Smart Artsy Scraping**: Advanced JSON-LD structured data extraction for reliable artist/artwork identification
- **High-Quality Images**: Automatically extracts original high-resolution images from CDN wrappers
- **Universal Compatibility**: Works with Artsy.net and generic art websites
- **Multi-Strategy Extraction**: Falls back gracefully through multiple extraction methods

### User Experience
- **Modern GUI Interface**: Clean PyQt5 interface with progress tracking and logging
- **Automatic Organization**: Images organized by artist name and artwork title
- **Download History**: Track and reuse previously scraped URLs
- **Example URLs**: Built-in Artsy examples for easy testing
- **Package Management**: Built-in dependency checker and updater

### Technical Features
- **Configurable Settings**: JSON-based configuration for site-specific behavior
- **Intelligent Resource Management**: Proper browser session handling with cleanup
- **Error Handling**: Comprehensive error handling with verbose logging options
- **Image Filtering**: Automatically filters out logos, icons, and thumbnails

## 🚀 Installation

### Prerequisites
- Python 3.11 or higher
- Google Chrome browser (for Selenium WebDriver)

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/A1Tman/artsy-imagescraper.git
   cd artsy-imagescraper
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python scraper_gui.py
   ```

## 📖 Usage

### GUI Mode (Recommended)
1. Launch the application: `python scraper_gui.py`
2. Enter or select an Artsy URL (examples provided in dropdown)
3. Choose save location (or use default)
4. Click "Start Scraping"
5. Monitor progress in the logs tab
6. Images are saved to: `{save_location}/{artist_name}/{artwork_title}.jpg`

### Command-Line Mode
```bash
python improved_scraper.py
```
- Interactive prompts for URL and save directory
- Verbose output for debugging
- Supports custom configuration files

### Example URLs
- `https://www.artsy.net/artwork/ellen-von-unwerth-isabelle`
- `https://www.artsy.net/artwork/ed-ruscha-history-kids-236`
- `https://www.artsy.net/artwork/shepard-fairey-shepard-fairey-screenprint-opt-art-green-gradient-street-contemporary-art-obey-giant`

## 🏗️ Project Structure

```
artsy-imagescraper/
├── improved_scraper.py    # Core scraping engine with JSON-LD extraction
├── config.py              # Configuration dataclass with site-specific settings
├── resources.py           # Resource management (WebDriver, HTTP sessions)
├── scraper_gui.py         # PyQt5 GUI application
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## 🔧 Configuration

The scraper uses a configuration system in `config.py` that can be customized:

```python
config = ScraperConfig(
    output_directory="Scraped",           # Base output folder
    browser_headless=True,                # Run browser in background
    render_wait_time=3,                   # Seconds to wait for JS rendering
    min_image_size=10000,                 # Minimum image size (bytes)
    # ... more options
)
```

Site-specific configurations are defined in `site_configs` dict for Artsy.net and can be extended for other sites.

## 🆕 What's New in v2.2

### Major Improvements
- ✅ **JSON-LD Structured Data Extraction**: Primary method for Artsy scraping (most reliable)
- ✅ **Fixed Image URL Extraction**: Properly extracts original high-res images from Artsy's CDN
- ✅ **Multi-Strategy Fallback**: JSON-LD → Preload Links → Meta Tags → IMG tags → URL parsing
- ✅ **Better Error Handling**: Replaced bare `except` clauses with specific exception handling
- ✅ **Enhanced Type Hints**: Complete type annotations for better IDE support
- ✅ **Improved Logging**: Verbose mode shows which extraction strategy succeeded

### Technical Details
- New helper functions for JSON-LD parsing and nested value extraction
- Regex-based CDN URL unwrapping configured per-site
- BeautifulSoup parsing of structured data from `<script type="application/ld+json">` tags

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## 📦 Dependencies

- **selenium** - Browser automation for dynamic content
- **beautifulsoup4** + **lxml** - HTML/XML parsing
- **requests** - HTTP requests
- **webdriver-manager** - Automatic ChromeDriver management
- **PyQt5** - GUI framework
- **appdirs** - Cross-platform config/data directories

## 🐛 Troubleshooting

**Images not downloading from Artsy:**
- Ensure Chrome browser is installed
- Check verbose logs for extraction method used
- Verify URL is an artwork page (`/artwork/` in path)

**GUI won't start:**
- Verify PyQt5 is installed: `pip install PyQt5`
- Check Python version is 3.11+

**ChromeDriver errors:**
- The app auto-installs ChromeDriver via webdriver-manager
- Ensure you have internet connection on first run

## 📄 License

This project is for educational purposes. Please respect website terms of service and copyright laws when scraping content.

## 🙏 Acknowledgments

Built with guidance from Claude Code (Anthropic) - v2.2 improvements based on analysis of actual Artsy HTML structure.