"""Compatibility module; all scraping uses the maintained implementation."""
if __name__ == "__main__":
    from launcher import use_project_environment
    use_project_environment()

from scraper import *  # noqa: F401,F403

if __name__ == "__main__":
    main()
