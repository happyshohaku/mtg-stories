# Network Layer Documentation

## File: `src/net.py`

## Purpose

Every outbound request (Contentful API, story pages, images, mtg.wiki, web.archive.org) goes through `net.get()`. It provides:

- One pooled `requests.Session`, so connections are reused
- Retries with exponential backoff on transient failures
- `(connect, read)` timeouts with a short connect timeout
- Cancellation: a `threading.Event` can interrupt the wait between attempts
- Fast offline detection, so a dropped connection aborts in a second or two instead of grinding through retries

No other module calls `requests.get` directly.

## Constants

| Name | Value | Meaning |
|------|-------|---------|
| `DEFAULT_TIMEOUT` | `(5, 30)` | Connect and read seconds for pages and API calls |
| `ARCHIVE_TIMEOUT` | `(5, 60)` | web.archive.org is slow to respond |
| `IMAGE_TIMEOUT` | `(5, 20)` | Image downloads |
| `PAGE_RETRIES` | `3` | Extra attempts for pages and API calls |
| `IMAGE_RETRIES` | `1` | Images are optional content; give up sooner |
| `RETRY_BACKOFF` | `1.0` | Seconds; doubles each attempt (1, 2, 4) |
| `RETRY_AFTER_MAX` | `30.0` | Cap on honouring a server's `Retry-After` header |
| `RETRY_STATUSES` | 429, 500, 502, 503, 504 | Statuses that are retried |
| `PROBE_URL` | `https://cdn.contentful.com/` | Host used to check for internet access |
| `PROBE_TIMEOUT` | `(3, 5)` | Timeout for the probe |

The short connect timeout matters most. With the machine offline, every attempt waits out the full connect timeout, and retries and per-story images multiply it.

## Exceptions

| Exception | Raised when | Handled by |
|-----------|-------------|------------|
| `net.Cancelled` | The cancel event is set before an attempt or during a backoff wait | GUI: run stops, nothing written |
| `net.Offline` | A connection-level failure occurs and the probe confirms there is no internet. Subclass of `requests.ConnectionError` | GUI: run aborts with "Lost internet connection" |

## Functions

### get(url, *, retries=PAGE_RETRIES, timeout=None, cancel=None, headers=None, params=None, probe_offline=True)

**Flow:**
```
loop:
  cancel set? ──► raise Cancelled
  session.get(url)
     │
     ├── connection error / timeout
     │      ├── probe_offline and not is_online() ──► raise Offline   (no retries)
     │      ├── out of retries ──► re-raise
     │      └── wait backoff (cancellable), try again
     │
     └── response
            ├── status not in RETRY_STATUSES, or out of retries ──► return response
            └── wait Retry-After or backoff (cancellable), try again
```

**Returns:** the final `requests.Response`. Status is not raised here; callers use `response.raise_for_status()` so the error names the URL.

**Why retries are not urllib3's `Retry`:** urllib3 sleeps inside the request call, which cannot be interrupted. With the loop here, the longest uninterruptible wait is one attempt's connect or read timeout.

### wait(seconds, cancel)
Sleeps, but returns early by raising `Cancelled` if the event is set. Use this instead of `time.sleep` anywhere inside generation.

### check_cancelled(cancel)
Raises `Cancelled` if the event is set.

### is_online(cancel=None) -> bool
One request to `PROBE_URL` with no retries. Any HTTP response counts as online.

### timeout_for(url) -> tuple
`ARCHIVE_TIMEOUT` for archive.org URLs, `DEFAULT_TIMEOUT` otherwise.

### get_session()
The process-wide session, created on first use (thread-safe). Its adapter has `max_retries=0`; retries are handled by `get()`.

## Behaviour seen by the user

| Situation | Result |
|-----------|--------|
| Server returns 429 or 503 once | Retried after backoff; the story is fetched |
| One site is down, internet is up | Retries exhausted; the story is listed as "site unreachable" and the run continues |
| Wifi off (DNS fails at once) | "Lost internet connection" in under a second |
| Connects hang (cached DNS) | "Lost internet connection" in about 8 seconds |
| Stop pressed | UI resets immediately; the worker exits at its next check |

## Maintenance Notes

### Adding a network call
Call `net.get()`. Inside generation, pass the run's `cancel` event and let `Cancelled` and `Offline` propagate.

### Being rate limited
Raise `RETRY_BACKOFF`, or increase the politeness delay in `scraper.fetch_story_page()`.

### Tests
`tests/test_net.py` runs `get()` against a local HTTP server: retries, `Retry-After`, cancel during backoff, and the offline probe. No real network is used.
