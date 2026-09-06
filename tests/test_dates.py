from datetime import datetime

import pytest

from src.dates import parse_date


@pytest.mark.parametrize("text, expected", [
    ("2025-06-20 14:00:00", datetime(2025, 6, 20, 14, 0, 0)),
    ("2025-06-20T14:00:00Z", datetime(2025, 6, 20, 14, 0, 0)),
    ("2025-06-20T14:00:00+02:00", datetime(2025, 6, 20, 14, 0, 0)),
    ("2025-06-20", datetime(2025, 6, 20)),
    ("June 20, 2025", datetime(2025, 6, 20)),
    ("Jun 20, 2025", datetime(2025, 6, 20)),
    ("20 June 2025", datetime(2025, 6, 20)),
    ("Published 2025-06-20 online", datetime(2025, 6, 20)),
    ("2025-06-20 14:00:00.123456+00:00", datetime(2025, 6, 20, 14, 0, 0, 123456)),
])
def test_parse_date_formats(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["", "   ", None, "nonsense", "20/06/2025"])
def test_parse_date_rejects_garbage(text):
    assert parse_date(text) is None


def test_parse_date_always_naive():
    assert parse_date("2025-06-20T14:00:00+05:00").tzinfo is None
