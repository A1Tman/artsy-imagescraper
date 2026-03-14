import sys
import os
import threading
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLineEdit, QLabel, QWidget, QFileDialog, 
                            QProgressBar, QMessageBox, QTextEdit, QGroupBox, 
                            QTabWidget, QListWidget, QComboBox)
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtCore import Qt, pyqtSignal, QObject
import json
import re
import copy
from dataclasses import dataclass
from datetime import datetime
import appdirs
from urllib.parse import urlparse
from typing import Any

# Import the unified scraper module
from scraper import scrape_images, OperationCancelledError
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
WINDOW_TITLE = 'Image Scraper'
APP_DESCRIPTION = 'Download and organize images from supported websites'
REQUIREMENTS_LOCKFILE = os.path.join(_MODULE_DIR, "requirements.txt")

# UI Text
URL_INPUT_PLACEHOLDER = 'Enter URL (e.g., https://www.example.com/artwork/title)'
URL_WARNING_MESSAGE = "⚠️ Invalid URL format or missing http(s)://"
SAVE_DIR_PLACEHOLDER = 'Choose a folder to save images'
DEFAULT_SCRAPED_IMAGES_DIR = 'Scraped_Images'
STATUS_READY = 'Ready'

# Button Text
BTN_START_SCRAPING = 'Start Scraping'
BTN_CHECK_ENVIRONMENT = 'Check Environment'
BTN_SYNC_DEPENDENCIES = 'Sync Dependencies'
BTN_CANCEL = 'Cancel'

# Configuration Files
SETTINGS_FILENAME = "settings.json"
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
SUBPROCESS_POLL_TIMEOUT_SECONDS = 1

# Security - System Directories
WINDOWS_FORBIDDEN_DIRS = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)"
]
UNIX_FORBIDDEN_DIRS = ["/bin", "/sbin", "/boot", "/etc", "/sys", "/proc"]
OPERATION_LABELS = {
    "scraping": "Scraping",
    "checking_environment": "Environment check",
    "syncing_dependencies": "Dependency sync",
}


@dataclass(frozen=True)
class EnvironmentStatus:
    total_locked: int
    matching_count: int
    missing: list[tuple[str, str]]
    mismatched: list[tuple[str, str, str]]

    @property
    def is_in_sync(self) -> bool:
        return not self.missing and not self.mismatched


def normalize_package_name(name: str) -> str:
    """Normalize package names to pip's canonical comparison form."""
    return re.sub(r"[-_.]+", "-", name.split("[", 1)[0]).lower()


def parse_locked_requirements(requirements_path: str) -> dict[str, str]:
    """Parse pinned packages from a pip-compile requirements.txt file."""
    locked_requirements: dict[str, str] = {}
    with open(requirements_path, "r", encoding="utf-8") as requirements_file:
        for raw_line in requirements_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "==" not in line:
                continue

            package_name, version = line.split("==", 1)
            locked_requirements[normalize_package_name(package_name)] = version.strip()

    return locked_requirements


def get_installed_packages(python_executable: str = sys.executable) -> dict[str, str]:
    """Return installed packages from the active Python environment."""
    result = subprocess.run(
        [python_executable, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pip list failed")

    try:
        package_list = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Could not parse pip list output") from exc

    return {
        normalize_package_name(package_data["name"]): package_data["version"]
        for package_data in package_list
        if "name" in package_data and "version" in package_data
    }


def build_environment_status(
    locked_requirements: dict[str, str],
    installed_packages: dict[str, str],
) -> EnvironmentStatus:
    """Compare the locked requirements against installed packages."""
    missing: list[tuple[str, str]] = []
    mismatched: list[tuple[str, str, str]] = []
    matching_count = 0

    for package_name, expected_version in sorted(locked_requirements.items()):
        installed_version = installed_packages.get(package_name)
        if installed_version is None:
            missing.append((package_name, expected_version))
        elif installed_version != expected_version:
            mismatched.append((package_name, expected_version, installed_version))
        else:
            matching_count += 1

    return EnvironmentStatus(
        total_locked=len(locked_requirements),
        matching_count=matching_count,
        missing=missing,
        mismatched=mismatched,
    )


def collect_environment_status(
    requirements_path: str = REQUIREMENTS_LOCKFILE,
    python_executable: str = sys.executable,
) -> EnvironmentStatus:
    """Inspect the current environment against the pinned requirements."""
    locked_requirements = parse_locked_requirements(requirements_path)
    installed_packages = get_installed_packages(python_executable)
    return build_environment_status(locked_requirements, installed_packages)


def format_environment_status_lines(status: EnvironmentStatus) -> list[str]:
    """Format an environment status report for display in the GUI log."""
    if status.is_in_sync:
        return [
            (
                "Environment matches requirements.txt "
                f"({status.matching_count}/{status.total_locked} locked packages matched)."
            )
        ]

    lines = [
        (
            "Environment drift detected: "
            f"{len(status.missing)} missing, {len(status.mismatched)} mismatched."
        )
    ]
    lines.extend(
        f"Missing: {package_name}=={expected_version}"
        for package_name, expected_version in status.missing
    )
    lines.extend(
        f"Mismatched: {package_name} expected {expected_version}, installed {installed_version}"
        for package_name, expected_version, installed_version in status.mismatched
    )
    return lines

def is_same_or_child_path(path: str, parent_path: str) -> bool:
    """Return True when path is the same as parent_path or contained within it."""
    normalized_path = os.path.normcase(os.path.abspath(path))
    normalized_parent = os.path.normcase(os.path.abspath(parent_path))
    try:
        return os.path.commonpath([normalized_path, normalized_parent]) == normalized_parent
    except ValueError:
        return False

class WorkerSignals(QObject):
    """
    Defines the signals available from the worker thread.
    """
    finished = pyqtSignal(int)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)
    cancelled = pyqtSignal(str)


class EnvironmentSignals(QObject):
    """Signals used by environment check and sync operations."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)
    cancelled = pyqtSignal(str)

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
            else:
                self.signals.cancelled.emit("Scraping cancelled.")
        except OperationCancelledError:
            self.signals.cancelled.emit("Scraping cancelled.")
        except Exception as e:
            self.signals.error.emit(str(e))


class EnvironmentCheckThread(threading.Thread):
    """Check whether the current environment matches requirements.txt."""

    def __init__(
        self,
        requirements_path: str = REQUIREMENTS_LOCKFILE,
        python_executable: str = sys.executable,
    ) -> None:
        super().__init__()
        self.requirements_path = requirements_path
        self.python_executable = python_executable
        self.signals = EnvironmentSignals()

    def run(self) -> None:
        try:
            self.signals.progress.emit("Checking installed packages against requirements.txt...")
            status = collect_environment_status(self.requirements_path, self.python_executable)
            self.signals.finished.emit(status)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class DependencySyncThread(threading.Thread):
    """Install the exact dependency set pinned in requirements.txt."""

    def __init__(
        self,
        requirements_path: str = REQUIREMENTS_LOCKFILE,
        python_executable: str = sys.executable,
    ) -> None:
        super().__init__()
        self.requirements_path = requirements_path
        self.python_executable = python_executable
        self.signals = EnvironmentSignals()
        self.cancel_requested = False
        self.process: subprocess.Popen[str] | None = None

    def request_cancel(self) -> None:
        self.cancel_requested = True
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def run(self) -> None:
        command = [self.python_executable, "-m", "pip", "install", "-r", self.requirements_path]
        try:
            self.signals.progress.emit("Syncing installed packages to requirements.txt...")
            self.signals.progress.emit(f"Running: {' '.join(command)}")
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            if self.process.stdout is not None:
                for line in self.process.stdout:
                    if self.cancel_requested:
                        break
                    message = line.strip()
                    if message:
                        self.signals.progress.emit(message)

            return_code = self.process.wait(timeout=SUBPROCESS_POLL_TIMEOUT_SECONDS)

            if self.cancel_requested:
                self.signals.cancelled.emit("Dependency sync cancelled.")
                return

            if return_code != 0:
                self.signals.error.emit(
                    f"Dependency sync failed with exit code {return_code}."
                )
                return

            status = collect_environment_status(self.requirements_path, self.python_executable)
            self.signals.finished.emit(status)
        except subprocess.TimeoutExpired:
            if self.process and self.process.poll() is None:
                self.process.kill()
            self.signals.cancelled.emit("Dependency sync cancelled.")
        except Exception as exc:
            self.signals.error.emit(str(exc))

class ImageScraperApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__() 
        self.settings = {} # For GUI specific persistent settings like last_save_dir
        self.scraper_config = ScraperConfig.load() # Load default scraper config
        # One could also load from a specific path, e.g., os.join(appdirs.user_config_dir("ImageScraper"), "scraper_config.json")
        # And save it if the user modifies settings via a potential future UI for config.
        self.environment_check_thread = None
        self.dependency_sync_thread = None
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

        self.check_environment_button = QPushButton(BTN_CHECK_ENVIRONMENT)
        self.check_environment_button.setFont(QFont(FONT_ARIAL, 10))
        self.check_environment_button.setStyleSheet("QPushButton {padding: 10px; background-color: #3498DB; color: white; border: none; border-radius: 4px;} QPushButton:hover {background-color: #2980B9;} QPushButton:disabled {background-color: #95A5A6;}")
        self.check_environment_button.clicked.connect(self.check_environment)
        buttons_layout.addWidget(self.check_environment_button)

        self.sync_dependencies_button = QPushButton(BTN_SYNC_DEPENDENCIES)
        self.sync_dependencies_button.setFont(QFont(FONT_ARIAL, 10))
        self.sync_dependencies_button.setStyleSheet("QPushButton {padding: 10px; background-color: #7F8C8D; color: white; border: none; border-radius: 4px;} QPushButton:hover {background-color: #5D6D7E;} QPushButton:disabled {background-color: #95A5A6;}")
        self.sync_dependencies_button.clicked.connect(self.sync_dependencies)
        buttons_layout.addWidget(self.sync_dependencies_button)

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
            default_dir_base = appdirs.user_data_dir(APP_NAME, "ImageScraperApp")
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

    def validate_url_input_live(self) -> None:
        """Validates URL input live as user types."""
        url = self.url_input.text().strip()
        is_valid = self.is_valid_url(url)
        self.url_warning_label.setVisible(not is_valid and bool(url)) # Show warning only if text exists and is invalid
        self.start_button.setEnabled(is_valid and self.active_operation is None)

    def save_settings(self) -> None:
        try:
            config_dir = appdirs.user_config_dir(APP_NAME, "ImageScraperApp")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, SETTINGS_FILENAME)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4) # Added indent for readability
        except Exception as e:
            self.add_log_message(f"Error saving settings: {e}")

    def load_settings(self) -> None:
        self.settings = {} # Initialize to empty dict first
        try:
            config_dir = appdirs.user_config_dir(APP_NAME, "ImageScraperApp")
            config_path = os.path.join(config_dir, SETTINGS_FILENAME)
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
            return parsed.scheme in VALID_URL_SCHEMES and bool(parsed.netloc) and '.' in parsed.netloc
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
        now = datetime.now().strftime(LOG_TIME_FORMAT) if timestamp else ""
        prefix = f"[{now}] " if timestamp else ""
        self.log_output.append(f"{prefix}{message}")
        self.log_output.moveCursor(QTextCursor.End)

    def add_to_history(self, url: str, count: int) -> None:
        timestamp = datetime.now().strftime(HISTORY_TIMESTAMP_FORMAT)
        item_text = HISTORY_ITEM_FORMAT.format(timestamp=timestamp, url=url, count=count)
        self.history_list.insertItem(0, item_text)
        self.save_history()

    def _get_history_file_path(self) -> str:
        data_dir = appdirs.user_data_dir(APP_NAME)
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, HISTORY_FILENAME)

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
            match = re.search(HISTORY_URL_PATTERN, item_text)
            if match:
                url = match.group(1)
                self.url_input.setText(url)
                self.tab_widget.setCurrentIndex(0) 
                self.url_input.setFocus()
                self.validate_url_input_live()
            else:
                self.add_log_message("Could not parse URL from selected history item.")

    def get_active_operation_label(self) -> str:
        return OPERATION_LABELS.get(self.active_operation, "Operation")
    
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
            self.status_label.setText(progress_update[:STATUS_TEXT_MAX_LENGTH])
            self.add_log_message(progress_update)
        else:
            self.add_log_message(f"Unknown progress type: {str(progress_update)}")

    def set_action_buttons_enabled(self, busy: bool, allow_cancel: bool = False) -> None:
        self.start_button.setEnabled(False if busy else self.is_valid_url(self.url_input.text().strip()))
        self.check_environment_button.setEnabled(not busy)
        self.sync_dependencies_button.setEnabled(not busy)
        self.cancel_button.setEnabled(False)
        if busy and allow_cancel:
            self.cancel_button.setEnabled(True)

    def operation_common_finish_ui(self) -> None:
        self.active_operation = None
        self.validate_url_input_live()  # Re-enables start button only if URL is valid
        self.check_environment_button.setEnabled(True)
        self.sync_dependencies_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0) # Reset progress bar
        self.cancel_button.setEnabled(False)

    def check_environment(self) -> None:
        if not os.path.exists(REQUIREMENTS_LOCKFILE):
            QMessageBox.critical(self, "Missing Lockfile", f"Could not find:\n{REQUIREMENTS_LOCKFILE}")
            return

        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Checking environment...")
        self.set_action_buttons_enabled(busy=True)
        self.active_operation = "checking_environment"
        self.tab_widget.setCurrentIndex(0)
        self.add_log_message("Checking environment against requirements.txt...")

        self.environment_check_thread = EnvironmentCheckThread(REQUIREMENTS_LOCKFILE)
        self.environment_check_thread.signals.progress.connect(self.update_ui_progress)
        self.environment_check_thread.signals.finished.connect(self.environment_check_finished)
        self.environment_check_thread.signals.error.connect(self.operation_error)
        self.environment_check_thread.daemon = True
        self.environment_check_thread.start()

    def environment_check_finished(self, status: EnvironmentStatus) -> None:
        for line in format_environment_status_lines(status):
            self.add_log_message(line)

        if status.is_in_sync:
            final_message = (
                f"Environment matches requirements.txt "
                f"({status.matching_count}/{status.total_locked} locked packages)."
            )
            self.status_label.setText(final_message)
            self.operation_common_finish_ui()
            QMessageBox.information(self, "Environment Check", final_message)
            return

        final_message = (
            "Environment drift detected. "
            f"{len(status.missing)} missing, {len(status.mismatched)} mismatched."
        )
        self.status_label.setText(final_message)
        self.operation_common_finish_ui()
        QMessageBox.warning(
            self,
            "Environment Check",
            f"{final_message}\nSee the Logs tab for package details.",
        )

    def sync_dependencies(self) -> None:
        if not os.path.exists(REQUIREMENTS_LOCKFILE):
            QMessageBox.critical(self, "Missing Lockfile", f"Could not find:\n{REQUIREMENTS_LOCKFILE}")
            return

        should_continue = QMessageBox.question(
            self,
            "Sync Dependencies",
            (
                "This will run `python -m pip install -r requirements.txt` "
                "for the current Python environment.\n\n"
                "Restart the app after completion to use any updated packages.\n\n"
                "Continue?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if should_continue != QMessageBox.Yes:
            return

        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Syncing dependencies...")
        self.set_action_buttons_enabled(busy=True, allow_cancel=True)
        self.active_operation = "syncing_dependencies"
        self.tab_widget.setCurrentIndex(0)
        self.log_output.clear()
        self.add_log_message("Starting dependency sync from requirements.txt...")
        self.add_log_message("Restart the app after the sync finishes.")

        self.dependency_sync_thread = DependencySyncThread(REQUIREMENTS_LOCKFILE)
        self.dependency_sync_thread.signals.progress.connect(self.update_ui_progress)
        self.dependency_sync_thread.signals.finished.connect(self.dependency_sync_finished)
        self.dependency_sync_thread.signals.cancelled.connect(self.dependency_sync_cancelled)
        self.dependency_sync_thread.signals.error.connect(self.operation_error)
        self.dependency_sync_thread.daemon = True
        self.dependency_sync_thread.start()

    def dependency_sync_finished(self, status: EnvironmentStatus) -> None:
        for line in format_environment_status_lines(status):
            self.add_log_message(line)

        if status.is_in_sync:
            final_message = "Dependency sync complete. Restart the app to use any updated packages."
            self.status_label.setText("Dependency sync complete.")
            self.operation_common_finish_ui()
            QMessageBox.information(self, "Dependency Sync", final_message)
            return

        final_message = (
            "Dependency sync completed, but the environment still differs from requirements.txt."
        )
        self.status_label.setText(final_message)
        self.operation_common_finish_ui()
        QMessageBox.warning(
            self,
            "Dependency Sync",
            f"{final_message}\nSee the Logs tab for package details.",
        )

    def dependency_sync_cancelled(self, message: str) -> None:
        self.status_label.setText(message)
        self.add_log_message(message)
        self.operation_common_finish_ui()

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

            # Check if path tries to access sensitive system directories
            forbidden_prefixes = []
            if sys.platform == PLATFORM_WINDOWS:
                # Windows: Prevent access to system directories.
                # Use env vars so the check works regardless of drive letter or locale.
                forbidden_prefixes = [
                    os.path.abspath(os.environ.get('SystemRoot', WINDOWS_FORBIDDEN_DIRS[0])),
                    os.path.abspath(os.environ.get('ProgramFiles', WINDOWS_FORBIDDEN_DIRS[1])),
                    os.path.abspath(os.environ.get('ProgramFiles(x86)', WINDOWS_FORBIDDEN_DIRS[2])),
                ]
            else:
                # Unix-like: Prevent access to system directories
                forbidden_prefixes = UNIX_FORBIDDEN_DIRS

            # Check if path is trying to access forbidden directories
            for forbidden in forbidden_prefixes:
                if is_same_or_child_path(save_dir, forbidden):
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
        self.set_action_buttons_enabled(busy=True, allow_cancel=True)
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
        self.scraper_thread.signals.cancelled.connect(self.scraping_cancelled)
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

    def scraping_cancelled(self, message: str) -> None:
        self.status_label.setText(message)
        self.add_log_message(f"\n{message}", timestamp=False)
        self.operation_common_finish_ui()

    def operation_error(self, error_message: str) -> None:
        op_name = self.get_active_operation_label()
        self.status_label.setText(f'Error during {op_name}!')
        self.add_log_message(f"\nERROR during {op_name}: {error_message}", timestamp=False)
        self.operation_common_finish_ui()
        QMessageBox.critical(self, f"{op_name} Error", f"An error occurred:\n\n{error_message}")

    def cancel_operation(self) -> None:
        if self.active_operation == "scraping" and self.scraper_thread and self.scraper_thread.is_alive():
            self.scraper_thread.request_cancel()
            self.add_log_message("Cancellation requested for scraping...")
            self.status_label.setText("Cancelling scraping...")
        elif (
            self.active_operation == "syncing_dependencies"
            and self.dependency_sync_thread
            and self.dependency_sync_thread.is_alive()
        ):
            self.dependency_sync_thread.request_cancel()
            self.add_log_message("Cancellation requested for dependency sync...")
            self.status_label.setText("Cancelling dependency sync...")
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
