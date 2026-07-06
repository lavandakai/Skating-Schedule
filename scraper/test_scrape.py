#!/usr/bin/env python3
"""Regression test for scrape.py against a saved ottrec dataset fixture.

Run with: python3 scraper/test_scrape.py
"""
import json
from pathlib import Path

from scrape import build_rink_data

FIXTURE = Path(__file__).parent / "fixtures" / "ottrec_sample.json"


def load_fixture():
    data = json.loads(FIXTURE.read_text())
    html_by_id = {h["id"]: h["html"] for h in data["html"]}
    return data["activity"], html_by_id


def test_sandy_hill():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    result = build_rink_data(rink, activities, html_by_id)

    assert len(result["tables"]) == 1
    table = result["tables"][0]
    assert table["caption"] == "Sandy Hill Arena - skating - June 29 to August 30"
    assert table["days"] == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    ]

    sessions = {s["name"]: s["days"] for s in table["sessions"]}
    assert sessions["Public Skating"] == {"Friday": "6 - 6:50 pm"}
    assert sessions["Family Skating"] == {
        "Friday": "5 - 5:50 pm",
        "Sunday": "3 - 3:50 pm",
    }
    assert sessions["Adult Skating (18+)"] == {
        "Monday": "4 - 4:50 pm",
        "Tuesday": "9 - 9:50 pm",
    }
    # figure skate must never leak in even though it's in the same rawScheduleGroup family
    assert "Figure Skating" not in sessions

    # cancellations come only from the skating group's exceptionsHtmlId (51), not
    # the ice sports group's (52)
    assert result["cancellations"] == [
        {"date": "May 31 to June 28", "notes": ["All drop-in skating, cancelled"]},
        {"date": "Friday, July 3", "notes": ["All drop-in skating, cancelled"]},
    ]
    print("test_sandy_hill OK")


def test_jim_durrell_time_formatting():
    activities, html_by_id = load_fixture()
    rink = {"name": "Jim Durrell Recreation Centre", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/jim-durrell-recreation-centre"}
    result = build_rink_data(rink, activities, html_by_id)
    sessions = {s["name"]: s["days"] for s in result["tables"][0]["sessions"]}
    assert sessions["Public Skating"] == {"Monday": "5:15 - 6:05 pm"}
    print("test_jim_durrell_time_formatting OK")


def test_fred_barrett_wording_variant_normalizes():
    activities, html_by_id = load_fixture()
    rink = {"name": "Fred Barrett Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/fred-barrett-arena"}
    result = build_rink_data(rink, activities, html_by_id)
    sessions = {s["name"]: s["days"] for s in result["tables"][0]["sessions"]}
    # rawActivity says "Adult skating (ages 18+)" but normalized name matches ours
    assert sessions["Adult Skating (18+)"] == {"Tuesday": "3:15 - 4:05 pm"}
    print("test_fred_barrett_wording_variant_normalizes OK")


def test_tom_brown_zero_exceptions_id_means_no_cancellations():
    activities, html_by_id = load_fixture()
    rink = {"name": "Tom Brown Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/tom-brown-arena"}
    result = build_rink_data(rink, activities, html_by_id)
    assert result["cancellations"] == []
    print("test_tom_brown_zero_exceptions_id_means_no_cancellations OK")


def test_unknown_rink_raises():
    activities, html_by_id = load_fixture()
    rink = {"name": "Nonexistent Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/nonexistent-arena"}
    try:
        build_rink_data(rink, activities, html_by_id)
    except Exception as exc:
        assert "No matching" in str(exc)
        print("test_unknown_rink_raises OK")
        return
    raise AssertionError("expected build_rink_data to raise for an unknown rink")


if __name__ == "__main__":
    test_sandy_hill()
    test_jim_durrell_time_formatting()
    test_fred_barrett_wording_variant_normalizes()
    test_tom_brown_zero_exceptions_id_means_no_cancellations()
    test_unknown_rink_raises()
