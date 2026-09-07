# Python Web Scraper

A small Flask web application for scraping public HTML pages.

## Features

- Fetches public HTTP/HTTPS HTML pages
- Checks `robots.txt` before scraping
- Extracts page title, H1/H2/H3 headings, links, images and readable text
- Optional CSS-selector extraction
- JSON and CSV export
- Request timeout and result limits
- Responsive browser interface

## Run locally

```bash
cd scraper
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

Use it only for pages you are permitted to access and respect the target site's terms, robots rules, rate limits, and copyright restrictions.
