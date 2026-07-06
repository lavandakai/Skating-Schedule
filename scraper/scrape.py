#!/usr/bin/env python3
"""Build data/schedule.json from the ottrec dataset.

ottawa.ca itself sits behind an Incapsula WAF that blocks GitHub-hosted
runners outright, so instead of scraping arena pages directly, this reads
https://data.ottrec.ca/export/latest.json — a community-maintained mirror
that scrapes the same ottawa.ca facility pages (with permission) into a
clean, normalized JSON dataset, updated daily. See its attribution terms
in ATTRIBUTION below; we display them verbatim on the site.

The dataset's `activity.name` field normalizes each rink's differently
worded activity labels (e.g. "Adult skating (18+)" vs "Adult skating (ages
18+)") down to a small stable set of strings, which is what SESSION_NAMES
below filters on.
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

DATASET_URL = "https://data.ottrec.ca/export/latest.json"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}
REQUEST_TIMEOUT = 60
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5

SESSION_NAMES = {
    "public skate": "Public Skating",
    "family skate": "Family Skating",
    "adult skate 18+": "Adult Skating (18+)",
}
SESSION_ORDER = list(SESSION_NAMES)

DAY_ORDER = [
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
]
DAY_LABELS = {d: d.capitalize() for d in DAY_ORDER}


class ScrapeError(Exception):
    pass


def clean_text(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def fetch_dataset():
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                DATASET_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise ScrapeError(f"Failed to fetch {DATASET_URL}: {last_error}")


def format_time_range(start, end):
    def parts(value):
        hour, minute = (int(x) for x in value.split(":"))
        period = "am" if hour < 12 else "pm"
        hour12 = hour % 12 or 12
        label = str(hour12) if minute == 0 else f"{hour12}:{minute:02d}"
        return label, period

    start_label, start_period = parts(start)
    end_label, end_period = parts(end)
    if start_period == end_period:
        return f"{start_label} - {end_label} {end_period}"
    return f"{start_label} {start_period} - {end_label} {end_period}"


def parse_cancellation_fragment(html_fragment):
    if not html_fragment:
        return []
    soup = BeautifulSoup(html_fragment, "lxml")
    top_list = soup.find("ul")
    if top_list is None:
        return []

    cancellations = []
    for item in top_list.find_all("li", recursive=False):
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


def build_rink_data(rink, activities, html_by_id):
    matches = [
        a for a in activities
        if a["facilityUrl"] == rink["url"] and a["name"] in SESSION_NAMES
    ]
    if not matches:
        raise ScrapeError("No matching skating sessions found in the dataset")

    groups = {}
    for activity in matches:
        caption = activity.get("rawSchedule") or (
            f"{activity.get('startDate', '?')} to {activity.get('endDate', '?')}"
        )
        groups.setdefault(caption, []).append(activity)

    tables = []
    exception_ids = set()
    for caption, entries in groups.items():
        sessions = {name: {} for name in SESSION_ORDER}
        for entry in entries:
            weekday = (entry.get("weekday") or "").lower()
            if weekday not in DAY_ORDER:
                continue
            start_time, end_time = entry.get("startTime"), entry.get("endTime")
            if not start_time or not end_time:
                continue
            day_label = DAY_LABELS[weekday]
            time_label = format_time_range(start_time, end_time)
            day_map = sessions[entry["name"]]
            if day_label in day_map:
                day_map[day_label] += f"; {time_label}"
            else:
                day_map[day_label] = time_label
            if entry.get("exceptionsHtmlId"):
                exception_ids.add(entry["exceptionsHtmlId"])

        tables.append({
            "caption": caption,
            "days": [DAY_LABELS[d] for d in DAY_ORDER],
            "sessions": [
                {"name": SESSION_NAMES[name], "days": sessions[name]}
                for name in SESSION_ORDER
                if sessions[name]
            ],
        })

    cancellations = []
    for eid in exception_ids:
        cancellations.extend(parse_cancellation_fragment(html_by_id.get(eid)))

    return {"tables": tables, "cancellations": cancellations}


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

    try:
        dataset = fetch_dataset()
        activities = dataset["activity"]
        html_by_id = {h["id"]: h["html"] for h in dataset["html"]}
        attribution = [a["text"] for a in dataset.get("attribution", [])]
        dataset_error = None
    except (ScrapeError, KeyError) as exc:
        activities, html_by_id = [], {}
        attribution = previous.get("attribution", [])
        dataset_error = str(exc)

    results = []
    failures = 0

    for rink in rinks:
        name = rink["name"]
        print(f"Processing {name}...")
        error = dataset_error
        parsed = None
        if error is None:
            try:
                parsed = build_rink_data(rink, activities, html_by_id)
            except ScrapeError as exc:
                error = str(exc)

        if parsed is not None:
            results.append({
                "name": name,
                "url": rink["url"],
                "status": "ok",
                "scraped_at": now,
                "tables": parsed["tables"],
                "cancellations": parsed["cancellations"],
            })
            continue

        failures += 1
        print(f"  failed: {error}", file=sys.stderr)
        previous_entry = previous_by_name.get(name)
        if previous_entry and previous_entry.get("tables"):
            results.append({**previous_entry, "status": "stale", "error": error})
        else:
            results.append({
                "name": name,
                "url": rink["url"],
                "status": "error",
                "error": error,
                "tables": [],
                "cancellations": [],
            })

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps({
        "generated_at": now,
        "attribution": attribution,
        "rinks": results,
    }, indent=2, ensure_ascii=False) + "\n")

    print(f"Wrote {OUTPUT_FILE} ({len(results)} rinks, {failures} failures)")
    if failures == len(rinks):
        sys.exit(1)


if __name__ == "__main__":
    main()
