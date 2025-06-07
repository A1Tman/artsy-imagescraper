import subprocess
import sys
from datetime import datetime
import os
from pathlib import Path

def update_packages():
    base_dir = Path(__file__).resolve().parent
    log_dir = base_dir / "Update Logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / datetime.now().strftime("update_log_%Y-%m-%d_%H-%M-%S.txt")
    
    with open(log_file, "a") as log:
        log.write(f"Update started at {datetime.now()}\n\n")
                
        requirements_path = base_dir / "requirements.txt"
        with open(requirements_path, "r") as file:
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
