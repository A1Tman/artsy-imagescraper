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

### Major Improvements

Rewrote the entire image extraction logic for Artsy.net. Old code was fragile and downloaded low-res versions.

**New extraction system:**
- JSON-LD structured data extraction (parses `<script type="application/ld+json">` tags)
- 4-tier fallback: JSON-LD → preload links → og:image meta tags → img tags
- CDN URL unwrapping to get original high-res images instead of scaled versions
- Added `extract_json_ld_data()`, `extract_artsy_info_from_json_ld()`, `get_nested_value()`

**Config improvements:**
- Extended `site_configs` for Artsy with `use_json_ld`, `json_ld_selectors`, `cdn_patterns`
- Configurable regex patterns for CDN URL parsing
- Handles double URL-encoded parameters

**Code quality:**
- Replaced all bare `except:` with specific exception types
- Added type hints: `-> Tuple[str, str]`, `-> Set[str]`, etc.
- Verbose mode shows which extraction strategy worked
- Better error messages for debugging

**Fixes:**
- Artsy extraction completely rewritten (old: searched divs with string ops, new: structured data)
- Actually downloads high-res images now (properly decodes CDN params)
- More reliable artist/artwork detection with fallback chain

**Docs:**
- Updated README with installation, usage, troubleshooting
- Created this CHANGELOG

**Technical:**
- BeautifulSoup parser: lxml with html.parser fallback
- Regex-based URL parameter extraction
- Better code organization

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
