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

Rather than shipping the frontend a weekly recurring pattern plus a
separate list of cancellation notices, this expands everything into
concrete calendar dates (today onward through each activity's own
startDate/endDate window) with cancelled occurrences already removed. That
way the site's Today/Week/Month views just filter a flat date list —
schedule changes disappear automatically instead of needing their own UI.
"""
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
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
    "adult skate": "Adult Skating (18+)",  # e.g. Canterbury normalizes without "18+"
    "figure skate": "Figure Skating",
    "figure skate 6+": "Figure Skating",  # e.g. Fred Barrett normalizes with an age suffix
}

DAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
]

# Cancellations confirmed to have happened but not reflected as an exceptions
# notice anywhere in the upstream dataset for that session's own schedule
# group (e.g. a rink's "ice sports"/figure-skate table has no cancellation
# text of its own even when its "skating" table does), so they can't be
# caught by parsing. Keyed by (rink URL, session type) to a set of dates.
MANUAL_CANCELLATIONS = {}

# Recurring sessions confirmed to run but missing entirely from the upstream
# dataset for that rink (e.g. a newly-published fall schedule that left one
# activity out). Remove an entry once the rink's own page/the dataset picks
# it up, to avoid double-booking it.
MANUAL_ADDITIONAL_SESSIONS = [
    {
        "rinkUrl": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena",
        "type": "Figure Skating",
        "weekday": "saturday",
        "startTime": "22:00",
        "endTime": "22:50",
        "startDate": date(2026, 9, 1),
        "endDate": date(2026, 12, 29),
        "reservationRequired": True,
    },
]

# Recurring activities whose upstream startTime/endTime is confirmed wrong
# (e.g. an AM/PM mislabel on the rink's own posted schedule). Matched by
# (rink URL, session type, weekday, wrong start, wrong end); remove an entry
# once the rink/dataset corrects it upstream.
MANUAL_TIME_CORRECTIONS = {
    (
        "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/jim-durrell-recreation-centre",
        "Adult Skating (18+)",
        "tuesday",
        "23:00",
        "23:50",
    ): ("11:00", "11:50"),
    (
        "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/jim-durrell-recreation-centre",
        "Adult Skating (18+)",
        "thursday",
        "23:00",
        "23:50",
    ): ("11:00", "11:50"),
}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Cancellation notices can carry multiple comma-separated labels before the
# actual date, e.g. "Civic Holiday, Monday, August 3" (not just a single
# "Weekday, " prefix), so the label group matches zero or more of them.
_LABEL_PREFIX = r"(?:[A-Za-z]+(?:\s+[A-Za-z]+)*,\s*)*"
CANCELLATION_RANGE_RE = re.compile(
    rf"^{_LABEL_PREFIX}([A-Za-z]+)\s+(\d{{1,2}})\s+to\s+{_LABEL_PREFIX}([A-Za-z]+)\s+(\d{{1,2}})$"
)
CANCELLATION_SINGLE_RE = re.compile(rf"^{_LABEL_PREFIX}([A-Za-z]+)\s+(\d{{1,2}})$")

try:
    from zoneinfo import ZoneInfo
    OTTAWA_TZ = ZoneInfo("America/Toronto")
except Exception:
    OTTAWA_TZ = None


class ScrapeError(Exception):
    pass


def today_in_ottawa():
    if OTTAWA_TZ is not None:
        return datetime.now(OTTAWA_TZ).date()
    return datetime.now(timezone.utc).date()


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


def _build_date(month_name, day, ref_start, ref_end):
    month = MONTHS.get(month_name.strip().lower())
    if not month:
        return None
    day = int(day)
    for year in (ref_start.year, ref_start.year + 1, ref_start.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if ref_start - timedelta(days=21) <= candidate <= ref_end + timedelta(days=21):
            return candidate
    try:
        return date(ref_start.year, month, day)
    except ValueError:
        return None


def parse_cancellation_dates(text, ref_start, ref_end):
    """Parse a cancellation notice's date text (no year given) into a list
    of (start, end) inclusive date ranges, using ref_start/ref_end (the
    schedule's own date range) to infer the year. Returns [] if the text
    doesn't match a recognized pattern."""
    if not text:
        return []
    text = text.strip()

    match = CANCELLATION_RANGE_RE.match(text)
    if match:
        month1, day1, month2, day2 = match.groups()
        start = _build_date(month1, day1, ref_start, ref_end)
        end = _build_date(month2, day2, ref_start, ref_end)
        if start and end:
            if end < start:
                end = end.replace(year=end.year + 1)
            return [(start, end)]
        return []

    match = CANCELLATION_SINGLE_RE.match(text)
    if match:
        month1, day1 = match.groups()
        d = _build_date(month1, day1, ref_start, ref_end)
        if d:
            return [(d, d)]
    return []


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_rink_sessions(rink, activities, html_by_id, today):
    exclude_types = set(rink.get("excludeTypes", []))
    matches = [
        a for a in activities
        if a["facilityUrl"] == rink["url"]
        and a["name"] in SESSION_NAMES
        and SESSION_NAMES[a["name"]] not in exclude_types
    ]
    if not matches:
        raise ScrapeError("No matching skating sessions found in the dataset")

    excluded_ranges_by_group = {}
    for activity in matches:
        eid = activity.get("exceptionsHtmlId")
        if eid is None or eid in excluded_ranges_by_group:
            continue
        group_start = _parse_iso_date(activity.get("startDate"))
        group_end = _parse_iso_date(activity.get("endDate"))
        if not group_start or not group_end:
            continue
        ranges = []
        for entry in parse_cancellation_fragment(html_by_id.get(eid)):
            ranges.extend(
                parse_cancellation_dates(entry.get("date"), group_start, group_end)
            )
        excluded_ranges_by_group[eid] = ranges

    sessions = []
    for activity in matches:
        start = _parse_iso_date(activity.get("startDate"))
        end = _parse_iso_date(activity.get("endDate"))
        weekday = (activity.get("weekday") or "").lower()
        start_time, end_time = activity.get("startTime"), activity.get("endTime")
        if not (start and end and weekday in DAY_NAMES and start_time and end_time):
            continue

        session_type = SESSION_NAMES[activity["name"]]
        correction = MANUAL_TIME_CORRECTIONS.get(
            (rink["url"], session_type, weekday, start_time, end_time)
        )
        if correction:
            start_time, end_time = correction

        excluded_ranges = excluded_ranges_by_group.get(activity.get("exceptionsHtmlId"), [])
        manual_excluded_dates = MANUAL_CANCELLATIONS.get((rink["url"], session_type), set())
        cursor = max(start, today)
        while cursor <= end:
            if DAY_NAMES[cursor.weekday()] == weekday:
                excluded = any(r_start <= cursor <= r_end for r_start, r_end in excluded_ranges)
                if not excluded and cursor not in manual_excluded_dates:
                    sessions.append({
                        "date": cursor.isoformat(),
                        "startTime": start_time,
                        "endTime": end_time,
                        "rink": rink["name"],
                        "rinkShort": rink.get("shortName", rink["name"]),
                        "rinkUrl": rink["url"],
                        "type": session_type,
                        "reservationRequired": bool(activity.get("reservationRequired")),
                    })
            cursor += timedelta(days=1)

    for extra in MANUAL_ADDITIONAL_SESSIONS:
        if extra["rinkUrl"] != rink["url"] or extra["type"] in exclude_types:
            continue
        cursor = max(extra["startDate"], today)
        while cursor <= extra["endDate"]:
            if DAY_NAMES[cursor.weekday()] == extra["weekday"]:
                session = {
                    "date": cursor.isoformat(),
                    "startTime": extra["startTime"],
                    "endTime": extra["endTime"],
                    "rink": rink["name"],
                    "rinkShort": rink.get("shortName", rink["name"]),
                    "rinkUrl": rink["url"],
                    "type": extra["type"],
                    "reservationRequired": bool(extra.get("reservationRequired")),
                }
                if extra.get("note"):
                    session["note"] = extra["note"]
                sessions.append(session)
            cursor += timedelta(days=1)

    return sessions


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

    today = today_in_ottawa()
    previous = load_json(OUTPUT_FILE, {"rinks": [], "sessions": []})
    previous_sessions_by_rink = {}
    for session in previous.get("sessions", []):
        previous_sessions_by_rink.setdefault(session["rink"], []).append(session)

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

    rink_results = []
    all_sessions = []
    failures = 0

    for rink in rinks:
        name = rink["name"]
        short_name = rink.get("shortName", name)
        print(f"Processing {name}...")
        error = dataset_error
        sessions = None
        if error is None:
            try:
                sessions = build_rink_sessions(rink, activities, html_by_id, today)
            except ScrapeError as exc:
                error = str(exc)

        if sessions is not None:
            rink_results.append({
                "name": name, "shortName": short_name, "url": rink["url"], "status": "ok",
            })
            all_sessions.extend(sessions)
            continue

        failures += 1
        print(f"  failed: {error}", file=sys.stderr)
        fallback = [
            s for s in previous_sessions_by_rink.get(name, [])
            if s["date"] >= today.isoformat()
        ]
        if fallback:
            rink_results.append({
                "name": name, "shortName": short_name, "url": rink["url"],
                "status": "stale", "error": error,
            })
            all_sessions.extend(fallback)
        else:
            rink_results.append({
                "name": name, "shortName": short_name, "url": rink["url"],
                "status": "error", "error": error,
            })

    all_sessions.sort(key=lambda s: (s["date"], s["startTime"]))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps({
        "generated_at": now,
        "attribution": attribution,
        "rinks": rink_results,
        "sessions": all_sessions,
    }, indent=2, ensure_ascii=False) + "\n")

    print(f"Wrote {OUTPUT_FILE} ({len(rink_results)} rinks, {len(all_sessions)} sessions, {failures} failures)")
    if failures == len(rinks):
        sys.exit(1)


if __name__ == "__main__":
    main()
