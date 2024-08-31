# Artsy Image Scraper

A simple web scraper that allows you to download images from specified URLs via a local web interface. It uses `selenium`, `beautifulsoup4`, and a local server to interact with the scraper through a web page.

## Features

- **Auto-Update:** Automatically updates dependencies using `auto_update.py`.
- **Local Web Server:** Provides a user-friendly web interface to enter URLs and download images.
- **Image Scraping:** Downloads images from the specified URLs.

## Prerequisites

- Python 3.11 or later
- `pip` (Python package installer)

## Setup Instructions

1. **Clone the Repository**.
   ```
   git clone https://github.com/A1Tman/artsy-imagescraper.git
   cd artsy-imagescraper
   ```

2. **Install Dependencies**.<br>
   Install the required packages listed in `requirements.txt`:
   ```
   pip install -r requirements.txt
   ```

3. **Run the Auto Update Script**.<br>
   Ensure all dependencies are up to date:
   ```
   python auto_update.py
   ```

4. **Start the Local Server**.<br>
   Run the local server to access the web interface:
   ```
   python local_server.py
   ```

5. **Access the Web Interface**.<br>
   The server will automatically open your default web browser to the web interface at:
   ```
   http://127.0.0.1:8000/
   ```

6. **Alternatively, run the GUI version:**.<br>
   ```
   py .\scraper_gui.py
   ```

## Usage

1. Enter the URL you want to scrape images from in the web interface.
2. Click the "Download" button to download the images to the designated directory.

## Contributing

If you'd like to contribute to this project, please follow these steps:

1. Fork the repository
2. Create a new branch (`git checkout -b feature/feature`)
3. Commit your changes (`git commit -m 'Add some feature'`)
4. Push to the branch (`git push origin feature/feature`)
5. Open a Pull Request

## License
This project is licensed under the MIT License. See the [LICENSE](https://github.com/A1Tman/artsy-imagescraper/blob/main/LICENSE) file for details.

Project Link: [https://github.com/A1Tman/artsy-imagescraper](https://github.com/A1Tman/artsy-imagescraper)
