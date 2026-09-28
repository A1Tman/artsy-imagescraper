"""Compatibility entry point; the maintained desktop application lives in gui.py."""
if __name__ == "__main__":
    from launcher import use_project_environment
    use_project_environment()

from gui import ImageScraperApp, main

if __name__ == "__main__":
    main()
