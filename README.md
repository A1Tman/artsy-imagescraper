# Artsy Image Scraper

A powerful, user-friendly tool for scraping and organizing artwork images from various websites.

## Features

- **Universal Scraping**: Download images from Artsy.net and other art websites
- **User-friendly Interface**: Simple GUI for easy image downloading
- **Automatic Organization**: Images are sorted by artist and artwork name
- **Configurable Settings**: Customize behavior for different websites
- **History Tracking**: Keep track of previously scraped URLs
- **Resource Management**: Proper handling of browser sessions

## Installation

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python scraper_gui.py`

## Usage

1. Enter a URL in the input field
2. Select where to save the images
3. Click "Start Scraping"
4. Images will be downloaded and organized by artist

## Project Structure

- `improved_scraper.py`: Core scraping functionality
- `config.py`: Configuration management
- `resources.py`: Browser and session management
- `scraper_gui.py`: Main GUI application

## Requirements

- Python 3.11+
- Required packages listed in requirements.txt