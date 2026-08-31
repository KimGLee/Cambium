#!/usr/bin/env python3
"""Stable public command; implementation lives in platform.distribution."""

import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from Tools.platform.distribution.tool_catalog import main as _main  # noqa: E402


IMPLEMENTATION_MODULE = "Tools.platform.distribution.tool_catalog"


def main(argv=None):
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
