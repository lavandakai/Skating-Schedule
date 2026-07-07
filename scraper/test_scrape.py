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

    # exceptionsHtmlId 51 (skating group) cancels May 31-June 28 and Friday July 3
    non_figure = [s for s in sessions if s["type"] != "Figure Skating"]
    assert all(s["date"] != "2026-07-03" for s in non_figure)
    assert all(not ("2026-05-31" <= s["date"] <= "2026-06-28") for s in non_figure)

    # the first Friday public skate after the cancellation window should still appear
    assert any(
        s["date"] == "2026-07-10" and s["type"] == "Public Skating" and s["startTime"] == "18:00"
        for s in sessions
    )
    print("test_sandy_hill_sessions_exclude_cancelled_dates OK")


def test_figure_skate_uses_its_own_cancellation_group():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    today = date(2026, 6, 29)
    sessions = build_rink_sessions(rink, activities, html_by_id, today)

    # figure skate (exceptionsHtmlId 52, "ice sports" group) runs Mondays and is
    # unaffected by the skating group's (id 51) May 31-June 28 cancellation
    figure_sessions = [s for s in sessions if s["type"] == "Figure Skating"]
    assert any(s["date"] == "2026-06-29" for s in figure_sessions)
    assert not any("2026-05-31" <= s["date"] <= "2026-06-28" for s in figure_sessions)

    # the skating group's cancellations must not leak into figure skate, and
    # figure skate's own "Sunday, July 5" cancellation (id 52) must not leak
    # into the family skate session that also runs on Sundays (id 51)
    assert any(
        s["date"] == "2026-07-05" and s["type"] == "Family Skating" for s in sessions
    )
    print("test_figure_skate_uses_its_own_cancellation_group OK")


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
    test_figure_skate_uses_its_own_cancellation_group()
    test_sessions_never_precede_today()
    test_unknown_rink_raises()
