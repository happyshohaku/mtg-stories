# Ideas / To-Do

Not scheduled. Captured so they are not forgotten.

## Parallel story downloads

Today each story is fetched, parsed and its images downloaded one after another. Proposal:

- Pool of ~3 worker threads, each handling one story end to end; results stored by position so chapter order is unchanged.
- Replace the fixed politeness sleep with a per-host rate limiter (one request per 0.5s to magic.wizards.com, one per 1s to archive.org; image hosts get their own buckets). Servers see the same rate as today, just less idle time.
- Cancel event passed to every task; Stop drops queued tasks, first `net.Offline` cancels the rest.
- Status becomes "Fetched 7/30 stories, 3 in progress" since completion is out of order.
- Expected 2-3x on image-heavy sets; archive.org sets gain least.
- Lower-risk alternative: keep pages serial, parallelize only each story's image downloads.

## Author fallback is fragile

`parser._extract_author()` falls back to the first page string starting with "by ", which can be a sentence of story prose ("By the time the storm broke..."). Restrict to short strings near the top of the article, or drop the heuristic.

## Cross-platform "open folder"

The success dialog uses `os.startfile`, which only exists on Windows. Use `subprocess` with `open` (macOS) / `xdg-open` (Linux) if the app is ever run elsewhere. Cover font paths are Windows-first for the same reason.

## Smaller items

- `.gitignore` contains `claude.md`, which also matches `CLAUDE.md` on Windows, so that file is untracked.
- SVG images are embedded as-is; Kindle does not render SVG. Dropping them may be cleaner.
- The Contentful storyGroup query has no pagination (default limit 100 per year); fine today, would silently truncate if a year ever had more.
