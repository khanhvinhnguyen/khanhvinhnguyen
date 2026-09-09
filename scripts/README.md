# GitHub activity card

The profile card is generated from the same **public contribution calendar** shown on the GitHub profile. Python's standard library fetches the calendar, validates every historical date, calculates streaks, and renders a static SVG. No server, third-party stats host, Python package, or personal access token is required.

## Refresh

The `GitHub activity card` workflow runs every six hours (01:37, 07:37, 13:37, and 19:37 in Vietnam), after changes to its code reach `main`, or from **Actions → GitHub activity card → Run workflow**. Scheduled jobs can be delayed by GitHub. GitHub can also disable schedules in public repositories after 60 days without repository activity; check the Actions page if the displayed update time stops advancing.

The workflow tests the code before refreshing. It uses `contents: write` only in the refresh job and commits as `github-actions[bot]`, so refresh commits are not attributed to the profile owner. The repository must allow Actions and permit that job to push to `main`. A protected branch may require a separate publishing approach; the workflow does not bypass branch protections.

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/github_activity.py
```

Python 3.10+ with IANA timezone data is required; Ubuntu GitHub-hosted runners include both. Configuration is in the workflow: `ACTIVITY_USERNAME`, `ACTIVITY_START_DATE` (account creation date), and `ACTIVITY_TIMEZONE`.

## Counting rules

- A contribution day is the date returned by GitHub's calendar. The script does **not** shift or recreate commit dates.
- `Asia/Ho_Chi_Minh` determines today and the displayed refresh time. It cannot retroactively rebucket GitHub's daily totals.
- If today has no contributions, yesterday's streak stays active until the day ends. A completed day with zero contributions breaks the streak.
- Longest streak and total contributions cover the account creation date through today, including across year boundaries. The grid shows 26 calendar weeks, including the current partial week.
- Only publicly displayed counts are collected. To include anonymized private activity, enable **Contribution settings → Private contributions** on your profile. Repository names and commit contents are never collected.
- Heatmap intensity is scaled against the maximum in the displayed window. Hover text contains exact daily counts; colors are not used to calculate statistics.

## Failure and caching behavior

`assets/github-activity.json` records the public daily counts, coverage, statistics, and fetch time for inspection. The public HTML calendar is not a versioned API: if GitHub changes its markup, denies a request, or omits a historical day, generation fails visibly in Actions and leaves the last published card intact. This is intentional: missing data must not become a false zero streak.

The card displays its last refresh time. Its README URL includes a hash of the SVG, changing whenever the image changes so GitHub's image proxy does not reuse the previous URL's cached image. The SVG, JSON, and README link are published in one commit.

The README's `github-activity:start` and `github-activity:end` comments delimit the only region changed by the generator. Leave exactly one pair in place. Git push conflicts or permission errors fail the run without force-pushing; the next successful refresh can update the card.
