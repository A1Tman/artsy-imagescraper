import os
import sys
import re
import time
import json
import copy
from dataclasses import dataclass
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup, FeatureNotFound
from urllib.parse import unquote, urljoin, urlparse
from typing import Optional, Union, Any, Callable, Dict, Tuple, Set, List

# Ensure the module directory is in sys.path for local module resolution.
# This can help linters like Pylance find 'config.py' and 'resources.py'
# when the project is opened in an IDE.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Import the configuration and resource management classes
from config import ScraperConfig, domain_matches
from resources import download_manager, ResourceManager

# ============================================================================
# Constants
# ============================================================================

# Filename handling
FILENAME_MAX_LENGTH = 100
INVALID_FILENAME_CHARS_PATTERN = r'[\\/*?:"<>|\x00]'
WHITESPACE_PATTERN = r'[\s-]+'

# HTML parsing
PRIMARY_HTML_PARSER = "lxml"
FALLBACK_HTML_PARSER = "html.parser"

# JSON-LD extraction
JSON_LD_SCRIPT_TYPE = 'application/ld+json'
JSON_LD_TYPE_KEY = '@type'
JSON_LD_GRAPH_KEY = '@graph'
JSON_LD_ARTWORK_TYPE = 'VisualArtwork'

# Default values for extraction fallbacks
DEFAULT_ARTIST_NAME = "unknown"
DEFAULT_ARTWORK_NAME = "artwork"

# Artsy-specific constants
ARTSY_DOMAIN = "artsy.net"
ARTSY_ARTWORK_PATH = '/artwork/'

# Site type identifiers
SITE_TYPE_ARTSY = "artsy"
SITE_TYPE_GENERIC = "generic"

# Generic page extraction
MIN_HEADING_LEVEL = 1
MAX_HEADING_LEVEL = 4
HEADING_MAX_LENGTH = 100
GENERIC_HEADING_SELECTORS = ('article h1', 'main h1', 'h1', 'article h2', 'main h2', 'h2')
GENERIC_TITLE_META_ATTRS = (
    ('property', 'og:title'),
    ('name', 'twitter:title'),
    ('name', 'title'),
)
GENERIC_SITE_NAME_META_ATTRS = (
    ('property', 'og:site_name'),
    ('name', 'application-name'),
)
GENERIC_IMAGE_META_ATTRS = (
    ('property', 'og:image'),
    ('name', 'twitter:image'),
    ('property', 'twitter:image'),
)
GENERIC_TITLE_SEPARATORS = (' | ', ' - ', ' — ', ' – ')
GENERIC_BOILERPLATE_TEXT = (
    'we and our partners process data',
    'cookie',
    'privacy',
    'consent',
    'advertisement',
)
TOKEN_SPLIT_PATTERN = r'[^a-z0-9]+'
GENERIC_IMAGE_SIZE_PATTERN = re.compile(r'^(?P<base>.+?)-(?P<width>\d+)x(?P<height>\d+)(?:-\d+)?$')

# Image content types mapping
IMAGE_CONTENT_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp'
}
DEFAULT_IMAGE_EXTENSION = '.jpg'

# Configuration
DEFAULT_CONFIG_FILENAME = "scraper_config.json"
EXIT_COMMAND = 'exit'
DISPLAY_ARROW = "->"

# Artsy image candidate scoring
ARTSY_VARIANT_PRIORITY = {
    'main': 100,
    'large': 80,
    'normalized': 60,
    'medium': 40,
    'small': 0,
}


@dataclass(frozen=True)
class ImageCandidate:
    """Represents an extracted image URL with its source and score."""
    url: str
    source: str
    score: int = 0


class OperationCancelledError(Exception):
    """Raised when a scraping operation is cancelled by the user."""
    pass


def clean_filename(name: str) -> str:
    """Convert a string to a valid filename.

    Removes invalid characters and limits length to 100 characters.
    Handles Windows NTFS alternate data streams and null bytes.

    Args:
        name: Original filename string

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove filesystem-invalid characters including null bytes
    name = re.sub(INVALID_FILENAME_CHARS_PATTERN, "", name)
    # Replace whitespace and hyphens with underscores
    name = re.sub(WHITESPACE_PATTERN, "_", name)
    # Remove trailing dots and spaces (Windows compatibility)
    name = name.strip('. ')
    # Limit length for compatibility
    return name[:FILENAME_MAX_LENGTH]


def parse_html_document(html: str) -> BeautifulSoup:
    """Parse HTML using the preferred parser with a safe fallback."""
    try:
        return BeautifulSoup(html, PRIMARY_HTML_PARSER)
    except (ImportError, FeatureNotFound):
        return BeautifulSoup(html, FALLBACK_HTML_PARSER)


def extract_meta_content(soup: BeautifulSoup, attr_name: str, attr_value: str) -> Optional[str]:
    """Return the content attribute for the first matching meta tag."""
    meta_tag = soup.find('meta', attrs={attr_name: attr_value})
    content = meta_tag.get('content') if meta_tag else None
    return content.strip() if isinstance(content, str) and content.strip() else None


def extract_domain_display_name(domain: str) -> str:
    """Convert a domain name into a readable site label."""
    domain_parts = [part for part in domain.split('.') if part and part != 'www']
    if len(domain_parts) >= 2:
        site_name = domain_parts[-2]
    elif domain_parts:
        site_name = domain_parts[0]
    else:
        site_name = DEFAULT_ARTIST_NAME
    return site_name.replace('-', ' ').title()


def normalize_title_candidate(title: str, site_name: str) -> str:
    """Trim whitespace and remove common trailing site-name suffixes."""
    normalized = title.strip()
    site_name_lower = site_name.lower().strip()

    for separator in GENERIC_TITLE_SEPARATORS:
        if separator in normalized:
            left, right = normalized.rsplit(separator, 1)
            if site_name_lower and right.strip().lower() == site_name_lower:
                normalized = left.strip()
                break

    return normalized


def is_boilerplate_text(text: str) -> bool:
    """Identify text that is unlikely to be useful as a title or filename."""
    normalized = text.strip().lower()
    return any(phrase in normalized for phrase in GENERIC_BOILERPLATE_TEXT)


def extract_generic_site_and_title(soup: BeautifulSoup, url: str, page_title: str) -> Tuple[str, str]:
    """Extract a readable site name and page title for generic pages."""
    parsed_url = urlparse(url)
    site_name = extract_domain_display_name(parsed_url.netloc)

    for attr_name, attr_value in GENERIC_SITE_NAME_META_ATTRS:
        meta_site_name = extract_meta_content(soup, attr_name, attr_value)
        if meta_site_name and not is_boilerplate_text(meta_site_name):
            site_name = meta_site_name.strip()
            break

    title_candidates: List[str] = []
    for attr_name, attr_value in GENERIC_TITLE_META_ATTRS:
        meta_title = extract_meta_content(soup, attr_name, attr_value)
        if meta_title:
            title_candidates.append(meta_title)

    if page_title:
        title_candidates.append(page_title)

    title_tag = soup.find('title')
    if title_tag and title_tag.get_text(strip=True):
        title_candidates.append(title_tag.get_text(strip=True))

    for selector in GENERIC_HEADING_SELECTORS:
        for element in soup.select(selector):
            text = element.get_text(" ", strip=True)
            if text:
                title_candidates.append(text)

    for heading_level in range(MIN_HEADING_LEVEL, MAX_HEADING_LEVEL + 1):
        for element in soup.find_all(f'h{heading_level}'):
            text = element.get_text(" ", strip=True)
            if text:
                title_candidates.append(text)

    for candidate in title_candidates:
        normalized = normalize_title_candidate(candidate, site_name)
        if normalized and len(normalized) < HEADING_MAX_LENGTH * 2 and not is_boilerplate_text(normalized):
            return site_name, normalized

    path_parts = [part for part in parsed_url.path.strip('/').split('/') if part]
    if path_parts:
        fallback_title = path_parts[-1].replace('-', ' ').title()
    else:
        fallback_title = DEFAULT_ARTWORK_NAME

    return site_name, fallback_title


def extract_json_ld_data(soup: BeautifulSoup, verbose: bool = False) -> List[Dict[str, Any]]:
    """Extract JSON-LD structured data from page.

    Returns a list of parsed JSON-LD objects found in script tags.
    """
    json_ld_data = []
    script_tags = soup.find_all('script', type=JSON_LD_SCRIPT_TYPE)

    for script in script_tags:
        try:
            data = json.loads(script.string)
            json_ld_data.append(data)
            if verbose:
                print(f"Found JSON-LD data with @type: {data.get(JSON_LD_TYPE_KEY, 'unknown')}")
        except (json.JSONDecodeError, AttributeError) as e:
            if verbose:
                print(f"Error parsing JSON-LD: {e}")
            continue

    return json_ld_data


def get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Get a nested value from a dictionary using dot notation path.

    Example: get_nested_value(data, "creator.name") -> data["creator"]["name"]
    """
    keys = path.split('.')
    current = data

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


def extract_artsy_info_from_json_ld(json_ld_data: List[Dict[str, Any]], config: ScraperConfig, verbose: bool = False) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract artist, artwork, and image URL from Artsy JSON-LD data.

    Returns: (artist_name, artwork_title, image_url)
    """
    site_config = config.get_site_config(ARTSY_DOMAIN)
    json_ld_selectors = site_config.get("json_ld_selectors", {})

    artist_path = json_ld_selectors.get("artist_path", "creator.name")
    artwork_path = json_ld_selectors.get("artwork_path", "name")
    image_path = json_ld_selectors.get("image_path", "image.url")

    artist_name = None
    artwork_title = None
    image_url = None

    # Look through all JSON-LD objects for VisualArtwork type
    for data in json_ld_data:
        # Handle @graph structure
        if JSON_LD_GRAPH_KEY in data:
            for item in data[JSON_LD_GRAPH_KEY]:
                if item.get(JSON_LD_TYPE_KEY) == JSON_LD_ARTWORK_TYPE:
                    artist_name = get_nested_value(item, artist_path)
                    artwork_title = get_nested_value(item, artwork_path)
                    image_url = get_nested_value(item, image_path)
                    if verbose:
                        print(f"JSON-LD extraction: Artist='{artist_name}', Artwork='{artwork_title}'")
                    if artist_name and artwork_title:
                        return artist_name, artwork_title, image_url

        # Handle direct VisualArtwork object
        elif data.get(JSON_LD_TYPE_KEY) == JSON_LD_ARTWORK_TYPE:
            artist_name = get_nested_value(data, artist_path)
            artwork_title = get_nested_value(data, artwork_path)
            image_url = get_nested_value(data, image_path)
            if verbose:
                print(f"JSON-LD extraction: Artist='{artist_name}', Artwork='{artwork_title}'")
            if artist_name and artwork_title:
                return artist_name, artwork_title, image_url

    return artist_name, artwork_title, image_url


def extract_artsy_info(url: str, driver: webdriver.Chrome, config: ScraperConfig, verbose: bool = False) -> Tuple[str, str]:
    """Extract artist name and artwork title from an Artsy page.

    Uses multiple extraction strategies in order of reliability:
    1. JSON-LD structured data (most reliable)
    2. CSS selectors (fallback)
    3. URL slug parsing (last resort)

    Returns: (artist_name, artwork_title)
    """
    site_specific_config = config.get_site_config(urlparse(url).netloc)
    use_json_ld = site_specific_config.get("use_json_ld", True)

    # Prepare URL-based fallback first
    url_path = urlparse(url).path
    fallback_artist, fallback_artwork = DEFAULT_ARTIST_NAME, DEFAULT_ARTWORK_NAME
    if ARTSY_ARTWORK_PATH in url_path:
        slug = url_path.split(ARTSY_ARTWORK_PATH)[1].strip('/')
        slug_parts = slug.split('-')
        fallback_artist = ' '.join(slug_parts[:2]).title()
        fallback_artwork = ' '.join(slug_parts[2:]).title() if len(slug_parts) > 2 else slug.title()
        if verbose:
            print(f"URL-based fallback prepared: Artist='{fallback_artist}', Artwork='{fallback_artwork}'")

    try:
        # Strategy 1: Try JSON-LD extraction (most reliable for Artsy)
        if use_json_ld:
            html = driver.page_source
            soup = parse_html_document(html)
            json_ld_data = extract_json_ld_data(soup, verbose)

            if json_ld_data:
                artist_name, artwork_title, _ = extract_artsy_info_from_json_ld(json_ld_data, config, verbose)
                if artist_name and artwork_title:
                    if verbose:
                        print(f"JSON-LD extraction successful: Artist='{artist_name}', Artwork='{artwork_title}'")
                    return artist_name, artwork_title
                elif verbose:
                    print("JSON-LD found but missing artist/artwork data, trying selectors...")

        # Strategy 2: Try CSS selectors (fallback)
        artist_selector = site_specific_config.get("artist_selector", "h2[data-test='artist-name']")
        artwork_selector = site_specific_config.get("artwork_selector", "h1[data-test='artwork-title']")

        try:
            artist_element = WebDriverWait(driver, config.element_wait_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, artist_selector))
            )
            artist_name = artist_element.text.strip()

            artwork_element = driver.find_element(By.CSS_SELECTOR, artwork_selector)
            artwork_title = artwork_element.text.strip()

            if artist_name and artwork_title:
                if verbose:
                    print(f"Selector-based extraction: Artist='{artist_name}', Artwork='{artwork_title}'")
                return artist_name, artwork_title
        except Exception as e:
            if verbose:
                print(f"Error extracting with selectors: {e}")

        # Strategy 3: Use URL-based fallback
        if verbose:
            print(f"Using URL-based fallback: Artist='{fallback_artist}', Artwork='{fallback_artwork}'")
        return fallback_artist, fallback_artwork

    except Exception as e:
        if verbose:
            print(f"Error in artist/artwork extraction: {e}")
        return fallback_artist, fallback_artwork


def extract_generic_info(url: str, driver: webdriver.Chrome, config: ScraperConfig, verbose: bool = False) -> Tuple[str, str]:
    """Extract artist/collection name and image name from a generic page using config.

    Returns: (artist_name, artwork_name)
    """
    parsed_url = urlparse(url)
    try:
        html = driver.page_source
        soup = parse_html_document(html)
        page_title = driver.title
        artist_name, artwork_name = extract_generic_site_and_title(soup, url, page_title)

        if verbose:
            print(f"Page-based extraction (generic): Artist='{artist_name}', Artwork='{artwork_name}'")
        return artist_name, artwork_name

    except Exception as e:
        if verbose:
            print(f"Error in generic info extraction: {e}")
        site_name = extract_domain_display_name(parsed_url.netloc)
        path_parts = [part for part in parsed_url.path.strip('/').split('/') if part]
        artwork_name = path_parts[-1].replace('-', ' ').title() if path_parts else DEFAULT_ARTWORK_NAME
        return site_name, artwork_name

# def setup_webdriver... # This function is removed, ResourceManager handles it.

def extract_original_image_url(cdn_url: str, config: ScraperConfig, verbose: bool = False) -> str:
    """Extract the original image URL from Artsy's CDN URL.

    Artsy wraps images in CDN URLs like:
    https://d7hftxdivxxvm.cloudfront.net?resize_to=fit&src=https%3A%2F%2Fd32dm0rphc51dk.cloudfront.net%2Fw1lhovVBCZMKBWMtqxH2fQ%2Flarge.jpg&width=1289

    This extracts the 'src' parameter which is the actual image URL.
    """
    site_config = config.get_site_config(ARTSY_DOMAIN)
    cdn_patterns = site_config.get("cdn_patterns", [r'resize_to=fit&src=([^&]+)', r'src=([^&]+)'])

    decoded_url = unquote(cdn_url)

    for pattern in cdn_patterns:
        match = re.search(pattern, decoded_url)
        if match:
            extracted_url = unquote(match.group(1))  # Double decode in case it's encoded twice
            if verbose:
                print(f"Extracted original URL: {extracted_url}")
            return extracted_url

    # If no pattern matches, return the original URL
    return cdn_url


def parse_srcset_urls(srcset: str, page_url: str) -> List[Tuple[int, str]]:
    """Parse a srcset attribute into width-scored absolute URLs."""
    candidates: List[Tuple[int, str]] = []
    for item in srcset.split(','):
        parts = item.strip().split()
        if not parts:
            continue

        resolved_url = resolve_page_asset_url(page_url, parts[0])
        if not resolved_url:
            continue

        width = 0
        if len(parts) > 1 and parts[1].endswith('w'):
            try:
                width = int(parts[1][:-1])
            except ValueError:
                width = 0

        candidates.append((width, resolved_url))

    return candidates


def resolve_page_asset_url(page_url: str, raw_url: str) -> Optional[str]:
    """Resolve a page-relative asset URL into an absolute HTTP(S) URL."""
    raw_url = raw_url.strip()
    if not raw_url or raw_url.startswith('data:'):
        return None

    absolute_url = urljoin(page_url, raw_url)
    parsed_url = urlparse(absolute_url)
    if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
        return None

    return absolute_url


def is_artsy_domain(domain: str) -> bool:
    """Return True when the given domain should use Artsy-specific logic."""
    return domain_matches(domain, ARTSY_DOMAIN)


def tokenize_url_path(url: str) -> Set[str]:
    """Split a URL path into exact-matchable tokens for filtering."""
    path = urlparse(url).path.lower()
    tokens: Set[str] = set()
    for segment in path.split('/'):
        if not segment:
            continue
        tokens.add(segment)
        tokens.update(token for token in re.split(TOKEN_SPLIT_PATTERN, segment) if token)
    return tokens


def contains_unwanted_image_term(url: str, unwanted_terms: List[str]) -> bool:
    """Return True when the URL path matches a configured unwanted term."""
    path = urlparse(url).path.lower()
    tokens = tokenize_url_path(url)

    for term in unwanted_terms:
        normalized_tokens = [token for token in re.split(TOKEN_SPLIT_PATTERN, term.lower()) if token]
        if not normalized_tokens:
            continue
        if len(normalized_tokens) == 1:
            if normalized_tokens[0] in tokens:
                return True
        else:
            hyphenated = '-'.join(normalized_tokens)
            underscored = '_'.join(normalized_tokens)
            if hyphenated in path or underscored in path:
                return True

    return False


def artsy_asset_group_key(url: str) -> str:
    """Group Artsy CDN variants for the same artwork image."""
    parsed_url = urlparse(url)
    path_parts = [part for part in parsed_url.path.split('/') if part]
    if parsed_url.netloc.endswith('cloudfront.net') and len(path_parts) >= 2:
        return f"{parsed_url.netloc}/{path_parts[0]}"
    return f"{parsed_url.netloc}{parsed_url.path}"


def score_artsy_candidate(url: str, source: str) -> int:
    """Score Artsy image candidates so the best variant survives dedupe."""
    parsed_url = urlparse(url)
    basename = os.path.splitext(os.path.basename(parsed_url.path))[0].lower()
    score = ARTSY_VARIANT_PRIORITY.get(basename, 5)

    if parsed_url.netloc.endswith('cloudfront.net'):
        score += 50
    elif parsed_url.netloc.endswith('artsy.net'):
        score += 10

    source_priority = {
        'json_ld': 30,
        'preload': 20,
        'meta': 10,
        'img': 0,
    }
    score += source_priority.get(source, 0)
    return score


def dedupe_artsy_candidates(candidates: List[ImageCandidate]) -> Set[str]:
    """Keep only the best candidate for each Artsy asset group."""
    best_candidates: Dict[str, ImageCandidate] = {}
    for candidate in candidates:
        key = artsy_asset_group_key(candidate.url)
        current_best = best_candidates.get(key)
        if current_best is None or candidate.score > current_best.score:
            best_candidates[key] = candidate
    return {candidate.url for candidate in best_candidates.values()}


def generic_asset_group_key(url: str) -> str:
    """Group resized variants of the same generic image asset."""
    parsed_url = urlparse(url)
    filename = os.path.splitext(os.path.basename(parsed_url.path))[0]
    match = GENERIC_IMAGE_SIZE_PATTERN.match(filename)
    if match:
        filename = match.group('base')
    parent_path = os.path.dirname(parsed_url.path)
    return f"{parsed_url.netloc}{parent_path}/{filename}"


def score_generic_candidate(url: str) -> int:
    """Prefer larger image variants when several URLs map to the same asset."""
    parsed_url = urlparse(url)
    filename = os.path.splitext(os.path.basename(parsed_url.path))[0]
    match = GENERIC_IMAGE_SIZE_PATTERN.match(filename)
    if match:
        return int(match.group('width')) * int(match.group('height'))
    return 10_000_000


def dedupe_generic_urls(urls: Set[str]) -> Set[str]:
    """Keep the highest-resolution URL for each generic asset group."""
    best_urls: Dict[str, str] = {}
    for url in urls:
        key = generic_asset_group_key(url)
        current_best = best_urls.get(key)
        if current_best is None or score_generic_candidate(url) > score_generic_candidate(current_best):
            best_urls[key] = url
    return set(best_urls.values())


def extract_images_from_page(soup: BeautifulSoup, url: str, site_type: str, config: ScraperConfig, driver: Optional[webdriver.Chrome] = None, verbose: bool = False) -> Set[str]:
    """Extract image URLs from the page based on site type and config.

    Args:
        soup: BeautifulSoup object containing parsed HTML
        url: Source URL being scraped
        site_type: Type of site ("artsy" or "generic")
        config: Scraper configuration object
        driver: Optional Selenium WebDriver instance (unused but kept for API compatibility)
        verbose: Enable verbose logging

    Returns:
        Set of image URLs found on the page
    """
    unique_urls = set()
    parsed_url_netloc = urlparse(url).netloc
    site_specific_config = config.get_site_config(parsed_url_netloc)
    unwanted_terms = site_specific_config.get('unwanted_image_terms_override', config.unwanted_image_terms)

    if site_type == SITE_TYPE_ARTSY:
        artsy_candidates: List[ImageCandidate] = []

        # Strategy 1: Try JSON-LD first (best quality)
        if site_specific_config.get("use_json_ld", True):
            json_ld_data = extract_json_ld_data(soup, verbose)
            if json_ld_data:
                _, _, image_url = extract_artsy_info_from_json_ld(json_ld_data, config, verbose)
                if image_url:
                    # Extract original URL from CDN wrapper
                    original_url = extract_original_image_url(image_url, config, verbose)
                    artsy_candidates.append(ImageCandidate(original_url, 'json_ld', score_artsy_candidate(original_url, 'json_ld')))
                    if verbose:
                        print(f"Added image from JSON-LD: {original_url}")

        # Strategy 2: Look for preload links (high-quality images)
        preload_links = soup.find_all('link', rel='preload', attrs={'as': 'image'})
        for link in preload_links:
            if 'href' in link.attrs:
                img_url = link['href']
                original_url = extract_original_image_url(img_url, config, verbose)
                if not contains_unwanted_image_term(original_url, unwanted_terms):
                    artsy_candidates.append(ImageCandidate(original_url, 'preload', score_artsy_candidate(original_url, 'preload')))
                    if verbose:
                        print(f"Added image from preload link: {original_url}")

        # Strategy 3: Look for meta tags with images
        meta_images = soup.find_all('meta', property='og:image')
        for meta in meta_images:
            if 'content' in meta.attrs:
                img_url = meta['content']
                original_url = extract_original_image_url(img_url, config, verbose)
                if not contains_unwanted_image_term(original_url, unwanted_terms):
                    artsy_candidates.append(ImageCandidate(original_url, 'meta', score_artsy_candidate(original_url, 'meta')))
                    if verbose:
                        print(f"Added image from og:image meta tag: {original_url}")

        # Strategy 4: Parse img tags as fallback
        if not artsy_candidates:
            img_tags = soup.find_all('img')
            for img in img_tags:
                if 'src' in img.attrs:
                    src = img['src']
                    original_url = extract_original_image_url(src, config, verbose)
                    if not contains_unwanted_image_term(original_url, unwanted_terms):
                        artsy_candidates.append(ImageCandidate(original_url, 'img', score_artsy_candidate(original_url, 'img')))

        unique_urls = dedupe_artsy_candidates(artsy_candidates)

    else: # Generic site
        for attr_name, attr_value in GENERIC_IMAGE_META_ATTRS:
            meta_image_url = extract_meta_content(soup, attr_name, attr_value)
            resolved_meta_url = resolve_page_asset_url(url, meta_image_url) if meta_image_url else None
            if resolved_meta_url:
                unique_urls.add(resolved_meta_url)

        preload_links = soup.find_all('link', rel='preload', attrs={'as': 'image'})
        for link in preload_links:
            resolved_link_url = resolve_page_asset_url(url, link.get('href', ''))
            if resolved_link_url:
                unique_urls.add(resolved_link_url)

        found_structured_candidate = bool(unique_urls)

        source_tags = soup.find_all('source')
        for source in source_tags:
            srcset = source.get('srcset', '')
            parsed_srcset_urls = parse_srcset_urls(srcset, url)
            if parsed_srcset_urls:
                unique_urls.add(max(parsed_srcset_urls, key=lambda candidate: candidate[0])[1])
                found_structured_candidate = True

        img_tags = soup.find_all('img')
        for img in img_tags:
            srcset = img.get('srcset', '')
            parsed_srcset_urls = parse_srcset_urls(srcset, url)
            if parsed_srcset_urls:
                unique_urls.add(max(parsed_srcset_urls, key=lambda candidate: candidate[0])[1])
                found_structured_candidate = True
                continue

            if found_structured_candidate:
                continue

            if 'src' in img.attrs:
                src = resolve_page_asset_url(url, img['src'])
                if not src:
                    continue
                if urlparse(src).path.lower().endswith('.svg'):
                    continue
                unique_urls.add(src)
                
        elements_with_style = soup.select('[style*="background-image"]')
        for element in elements_with_style:
            style = element.get('style', '')
            found_style_urls = re.findall(r'url\([\'"]?(.*?)[\'"]?\)', style)
            for img_url_style in found_style_urls:
                resolved_style_url = resolve_page_asset_url(url, img_url_style)
                if resolved_style_url:
                    unique_urls.add(resolved_style_url)

        filtered_urls = {iu for iu in unique_urls if not contains_unwanted_image_term(iu, unwanted_terms)}
        unique_urls = dedupe_generic_urls(filtered_urls)
    
    if verbose: print(f"Found {len(unique_urls)} potential image URLs after filtering")
    return unique_urls


def download_images(unique_urls: Set[str], artist_dir: str, artwork_name: str, config: ScraperConfig, manager: ResourceManager, verbose: bool = False, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> int:
    """Download images using ResourceManager for session and config for settings.

    Args:
        unique_urls: Set of image URLs to download
        artist_dir: Directory path where images should be saved
        artwork_name: Base filename for saved images
        config: Scraper configuration object
        manager: ResourceManager instance for HTTP session
        verbose: Enable verbose logging
        progress_callback: Optional callback function for progress updates

    Returns:
        Number of images successfully downloaded
    """
    num_images_downloaded = 0
    total_to_download = len(unique_urls)

    with manager.get_session() as session: # Use session from ResourceManager
        for i, img_url in enumerate(unique_urls):
            try:
                response = session.get(img_url, timeout=config.download_timeout)
                response.raise_for_status()

                content_type_header = response.headers.get('content-type', '').lower()
                file_extension = DEFAULT_IMAGE_EXTENSION

                # Map content type to extension
                for content_type, ext in IMAGE_CONTENT_TYPES.items():
                    if content_type in content_type_header:
                        file_extension = ext
                        break
                else:
                    # If no content type match, try to get extension from URL
                    path_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
                    if path_ext in config.preferred_extensions:
                        file_extension = path_ext

                image_path = os.path.join(artist_dir, artwork_name + file_extension)
                counter = 1
                base_name_for_path = artwork_name
                while os.path.exists(image_path):
                    image_path = os.path.join(artist_dir, f"{base_name_for_path}_{counter}{file_extension}")
                    counter += 1
                
                if not content_type_header.startswith('image/') or len(response.content) < config.min_image_size:
                    msg = f"Skipping small/non-image (Type: {content_type_header}, Size: {len(response.content)}): {os.path.basename(img_url)}"
                    if verbose: print(msg)
                    if progress_callback: progress_callback({'type': 'message', 'value': msg})
                    continue
                
                with open(image_path, "wb") as file: file.write(response.content)
                num_images_downloaded += 1

                dl_msg = f"DL {os.path.basename(image_path)} ({i+1}/{total_to_download})"
                if verbose: print(dl_msg)
                if progress_callback:
                    percentage = int(((i + 1) / total_to_download) * 100) if total_to_download else 100
                    progress_callback({'type': 'percentage', 'value': percentage})
                    progress_callback({'type': 'message', 'value': dl_msg})
                    
            except requests.exceptions.RequestException as e:
                err_msg = f"Error DL {img_url}: {e}"
                if verbose: print(err_msg)
                if progress_callback: progress_callback({'type': 'message', 'value': err_msg})
            except Exception as e:
                err_msg = f"Error with {img_url}: {e}"
                if verbose: print(err_msg)
                if progress_callback: progress_callback({'type': 'message', 'value': err_msg})
                    
    return num_images_downloaded


def scrape_images(url: str, config_input: Optional[Union[ScraperConfig, str]] = None, verbose: bool = False, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
    """Unified scraper using ScraperConfig and ResourceManager."""
    
    if isinstance(config_input, ScraperConfig): config = config_input
    elif isinstance(config_input, str): config = ScraperConfig.load(config_input)
    else: config = ScraperConfig.load() 
    if verbose: print(f"Using configuration: {config}")

    directory_name = config.output_directory # This is the base output directory from config
    num_images_downloaded = 0
    
    # download_manager will handle resource cleanup (driver, session)
    with download_manager(config, verbose=verbose, progress_callback=progress_callback) as manager:
        try:
            if not os.path.exists(directory_name):
                os.makedirs(directory_name)
                msg = f"Created main directory: {directory_name}"
                if verbose: print(msg)
                if progress_callback: progress_callback({'type': 'message', 'value': msg})
            
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            site_type = SITE_TYPE_ARTSY if is_artsy_domain(domain) else SITE_TYPE_GENERIC
            
            msg = f"Detected site type: {site_type} for domain: {domain}"
            if verbose: print(msg)
            if progress_callback: progress_callback({'type': 'message', 'value': msg})
            
            # WebDriver is now obtained via the manager's context manager
            with manager.get_driver(verbose=verbose) as driver:
                msg = f"Loading page: {url}..."
                if verbose: print(msg)
                if progress_callback: progress_callback({'type': 'message', 'value': msg})
                driver.get(url) # Page load timeout is set in get_driver
                
                if verbose: print(f"Waiting {config.render_wait_time}s for page to render...")
                time.sleep(config.render_wait_time)
                
                if site_type == SITE_TYPE_ARTSY:
                    artist_name, artwork_title = extract_artsy_info(url, driver, config, verbose)
                else:
                    artist_name, artwork_title = extract_generic_info(url, driver, config, verbose)
                
                artist_name_clean = clean_filename(artist_name)
                artwork_title_clean = clean_filename(artwork_title)
                
                msg_artist = f"Artist: {artist_name} {DISPLAY_ARROW} {artist_name_clean}"
                msg_artwork = f"Artwork: {artwork_title} {DISPLAY_ARROW} {artwork_title_clean}"
                if verbose: print(msg_artist); print(msg_artwork)
                if progress_callback: 
                    progress_callback({'type': 'message', 'value': msg_artist})
                    progress_callback({'type': 'message', 'value': msg_artwork})
                
                artist_dir = os.path.join(directory_name, artist_name_clean)
                if not os.path.exists(artist_dir):
                    os.makedirs(artist_dir)
                    msg = f"Created artist directory: {artist_dir}"
                    if verbose: print(msg)
                    if progress_callback: progress_callback({'type': 'message', 'value': msg})
                
                msg = "Parsing webpage content for images..."
                if verbose: print(msg)
                if progress_callback: progress_callback({'type': 'message', 'value': msg})
                html = driver.page_source
                soup = parse_html_document(html)
                
                unique_urls = extract_images_from_page(soup, url, site_type, config, driver, verbose)
                msg = f"Found {len(unique_urls)} potential image URLs."
                if verbose: print(msg)
                if progress_callback: progress_callback({'type': 'message', 'value': msg})
                
                if progress_callback: progress_callback({'type': 'message', 'value': "Starting image downloads..."})
                # Pass the manager to download_images so it can use the session
                num_images_downloaded = download_images(unique_urls, artist_dir, artwork_title_clean, config, manager, verbose, progress_callback)
            
            # Driver is automatically closed here by exiting the `with manager.get_driver()` context
            msg = f"Total number of images downloaded: {num_images_downloaded}"
            if verbose: print(msg)
            if progress_callback: progress_callback({'type': 'message', 'value': msg})
                
            return num_images_downloaded

        except OperationCancelledError:
            raise  # Re-raise without wrapping so callers can detect cancellation cleanly
        except Exception as e:
            err_msg = f"Error during scraping: {str(e)}"
            if verbose: print(err_msg)
            if progress_callback: progress_callback({'type': 'message', 'value': err_msg})
            # The download_manager's finally block will still run for cleanup
            raise Exception(f"Failed to scrape images: {str(e)}") from e
        # No explicit finally block for driver.quit() needed here, download_manager handles it.


def main():
    """Main function for running the scraper as a standalone script."""
    print("Image Scraper Tool")
    print("--------------------------")
    
    # Load or create a default config file for standalone use
    config_file_path = DEFAULT_CONFIG_FILENAME
    if os.path.exists(config_file_path):
        config = ScraperConfig.load(config_file_path)
        print(f"Loaded configuration from {config_file_path}")
    else:
        config = ScraperConfig()
        config.save(config_file_path)
        print(f"Default configuration saved to {config_file_path}. You can customize it.")

    while True:
        url = input("Enter the URL to scrape (or 'exit' to quit): ")
        if url.lower() == EXIT_COMMAND: break
        
        # For standalone, use the output_directory from the loaded/default config
        # Or allow override via input:
        custom_output_dir_prompt = input(f"Enter output directory (default: '{config.output_directory}', press Enter to use default): ").strip()
        
        # Create a config instance for this specific run
        # Start with a deepcopy of the loaded/default config to avoid modifying it globally
        current_run_config = copy.deepcopy(config)
        if custom_output_dir_prompt:
            current_run_config.output_directory = custom_output_dir_prompt
        
        try:
            num_downloaded = scrape_images(url, config_input=current_run_config, verbose=True)
            print(f"\nSuccessfully downloaded {num_downloaded} images to '{current_run_config.output_directory}'.\n")
        except Exception as e:
            print(f"\nError: {str(e)}\n")

if __name__ == "__main__":
    main()
