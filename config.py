"""
Configuration module for the image scraper.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os
import json


def domain_matches(domain: str, site_domain: str) -> bool:
    """Return True when the domain is an exact match or subdomain."""
    return domain == site_domain or domain.endswith('.' + site_domain)


@dataclass
class ScraperConfig:
    """Configuration for the image scraper."""
    # Base directories
    output_directory: str = "Scraped"
    
    # Browser settings
    browser_headless: bool = True
    browser_user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
    browser_incognito: bool = True
    browser_disable_automation: bool = True
    browser_ignore_cert_errors: bool = False  # Security: Only ignore cert errors when explicitly needed
    
    # Timeouts (in seconds)
    page_load_timeout: int = 30  # Maximum time to wait for page to load (30 seconds)
    element_wait_timeout: int = 10  # Maximum time to wait for elements to appear (10 seconds)
    download_timeout: int = 10  # Maximum time to wait for image downloads (10 seconds)
    render_wait_time: int = 3  # Time to wait for JavaScript to render dynamic content (3 seconds)

    # Image settings
    min_image_size: int = 10000  # Minimum image size in bytes (~10KB) to filter out thumbnails and icons
    preferred_extensions: List[str] = field(default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp", ".bmp"]) # Added .bmp
    
    # Filtering
    unwanted_image_terms: List[str] = field(default_factory=lambda: [
        'logo', 'icon', 'avatar', 'banner', 'button', 'thumbnail', 
        'favicon', 'ads', 'tracking', 'universal-footer', 'larger', 
        'small', 'square', 'source'
    ])
    
    # Site-specific configurations
    site_configs: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "artsy.net": {
            # Artsy no longer uses data-test attributes consistently, rely on JSON-LD instead
            "artist_selector": "h2[data-test='artist-name']",  # Fallback only
            "artwork_selector": "h1[data-test='artwork-title']",  # Fallback only
            "use_json_ld": True,  # Primary method: extract from JSON-LD structured data
            "json_ld_selectors": {
                "artist_path": "creator.name",  # Path in JSON-LD for artist name
                "artwork_path": "name",  # Path in JSON-LD for artwork title
                "image_path": "image.url"  # Path in JSON-LD for image URL
            },
            # CDN patterns for extracting original image URLs from Artsy's CDN
            "cdn_patterns": [
                r'resize_to=fit&src=([^&]+)',  # Extract src parameter from Artsy CDN URLs
                r'src=([^&]+)'  # Backup pattern
            ],
            "unwanted_image_terms_override": ['universal-footer', 'larger', 'small', 'square', 'source', 'logo', 'icon', 'favicon', 'thumbnail']
        }
        # Add other site configs here, e.g.
        # "generic_site.com": { ... }
    })
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> 'ScraperConfig':
        """Load configuration from a JSON file."""
        config = cls() # Start with default config
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # Update config fields from loaded data
                for key, value in config_data.items():
                    if hasattr(config, key):
                        current = getattr(config, key)
                        # Handle nested dicts like site_configs carefully
                        if isinstance(current, dict) and isinstance(value, dict):
                            current.update(value)
                        elif cls._is_compatible_config_value(current, value):
                            setattr(config, key, value)
                        else:
                            print(f"Warning: Skipping config key '{key}': "
                                  f"expected {type(current).__name__}, got {type(value).__name__}")
            except Exception as e:
                print(f"Warning: Error loading configuration from {config_path}: {str(e)}")
                print("Using default configuration.")
        
        return config
    
    def save(self, config_path: str) -> bool:
        """Save configuration to a JSON file."""
        try:
            # Ensure directory exists
            config_dir = os.path.dirname(os.path.abspath(config_path))
            if config_dir: # Ensure config_dir is not empty (e.g. if path is just a filename)
                 os.makedirs(config_dir, exist_ok=True)
            
            # Convert dataclass to dict for JSON serialization
            # For dataclasses.asdict, ensure you handle nested dataclasses if any
            # For simple fields, self.__dict__ is okay but might include extra methods if not careful
            # A more robust way for dataclasses:
            # import dataclasses
            # config_dict = dataclasses.asdict(self)

            # Using __dict__ for simplicity here, assuming no complex nested dataclasses
            config_dict = {f.name: getattr(self, f.name) for f in self.__class__.__dataclass_fields__.values()}

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=4)
            print(f"Configuration saved to {config_path}")
            return True
        except Exception as e:
            print(f"Error saving configuration to {config_path}: {str(e)}")
            return False

    @staticmethod
    def _is_compatible_config_value(current: Any, value: Any) -> bool:
        """Validate loaded values without treating bool as a numeric subtype."""
        if isinstance(current, bool):
            return isinstance(value, bool)
        if isinstance(current, int):
            return isinstance(value, int) and not isinstance(value, bool)
        if isinstance(current, float):
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return type(current) == type(value)
    
    def get_site_config(self, domain: str) -> Dict[str, Any]:
        """Get site-specific configuration based on domain."""
        # Find the most specific matching domain key from site_configs
        # e.g., if domain is "sub.artsy.net", "artsy.net" should match.
        best_match_key = None
        for site_key in self.site_configs.keys():
            if domain_matches(domain, site_key):
                if best_match_key is None or len(site_key) > len(best_match_key):
                    best_match_key = site_key
        
        if best_match_key:
            return self.site_configs[best_match_key]
        return {}  # Return empty dict if no specific config found
