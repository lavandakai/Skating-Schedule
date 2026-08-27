#!/usr/bin/env python3
"""Regression test for scrape.py against a saved ottrec dataset fixture.

Run with: python3 scraper/test_scrape.py
"""
import json
from datetime import date
from pathlib import Path

import scrape
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


def test_parse_cancellation_dates_multi_label_prefix():
    # real-world text has more than one comma-separated label before the
    # date, e.g. "Civic Holiday, Monday, August 3" -- not just "Weekday, "
    ref_start, ref_end = date(2026, 6, 29), date(2026, 8, 30)
    result = parse_cancellation_dates("Civic Holiday, Monday, August 3", ref_start, ref_end)
    assert result == [(date(2026, 8, 3), date(2026, 8, 3))]
    print("test_parse_cancellation_dates_multi_label_prefix OK")


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


def test_reservation_required_is_propagated_per_session():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    sessions = build_rink_sessions(rink, activities, html_by_id, date(2026, 6, 29))

    assert all(s["reservationRequired"] for s in sessions if s["type"] == "Figure Skating")
    assert not any(s["reservationRequired"] for s in sessions if s["type"] != "Figure Skating")
    print("test_reservation_required_is_propagated_per_session OK")


def test_exceptions_html_id_zero_is_not_treated_as_missing():
    # exceptionsHtmlId is a real, valid id -- 0 is falsy in Python, so a
    # naive `if not eid` check would wrongly treat this group as absent and
    # skip its cancellation notice entirely
    activities = [{
        "facilityUrl": "https://example.com/test-arena",
        "startDate": "2026-06-29",
        "endDate": "2026-08-30",
        "weekday": "monday",
        "startTime": "17:00",
        "endTime": "17:50",
        "name": "public skate",
        "exceptionsHtmlId": 0,
    }]
    html_by_id = {
        0: "<ul><li><strong>Monday, August 3</strong><ul>"
           "<li>All drop-in skating, cancelled</li></ul></li></ul>"
    }
    rink = {"name": "Test Arena", "url": "https://example.com/test-arena"}
    sessions = build_rink_sessions(rink, activities, html_by_id, date(2026, 6, 29))

    assert not any(s["date"] == "2026-08-03" for s in sessions)
    assert any(s["date"] == "2026-08-10" for s in sessions)
    print("test_exceptions_html_id_zero_is_not_treated_as_missing OK")


def test_manual_cancellation_override():
    # covers cases like a rink's schedule group carrying no cancellation
    # notice of its own for a known one-off closure in the upstream
    # dataset, so it must be caught by MANUAL_CANCELLATIONS instead of parsing
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    original = scrape.MANUAL_CANCELLATIONS
    try:
        scrape.MANUAL_CANCELLATIONS = {(rink["url"], "Figure Skating"): {date(2026, 8, 3)}}
        sessions = build_rink_sessions(rink, activities, html_by_id, date(2026, 6, 29))
    finally:
        scrape.MANUAL_CANCELLATIONS = original

    figure_sessions = [s for s in sessions if s["type"] == "Figure Skating"]
    assert not any(s["date"] == "2026-08-03" for s in figure_sessions)
    assert any(s["date"] == "2026-08-10" for s in figure_sessions)
    print("test_manual_cancellation_override OK")


def test_manual_additional_sessions_are_injected_per_rink():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    original = scrape.MANUAL_ADDITIONAL_SESSIONS
    try:
        scrape.MANUAL_ADDITIONAL_SESSIONS = [{
            "rinkUrl": rink["url"],
            "type": "Figure Skating",
            "weekday": "saturday",
            "startTime": "22:00",
            "endTime": "22:50",
            "startDate": date(2026, 9, 1),
            "endDate": date(2026, 9, 30),
            "reservationRequired": True,
            "note": "Ages 6+",
        }]
        sessions = build_rink_sessions(rink, activities, html_by_id, date(2026, 6, 29))
    finally:
        scrape.MANUAL_ADDITIONAL_SESSIONS = original

    added = [s for s in sessions if s["date"] == "2026-09-05" and s["type"] == "Figure Skating"]
    assert len(added) == 1
    assert added[0]["startTime"] == "22:00" and added[0]["endTime"] == "22:50"
    assert added[0]["reservationRequired"] is True
    assert added[0]["note"] == "Ages 6+"
    print("test_manual_additional_sessions_are_injected_per_rink OK")


def test_manual_time_correction_fixes_mislabeled_activity():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    original = scrape.MANUAL_TIME_CORRECTIONS
    try:
        # the fixture's Sandy Hill adult skate runs Monday 16:00-16:50;
        # pretend that was mislabeled and should really be 4:00-4:50am
        scrape.MANUAL_TIME_CORRECTIONS = {
            (rink["url"], "Adult Skating (18+)", "monday", "16:00", "16:50"): ("04:00", "04:50"),
        }
        sessions = build_rink_sessions(rink, activities, html_by_id, date(2026, 6, 29))
    finally:
        scrape.MANUAL_TIME_CORRECTIONS = original

    monday_adult = [s for s in sessions if s["type"] == "Adult Skating (18+)" and s["date"] == "2026-07-06"]
    assert len(monday_adult) == 1
    assert monday_adult[0]["startTime"] == "04:00"
    assert monday_adult[0]["endTime"] == "04:50"
    print("test_manual_time_correction_fixes_mislabeled_activity OK")


def test_sessions_never_precede_today():
    activities, html_by_id = load_fixture()
    rink = {"name": "Sandy Hill Arena", "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena"}
    today = date(2026, 7, 15)
    sessions = build_rink_sessions(rink, activities, html_by_id, today)
    assert all(s["date"] >= "2026-07-15" for s in sessions)
    print("test_sessions_never_precede_today OK")


def test_exclude_types_omits_matching_sessions():
    activities, html_by_id = load_fixture()
    rink = {
        "name": "Sandy Hill Arena",
        "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/sandy-hill-arena",
        "excludeTypes": ["Family Skating"],
    }
    sessions = build_rink_sessions(rink, activities, html_by_id, date(2026, 6, 29))
    assert not any(s["type"] == "Family Skating" for s in sessions)
    assert any(s["type"] == "Public Skating" for s in sessions)
    print("test_exclude_types_omits_matching_sessions OK")


def test_adult_skate_without_18_plus_suffix_is_recognized():
    # some rinks (e.g. Canterbury) normalize the activity name to "adult
    # skate" instead of "adult skate 18+"; both should map to the same type
    activities = [{
        "facilityUrl": "https://example.com/test-arena",
        "startDate": "2026-09-01",
        "endDate": "2026-12-01",
        "weekday": "monday",
        "startTime": "11:00",
        "endTime": "12:00",
        "name": "adult skate",
        "reservationRequired": False,
        "exceptionsHtmlId": 0,
    }]
    rink = {"name": "Test Arena", "url": "https://example.com/test-arena"}
    sessions = build_rink_sessions(rink, activities, {}, date(2026, 9, 1))
    assert any(s["type"] == "Adult Skating (18+)" for s in sessions)
    print("test_adult_skate_without_18_plus_suffix_is_recognized OK")


def test_figure_skate_age_suffix_variant_is_recognized():
    # some rinks (e.g. Fred Barrett) normalize the activity name to "figure
    # skate 6+"; it should still map to the plain "Figure Skating" type/label
    activities = [{
        "facilityUrl": "https://example.com/test-arena",
        "startDate": "2026-09-08",
        "endDate": "2026-12-27",
        "weekday": "friday",
        "startTime": "15:00",
        "endTime": "15:50",
        "name": "figure skate 6+",
        "reservationRequired": True,
        "exceptionsHtmlId": 0,
    }]
    rink = {"name": "Test Arena", "url": "https://example.com/test-arena"}
    sessions = build_rink_sessions(rink, activities, {}, date(2026, 9, 1))
    assert any(s["type"] == "Figure Skating" for s in sessions)
    print("test_figure_skate_age_suffix_variant_is_recognized OK")


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
    test_parse_cancellation_dates_multi_label_prefix()
    test_sandy_hill_sessions_exclude_cancelled_dates()
    test_figure_skate_uses_its_own_cancellation_group()
    test_reservation_required_is_propagated_per_session()
    test_exceptions_html_id_zero_is_not_treated_as_missing()
    test_manual_cancellation_override()
    test_manual_additional_sessions_are_injected_per_rink()
    test_manual_time_correction_fixes_mislabeled_activity()
    test_exclude_types_omits_matching_sessions()
    test_adult_skate_without_18_plus_suffix_is_recognized()
    test_figure_skate_age_suffix_variant_is_recognized()
    test_sessions_never_precede_today()
    test_unknown_rink_raises()
