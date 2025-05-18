import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse
from pathlib import Path

def sanitize_path_component(component):
    if not component:
        return "unnamed"
    
    sanitized = component.replace('..', '').replace('/', '').replace('\\', '')
    sanitized = sanitized.replace(':', '').replace('*', '').replace('?', '')
    sanitized = sanitized.replace('"', '').replace('<', '').replace('>', '').replace('|', '')
    sanitized = sanitized.strip(' .')
    
    return sanitized if sanitized else "unnamed"

def scrape_images(url):
    # Extract the image name from the URL
    image_name = url.split("/artwork/")[1]
    safe_image_name = sanitize_path_component(image_name)
    # Directory name to save the images
    directory_name = "Scraped"
    base_path = Path(directory_name).resolve()
    # Create a directory if it doesn't exist
    if not os.path.exists(directory_name):
        os.makedirs(directory_name)
    # Selenium setup with webdriver_manager to automatically manage the ChromeDriver
    options = Options()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--incognito')
    options.add_argument('--headless')
    # Use webdriver_manager to get the latest chromedriver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(url)
    # Wait for the website to load all the elements
    driver.implicitly_wait(5)
    # Render the JS code and store all of the information in static HTML code
    html = driver.page_source
    # Apply bs4 to the HTML variable
    soup = BeautifulSoup(html, "html.parser")
    # Find all <div> elements
    all_divs = soup.find_all('div')
    # Set to store unique URLs
    unique_urls = set()
    # Iterate over each <div> element
    for div in all_divs:
        img_tags = div.find_all('img')
        for img in img_tags:
            src = img['src']
            decoded_url = unquote(src)
            start_index = decoded_url.find("resize_to=fit&src=") + len("resize_to=fit&src=")
            end_index = decoded_url.find("&width")
            modified_url = decoded_url[start_index:end_index]
            if 'universal-footer' not in modified_url and 'larger' not in modified_url and 'small' not in modified_url and 'square' not in modified_url and 'source' not in modified_url:
                unique_urls.add(modified_url)
    # Download the unique images
    num_images_downloaded = 0
    for url in unique_urls:
        try:
            file_extension = os.path.splitext(urlparse(url).path)[1]
            safe_extension = sanitize_path_component(file_extension)
            
            filename = f"{safe_image_name}_{num_images_downloaded}.{safe_extension.lstrip('.')}"
            image_path = (base_path / filename).resolve()
            
            if not str(image_path).startswith(str(base_path)):
                print(f"Skipping suspicious path: {filename}")
                continue
            
            response = requests.get(url)
            response.raise_for_status()
            with open(image_path, "wb") as file:
                file.write(response.content)
            num_images_downloaded += 1
        except requests.exceptions.RequestException as e:
            print(f"Error downloading image: {url}")
            print(f"Error details: {str(e)}")
    # Close the webdriver
    driver.quit()
    # Return the number of images downloaded
    return num_images_downloaded
