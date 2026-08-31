#!/usr/bin/env python3
"""Stable public command; implementation lives in platform.distribution."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from Tools.platform.distribution.test_catalog import main as _main


IMPLEMENTATION_MODULE = "Tools.platform.distribution.test_catalog"


def main(argv=None):
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
