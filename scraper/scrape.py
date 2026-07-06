#!/usr/bin/env python3
"""Scrape Ottawa arena drop-in skating schedules into data/schedule.json.

Each rink page on ottawa.ca uses the same Drupal template: a collapsible
"Drop-in schedule - skating" section containing a "Schedule changes" bullet
list (cancellations) and one or more HTML tables (day-of-week x session).
This script finds that section on each configured rink page, extracts the
Public/Family/Adult skating rows, and writes a combined JSON file consumed
by the static site in index.html.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RINKS_FILE = ROOT / "rinks.json"
OUTPUT_FILE = ROOT / "data" / "schedule.json"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
}
REQUEST_TIMEOUT = 30
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5

SESSION_MATCHERS = [
    ("Public Skating", re.compile(r"public\s+skating", re.I)),
    ("Family Skating", re.compile(r"family\s+skating", re.I)),
    ("Adult Skating (18+)", re.compile(r"adult\s+skating", re.I)),
]

DAY_ORDER = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]


class ScrapeError(Exception):
    pass


def clean_text(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


_session = requests.Session()
_session.headers.update(REQUEST_HEADERS)


def fetch(url):
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = _session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise ScrapeError(f"Failed to fetch {url}: {last_error}")


def find_skating_article(soup):
    for article in soup.select("article.node--type-article"):
        heading = article.find(["h2", "h3"])
        if not heading:
            continue
        heading_text = heading.get_text(strip=True).lower()
        if "schedule" in heading_text and "skat" in heading_text:
            return article
    return None


def parse_tables(article):
    tables = []
    for table in article.find_all("table"):
        caption_tag = table.find("caption")
        caption = clean_text(caption_tag.get_text()) if caption_tag else None

        header_cells = table.select("thead th")
        day_names = [clean_text(th.get_text()) for th in header_cells[1:]]

        sessions = []
        for row in table.select("tbody tr"):
            row_header = row.find("th")
            if row_header is None:
                continue
            row_label = clean_text(row_header.get_text())

            matched_name = None
            for name, pattern in SESSION_MATCHERS:
                if pattern.search(row_label):
                    matched_name = name
                    break
            if matched_name is None:
                continue

            days = {}
            for day_name, cell in zip(day_names, row.find_all("td")):
                value = clean_text(cell.get_text(separator=" "))
                if value and value.lower() not in ("n/a", "na"):
                    days[day_name] = value
            sessions.append({"name": matched_name, "days": days})

        if sessions:
            tables.append({"caption": caption, "days": day_names, "sessions": sessions})
    return tables


def parse_cancellations(article):
    changes_heading = None
    for heading in article.find_all(["h2", "h3", "h4"]):
        if "schedule change" in heading.get_text(strip=True).lower():
            changes_heading = heading
            break
    if changes_heading is None:
        return []

    change_list = changes_heading.find_next_sibling("ul")
    if change_list is None:
        return []

    cancellations = []
    for item in change_list.find_all("li", recursive=False):
        strong = item.find("strong")
        date_text = clean_text(strong.get_text()) if strong else None

        nested_list = item.find("ul")
        notes = []
        if nested_list is not None:
            for note_item in nested_list.find_all("li", recursive=False):
                note = clean_text(note_item.get_text())
                if note:
                    notes.append(note)
        else:
            full_text = clean_text(item.get_text())
            if date_text and full_text.startswith(date_text):
                full_text = full_text[len(date_text):].strip(" ,:-")
            if full_text:
                notes.append(full_text)

        if date_text or notes:
            cancellations.append({"date": date_text, "notes": notes})
    return cancellations


def scrape_html(html):
    """Parse a rink page's HTML into {tables, cancellations}. Raises ScrapeError."""
    soup = BeautifulSoup(html, "lxml")
    article = find_skating_article(soup)
    if article is None:
        raise ScrapeError("Could not find the 'Drop-in schedule - skating' section")

    tables = parse_tables(article)
    if not tables:
        raise ScrapeError("Found the skating section but no matching schedule rows")

    cancellations = parse_cancellations(article)
    return {"tables": tables, "cancellations": cancellations}


def scrape_rink(rink):
    html = fetch(rink["url"])
    return scrape_html(html)


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def main():
    rinks = load_json(RINKS_FILE, [])
    if not rinks:
        print(f"No rinks configured in {RINKS_FILE}", file=sys.stderr)
        sys.exit(1)

    previous = load_json(OUTPUT_FILE, {"rinks": []})
    previous_by_name = {rink["name"]: rink for rink in previous.get("rinks", [])}

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    failures = 0

    for rink in rinks:
        name = rink["name"]
        print(f"Scraping {name}...")
        try:
            parsed = scrape_rink(rink)
            results.append({
                "name": name,
                "url": rink["url"],
                "status": "ok",
                "scraped_at": now,
                "tables": parsed["tables"],
                "cancellations": parsed["cancellations"],
            })
        except ScrapeError as exc:
            failures += 1
            print(f"  failed: {exc}", file=sys.stderr)
            previous_entry = previous_by_name.get(name)
            if previous_entry and previous_entry.get("tables"):
                results.append({
                    **previous_entry,
                    "status": "stale",
                    "error": str(exc),
                })
            else:
                results.append({
                    "name": name,
                    "url": rink["url"],
                    "status": "error",
                    "error": str(exc),
                    "tables": [],
                    "cancellations": [],
                })

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(
        {"generated_at": now, "rinks": results}, indent=2, ensure_ascii=False
    ) + "\n")

    print(f"Wrote {OUTPUT_FILE} ({len(results)} rinks, {failures} failures)")
    if failures == len(rinks):
        sys.exit(1)


if __name__ == "__main__":
    main()
