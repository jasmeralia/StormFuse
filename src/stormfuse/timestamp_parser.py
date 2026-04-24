# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse sortable timestamps from video filenames (§5.1).

Two formats are recognized:
  Format A (OBS): YYYYMMDD-HHMMSS anywhere in the basename
  Format B (MFC): M-D-YYYY followed by HHMM[am|pm]
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

_OBS_RE = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")
_MFC_RE = re.compile(
    r"(\d{1,2})-(\d{1,2})-(\d{4}).*?(\d{1,2})(\d{2})\s*(am|pm)",
    re.IGNORECASE,
)


def parse_filename_timestamp(filename: str | Path) -> datetime | None:
    """Return a datetime parsed from *filename*, or None if no pattern matched."""
    base = Path(filename).stem

    m = _OBS_RE.search(base)
    if m:
        try:
            return datetime(
                int(m[1]),
                int(m[2]),
                int(m[3]),
                int(m[4]),
                int(m[5]),
                int(m[6]),
            )
        except ValueError:
            pass

    m = _MFC_RE.search(base)
    if m:
        try:
            month = int(m[1])
            day = int(m[2])
            year = int(m[3])
            hour12 = int(m[4])
            minute = int(m[5])
            ampm = m[6].lower()
            hour24 = hour12 % 12
            if ampm == "pm":
                hour24 += 12
            return datetime(year, month, day, hour24, minute)
        except ValueError:
            pass

    return None
