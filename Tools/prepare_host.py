#!/usr/bin/env python3
"""Stable Host preparation command; no Python API re-exports."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from Tools.platform.distribution.prepare_host import main as _main

IMPLEMENTATION_MODULE = "Tools.platform.distribution.prepare_host"


def main(argv=None):
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
