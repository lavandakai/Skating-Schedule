# Ottawa Public Skating Schedule

A static site that compiles Public, Family, and Adult (18+) drop-in skating
schedules from several City of Ottawa arena pages into one page, kept up to
date by a scheduled scraper.

## How it works

- `rinks.json` lists the rinks to track (name + ottawa.ca page URL).
- `scraper/scrape.py` fetches each rink's page and parses its "Drop-in
  schedule - skating" section: the schedule table(s) (filtered to Public
  Skating, Family Skating, and Adult Skating (18+) rows) and the "Schedule
  changes" cancellation bullet list. Output is written to `data/schedule.json`.
- `index.html` / `app.js` / `style.css` render that JSON as a page, one card
  per rink.
- `.github/workflows/scrape.yml` runs the scraper on a schedule (every two
  days) and commits `data/schedule.json` if it changed, so the published
  page stays current without any manual steps.

If a rink's page can't be scraped on a given run (site layout change, network
hiccup, etc.), that rink keeps showing its last successfully scraped schedule
with a "couldn't refresh" note, rather than going blank.

## Adding a rink

Add an entry to `rinks.json`:

```json
{
  "name": "Some Arena",
  "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/some-arena"
}
```

The next scrape run (scheduled or manual) will pick it up automatically. No
other changes are needed as long as the page uses the same "Drop-in schedule
- skating" layout as the other rinks.

## Running the scraper locally

```bash
pip install -r scraper/requirements.txt
python scraper/scrape.py
```

This overwrites `data/schedule.json`. Open `index.html` via a local server
(e.g. `python3 -m http.server`) to preview — opening it directly as a
`file://` URL won't be able to fetch the JSON.

## Publishing with GitHub Pages

In the repo's Settings → Pages, set the source to "Deploy from a branch",
branch `main` (or your default branch), folder `/ (root)`. The page will be
available at the repo's Pages URL and will pick up new commits to
`data/schedule.json` automatically.

## Notes

- The scheduled workflow only runs on the repository's **default branch** —
  merge this branch to your default branch for the cron schedule to take
  effect. You can also trigger a run manually anytime from the Actions tab
  ("Scrape skating schedules" → "Run workflow").
- `cron: "0 12 */2 * */2"`-style "every N days" schedules are approximate:
  because they're expressed as "every 2nd day-of-month", the gap is briefly 1
  day around month boundaries (e.g. the 31st then the 1st). This is harmless
  here — worst case the schedule refreshes a day sooner than usual.
- The scraper doesn't try to guess which cancellation notices are still
  current; it shows exactly what's listed on the source page, so out-of-date
  notices there would show here too.
