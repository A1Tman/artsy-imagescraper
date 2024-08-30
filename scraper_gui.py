import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QPushButton, QLineEdit, QLabel, QWidget
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
from scraper import scrape_images
from auto_update import update_packages

class ScraperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Web Scraper')
        self.setGeometry(100, 100, 500, 300)

        # Set up the layout
        layout = QVBoxLayout()

        # Title Label
        title_label = QLabel('Web Scraper')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont('Arial', 24))
        title_label.setStyleSheet("color: #25A77A; margin-bottom: 20px;")
        layout.addWidget(title_label)

        # URL Input Field
        url_label = QLabel('Enter URL:')
        url_label.setFont(QFont('Arial', 14))
        layout.addWidget(url_label)

        self.url_input = QLineEdit(self)
        self.url_input.setFont(QFont('Arial', 12))
        self.url_input.setPlaceholderText('https://example.com')
        self.url_input.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 5px;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.url_input)

        # Download Image Button
        self.download_button = QPushButton('Download Image', self)
        self.download_button.setFont(QFont('Arial', 14))
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #25A77A;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #218868;
            }
        """)
        layout.addWidget(self.download_button)

        # Update Packages Button
        self.update_button = QPushButton('Update Packages', self)
        self.update_button.setFont(QFont('Arial', 14))
        self.update_button.setStyleSheet("""
            QPushButton {
                background-color: #007BFF;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        layout.addWidget(self.update_button)

        # Status Label
        self.status_label = QLabel('Status: Ready', self)
        self.status_label.setFont(QFont('Arial', 12))
        self.status_label.setStyleSheet("color: #555; margin-top: 20px;")
        layout.addWidget(self.status_label)

        # Central Widget
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Connect buttons to their respective functions
        self.download_button.clicked.connect(self.run_scraper)
        self.update_button.clicked.connect(self.run_update)

    def run_scraper(self):
        url = self.url_input.text()
        if url:
            self.status_label.setText(f'Status: Downloading images from {url}')
            try:
                result = scrape_images(url)
                self.status_label.setText(f'Status: Downloaded {result} images.')
            except Exception as e:
                self.status_label.setText(f'Error: {str(e)}')

    def run_update(self):
        self.status_label.setText('Status: Updating packages...')
        try:
            update_packages()
            self.status_label.setText('Status: Packages updated successfully.')
        except Exception as e:
            self.status_label.setText(f'Error: {str(e)}')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    scraper_app = ScraperApp()
    scraper_app.show()
    sys.exit(app.exec_())
