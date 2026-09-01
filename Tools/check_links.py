#!/usr/bin/env python3
"""Stable public command; implementation lives at :mod:`Tools.knowledge.content.check_links`."""

import os
import sys

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from Tools.knowledge.content.check_links import main as _main

IMPLEMENTATION_MODULE = "Tools.knowledge.content.check_links"

def main():
    return _main()

if __name__ == "__main__":
    raise SystemExit(main())
