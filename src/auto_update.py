import subprocess
import sys
from datetime import datetime
import os

def update_packages():
    log_dir = "Update Logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, datetime.now().strftime("update_log_%Y-%m-%d_%H-%M-%S.txt"))
    
    with open(log_file, "a") as log:
        log.write(f"Update started at {datetime.now()}\n\n")
                
        with open("requirements.txt", "r") as file:
            packages = file.readlines()

        for package in packages:
            package = package.strip()
            if package:  # Make sure it's not an empty line
                try:
                    # Attempt to update the package
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--upgrade", package],
                        capture_output=True, text=True
                    )
                    # Log the full output
                    log.write(f"Updating {package}:\n{result.stdout}\n{result.stderr}\n")
                    # Print a short message in the terminal
                    if "Successfully installed" in result.stdout:
                        print(f"{package} updated successfully.")
                    elif "Requirement already satisfied" in result.stdout:
                        print(f"{package} is already up to date.")
                    else:
                        print(f"{package} encountered an issue during update.")
                except subprocess.CalledProcessError as e:
                    log.write(f"Failed to update {package}: {e}\n")
                    print(f"{package} failed to update. Check log for details.")
        
        log.write(f"Update finished at {datetime.now()}\n{'-'*40}\n")

if __name__ == "__main__":
    update_packages()
