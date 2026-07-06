# Ottawa Public Skating Schedule

A static site that compiles Public, Family, and Adult (18+) drop-in skating
schedules from several City of Ottawa arenas into one page, kept up to date
by a scheduled job.

## How it works

- `rinks.json` lists the rinks to track (display name + the rink's ottawa.ca
  facility page URL).
- `scraper/scrape.py` reads [data.ottrec.ca](https://data.ottrec.ca/), a
  community-maintained dataset that mirrors ottawa.ca's recreation schedules
  (with permission) as clean, normalized JSON, refreshed daily. For each
  configured rink it pulls out the Public/Family/Adult (18+) skating rows and
  the matching cancellation notices, and writes `data/schedule.json`.
- `index.html` / `app.js` / `style.css` render that JSON as a page, one card
  per rink.
- `.github/workflows/scrape.yml` runs the scraper on a schedule (every two
  days) and commits `data/schedule.json` if it changed, so the published page
  stays current without any manual steps.

If a rink's data can't be fetched on a given run, that rink keeps showing its
last successfully scraped schedule with a "couldn't refresh" note, rather
than going blank.

### Why not scrape ottawa.ca directly?

ottawa.ca sits behind an Imperva/Incapsula WAF that blocks GitHub-hosted
runners' IP ranges outright (confirmed via direct `curl` and via headless
Chromium — both got the same Incapsula challenge page from different runner
IPs). That's an IP-reputation block, not a fingerprinting issue, so no client
change fixes it from GitHub Actions. data.ottrec.ca republishes the same
facility/schedule data (scraped from ottawa.ca with the City's permission)
from infrastructure that isn't blocked, and as a bonus gives us normalized
activity names instead of the inconsistently-worded labels each rink page
uses (e.g. "Adult skating (18+)" vs "Adult skating (ages 18+)").

Per data.ottrec.ca's license terms, its attribution text is fetched alongside
the schedule data and displayed in the page footer — don't remove it.

## Adding a rink

Add an entry to `rinks.json` using the rink's ottawa.ca facility page URL
(this must match exactly, since it's used to look the rink up in the
dataset):

```json
{
  "name": "Some Arena",
  "url": "https://ottawa.ca/en/recreation-and-parks/facilities/place-listing/some-arena"
}
```

The next scrape run (scheduled or manual) will pick it up automatically, as
long as data.ottrec.ca already covers that facility (it currently covers all
City of Ottawa recreation facilities, so this should just work).

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

- GitHub Actions workflows only get registered/dispatchable once "Actions
  permissions" for the repo (Settings → Actions → General) allows them, and
  only after a push lands while that setting is already enabled. If a new
  workflow file 404s on manual dispatch right after being added, check that
  setting, then push any small change to nudge GitHub into re-scanning it.
- The scheduled workflow only runs on the repository's **default branch**.
  You can trigger a run manually anytime from the Actions tab ("Scrape
  skating schedules" → "Run workflow").
- `cron: "0 12 */2 * *"`-style "every N days" schedules are approximate:
  because they're expressed as "every 2nd day-of-month", the gap is briefly 1
  day around month boundaries (e.g. the 31st then the 1st). This is harmless
  here — worst case the schedule refreshes a day sooner than usual.
- The scraper doesn't try to guess which cancellation notices are still
  current; it shows exactly what data.ottrec.ca has, so out-of-date notices
  there would show here too.
