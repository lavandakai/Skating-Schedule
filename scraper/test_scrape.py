#!/usr/bin/env python3
"""Regression test for scrape.py against a saved ottrec dataset fixture.

Run with: python3 scraper/test_scrape.py
"""
import json
from datetime import date
from pathlib import Path

from scrape import build_rink_sessions, parse_cancellation_dates

FIXTURE = Path(__file__).parent / "fixtures" / "ottrec_sample.json"


def load_fixture():
    data = json.loads(FIXTURE.read_text())
    html_by_id = {h["id"]: h["html"] for h in data["html"]}
    return data["activity"], html_by_id


def test_parse_cancellation_dates_single():
    ref_start, ref_end = date(2026, 6, 29), date(2026, 8, 30)
    result = parse_cancellation_dates("Friday, July 3", ref_start, ref_end)
    assert result == [(date(2026, 7, 3), date(2026, 7, 3))]
    print("test_parse_cancellation_dates_single OK")


def test_parse_cancellation_dates_range():
    ref_start, ref_end = date(2026, 6, 29), date(2026, 8, 30)
    result = parse_cancellation_dates("May 31 to June 28", ref_start, ref_end)
    assert result == [(date(2026, 5, 31), date(2026, 6, 28))]
    print("test_parse_cancellation_dates_range OK")


def test_parse_cancellation_dates_unparseable_returns_empty():
    ref_start, ref_end = date(2026, 6, 29), date(2026, 8, 30)
    assert parse_cancellation_dates("Statutory holidays vary", ref_start, ref_end) == []
    print("test_parse_cancellation_dates_unparseable_returns_empty OK")


def test_sandy_hill_sessions_exclude_cancelled_dates():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    today = date(2026, 6, 29)
    sessions = build_rink_sessions(rink, activities, html_by_id, today)

    # exceptionsHtmlId 51 (skating group) cancels May 31-June 28 and Friday July 3;
    # figure skate's ice-sports group (id 52) cancellation must not leak in since
    # figure skate isn't one of our tracked session types anyway.
    assert all(s["date"] != "2026-07-03" for s in sessions)
    assert all(not ("2026-05-31" <= s["date"] <= "2026-06-28") for s in sessions)

    # the first Friday public skate after the cancellation window should still appear
    assert any(
        s["date"] == "2026-07-10" and s["type"] == "Public Skating" and s["startTime"] == "18:00"
        for s in sessions
    )
    assert all(s["type"] != "Figure Skating" for s in sessions)
    print("test_sandy_hill_sessions_exclude_cancelled_dates OK")


def test_sessions_never_precede_today():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    today = date(2026, 7, 15)
    sessions = build_rink_sessions(rink, activities, html_by_id, today)
    assert all(s["date"] >= "2026-07-15" for s in sessions)
    print("test_sessions_never_precede_today OK")


def test_unknown_rink_raises():
    activities, html_by_id = load_fixture()
    rink = {"name": "Nonexistent Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/nonexistent-arena"}
    try:
        build_rink_sessions(rink, activities, html_by_id, date(2026, 6, 29))
    except Exception as exc:
        assert "No matching" in str(exc)
        print("test_unknown_rink_raises OK")
        return
    raise AssertionError("expected build_rink_sessions to raise for an unknown rink")


if __name__ == "__main__":
    test_parse_cancellation_dates_single()
    test_parse_cancellation_dates_range()
    test_parse_cancellation_dates_unparseable_returns_empty()
    test_sandy_hill_sessions_exclude_cancelled_dates()
    test_sessions_never_precede_today()
    test_unknown_rink_raises()
