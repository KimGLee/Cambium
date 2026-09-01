#!/usr/bin/env python3
"""Stable public command; implementation lives at :mod:`Tools.platform.distribution.module_boundary_report`."""

import os
import sys

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from Tools.platform.distribution.module_boundary_report import main as _main

IMPLEMENTATION_MODULE = "Tools.platform.distribution.module_boundary_report"

def main(argv=None):
    return _main(argv)

if __name__ == "__main__":
    raise SystemExit(main())
