import os
import sys

# Ensure the script's directory is in sys.path for local module resolution.
# This can help linters like Pylance find 'config.py' and 'resources.py'
# when the script is part of a project opened in an IDE.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
import requests # Still needed for type hints and potential direct use if session fails
import re
import time
from selenium import webdriver # Still needed for type hints (driver type)
# from selenium.webdriver.chrome.service import Service # Encapsulated in ResourceManager
# from selenium.webdriver.chrome.options import Options # Encapsulated in ResourceManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# from webdriver_manager.chrome import ChromeDriverManager # Encapsulated in ResourceManager
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse
from typing import Optional, Union, Any, Callable, Dict # Added Any for progress_callback type, Dict for type hint

# Import the configuration and resource management classes
# Use explicit imports with the script directory to help Pylance resolve modules
# Ensure the script's directory is in sys.path for local module resolution.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from config import ScraperConfig
from resources import download_manager, ResourceManager


def clean_filename(name: str) -> str:
    """Convert a string to a valid filename"""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'[\s-]+', "_", name)
    return name[:100]


def extract_artsy_info(url: str, driver: webdriver.Chrome, config: ScraperConfig, verbose: bool = False):
    """Extract artist name and artwork title from an Artsy page using config."""
    site_specific_config = config.get_site_config(urlparse(url).netloc)
    artist_selector = site_specific_config.get("artist_selector", "h2[data-test='artist-name']")
    artwork_selector = site_specific_config.get("artwork_selector", "h1[data-test='artwork-title']")

    try:
        url_path = urlparse(url).path
        fallback_artist, fallback_artwork = "unknown", "artwork"
        if '/artwork/' in url_path:
            slug = url_path.split('/artwork/')[1].strip('/')
            slug_parts = slug.split('-')
            fallback_artist = ' '.join(slug_parts[:2]).title()
            fallback_artwork = ' '.join(slug_parts[2:]).title() if len(slug_parts) > 2 else slug.title()
            if verbose: print(f"URL-based fallback: Artist='{fallback_artist}', Artwork='{fallback_artwork}'")
        
        try:
            artist_element = WebDriverWait(driver, config.element_wait_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, artist_selector))
            )
            artist_name = artist_element.text.strip()
            
            artwork_element = driver.find_element(By.CSS_SELECTOR, artwork_selector)
            artwork_title = artwork_element.text.strip()
            
            if verbose: print(f"Page-based extraction: Artist='{artist_name}', Artwork='{artwork_title}'")
            return artist_name, artwork_title
            
        except Exception as e:
            if verbose: print(f"Error extracting from page (selectors): {e}. Using fallback.")
            return fallback_artist, fallback_artwork
            
    except Exception as e:
        if verbose: print(f"Error in artist/artwork extraction: {e}")
        return "unknown", "artwork"


def extract_generic_info(url: str, driver: webdriver.Chrome, config: ScraperConfig, verbose: bool = False):
    """Extract artist/collection name and image name from a generic page using config."""
    try:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip('/').split('/')
        
        try:
            page_title = driver.title
            headings = []
            # Use WebDriverWait for finding headings if possible, or at least handle timeouts
            for h_level in range(1, 4):
                try:
                    elements = WebDriverWait(driver, config.element_wait_timeout / 3).until( # Shorter wait per heading level
                        EC.presence_of_all_elements_located((By.TAG_NAME, f'h{h_level}'))
                    )
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) < 100: headings.append(text)
                except: pass # Ignore if specific heading level not found quickly
            
            if len(headings) >= 2: artist_name, artwork_name = headings[0], headings[1]
            elif len(headings) == 1:
                artist_name = path_parts[0].replace('-', ' ').title() if path_parts else "unknown"
                artwork_name = headings[0]
            else:
                artist_name = path_parts[0].replace('-', ' ').title() if path_parts else "unknown"
                artwork_name = path_parts[-1].replace('-', ' ').title() if len(path_parts) > 1 else page_title or "artwork"
            
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
        site_name = domain_parts[1] if len(domain_parts) > 2 else domain_parts[0]
        return site_name.title(), "artwork"

# def setup_webdriver... # This function is removed, ResourceManager handles it.

def extract_images_from_page(soup, url: str, site_type: str, config: ScraperConfig, verbose: bool = False):
    """Extract image URLs from the page based on site type and config."""
    unique_urls = set()
    parsed_url_netloc = urlparse(url).netloc
    site_specific_config = config.get_site_config(parsed_url_netloc)
    unwanted_terms = site_specific_config.get('unwanted_image_terms_override', config.unwanted_image_terms)

    if site_type == "artsy":
        all_divs = soup.find_all('div') # Consider using more specific selectors from config if available
        for div in all_divs:
            img_tags = div.find_all('img')
            for img in img_tags:
                if 'src' not in img.attrs: continue
                src = img['src']
                decoded_url = unquote(src)
                if "resize_to=fit&src=" in decoded_url: # Artsy specific URL transformation
                    start_index = decoded_url.find("resize_to=fit&src=") + len("resize_to=fit&src=")
                    end_index = decoded_url.find("&width") if "&width" in decoded_url else len(decoded_url)
                    modified_url = decoded_url[start_index:end_index]
                else: modified_url = decoded_url
                if not any(term in modified_url.lower() for term in unwanted_terms):
                    unique_urls.add(modified_url)
    else: # Generic site
        img_tags = soup.find_all('img')
        for img in img_tags:
            if 'src' in img.attrs:
                src = img['src']
                if 'data:image' in src or '.svg' in src: continue
                if not src.startswith(('http://', 'https://')):
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


def download_images(unique_urls, artist_dir: str, artwork_name: str, config: ScraperConfig, manager: ResourceManager, verbose: bool = False, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
    """Download images using ResourceManager for session and config for settings."""
    num_images_downloaded = 0
    total_to_download = len(unique_urls)

    with manager.get_session() as session: # Use session from ResourceManager
        for i, img_url in enumerate(unique_urls):
            try:
                response = session.get(img_url, timeout=config.download_timeout)
                response.raise_for_status()

                content_type_header = response.headers.get('content-type', '').lower()
                file_extension = ".jpg" 
                
                if 'image/jpeg' in content_type_header: file_extension = ".jpg"
                elif 'image/png' in content_type_header: file_extension = ".png"
                elif 'image/gif' in content_type_header: file_extension = ".gif"
                elif 'image/webp' in content_type_header: file_extension = ".webp"
                elif 'image/bmp' in content_type_header: file_extension = ".bmp"
                else:
                    path_ext = os.path.splitext(urlparse(img_url).path)[1].lower()
                    if path_ext in config.preferred_extensions: file_extension = path_ext

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
                
                if site_type == "artsy":
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
                soup = BeautifulSoup(html, "html.parser")
                
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
    config_file_path = "scraper_config.json" 
    if os.path.exists(config_file_path):
        config = ScraperConfig.load(config_file_path)
        print(f"Loaded configuration from {config_file_path}")
    else:
        config = ScraperConfig()
        config.save(config_file_path)
        print(f"Default configuration saved to {config_file_path}. You can customize it.")
    
    while True:
        url = input("Enter the URL to scrape (or 'exit' to quit): ")
        if url.lower() == 'exit': break
        
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
