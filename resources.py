"""
Session and resource management module for the image scraper.
"""
import os
import sys
import logging
from contextlib import contextmanager
from typing import Optional, Callable, Dict, Any, Generator

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Import config using absolute import instead of relative import
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.insert(0, _MODULE_DIR)
from config import ScraperConfig

# ============================================================================
# Constants
# ============================================================================

# Logging
LOGGER_NAME = "image_scraper"
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# HTTP Headers
HEADER_USER_AGENT = 'User-Agent'
HEADER_ACCEPT = 'Accept'
HEADER_ACCEPT_LANGUAGE = 'Accept-Language'
HEADER_CONNECTION = 'Connection'
HTTP_ACCEPT_VALUE = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
HTTP_ACCEPT_LANGUAGE_VALUE = 'en-US,en;q=0.9'
HTTP_CONNECTION_VALUE = 'keep-alive'

# Chrome Arguments
CHROME_ARG_IGNORE_CERT = '--ignore-certificate-errors'
CHROME_ARG_INCOGNITO = '--incognito'
CHROME_ARG_HEADLESS = '--headless'
CHROME_ARG_DISABLE_AUTOMATION = '--disable-blink-features=AutomationControlled'
CHROME_ARG_USER_AGENT_PREFIX = '--user-agent='

# Configure logging - basic setup if not configured by the main application
# This allows the logger to output messages if the main app doesn't set up handlers.
logger = logging.getLogger(LOGGER_NAME)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


class ResourceManager:
    """Manages resources like WebDriver and HTTP sessions."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self._session: Optional[requests.Session] = None
        self._driver: Optional[webdriver.Chrome] = None
    
    @contextmanager
    def get_session(self) -> Generator[requests.Session, None, None]:
        """Get or create a requests Session with proper configuration."""
        if self._session is None:
            logger.debug("Initializing new HTTP session.")
            self._session = requests.Session()
            self._session.headers.update({
                HEADER_USER_AGENT: self.config.browser_user_agent,
                HEADER_ACCEPT: HTTP_ACCEPT_VALUE,
                HEADER_ACCEPT_LANGUAGE: HTTP_ACCEPT_LANGUAGE_VALUE,
                HEADER_CONNECTION: HTTP_CONNECTION_VALUE,
            })
        
        try:
            yield self._session
        except Exception as e:
            logger.error(f"HTTP Session error: {str(e)}")
            # Optionally, decide if session should be closed and recreated on specific errors
            # For now, we let it be reused unless explicitly closed by close_session or close_all
            raise
    
    @contextmanager
    def get_driver(self, verbose: bool = False) -> Generator[webdriver.Chrome, None, None]:
        """Get or create a properly configured Chrome WebDriver."""
        # This context manager ensures driver is created if None, and yields it.
        # Closing is handled by close_driver or close_all, typically in a broader finally block.
        if self._driver is None:
            if verbose: # verbose from the calling function, not self.config.verbose
                logger.info("Initializing Chrome WebDriver via ResourceManager...")
            
            try:
                options = Options()
                
                if self.config.browser_ignore_cert_errors:
                    options.add_argument(CHROME_ARG_IGNORE_CERT)

                if self.config.browser_incognito:
                    options.add_argument(CHROME_ARG_INCOGNITO)

                if self.config.browser_headless:
                    options.add_argument(CHROME_ARG_HEADLESS)

                if self.config.browser_disable_automation:
                    options.add_argument(CHROME_ARG_DISABLE_AUTOMATION)

                if self.config.browser_user_agent:
                    options.add_argument(f'{CHROME_ARG_USER_AGENT_PREFIX}{self.config.browser_user_agent}')
                
                # Add Chrome performance logging (optional, can be noisy)
                # options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
                
                # Initialize Chrome driver
                # Consider making ChromeDriver path configurable in ScraperConfig too
                self._driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager().install()), 
                    options=options
                )
                
                # Set timeouts
                # page_load_timeout is for driver.get()
                self._driver.set_page_load_timeout(self.config.page_load_timeout)
                # implicitly_wait is a global wait for find_element(s)
                # It's often better to use explicit WebDriverWait
                # self._driver.implicitly_wait(self.config.element_wait_timeout) 
                logger.info("WebDriver initialized successfully.")
                
            except Exception as e:
                logger.error(f"Failed to initialize WebDriver: {str(e)}")
                self.close_driver() # Attempt cleanup if init fails
                raise
        
        try:
            yield self._driver
        except Exception as e:
            logger.error(f"WebDriver operation error: {str(e)}")
            # Don't automatically close driver here, let the main context manager (download_manager) handle it
            raise
    
    def close_driver(self):
        """Close the WebDriver if it exists."""
        if self._driver:
            logger.info("Closing WebDriver...")
            try:
                self._driver.quit()
                logger.debug("WebDriver closed successfully.")
            except Exception as e:
                logger.error(f"Error closing WebDriver: {str(e)}")
            finally:
                self._driver = None
    
    def close_session(self):
        """Close the requests Session if it exists."""
        if self._session:
            logger.info("Closing HTTP session...")
            try:
                self._session.close()
                logger.debug("HTTP session closed successfully.")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {str(e)}")
            finally:
                self._session = None
    
    def close_all(self):
        """Close all managed resources."""
        logger.info("Closing all managed resources.")
        self.close_driver()
        self.close_session()


@contextmanager
def download_manager(
    config: ScraperConfig, 
    # output_dir: str, # output_dir is part of config now
    verbose: bool = False, # Pass verbose for logging within manager
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Generator[ResourceManager, None, None]:
    """Context manager for resource handling during scraping."""
    
    # Output directory is now handled by scrape_images using config.output_directory
    # os.makedirs(config.output_directory, exist_ok=True) # Ensure output dir from config exists
    
    manager = ResourceManager(config)
    
    try:
        if verbose:
            logger.info("Download manager entered.")
        yield manager
    except Exception as e:
        logger.error(f"Error within download_manager scope: {e}")
        if progress_callback:
            progress_callback({'type': 'message', 'value': f"Critical error in download manager: {e}"})
        raise # Re-raise the exception so scrape_images can catch it
    finally:
        if verbose:
            logger.info("Cleaning up resources via download_manager...")
        
        manager.close_all()
        
        if verbose:
            logger.info("Resources cleaned up by download_manager.")
        
        if progress_callback:
            progress_callback({'type': 'message', 'value': "Scraping process finished, resources cleaned up."})
