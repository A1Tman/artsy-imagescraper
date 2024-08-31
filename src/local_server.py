import http.server
import socketserver
import urllib.parse
import webbrowser
from io import StringIO
from scraper import scrape_images
from auto_update import update_packages  

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open('scraper_interface.html', 'rb') as file:
                self.wfile.write(file.read())
        elif self.path == '/update':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            try:
                update_packages()
                self.wfile.write(b"Packages updated successfully.")
            except Exception as e:
                self.wfile.write(f"Error updating packages: {str(e)}".encode())
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/run_scraper':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(post_data)
            url = params['url'][0]

            # Run the scraper
            result = scrape_images(url)

            # Prepare the response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Read the HTML file
            with open('scraper_interface.html', 'r') as file:
                html_content = file.read()

            # Insert the result into the HTML
            html_content = html_content.replace('<!-- The result will be inserted here by the Python script -->', 
                                                f'<p>Downloaded {result} images.</p>')

            # Send the modified HTML
            self.wfile.write(html_content.encode())

def start_server():
    PORT = 8000
    with socketserver.TCPServer(("", PORT), MyHandler) as httpd:
        print(f"Serving at port {PORT}")

        # Automatically open the default web browser to the local server URL
        webbrowser.open(f"http://127.0.0.1:{PORT}/")

        # Start the server
        httpd.serve_forever()

if __name__ == '__main__':
    start_server()
