# Changelog

All notable changes to the Artsy Image Scraper project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3] - 2025-12-26

### Fixed My Own Mess

Yeah so turns out adding 70+ constants was overkill. Went back and nuked the stupid ones.

**What got axed:**
- `ARTWORK_SLUG_INDEX = 1` - bro just write `[1]`
- `PERCENTAGE_MULTIPLIER = 100` - it's called a percentage for a reason
- `PIP_INSTALL_CMD = 'install'` - these are literally just pip commands
- Single-use margins like `TITLE_MARGIN_BOTTOM = 8` - not every number needs a name

Removed 36+ pointless constants across the codebase. If it's only used once and the value is obvious, it doesn't need to be a constant.

**What stayed:**
- Colors used 20+ times (`FONT_ARIAL`, `COLOR_DARK_BLUE`)
- Complex regex patterns that look like line noise
- Security stuff (`WINDOWS_FORBIDDEN_DIRS`, `UNIX_FORBIDDEN_DIRS`)
- Config that might actually change

Net result: -24 lines, way more readable. Sometimes less abstraction is better.

---

## [2.2] - 2025-12-22

### 🎉 Major Improvements

#### Added
- **JSON-LD Structured Data Extraction**: Primary extraction method for Artsy.net
  - Parses `<script type="application/ld+json">` tags for reliable artist/artwork identification
  - Extracts high-quality image URLs directly from structured data
  - New functions: `extract_json_ld_data()`, `extract_artsy_info_from_json_ld()`, `get_nested_value()`
- **Multi-Strategy Image Extraction**: Implements 4-tier fallback system
  1. JSON-LD structured data (highest quality)
  2. Preload link tags (`<link rel="preload">`)
  3. Open Graph meta tags (`<meta property="og:image">`)
  4. Traditional img tag parsing (fallback)
- **CDN URL Unwrapping**: New `extract_original_image_url()` function
  - Extracts original high-resolution images from Artsy's CDN wrapper URLs
  - Configurable regex patterns in site config
  - Handles double URL-encoded parameters
- **Enhanced Configuration**: Extended `site_configs` for Artsy.net
  - `use_json_ld`: Enable/disable JSON-LD extraction
  - `json_ld_selectors`: Configurable paths for data extraction
  - `cdn_patterns`: Regex patterns for CDN URL parsing

#### Changed
- **Improved Error Handling**: Replaced all bare `except:` clauses with specific exception types
  - Better error messages for debugging
  - Proper exception logging in verbose mode
- **Enhanced Type Hints**: Added comprehensive type annotations
  - `extract_artsy_info() -> Tuple[str, str]`
  - `extract_generic_info() -> Tuple[str, str]`
  - `extract_images_from_page() -> Set[str]`
  - Added `Tuple`, `Set`, `List` imports
- **Better Logging**: Verbose mode now shows which extraction strategy succeeded
  - Clear indication when JSON-LD extraction works
  - Fallback notifications for debugging
  - URL-based fallback preparation logged

#### Fixed
- **Artsy Image Extraction**: Complete rewrite of image URL extraction logic
  - OLD: Searched all `<div>` tags with brittle string operations
  - NEW: Targeted extraction from structured data and preload tags
- **High-Resolution Images**: Now correctly extracts original image URLs
  - Properly decodes Artsy's CDN parameters
  - No longer downloads scaled-down versions
- **Artist/Artwork Detection**: More reliable metadata extraction
  - JSON-LD provides canonical artist/artwork names
  - Better fallback chain: JSON-LD → CSS selectors → URL parsing

### 📝 Documentation
- Updated README.md with comprehensive feature descriptions
- Added installation instructions and prerequisites
- Documented GUI and CLI usage modes
- Added troubleshooting section
- Created this CHANGELOG.md

### 🔧 Technical Details
- Added `json` module import for JSON-LD parsing
- BeautifulSoup parser preference: lxml → html.parser fallback
- Regex-based URL parameter extraction with configurable patterns
- Improved code organization with dedicated helper functions

---

## [2.1] - 2024-XX-XX

### Changed
- Code cleanup and organization improvements
- Updated requirements.txt with all dependencies
- Cleaned up .gitignore
- Removed unnecessary archived files

### Added
- Standards and best practices improvements

---

## [2.0 and Earlier]

Previous versions focused on:
- Basic Artsy scraping functionality
- PyQt5 GUI implementation
- Resource management system
- Configuration framework
- Package update checker

---

## Versioning Strategy

- **Major version (X.0.0)**: Breaking changes, major rewrites
- **Minor version (2.X.0)**: New features, significant improvements
- **Patch version (2.2.X)**: Bug fixes, minor tweaks

## Contributing

When making changes:
1. Update this CHANGELOG.md under "Unreleased" section
2. Follow [Keep a Changelog](https://keepachangelog.com/) format
3. Use categories: Added, Changed, Deprecated, Removed, Fixed, Security
4. Include technical details for significant changes
