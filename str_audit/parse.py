"""Pure helpers for parsing user-entered text. No Streamlit imports."""

from __future__ import annotations

import re

_ROOMS_RE = re.compile(r"rooms?(?:/plus)?/(\d+)", re.IGNORECASE)
_LONG_DIGITS_RE = re.compile(r"\d{6,}")


def parse_listing_id(text: object) -> int | None:
    """Extract an Airbnb listing id from a URL or raw digits.

    Accepts: '21004527', 'https://www.airbnb.com/rooms/21004527',
             'https://www.airbnb.com/rooms/plus/5094445?adults=2'
    Returns None when nothing parseable is present.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    m = _ROOMS_RE.search(s)
    if m:
        return int(m.group(1))
    m = _LONG_DIGITS_RE.search(s)
    return int(m.group()) if m else None
