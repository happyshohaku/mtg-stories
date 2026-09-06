"""
Date parsing shared by the scrapers and the page parser.

All sources produce naive datetimes (any timezone offset is dropped) so
that stories from different sources sort together without mixing aware
and naive values.
"""

import re
from datetime import datetime

# Order matters: more specific formats first.
_FORMATS = (
    "%Y-%m-%d %H:%M:%S",   # Contentful publishedDate
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%B %d, %Y",           # "June 20, 2025"
    "%b %d, %Y",           # "Jun 20, 2025"
    "%d %B %Y",            # "20 June 2025"
    "%d %b %Y",            # "20 Jun 2025"
)

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_date(text: str | None) -> datetime | None:
    """
    Parse a date string in any of the formats the sources use.

    Handles ISO 8601 with a timezone ("2025-06-20T14:00:00Z", "+00:00"),
    Contentful's "YYYY-MM-DD HH:MM:SS", plain "YYYY-MM-DD", and English
    month-name forms. As a last resort, picks out an embedded YYYY-MM-DD.

    Returns:
        A naive datetime, or None if nothing parseable was found.
    """
    if not text:
        return None
    text = text.strip()
    if not text:
        return None

    # ISO 8601 with timezone or fractional seconds
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass

    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # Truncate a longer timestamp ("2025-06-20 14:00:00.123+00:00") or find an
    # embedded date in free text
    match = _ISO_DATE_RE.search(text)
    if match:
        try:
            return datetime.strptime(match.group(0), "%Y-%m-%d")
        except ValueError:
            pass

    return None
