"""Prefer this project's isolated environment when running a desktop entry point."""
import os
from pathlib import Path
import sys


def use_project_environment():
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file() and Path(sys.prefix).resolve() != environment.resolve():
        os.execv(str(python), [str(python), *sys.argv])
