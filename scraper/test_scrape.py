#!/usr/bin/env python3
"""Regression test for scrape.py against a saved HTML fixture.

Run with: python3 scraper/test_scrape.py
"""
from pathlib import Path

from scrape import scrape_html

FIXTURE = Path(__file__).parent / "fixtures" / "sandy-hill-arena.html"


def test_sandy_hill_fixture():
    html = FIXTURE.read_text()
    result = scrape_html(html)

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
        "Sunday": "3 - 3:50 pm Play Free",
    }
    assert sessions["Adult Skating (18+)"] == {
        "Monday": "4 - 4:50 pm",
        "Tuesday": "9 - 9:50 pm",
    }

    assert len(result["cancellations"]) == 5
    assert result["cancellations"][0] == {
        "date": "May 31 to June 28",
        "notes": ["All drop-in skating, cancelled"],
    }
    assert result["cancellations"][-1] == {
        "date": "Friday, August 14",
        "notes": ["All drop-in skating, cancelled"],
    }

    print("OK")


if __name__ == "__main__":
    test_sandy_hill_fixture()
