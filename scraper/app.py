from flask import Flask, render_template, request, jsonify, send_file
import csv
import io
import json
import re
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

USER_AGENT = "Mozilla/5.0 (compatible; SimplePythonScraper/1.0; +https://github.com/ppriyamsh241/Shop)"
TIMEOUT = 12
MAX_ITEMS = 200


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        # If robots.txt is unavailable, continue for ordinary public pages.
        return True


def scrape(url: str, selector: str = ""):
    url = normalize_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid public http(s) URL.")

    if not robots_allowed(url):
        raise PermissionError("This page disallows this scraper in robots.txt.")

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise ValueError("The URL did not return an HTML page.")

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])][:MAX_ITEMS]

    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(response.url, a["href"])
        if urlparse(href).scheme not in {"http", "https"}:
            continue
        links.append({
            "text": a.get_text(" ", strip=True),
            "url": href,
        })
        if len(links) >= MAX_ITEMS:
            break

    images = []
    for img in soup.find_all("img", src=True)[:MAX_ITEMS]:
        images.append({
            "alt": (img.get("alt") or "").strip(),
            "url": urljoin(response.url, img["src"]),
        })

    selected = []
    if selector:
        try:
            selected = [el.get_text(" ", strip=True) for el in soup.select(selector)][:MAX_ITEMS]
        except Exception as exc:
            raise ValueError(f"Invalid CSS selector: {exc}") from exc

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    return {
        "url": response.url,
        "status_code": response.status_code,
        "title": title,
        "headings": headings,
        "links": links,
        "images": images,
        "selected": selected,
        "text": text[:100000],
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/scrape")
def api_scrape():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    selector = data.get("selector", "").strip()
    if not url:
        return jsonify({"error": "URL is required."}), 400
    try:
        return jsonify(scrape(url, selector))
    except requests.RequestException as exc:
        return jsonify({"error": f"Request failed: {exc}"}), 502
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/export")
def export_data():
    payload = request.get_json(silent=True) or {}
    fmt = payload.get("format", "json").lower()
    data = payload.get("data", {})

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["type", "text", "url", "alt"])
        for item in data.get("links", []):
            writer.writerow(["link", item.get("text", ""), item.get("url", ""), ""])
        for item in data.get("images", []):
            writer.writerow(["image", "", item.get("url", ""), item.get("alt", "")])
        for heading in data.get("headings", []):
            writer.writerow(["heading", heading, "", ""])
        raw = output.getvalue().encode("utf-8-sig")
        return send_file(io.BytesIO(raw), mimetype="text/csv", as_attachment=True, download_name="scrape.csv")

    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(io.BytesIO(raw), mimetype="application/json", as_attachment=True, download_name="scrape.json")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
