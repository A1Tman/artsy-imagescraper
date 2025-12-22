import os
import sys
import re
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse
from typing import Optional, Union, Any, Callable, Dict, Tuple, Set, List

# Ensure the script's directory is in sys.path for local module resolution.
# This can help linters like Pylance find 'config.py' and 'resources.py'
# when the script is part of a project opened in an IDE.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Import the configuration and resource management classes
from config import ScraperConfig
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
JSON_LD_UNKNOWN_TYPE = 'unknown'

# Default values for extraction fallbacks
DEFAULT_ARTIST_NAME = "unknown"
DEFAULT_ARTWORK_NAME = "artwork"

# Artsy-specific constants
ARTSY_DOMAIN = "artsy.net"
ARTSY_ARTWORK_PATH = '/artwork/'
ARTWORK_SLUG_INDEX = 1
ARTIST_NAME_WORD_COUNT = 2
SLUG_PARTS_MIN_FOR_TITLE = 2

# Site type identifiers
SITE_TYPE_ARTSY = "artsy"
SITE_TYPE_GENERIC = "generic"

# Generic page extraction
MIN_HEADING_LEVEL = 1
MAX_HEADING_LEVEL = 4
HEADING_WAIT_DIVISOR = 3
HEADING_MAX_LENGTH = 100
MIN_HEADINGS_FOR_BOTH = 2
ARTIST_HEADING_INDEX = 0
ARTWORK_HEADING_INDEX = 1
MIN_PATH_PARTS_FOR_ARTWORK = 1
DOMAIN_PARTS_THRESHOLD = 2

# URL schemes
HTTP_SCHEME = 'http://'
HTTPS_SCHEME = 'https://'
DATA_URI_PREFIX = 'data:image'
SVG_EXTENSION = '.svg'

# Image content types mapping
IMAGE_CONTENT_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp'
}
IMAGE_CONTENT_TYPE_PREFIX = 'image/'
DEFAULT_IMAGE_EXTENSION = '.jpg'

# Progress tracking
PERCENTAGE_MULTIPLIER = 100

# Configuration
DEFAULT_CONFIG_FILENAME = "scraper_config.json"
EXIT_COMMAND = 'exit'

# Regex group indices
REGEX_FIRST_MATCH_GROUP = 1


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
                print(f"Found JSON-LD data with @type: {data.get(JSON_LD_TYPE_KEY, JSON_LD_UNKNOWN_TYPE)}")
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
        slug = url_path.split(ARTSY_ARTWORK_PATH)[ARTWORK_SLUG_INDEX].strip('/')
        slug_parts = slug.split('-')
        fallback_artist = ' '.join(slug_parts[:ARTIST_NAME_WORD_COUNT]).title()
        fallback_artwork = ' '.join(slug_parts[ARTIST_NAME_WORD_COUNT:]).title() if len(slug_parts) > SLUG_PARTS_MIN_FOR_TITLE else slug.title()
        if verbose:
            print(f"URL-based fallback prepared: Artist='{fallback_artist}', Artwork='{fallback_artwork}'")

    try:
        # Strategy 1: Try JSON-LD extraction (most reliable for Artsy)
        if use_json_ld:
            html = driver.page_source
            # Try lxml parser first for better performance, fall back to html.parser
            try:
                soup = BeautifulSoup(html, PRIMARY_HTML_PARSER)
            except ImportError:
                soup = BeautifulSoup(html, FALLBACK_HTML_PARSER)
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
    try:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip('/').split('/')

        try:
            page_title = driver.title
            headings = []
            # Use WebDriverWait for finding headings if possible, or at least handle timeouts
            for h_level in range(MIN_HEADING_LEVEL, MAX_HEADING_LEVEL):
                try:
                    elements = WebDriverWait(driver, config.element_wait_timeout / HEADING_WAIT_DIVISOR).until( # Shorter wait per heading level
                        EC.presence_of_all_elements_located((By.TAG_NAME, f'h{h_level}'))
                    )
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) < HEADING_MAX_LENGTH:
                            headings.append(text)
                except Exception as e:
                    # Ignore if specific heading level not found quickly
                    if verbose:
                        print(f"No h{h_level} headings found: {e}")
                    continue
            
            if len(headings) >= MIN_HEADINGS_FOR_BOTH:
                artist_name, artwork_name = headings[ARTIST_HEADING_INDEX], headings[ARTWORK_HEADING_INDEX]
            elif len(headings) == 1:
                artist_name = path_parts[0].replace('-', ' ').title() if path_parts else DEFAULT_ARTIST_NAME
                artwork_name = headings[0]
            else:
                artist_name = path_parts[0].replace('-', ' ').title() if path_parts else DEFAULT_ARTIST_NAME
                artwork_name = path_parts[-1].replace('-', ' ').title() if len(path_parts) > MIN_PATH_PARTS_FOR_ARTWORK else page_title or DEFAULT_ARTWORK_NAME
            
            if verbose: print(f"Page-based extraction (generic): Artist='{artist_name}', Artwork='{artwork_name}'")
            return artist_name, artwork_name
                
        except Exception as e:
            if verbose: print(f"Error extracting generic page elements: {e}")
            # Fallback logic remains similar
            if len(path_parts) >= 2: artist_name, artwork_name = path_parts[0].replace('-', ' ').title(), path_parts[-1].replace('-', ' ').title()
            elif len(path_parts) == 1: artist_name, artwork_name = parsed_url.netloc.split('.')[0].title(), path_parts[0].replace('-', ' ').title()
            else: artist_name, artwork_name = parsed_url.netloc.split('.')[0].title(), "artwork"
            if verbose: print(f"URL-based extraction (generic fallback): Artist='{artist_name}', Artwork='{artwork_name}'")
            return artist_name, artwork_name
            
    except Exception as e:
        if verbose: print(f"Error in generic info extraction: {e}")
        domain_parts = parsed_url.netloc.split('.')
        site_name = domain_parts[1] if len(domain_parts) > DOMAIN_PARTS_THRESHOLD else domain_parts[0]
        return site_name.title(), DEFAULT_ARTWORK_NAME

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
            extracted_url = unquote(match.group(REGEX_FIRST_MATCH_GROUP))  # Double decode in case it's encoded twice
            if verbose:
                print(f"Extracted original URL: {extracted_url}")
            return extracted_url

    # If no pattern matches, return the original URL
    return cdn_url


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
        # Strategy 1: Try JSON-LD first (best quality)
        if site_specific_config.get("use_json_ld", True):
            json_ld_data = extract_json_ld_data(soup, verbose)
            if json_ld_data:
                _, _, image_url = extract_artsy_info_from_json_ld(json_ld_data, config, verbose)
                if image_url:
                    # Extract original URL from CDN wrapper
                    original_url = extract_original_image_url(image_url, config, verbose)
                    unique_urls.add(original_url)
                    if verbose:
                        print(f"Added image from JSON-LD: {original_url}")

        # Strategy 2: Look for preload links (high-quality images)
        preload_links = soup.find_all('link', rel='preload', attrs={'as': 'image'})
        for link in preload_links:
            if 'href' in link.attrs:
                img_url = link['href']
                original_url = extract_original_image_url(img_url, config, verbose)
                if not any(term in original_url.lower() for term in unwanted_terms):
                    unique_urls.add(original_url)
                    if verbose:
                        print(f"Added image from preload link: {original_url}")

        # Strategy 3: Look for meta tags with images
        meta_images = soup.find_all('meta', property='og:image')
        for meta in meta_images:
            if 'content' in meta.attrs:
                img_url = meta['content']
                original_url = extract_original_image_url(img_url, config, verbose)
                if not any(term in original_url.lower() for term in unwanted_terms):
                    unique_urls.add(original_url)
                    if verbose:
                        print(f"Added image from og:image meta tag: {original_url}")

        # Strategy 4: Parse img tags as fallback
        img_tags = soup.find_all('img')
        for img in img_tags:
            if 'src' in img.attrs:
                src = img['src']
                original_url = extract_original_image_url(src, config, verbose)
                if not any(term in original_url.lower() for term in unwanted_terms):
                    unique_urls.add(original_url)

    else: # Generic site
        img_tags = soup.find_all('img')
        for img in img_tags:
            if 'src' in img.attrs:
                src = img['src']
                if DATA_URI_PREFIX in src or SVG_EXTENSION in src: continue
                if not src.startswith((HTTP_SCHEME, HTTPS_SCHEME)):
                    base_url_scheme = urlparse(url).scheme
                    base_url_netloc = urlparse(url).netloc
                    src = f"{base_url_scheme}://{base_url_netloc.rstrip('/')}/{src.lstrip('/')}"
                unique_urls.add(src)
                
        elements_with_style = soup.select('[style*="background-image"]')
        for element in elements_with_style:
            style = element.get('style', '')
            found_style_urls = re.findall(r'url\([\'"]?(.*?)[\'"]?\)', style)
            for img_url_style in found_style_urls:
                if img_url_style and not img_url_style.startswith('data:'):
                    if not img_url_style.startswith(('http://', 'https://')):
                        base_url_scheme = urlparse(url).scheme
                        base_url_netloc = urlparse(url).netloc
                        img_url_style = f"{base_url_scheme}://{base_url_netloc.rstrip('/')}/{img_url_style.lstrip('/')}"
                    unique_urls.add(img_url_style)
        
        filtered_urls = {iu for iu in unique_urls if not any(term in iu.lower() for term in unwanted_terms)}
        unique_urls = filtered_urls
    
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
                
                if not content_type_header.startswith(IMAGE_CONTENT_TYPE_PREFIX) or len(response.content) < config.min_image_size:
                    msg = f"Skipping small/non-image (Type: {content_type_header}, Size: {len(response.content)}): {os.path.basename(img_url)}"
                    if verbose: print(msg)
                    if progress_callback: progress_callback({'type': 'message', 'value': msg})
                    continue
                
                with open(image_path, "wb") as file: file.write(response.content)
                num_images_downloaded += 1

                dl_msg = f"DL {os.path.basename(image_path)} ({i+1}/{total_to_download})"
                if verbose: print(dl_msg)
                if progress_callback:
                    percentage = int(((i + 1) / total_to_download) * PERCENTAGE_MULTIPLIER) if total_to_download else PERCENTAGE_MULTIPLIER
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
            site_type = "artsy" if "artsy.net" in domain else "generic"
            
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
                
                msg_artist = f"Artist: {artist_name} → {artist_name_clean}"
                msg_artwork = f"Artwork: {artwork_title} → {artwork_title_clean}"
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
                # Try to use lxml parser for better performance, fall back to html.parser
                try:
                    soup = BeautifulSoup(html, PRIMARY_HTML_PARSER)
                except ImportError:
                    soup = BeautifulSoup(html, FALLBACK_HTML_PARSER)
                
                unique_urls = extract_images_from_page(soup, url, site_type, config, verbose)
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
            
        except Exception as e:
            err_msg = f"Error during scraping: {str(e)}"
            if verbose: print(err_msg)
            if progress_callback: progress_callback({'type': 'message', 'value': err_msg})
            # The download_manager's finally block will still run for cleanup
            raise Exception(f"Failed to scrape images: {str(e)}") from e
        # No explicit finally block for driver.quit() needed here, download_manager handles it.


def main():
    """Main function for running the scraper as a standalone script."""
    print("Universal Image Scraper Tool")
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
        import copy
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
