import sys
import os
import threading
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLineEdit, QLabel, QWidget, QFileDialog, 
                            QProgressBar, QMessageBox, QTextEdit, QGroupBox, 
                            QTabWidget, QListWidget, QSplitter, QComboBox)
from PyQt5.QtGui import QFont, QIcon, QTextCursor
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
import json
import re
import copy
from datetime import datetime
import appdirs
from urllib.parse import urlparse
from typing import Any, Dict, Optional

# Import the unified scraper module
from improved_scraper import scrape_images
# Import config using absolute import instead of relative import
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE_DIR not in sys.path:
    sys.path.insert(0, _MODULE_DIR)
from config import ScraperConfig

# Progress update dictionary keys and values
PROG_TYPE = 'type'
PROG_VALUE = 'value'
PROG_PERCENTAGE = 'percentage'
PROG_MESSAGE = 'message'

# ============================================================================
# Constants
# ============================================================================

# UI Dimensions
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700

# Font Sizes
TITLE_FONT_SIZE = 22
HEADING_FONT_SIZE = 11
NORMAL_FONT_SIZE = 10
SMALL_FONT_SIZE = 9

# Fonts
FONT_ARIAL = 'Arial'

# Text Limits
STATUS_TEXT_MAX_LENGTH = 100
FILENAME_MAX_LENGTH = 100

# Margins and Spacing (removed over-engineered single-use margin constants)

# Color Scheme
COLOR_DARK_BLUE = "#2C3E50"
COLOR_GRAY = "#7F8C8D"
COLOR_LIGHT_GRAY = "#BDC3C7"
COLOR_BLUE = "#3498DB"
COLOR_VERY_LIGHT_GRAY = "#ECF0F1"
COLOR_MEDIUM_GRAY = "#D0D3D4"
COLOR_GREEN = "#2ECC71"
COLOR_DARK_GREEN = "#27AE60"
COLOR_SLATE_GRAY = "#95A5A6"
COLOR_DARKER_BLUE = "#2980B9"
COLOR_RED = "#E74C3C"
COLOR_DARK_RED = "#C0392B"

# Application Info
APP_NAME = "ImageScraper"
WINDOW_TITLE = 'Universal Image Scraper'
APP_DESCRIPTION = 'Download and organize artwork from various websites'

# UI Text
URL_INPUT_PLACEHOLDER = 'Enter URL (e.g., https://www.example.com/artwork/title)'
URL_WARNING_MESSAGE = "⚠️ Invalid URL format or missing http(s)://"
SAVE_DIR_PLACEHOLDER = 'Choose a folder to save images'
DEFAULT_SCRAPED_IMAGES_DIR = 'Scraped_Images'
STATUS_READY = 'Ready'

# Button Text
BTN_START_SCRAPING = 'Start Scraping'
BTN_CHECK_UPDATE_PACKAGES = 'Check/Update Packages'
BTN_CANCEL = 'Cancel'

# Configuration Files
SETTINGS_FILENAME = "settings.json"
SCRAPER_CONFIG_FILENAME = "scraper_config.json"
HISTORY_FILENAME = 'scraper_history.json'

# History
HISTORY_URL_PATTERN = r' - (https?://[^\s]+) \(.*'
HISTORY_ITEM_FORMAT = "{timestamp} - {url} ({count} images)"
HISTORY_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_TIME_FORMAT = "%H:%M:%S"

# URL Validation
VALID_URL_SCHEMES = ("http", "https")

# Platform-Specific
PLATFORM_WINDOWS = 'win32'
PLATFORM_MACOS = 'darwin'
WINDOWS_INVALID_PATH_CHARS = ['<', '>', '|', '&', '^']
FILE_OPEN_TIMEOUT_SECONDS = 5

# Security - System Directories
WINDOWS_FORBIDDEN_DIRS = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)"
]
UNIX_FORBIDDEN_DIRS = ["/bin", "/sbin", "/boot", "/etc", "/sys", "/proc"]

# Package Management
REQUIRED_PACKAGES = ['selenium', 'beautifulsoup4', 'requests', 'webdriver-manager', 'PyQt5', 'appdirs']

class WorkerSignals(QObject):
    """
    Defines the signals available from the worker thread.
    """
    finished = pyqtSignal(int)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)

class UpdatePackagesThread(threading.Thread):
    """
    Worker thread for updating packages.
    Checks current versions and only updates outdated packages.
    """
    def __init__(self) -> None:
        # self.settings = {} # This was in the original, but settings belong to the app
        super().__init__()
        self.signals: WorkerSignals = WorkerSignals()
        self.cancel_requested: bool = False

    def request_cancel(self) -> None:
        """Set the cancel flag to request cancellation."""
        self.cancel_requested = True

    def run(self) -> None:
        try:
            self.signals.progress.emit("Starting package check...")
            required_packages = REQUIRED_PACKAGES
            updated_count = 0
            already_latest_count = 0

            self.signals.progress.emit("Checking for outdated packages...")
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list', '--outdated', '--format=json'],
                capture_output=True, text=True, check=False
            )

            if self.cancel_requested:
                self.signals.progress.emit("Package update cancelled by user.")
                self.signals.finished.emit(updated_count)
                return

            outdated_dict = {}
            current_version_from_outdated_list_dict = {}
            if result.returncode == 0 and result.stdout:
                try:
                    outdated_packages = json.loads(result.stdout)
                    outdated_dict = {pkg["name"].lower(): pkg["latest_version"] for pkg in outdated_packages}
                    current_version_from_outdated_list_dict = {pkg["name"].lower(): pkg["version"] for pkg in outdated_packages}
                    required_outdated = [pkg for pkg in required_packages if pkg.lower() in outdated_dict]
                    if required_outdated:
                        self.signals.progress.emit(f"Found {len(required_outdated)} outdated required packages out of {len(outdated_dict)} total outdated packages.")
                    else:
                        self.signals.progress.emit(f"None of the required packages are outdated (although {len(outdated_dict)} other packages in your environment could be updated).")
                except json.JSONDecodeError:
                    self.signals.progress.emit("Warning: Could not parse outdated packages list. Will check each package individually.")
            else:
                 self.signals.progress.emit(f"Could not get outdated packages list (pip list --outdated). Will check each individually. Error: {result.stderr}")


            for package in required_packages:
                if self.cancel_requested: break
                package_lower = package.lower()
                should_update = False
                current_version_str = "N/A"

                if package_lower in outdated_dict:
                    current_version_str = current_version_from_outdated_list_dict.get(package_lower, "N/A")
                    latest_version = outdated_dict[package_lower]
                    self.signals.progress.emit(f"Updating {package} from {current_version_str} to {latest_version}...")
                    should_update = True
                else:
                    current_version = self._get_package_version(package)
                    if current_version:
                        self.signals.progress.emit(f"{package} is already installed ({current_version}). Assuming latest or checking individually if list failed.")
                        # If outdated_dict is empty (e.g. pip list --outdated failed), we might still want to try an update
                        if not outdated_dict: # If the main list failed, try to update anyway
                             self.signals.progress.emit(f"Attempting to update {package} as outdated check was inconclusive...")
                             should_update = True
                        else: # outdated_dict is populated, and this package is not in it
                             already_latest_count +=1 # Count as already latest based on pip list --outdated
                    else: # Not installed
                        self.signals.progress.emit(f"Installing {package}...")
                        should_update = True # Treat as an update/install

                if should_update:
                    pip_command = ['install', '--upgrade', package] if package_lower in outdated_dict or (not outdated_dict and self._get_package_version(package)) else ['install', package]
                    update_result = subprocess.run(
                        [sys.executable, '-m', 'pip'] + pip_command,
                        capture_output=True, text=True, check=False
                    )
                    if self.cancel_requested: break
                    if update_result.returncode == 0:
                        new_version = self._get_package_version(package)
                        self.signals.progress.emit(f"Successfully {'updated' if package_lower in outdated_dict else 'installed'} {package} to {new_version or 'latest'}")
                        updated_count += 1
                    else:
                        self.signals.progress.emit(f"Error {'updating' if package_lower in outdated_dict else 'installing'} {package}: {update_result.stderr}")
            
            if self.cancel_requested:
                self.signals.progress.emit("Package update cancelled by user.")
                self.signals.finished.emit(updated_count)
                return

            self.signals.progress.emit("\nFinal package versions:")
            for package in required_packages:
                if self.cancel_requested: break
                version = self._get_package_version(package)
                self.signals.progress.emit(f"{package}: {version or 'Not Installed'}")

            summary_msg = f"\nSummary: {updated_count} packages processed for update/install."
            if already_latest_count > 0 and outdated_dict : # Only count if pip list --outdated worked
                 summary_msg += f" {already_latest_count} packages were already at the latest version."
            self.signals.progress.emit(summary_msg)
            self.signals.finished.emit(updated_count)

        except Exception as e:
            self.signals.error.emit(f"Update thread error: {str(e)}")

    def _get_package_version(self, package_name: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'show', package_name],
                capture_output=True, text=True, check=False
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
            return None
        except (subprocess.SubprocessError, OSError):
            # Handle subprocess and OS errors gracefully
            return None

class ScraperThread(threading.Thread):
    def __init__(self, url: str, config: ScraperConfig) -> None:
        super().__init__()
        self.url: str = url
        self.config: ScraperConfig = config
        self.signals: WorkerSignals = WorkerSignals()
        self.cancel_requested: bool = False

    def request_cancel(self) -> None:
        self.cancel_requested = True

    def handle_scraper_progress(self, progress_data: Any) -> None:
        if self.cancel_requested:
            # To effectively stop, the main scrape_images loop needs to check a flag or this needs to raise
            # For now, just emit progress and let the main loop in scrape_images handle actual stoppage if it can
            progress_data['cancelled'] = True # Add a cancel flag to the data
        self.signals.progress.emit(progress_data)
        if self.cancel_requested:
             raise OperationCancelledError("Scraping cancelled by user from callback.")


    def run(self) -> None:
        try:
            result = scrape_images(
                url=self.url,
                config_input=self.config,
                verbose=False,
                progress_callback=self.handle_scraper_progress
            )
            if not self.cancel_requested:
                self.signals.finished.emit(result)
            else: # If cancelled, finished signal might have been emitted by handle_scraper_progress or here
                self.signals.progress.emit({'type': PROG_MESSAGE, 'value': "Scraping operation was cancelled."})
                self.signals.finished.emit(0) # Indicate 0 images if cancelled
        except OperationCancelledError:
            self.signals.progress.emit({'type': PROG_MESSAGE, 'value': "Scraping cancelled."})
            self.signals.finished.emit(0)
        except Exception as e:
            self.signals.error.emit(str(e))

class OperationCancelledError(Exception):
    """Custom exception for cancelled operations."""
    pass

class ImageScraperApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__() 
        self.settings = {} # For GUI specific persistent settings like last_save_dir
        self.scraper_config = ScraperConfig.load() # Load default scraper config
        # One could also load from a specific path, e.g., os.join(appdirs.user_config_dir("ImageScraper"), "scraper_config.json")
        # And save it if the user modifies settings via a potential future UI for config.
        self.initUI()      

    def initUI(self) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title_label = QLabel(WINDOW_TITLE)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont(FONT_ARIAL, TITLE_FONT_SIZE, QFont.Bold))
        title_label.setStyleSheet(f"color: {COLOR_DARK_BLUE}; margin-bottom: 8px;")
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(APP_DESCRIPTION)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setFont(QFont(FONT_ARIAL, HEADING_FONT_SIZE))
        desc_label.setStyleSheet(f"color: {COLOR_GRAY}; margin-bottom: 15px;")
        main_layout.addWidget(desc_label)

        # URL Input Group
        url_group = QGroupBox("Website URL")
        url_group.setFont(QFont(FONT_ARIAL, NORMAL_FONT_SIZE))
        url_layout = QVBoxLayout()
        url_layout.setSpacing(5)

        url_examples_label = QLabel("Example URLs:")
        url_examples_label.setFont(QFont(FONT_ARIAL, SMALL_FONT_SIZE))
        url_layout.addWidget(url_examples_label)

        self.url_examples = QComboBox()
        self.url_examples.setFont(QFont(FONT_ARIAL, NORMAL_FONT_SIZE))
        self.url_examples.addItem("Select an example...")
        self.url_examples.addItem("Artsy: https://www.artsy.net/artwork/ed-ruscha-history-kids-236")
        self.url_examples.addItem("Artsy: https://www.artsy.net/artwork/shepard-fairey-shepard-fairey-screenprint-opt-art-green-gradient-street-contemporary-art-obey-giant")
        self.url_examples.addItem("Artsy: https://www.artsy.net/artwork/frank-stella-homage-unique-signed-paper-collage-warmly-inscribed-to-european-curator")
        self.url_examples.currentIndexChanged.connect(self.on_example_selected)
        url_layout.addWidget(self.url_examples)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(URL_INPUT_PLACEHOLDER)
        self.url_input.setFont(QFont(FONT_ARIAL, NORMAL_FONT_SIZE))
        self.url_input.setStyleSheet("QLineEdit {padding: 10px; border: 1px solid #BDC3C7; border-radius: 4px;} QLineEdit:focus {border: 1px solid #3498DB;}")
        self.url_input.textChanged.connect(self.validate_url_input_live) # Live validation
        url_layout.addWidget(self.url_input)

        self.url_warning_label = QLabel(URL_WARNING_MESSAGE)
        self.url_warning_label.setStyleSheet(f"color: {COLOR_RED}; font-size: {SMALL_FONT_SIZE}px; margin-left: 4px;")
        self.url_warning_label.setVisible(False)
        url_layout.addWidget(self.url_warning_label)
        
        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)

        # Save Directory Group
        save_group = QGroupBox("Save Location")
        save_group.setFont(QFont(FONT_ARIAL, 10))
        save_layout = QHBoxLayout()
        
        self.save_dir_input = QLineEdit()
        self.save_dir_input.setPlaceholderText(SAVE_DIR_PLACEHOLDER)
        self.save_dir_input.setFont(QFont(FONT_ARIAL, 10))
        self.save_dir_input.setStyleSheet("QLineEdit {padding: 10px; border: 1px solid #BDC3C7; border-radius: 4px;}")
        save_layout.addWidget(self.save_dir_input)

        self.browse_button = QPushButton('Browse')
        self.browse_button.setFont(QFont(FONT_ARIAL, 10, QFont.Bold))
        self.browse_button.setStyleSheet("QPushButton {padding: 10px 15px; background-color: #ECF0F1; border: none; border-radius: 4px;} QPushButton:hover {background-color: #D0D3D4;}")
        self.browse_button.clicked.connect(self.browse_directory)
        save_layout.addWidget(self.browse_button)
        save_group.setLayout(save_layout)
        main_layout.addWidget(save_group)

        # Tab Widget for Logs and History
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(QFont(FONT_ARIAL, 10))

        # Log Tab
        log_tab = QWidget()
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont('Courier New', 9))
        log_layout.addWidget(self.log_output)
        log_tab.setLayout(log_layout)
        self.tab_widget.addTab(log_tab, "Logs")

        # History Tab
        history_tab = QWidget()
        history_layout = QVBoxLayout()
        self.history_list = QListWidget()
        self.history_list.setFont(QFont(FONT_ARIAL, 10))
        self.history_list.itemDoubleClicked.connect(self.reuse_selected_url)
        history_layout.addWidget(self.history_list)
        
        history_buttons_layout = QHBoxLayout()
        self.reuse_button = QPushButton("Reuse Selected URL")
        self.reuse_button.setFont(QFont(FONT_ARIAL, 10))
        self.reuse_button.clicked.connect(self.reuse_selected_url)
        history_buttons_layout.addWidget(self.reuse_button)
        
        self.clear_history_button = QPushButton("Clear History")
        self.clear_history_button.setFont(QFont(FONT_ARIAL, 10))
        self.clear_history_button.setStyleSheet("QPushButton {color: #E74C3C;}")
        self.clear_history_button.clicked.connect(self.clear_history)
        history_buttons_layout.addWidget(self.clear_history_button)
        history_layout.addLayout(history_buttons_layout)
        
        history_tab.setLayout(history_layout)
        self.tab_widget.addTab(history_tab, "History")
        
        main_layout.addWidget(self.tab_widget) # Add tab widget to main layout

        # Status Label and Progress Bar
        status_layout = QHBoxLayout()
        self.status_label = QLabel('Ready')
        self.status_label.setFont(QFont(FONT_ARIAL, 10))
        status_layout.addWidget(self.status_label, 1) # Give it more space

        self.progress_bar = QProgressBar()
        self.progress_bar.setFont(QFont(FONT_ARIAL, 9))
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0,100) # Default to percentage
        status_layout.addWidget(self.progress_bar)
        main_layout.addLayout(status_layout)

        # Buttons Layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.start_button = QPushButton(BTN_START_SCRAPING)
        self.start_button.setFont(QFont(FONT_ARIAL, 11, QFont.Bold))
        self.start_button.setStyleSheet("QPushButton {padding: 12px; background-color: #2ECC71; color: white; border: none; border-radius: 4px;} QPushButton:hover {background-color: #27AE60;} QPushButton:disabled {background-color: #95A5A6;}")
        self.start_button.clicked.connect(self.start_scraping)
        buttons_layout.addWidget(self.start_button)

        self.update_button = QPushButton(BTN_CHECK_UPDATE_PACKAGES)
        self.update_button.setFont(QFont(FONT_ARIAL, 10))
        self.update_button.setStyleSheet("QPushButton {padding: 10px; background-color: #3498DB; color: white; border: none; border-radius: 4px;} QPushButton:hover {background-color: #2980B9;} QPushButton:disabled {background-color: #95A5A6;}")
        self.update_button.clicked.connect(self.update_packages)
        buttons_layout.addWidget(self.update_button)
        
        self.cancel_button = QPushButton(BTN_CANCEL)
        self.cancel_button.setFont(QFont(FONT_ARIAL, 10))
        self.cancel_button.setStyleSheet("QPushButton {padding: 10px; background-color: #E74C3C; color: white; border: none; border-radius: 4px;} QPushButton:hover {background-color: #C0392B;} QPushButton:disabled {background-color: #95A5A6;}")
        self.cancel_button.clicked.connect(self.cancel_operation)
        buttons_layout.addWidget(self.cancel_button)

        # Utility buttons
        utility_buttons_layout = QHBoxLayout()
        self.clear_fields_button = QPushButton("Clear Inputs")
        self.clear_fields_button.setFont(QFont(FONT_ARIAL, 10))
        self.clear_fields_button.clicked.connect(self.clear_fields)
        utility_buttons_layout.addWidget(self.clear_fields_button)

        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.setFont(QFont(FONT_ARIAL, 10))
        self.open_folder_button.clicked.connect(self.open_output_folder)
        utility_buttons_layout.addWidget(self.open_folder_button)
        
        # Add button layouts to main_layout
        main_layout.addLayout(buttons_layout)
        main_layout.addLayout(utility_buttons_layout)

        # Create a central widget and set the main layout
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Load settings and history
        self.load_settings() 
        self.load_history()

        # Initialize UI elements that depend on settings
        last_save_dir = self.settings.get("last_save_dir")
        if last_save_dir and os.path.isdir(last_save_dir):
            self.save_dir_input.setText(last_save_dir)
        else:
            # Fallback to a 'Scraped_Images' directory in the app's user data directory
            default_dir_base = appdirs.user_data_dir("ImageScraper", "ImageScraperApp")
            # Ensure the base directory itself exists before creating a subdirectory
            os.makedirs(default_dir_base, exist_ok=True) 
            default_dir = os.path.join(default_dir_base, 'Scraped_Images')
            os.makedirs(default_dir, exist_ok=True) # Ensure the Scraped_Images directory also exists
            self.save_dir_input.setText(default_dir)

        self.validate_url_input_live() # Initial validation based on current (possibly empty) text
        
        # Set initial status
        self.status_label.setText(STATUS_READY)
        self.progress_bar.setVisible(False)
        self.cancel_button.setEnabled(False)
        self.active_operation = None
        self.scraper_thread = None # Initialize scraper_thread attribute
        self.update_thread = None  # Initialize update_thread attribute

    def validate_url_input_live(self) -> None:
        """Validates URL input live as user types."""
        url = self.url_input.text().strip()
        is_valid = self.is_valid_url(url)
        self.url_warning_label.setVisible(not is_valid and bool(url)) # Show warning only if text exists and is invalid
        self.start_button.setEnabled(is_valid)

    def save_settings(self) -> None:
        try:
            config_dir = appdirs.user_config_dir("ImageScraper", "ImageScraperApp")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "settings.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4) # Added indent for readability
        except Exception as e:
            self.add_log_message(f"Error saving settings: {e}")

    def load_settings(self) -> None:
        self.settings = {} # Initialize to empty dict first
        try:
            config_dir = appdirs.user_config_dir("ImageScraper", "ImageScraperApp")
            config_path = os.path.join(config_dir, "settings.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    loaded_settings = json.load(f)
                    if isinstance(loaded_settings, dict): # Ensure it's a dict
                        self.settings = loaded_settings
                    else:
                        self.add_log_message("Warning: Settings file was not a valid format. Using defaults.")
            # else: # No settings file exists, self.settings remains {}
            #    self.add_log_message("No settings file found. Using default settings.")
        except json.JSONDecodeError:
            self.add_log_message("Error: Could not decode settings.json. Using default settings.")
        except Exception as e:
            self.add_log_message(f"Error loading settings: {e}. Using default settings.")

    def is_valid_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc) and '.' in parsed.netloc
        except Exception:
            return False

    def on_example_selected(self, index: int) -> None:
        if index > 0:
            example_text = self.url_examples.currentText()
            url_part = example_text.split("Artsy: ", 1)[1] if "Artsy: " in example_text else example_text
            self.url_input.setText(url_part.strip())
            self.validate_url_input_live() # Validate after setting example

    def browse_directory(self) -> None:
        """Open file dialog to select save directory and update settings."""
        current_dir = self.save_dir_input.text()
        if not os.path.isdir(current_dir): # If current text is not a dir, start from home
            current_dir = os.path.expanduser("~")

        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory", current_dir)
        if directory:
            self.save_dir_input.setText(directory)
            self.settings["last_save_dir"] = directory
            self.save_settings()

    def clear_fields(self) -> None:
        """Clear URL input and reset UI to initial state."""
        self.url_input.clear()
        self.status_label.setText(STATUS_READY)
        self.url_examples.setCurrentIndex(0)
        self.validate_url_input_live()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

    def open_output_folder(self) -> None:
        """Open the selected output folder in system file explorer."""
        path = self.save_dir_input.text().strip()
        if not path:
            QMessageBox.information(self, "No Folder Specified", "Please select a save directory first.")
            return

        # Security: Validate and normalize the path
        try:
            path = os.path.abspath(os.path.normpath(path))
        except Exception as e:
            QMessageBox.warning(self, "Invalid Path", f"Invalid folder path: {e}")
            return

        # Security: Verify path exists and is actually a directory
        if not os.path.exists(path):
            QMessageBox.warning(self, "Folder Not Found", f"The folder does not exist:\n{path}")
            return

        if not os.path.isdir(path):
            QMessageBox.warning(self, "Not a Directory", f"The path is not a directory:\n{path}")
            return

        # Security: On Windows, verify path doesn't contain special characters that could be exploited
        if sys.platform == PLATFORM_WINDOWS and any(char in path for char in WINDOWS_INVALID_PATH_CHARS):
            QMessageBox.warning(self, "Invalid Path", "Path contains invalid characters.")
            return

        try:
            if sys.platform == PLATFORM_WINDOWS:
                # Use os.startfile which is safer on Windows
                os.startfile(path)
            elif sys.platform == PLATFORM_MACOS:
                # macOS: Use list form to prevent shell injection
                subprocess.run(['open', path], check=True, timeout=FILE_OPEN_TIMEOUT_SECONDS)
            else:
                # Linux: Use list form to prevent shell injection
                subprocess.run(['xdg-open', path], check=True, timeout=FILE_OPEN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "Timeout", "Opening folder timed out.")
        except Exception as e:
            QMessageBox.warning(self, "Error Opening Folder", f"Could not open folder: {e}")
        
    def add_log_message(self, message: str, timestamp: bool = True) -> None:
        now = datetime.now().strftime("%H:%M:%S") if timestamp else ""
        prefix = f"[{now}] " if timestamp else ""
        self.log_output.append(f"{prefix}{message}")
        self.log_output.moveCursor(QTextCursor.End)

    def add_to_history(self, url: str, count: int) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item_text = f"{timestamp} - {url} ({count} images)"
        self.history_list.insertItem(0, item_text)
        self.save_history()

    def _get_history_file_path(self) -> str:
        app_name = "ImageScraper"
        data_dir = appdirs.user_data_dir(app_name)
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'scraper_history.json')

    def save_history(self) -> None:
        history_file = self._get_history_file_path()
        history_data = []
        for i in range(self.history_list.count()):
            history_data.append(self.history_list.item(i).text())
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=4)
        except Exception as e:
            self.add_log_message(f"Error saving history: {str(e)}")

    def load_history(self) -> None:
        history_file = self._get_history_file_path()
        try:
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                    if isinstance(history_data, list):
                        self.history_list.clear() # Clear before loading
                        for item_text in history_data:
                            if isinstance(item_text, str): # Basic validation
                                self.history_list.addItem(item_text)
                    else:
                        self.add_log_message("History file is not in the correct list format.")
        except json.JSONDecodeError:
            self.add_log_message(f"Error decoding history file: {history_file}. It might be corrupted.")
        except Exception as e:
            self.add_log_message(f"Error loading history: {str(e)}")

    def clear_history(self) -> None:
        confirm = QMessageBox.question(
            self, "Clear History", "Are you sure you want to clear the entire history?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No # Default to No
        )
        if confirm == QMessageBox.Yes:
            self.history_list.clear()
            self.save_history() # This will save an empty list
            self.add_log_message("History cleared.")

    def reuse_selected_url(self) -> None:
        selected_items = self.history_list.selectedItems()
        if selected_items:
            item_text = selected_items[0].text()
            match = re.search(r' - (https?://[^\s]+) \(.*', item_text) # Regex to find URL
            if match:
                url = match.group(1)
                self.url_input.setText(url)
                self.tab_widget.setCurrentIndex(0) 
                self.url_input.setFocus()
                self.validate_url_input_live()
            else:
                self.add_log_message("Could not parse URL from selected history item.")
    
    def update_packages(self) -> None:
        """Check for and update required Python packages in background thread."""
        self.progress_bar.setRange(0,0) # Indeterminate for package updates
        self.progress_bar.setVisible(True)
        self.status_label.setText('Checking/Updating packages...')
        self.update_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.log_output.clear()
        self.add_log_message("Starting package update process...")
        self.active_operation = "updating"
        self.tab_widget.setCurrentIndex(0)

        self.update_thread = UpdatePackagesThread()
        self.update_thread.signals.progress.connect(self.update_ui_progress)
        self.update_thread.signals.finished.connect(self.update_finished)
        self.update_thread.signals.error.connect(self.operation_error)
        self.update_thread.daemon = True
        self.update_thread.start()
        
    def update_ui_progress(self, progress_update: Any) -> None:
        if isinstance(progress_update, dict):
            prog_type = progress_update.get(PROG_TYPE)
            prog_value = progress_update.get(PROG_VALUE)

            if prog_type == PROG_PERCENTAGE:
                # Progress bar range is already set to 0-100 in start_scraping
                self.progress_bar.setValue(int(prog_value))
                self.status_label.setText(f"Scraping: {int(prog_value)}%")
            elif prog_type == PROG_MESSAGE:
                self.status_label.setText(str(prog_value)[:STATUS_TEXT_MAX_LENGTH])
                self.add_log_message(str(prog_value))
            else:
                self.add_log_message(f"Unknown progress data: {str(progress_update)}")
        elif isinstance(progress_update, str):
            # Handle string progress updates (used by package update thread)
            self.add_log_message(progress_update)
            self.status_label.setText(progress_update[:STATUS_TEXT_MAX_LENGTH])
        else:
            self.add_log_message(f"Unknown progress type: {str(progress_update)}")
        
    def operation_common_finish_ui(self) -> None:
        self.start_button.setEnabled(True)
        self.update_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0) # Reset progress bar
        self.active_operation = None

    def update_finished(self, count: int) -> None:
        final_message = f'Package check complete. {count} packages processed.'
        self.status_label.setText(final_message)
        self.add_log_message(f"\nPackage update process finished! {count} packages were processed for update/install.", timestamp=False)
        self.operation_common_finish_ui()
        QMessageBox.information(self, "Update Complete", final_message)

    def start_scraping(self) -> None:
        """
        Start the image scraping process in a background thread.
        Validates paths and creates scraper thread with progress callbacks.
        """
        url = self.url_input.text().strip()
        save_dir = self.save_dir_input.text().strip()

        if not save_dir:
            QMessageBox.warning(self, "Input Error", "Please select or enter a directory to save images.")
            return

        try:
            # Normalize and resolve the path to prevent traversal attacks
            save_dir = os.path.abspath(os.path.normpath(save_dir))

            # Security: Ensure the resolved path doesn't escape to system directories
            # Get user's home directory as a safe base reference
            user_home = os.path.expanduser("~")

            # Check if path tries to access sensitive system directories
            forbidden_prefixes = []
            if sys.platform == PLATFORM_WINDOWS:
                # Windows: Prevent access to system directories
                forbidden_prefixes = [os.path.abspath(path) for path in WINDOWS_FORBIDDEN_DIRS]
            else:
                # Unix-like: Prevent access to system directories
                forbidden_prefixes = UNIX_FORBIDDEN_DIRS

            # Check if path is trying to access forbidden directories
            for forbidden in forbidden_prefixes:
                if save_dir.lower().startswith(forbidden.lower()):
                    QMessageBox.warning(self, "Security Error",
                                      "Cannot save to system directories.\nPlease choose a location in your user folders.")
                    return

        except Exception as e:
            QMessageBox.critical(self, "Path Error", f"Invalid directory path:\n{e}")
            return

        if not os.path.isdir(save_dir):
            try:
                os.makedirs(save_dir, exist_ok=True)
                self.add_log_message(f"Created save directory: {save_dir}")
            except Exception as e:
                QMessageBox.critical(self, "Directory Error", f"Could not create save directory:\n{save_dir}\nError: {e}")
                return

        self.settings["last_save_dir"] = save_dir
        self.save_settings()

        self.progress_bar.setRange(0,100) # Expecting percentages for scraping
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText('Starting scraping...')
        self.start_button.setEnabled(False)
        self.update_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.log_output.clear() # Clear log for new scrape
        self.add_log_message(f"Starting scraper for URL: {url}")
        self.add_log_message(f"Saving images to: {save_dir}")
        self.active_operation = "scraping"
        self.tab_widget.setCurrentIndex(0)

        thread_config = copy.deepcopy(self.scraper_config)
        thread_config.output_directory = save_dir

        self.scraper_thread = ScraperThread(url, thread_config)
        self.scraper_thread.signals.progress.connect(self.update_ui_progress)
        self.scraper_thread.signals.finished.connect(self.scraping_finished)
        self.scraper_thread.signals.error.connect(self.operation_error)
        self.scraper_thread.daemon = True
        self.scraper_thread.start()
        
    def scraping_finished(self, count: int) -> None:
        final_message = f'Scraping complete! Downloaded {count} images.'
        self.status_label.setText(final_message)
        self.add_log_message(f"\nScraping completed successfully! Total images downloaded: {count}", timestamp=False)
        if count > 0:
            self.add_to_history(self.url_input.text().strip(), count)
        self.operation_common_finish_ui()
        QMessageBox.information(self, "Scraping Complete", f"{final_message}\nSaved to: {self.save_dir_input.text()}")

    def operation_error(self, error_message: str) -> None:
        op_name = self.active_operation if self.active_operation else "Operation"
        self.status_label.setText(f'Error during {op_name}!')
        self.add_log_message(f"\nERROR during {op_name}: {error_message}", timestamp=False)
        self.operation_common_finish_ui()
        QMessageBox.critical(self, f"{op_name.capitalize()} Error", f"An error occurred:\n\n{error_message}")

    def cancel_operation(self) -> None:
        if self.active_operation == "scraping" and self.scraper_thread and self.scraper_thread.is_alive():
            self.scraper_thread.request_cancel()
            self.add_log_message("Cancellation requested for scraping...")
            self.status_label.setText("Cancelling scraping...")
        elif self.active_operation == "updating" and self.update_thread and self.update_thread.is_alive():
            self.update_thread.request_cancel()
            self.add_log_message("Cancellation requested for package update...")
            self.status_label.setText("Cancelling package update...")
        else:
            self.add_log_message("No active cancellable operation running.")
            return # No need to disable cancel button if nothing to cancel

        self.cancel_button.setEnabled(False) # Disable after requesting
        # The thread itself will signal finish/error, which will re-enable buttons

def main() -> None:
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = ImageScraperApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
