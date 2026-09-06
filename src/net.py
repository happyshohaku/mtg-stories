"""
Shared HTTP access with connection pooling, cancellable retries and timeouts.

All outbound requests (Contentful API, story pages, images, mtg.wiki,
web.archive.org) go through get() so that:
  - connections are reused instead of re-opened for every request,
  - transient failures (429 rate limits, 5xx, connection errors, timeouts)
    are retried with exponential backoff, honouring Retry-After, and
  - a cancel event can interrupt the wait between attempts immediately.

Retries are implemented here rather than with urllib3's Retry so that the
backoff sleeps can be cancelled. The longest uninterruptible wait is one
attempt's connect or read timeout.

Timeouts are (connect, read) tuples. A short connect timeout matters most:
when the machine is offline every attempt waits out the full connect timeout.
Reads get longer because archive.org is slow.
"""

import threading
import time

import requests
from requests.adapters import HTTPAdapter

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# (connect, read) seconds
DEFAULT_TIMEOUT = (5, 30)
ARCHIVE_TIMEOUT = (5, 60)   # web.archive.org can take a long time to respond
IMAGE_TIMEOUT = (5, 20)

# Story pages and metadata: retry on rate limiting, server errors and
# connection problems. archive.org in particular returns 429/503 under load.
PAGE_RETRIES = 3
# Images are optional content; give up sooner so an offline machine or a dead
# image host does not stall a whole story.
IMAGE_RETRIES = 1
RETRY_BACKOFF = 1.0          # seconds; doubles each attempt: 1, 2, 4
RETRY_AFTER_MAX = 30.0       # cap on honouring a server's Retry-After header
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class Cancelled(Exception):
    """Raised by get() when the cancel event is set before or between attempts."""


class Offline(requests.ConnectionError):
    """
    Raised by get() when a connection-level failure occurs and a probe confirms
    the machine has no internet access. Subclasses ConnectionError so generic
    handlers still treat it as a network error.
    """


_session: requests.Session | None = None
_lock = threading.Lock()


def get_session() -> requests.Session:
    """Process-wide pooled session (no automatic retries; see get()). Thread-safe."""
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                session = requests.Session()
                session.headers["User-Agent"] = USER_AGENT
                adapter = HTTPAdapter(max_retries=0, pool_connections=10, pool_maxsize=10)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                _session = session
    return _session


def timeout_for(url: str) -> tuple[int, int]:
    """Pick the (connect, read) timeout appropriate for a page URL."""
    return ARCHIVE_TIMEOUT if "web.archive.org" in url else DEFAULT_TIMEOUT


def check_cancelled(cancel: threading.Event | None) -> None:
    """Raise Cancelled if the event is set."""
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def wait(seconds: float, cancel: threading.Event | None) -> None:
    """Sleep, but return early (raising Cancelled) if the event is set."""
    if seconds <= 0:
        check_cancelled(cancel)
        return
    if cancel is None:
        time.sleep(seconds)
    elif cancel.wait(seconds):
        raise Cancelled()


def _retry_after(response: requests.Response, attempt: int) -> float:
    """Seconds to wait before retrying a response, honouring Retry-After (capped)."""
    header = response.headers.get("Retry-After")
    if header:
        try:
            return min(float(header), RETRY_AFTER_MAX)
        except ValueError:
            pass  # HTTP-date form; fall back to backoff
    return RETRY_BACKOFF * (2 ** attempt)


def get(
    url: str,
    *,
    retries: int = PAGE_RETRIES,
    timeout: tuple[int, int] | None = None,
    cancel: threading.Event | None = None,
    headers: dict | None = None,
    params: dict | None = None,
    probe_offline: bool = True,
) -> requests.Response:
    """
    GET with cancellable retries and fast offline detection.

    Args:
        url: Request URL.
        retries: Extra attempts after the first (so retries=3 means up to 4 tries).
        timeout: (connect, read) seconds; defaults to timeout_for(url).
        cancel: Event checked before each attempt and during backoff sleeps.
        headers, params: Passed to the session.
        probe_offline: On a connection-level failure, probe a known-good host
            first and raise Offline immediately instead of retrying when the
            internet itself is gone. Retries are only useful when it is up.

    Returns:
        The final response. Status is NOT raised here; callers use
        response.raise_for_status() so the error message names the URL.

    Raises:
        Cancelled: the cancel event was set.
        Offline: no internet access (only when probe_offline is True).
        requests.RequestException: connection/timeout failure on the last attempt.
    """
    session = get_session()
    timeout = timeout or timeout_for(url)
    attempt = 0

    while True:
        check_cancelled(cancel)
        try:
            response = session.get(
                url, headers=headers, params=params, timeout=timeout, allow_redirects=True
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            if probe_offline and not is_online(cancel):
                raise Offline(f"No internet connection (while fetching {url})") from e
            if attempt >= retries:
                raise
            delay = RETRY_BACKOFF * (2 ** attempt)
        else:
            if response.status_code not in RETRY_STATUSES or attempt >= retries:
                return response
            delay = _retry_after(response, attempt)
            response.close()

        attempt += 1
        wait(delay, cancel)


# Probe target used to tell "the internet is gone" apart from "this one host
# is down". Any HTTP response at all counts as online.
PROBE_URL = "https://cdn.contentful.com/"
PROBE_TIMEOUT = (3, 5)


def is_online(cancel: threading.Event | None = None) -> bool:
    """Best-effort check that the machine still has internet access."""
    try:
        get(PROBE_URL, retries=0, timeout=PROBE_TIMEOUT, cancel=cancel, probe_offline=False).close()
        return True
    except Cancelled:
        raise
    except requests.RequestException:
        return False
