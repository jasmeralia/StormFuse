# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys

from stormfuse.app import run_app


def main() -> None:
    sys.exit(run_app())


if __name__ == "__main__":
    main()
